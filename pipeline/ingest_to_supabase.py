# -*- coding: utf-8 -*-
"""대화형 → Supabase 적재기 (C단계).

대화형 `items/item_<별명>/run_<시도>/` 의 단계 결과를 자동화형 Supabase에 멱등 적재한다.

설계 (매핑: 대화형/agents/_shared/db_적재_매핑.md):
- 구조화 추출은 Claude(적재 트리거)가 1회 수행 → run폴더/_ingest_payload.json 으로 저장.
  (md 표를 정규식으로 긁으면 깨지기 쉬우므로, 추출은 Claude가 / 적재는 스크립트가 — 역할 분리)
- 이 스크립트는 payload(검증된 dict) + product.json + status.json 을 받아
  storage.py(SupabaseStorage)로 멱등 upsert만 책임진다 (결정론적).
- 멱등: (상품_id, 시도_키, 버전) 실행을 upsert하고, 그 실행의 하위 단계는 교체(삭제→삽입).
  재작업 후 다시 올려도 안전.

실행:
    cd "엠타트업식 판매/자동화형"
    python pipeline/ingest_to_supabase.py "<대화형 run폴더 절대경로>"

입력 파일:
- <run폴더>/_ingest_payload.json   ← Claude가 적재 시 생성 (아래 스키마)
- <run폴더>/status.json            ← 참고(메타)
- <run폴더>/../product.json        ← 상품 레벨 권위필드·스냅샷

_ingest_payload.json 스키마 (done 단계만 키 포함, 미완 단계는 생략):
{
  "상품_db_id": 1561,
  "product": { "제품명": "...", "소매가": 12000, ... },     # 상품 PATCH (None/미언급 필드는 넣지 않음)
  "실행": { "시도_키":"전원생활자-자유", "시도_라벨":"...", "타겟_가설":"...",
            "결핍_가설":"...", "버전":1, "대화형_폴더명":"item_독수리/run_전원생활자-자유" },
  "vision": "<00_vision_pass.md 본문>",                      # 상품.시각설명 + 비전패스_이력
  "targets_raw": "<01_deficit_target.md 본문>",             # 모든 타겟 행의 원본_출력
  "targets": [ {"rank":1,"label":"...","character":"...","deficit":"...",
                "deficit_source":"...","benefit_type":"...","involvement":6,
                "channel":"...","buyer_user_split":"...","wants_3tier":"...","note":"..."}, ... ],
  "selected_rank": 1,
  "positioning": {"raw":"<02 md>","category_objections":[...],"rule_engine_inputs":{...},
                  "rule_engine_flags":{...},"persuasion_method_candidates":[...]},
  "naming": {"raw":"<03 md>","분류":"..."},
  "detail": {"raw":"<04_a md>","engine_plan":{...},"한_축_사슬":"...",
             "설득_방식_주":"...","설득_방식_보조":[...]},
  "review": {"raw":"<04_b md>","검수_보고서":"...","다듬은_콘티":"..."},
  "image_direction": {"raw":"<04_1 md>","sections":[...],"design_system":{...},"selection_method":"..."},
  "channel": {"raw":"<05 md>"}
}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# pipeline/storage.py 재사용 (이 스크립트는 pipeline/ 에 위치)
from storage import SupabaseStorage, _db

MODEL = "interactive"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_raw(v, run: Path) -> str:
    """payload raw 필드 해석: 파일 경로이면 읽고, 아니면 텍스트 그대로 반환.
    v가 dict이면 'raw_file' 우선, 없으면 'raw'. str이면 경로 또는 텍스트로 판단."""
    if v is None:
        return ""
    if isinstance(v, dict):
        text = v.get("raw_file") or v.get("raw") or ""
    else:
        text = str(v)
    if not text:
        return ""
    p = Path(text) if Path(text).is_absolute() else run / text
    if p.exists():
        return p.read_text(encoding="utf-8")
    if not Path(text).is_absolute():
        p_item = run.parent / text
        if p_item.exists():
            return p_item.read_text(encoding="utf-8")
    return text


def main(run_dir: str) -> int:
    run = Path(run_dir)
    if not run.is_dir():
        print(f"[ERROR] run 폴더 없음: {run}")
        return 1

    payload_path = run / "_ingest_payload.json"
    if not payload_path.exists():
        print(f"[ERROR] _ingest_payload.json 없음. 적재 트리거(Claude)가 먼저 생성해야 함:\n        {payload_path}")
        return 1

    payload = _load_json(payload_path)
    product_json = run.parent / "product.json"
    product_meta = _load_json(product_json) if product_json.exists() else {}

    상품_id = payload.get("상품_db_id") or product_meta.get("상품_db_id")
    if not 상품_id:
        print("[ERROR] 상품_db_id 없음 (payload/product.json). 적재 시 'id=NNNN' 지정 필요.")
        return 1

    db = _db()
    store = SupabaseStorage()

    print("=" * 60)
    print(f"대화형 → Supabase 적재  (상품_id={상품_id}, run={run.name})")
    print("=" * 60)

    # ── 1) 상품 존재 확인 + 권위필드 PATCH ─────────────────────
    res = db.table("상품").select("id, 제품명").eq("id", 상품_id).limit(1).execute()
    if not res.data:
        print(f"[ERROR] 상품 id={상품_id} 가 DB에 없음. 신규 상품이면 상품 행을 먼저 생성하세요.")
        return 1
    제품명_db = res.data[0].get("제품명")

    # PATCH 시맨틱: payload.product에 들어온 값만 덮어쓰기 (미언급 필드는 DB값 유지)
    product_patch = {k.lower(): v for k, v in (payload.get("product") or {}).items() if v is not None}
    if product_patch:
        db.table("상품").update(product_patch).eq("id", 상품_id).execute()
        print(f"[상품] 권위필드 PATCH: {list(product_patch.keys())}")
    else:
        print("[상품] PATCH 없음 (대화형 권위필드 미제공 — DB값 유지)")

    제품명 = product_patch.get("제품명") or product_meta.get("제품명") or 제품명_db or "(이름 없음)"

    # ── 2) 00 비전패스 → 상품.시각설명 + 비전패스_이력 ─────────
    vision = _read_raw(payload.get("vision"), run)
    if vision:
        db.table("상품").update({"시각설명": vision}).eq("id", 상품_id).execute()
        db.table("비전패스_이력").insert({
            "상품_id": 상품_id, "모델명": MODEL, "결과": vision, "실행_모드": "bulk",
        }).execute()
        print("[00] 시각설명 갱신 + 비전패스_이력 기록")

    # ── 3) 엠군_실행 upsert (상품_id, 시도_키, 버전) ────────────
    실행 = payload.get("실행") or {}
    시도_키 = 실행.get("시도_키")
    버전 = 실행.get("버전", 1)
    if not 시도_키:
        print("[ERROR] payload.실행.시도_키 없음 (시도 식별 불가)")
        return 1

    run_row = {
        "상품_id": 상품_id,
        "제품명": 제품명,
        "제품_스냅샷": json.dumps(product_meta, ensure_ascii=False),
        "시도_키": 시도_키,
        "시도_라벨": 실행.get("시도_라벨"),
        "타겟_가설": 실행.get("타겟_가설"),
        "결핍_가설": 실행.get("결핍_가설"),
        "모드": MODEL,
        "대화형_폴더명": 실행.get("대화형_폴더명") or f"{run.parent.name}/{run.name}",
        "버전": 버전,
    }
    up = db.table("엠군_실행").upsert(run_row, on_conflict="상품_id,시도_키,버전").execute()
    run_id = up.data[0]["id"]
    print(f"[실행] upsert run_id={run_id} (시도_키={시도_키}, 버전={버전})")

    # 멱등: 이 실행의 기존 타겟 제거 → FK CASCADE로 02~05도 함께 정리 후 재삽입
    db.table("엠군_타겟").delete().eq("실행_id", run_id).execute()

    # ── 4) 01 타겟 ────────────────────────────────────────────
    targets = payload.get("targets") or []
    if not targets:
        print("[01] 타겟 없음 — 02~05 적재 불가 (00·상품만 반영됨)")
        print("=" * 60)
        print(f"[완료] run_id={run_id} (타겟 미적재)")
        return 0

    selected_rank = payload.get("selected_rank")
    store.save_targets(run_id=run_id, targets=targets, model=MODEL,
                       raw_output=_read_raw(payload.get("targets_raw"), run),
                       recommended_rank=selected_rank)
    print(f"[01] 타겟 {len(targets)}개 적재")

    # 선택 타겟 마크 + target_id 확보
    store.clear_selected_in_run(run_id)
    sel = db.table("엠군_타겟").select("id, 순위").eq("실행_id", run_id).execute()
    target_id = None
    for row in (sel.data or []):
        if row.get("순위") == selected_rank:
            target_id = row["id"]
            break
    if target_id is None:
        print(f"[01] selected_rank={selected_rank} 타겟 못 찾음 — 02~05 건너뜀")
        print("=" * 60)
        print(f"[완료] run_id={run_id}")
        return 0
    store.mark_target_selected(target_id, True)
    print(f"[01] 선택 타겟 target_id={target_id} (순위 {selected_rank})")

    # ── 5) 02~05 (선택 타겟에 매달아 적재) ─────────────────────
    p = payload.get("positioning")
    if p:
        store.save_positioning(target_id, MODEL, _read_raw(p, run),
                               category_objections=p.get("category_objections"),
                               rule_engine_inputs=p.get("rule_engine_inputs"),
                               rule_engine_flags=p.get("rule_engine_flags"),
                               persuasion_method_candidates=p.get("persuasion_method_candidates"))
        print("[02] 포지셔닝 적재")

    n = payload.get("naming")
    if n:
        store.save_네이밍(target_id, MODEL, _read_raw(n, run), 분류=n.get("분류", ""))
        print("[03] 네이밍 적재")

    detail_id = None
    d = payload.get("detail")
    if d:
        detail_id = store.save_상세페이지(target_id, MODEL, _read_raw(d, run),
                                       engine_plan=d.get("engine_plan"),
                                       한_축_사슬=d.get("한_축_사슬"),
                                       설득_방식_주=d.get("설득_방식_주"),
                                       설득_방식_보조=d.get("설득_방식_보조"))
        print(f"[04_a] 상세페이지 적재 detail_id={detail_id}")

    r = payload.get("review")
    if r and detail_id:
        store.save_상세페이지_검수(detail_id, MODEL, _read_raw(r, run),
                                검수_보고서=r.get("검수_보고서"), 다듬은_콘티=r.get("다듬은_콘티"))
        print("[04_b] 검수 적재")
    elif r and not detail_id:
        print("[04_b] 검수 payload 있으나 04_a(detail) 없음 — 건너뜀")

    img = payload.get("image_direction")
    if img:
        store.save_이미지디렉션(target_id, MODEL, _read_raw(img, run),
                            sections=img.get("sections"),
                            design_system=img.get("design_system"),
                            selection_method=img.get("selection_method"))
        print("[04_1] 이미지디렉션 적재")

    c = payload.get("channel")
    if c:
        store.save_채널(target_id, MODEL, _read_raw(c, run))
        print("[05] 채널 적재")

    print("=" * 60)
    print(f"[완료] run_id={run_id}, target_id={target_id} -- 적재 성공")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('사용법: python pipeline/ingest_to_supabase.py "<대화형 run폴더 절대경로>"')
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
