"""내 Supabase DB 클라이언트 (read/write).

상품, 상품_파일 테이블 기준. MY_SUPABASE_* 환경변수 사용.
"""
from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

CHUNK = 1000


@lru_cache(maxsize=1)
def _client() -> Client:
    url = os.getenv("MY_SUPABASE_URL", "").strip()
    key = os.getenv("MY_SUPABASE_ANON_KEY", "").strip()
    if not url or not key:
        raise RuntimeError(".env에 MY_SUPABASE_URL과 MY_SUPABASE_ANON_KEY를 설정하세요.")
    return create_client(url, key)


def _fetch_all(table: str, query_fn=None) -> list[dict]:
    """1,000행 제한 우회 페이지네이션."""
    rows, start = [], 0
    while True:
        q = _client().table(table).select("*").range(start, start + CHUNK - 1)
        if query_fn:
            q = query_fn(q)
        batch = q.execute().data or []
        rows.extend(batch)
        if len(batch) < CHUNK:
            break
        start += CHUNK
    return rows


# ── 목록 조회 ─────────────────────────────────────────────

def list_products(
    search: str = "",
    엠군상태: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """상품 목록 조회. 검색·엠군상태 필터 지원.

    limit=None(기본): 1,000행 제한 우회 페이지네이션으로 전체 조회.
    limit=N: N행까지만 조회 (단일 요청, supabase 한도 1,000 적용).
    """
    def _apply_filters(q):
        if search:
            q = q.ilike("제품명", f"%{search}%")
        if 엠군상태 and 엠군상태 != "전체":
            if 엠군상태 == "미시작":
                # NULL 저장된 레코드도 미시작으로 취급
                q = q.or_("엠군상태.eq.미시작,엠군상태.is.null")
            else:
                q = q.eq("엠군상태", 엠군상태)
        return q

    if limit is not None:
        q = _client().table("상품").select("*").order("id", desc=True).limit(limit)
        q = _apply_filters(q)
        return q.execute().data or []

    rows, start = [], 0
    while True:
        q = (
            _client()
            .table("상품")
            .select("*")
            .order("id", desc=True)
            .range(start, start + CHUNK - 1)
        )
        q = _apply_filters(q)
        batch = q.execute().data or []
        rows.extend(batch)
        if len(batch) < CHUNK:
            break
        start += CHUNK
    return rows


def list_엠군상태_values() -> list[str]:
    """엠군상태 필터 선택지."""
    return ["전체", "미시작", "진행중", "완료"]


# ── 단일 상품 조회 ────────────────────────────────────────

def get_product(상품_id: int) -> dict | None:
    """상품 전체 필드 조회."""
    res = (
        _client()
        .table("상품")
        .select("*")
        .eq("id", 상품_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def get_product_spec(상품_id: int) -> dict | None:
    """엠군 01/02 입력용 스펙 딕셔너리.

    반환 구조는 파이프라인 loader.py와 계약된 형식 유지.
    """
    row = get_product(상품_id)
    if not row:
        return None

    return {
        "id":           row["id"],
        "제품명":       row.get("제품명"),
        "카테고리":     row.get("카테고리"),
        "서브카테고리": row.get("서브카테고리"),
        "엠군상태":     row.get("엠군상태"),
        "시각설명":     row.get("시각설명"),
        "스펙": {
            "모델명":     row.get("모델명"),
            "제조사":     row.get("제조사"),
            "수입자":     row.get("수입자"),
            "원산지":     row.get("원산지"),
            "사용연령":   row.get("사용연령"),
            "가로_cm":    row.get("가로_cm"),
            "세로_cm":    row.get("세로_cm"),
            "높이_cm":    row.get("높이_cm"),
            "무게_g":     row.get("무게_g"),
            "박스_가로_cm": row.get("박스_가로_cm"),
            "박스_세로_cm": row.get("박스_세로_cm"),
            "박스_높이_cm": row.get("박스_높이_cm"),
            "박스_무게_g":  row.get("박스_무게_g"),
            "재질":       row.get("재질"),
            "색상":       row.get("색상"),
            "구성품":     row.get("구성품"),
            "박스_재질":  row.get("박스_재질"),
            "박스_색상":  row.get("박스_색상"),
            "치수정보":   row.get("치수정보"),
        },
        "인증": {
            "kc인증":    row.get("kc인증"),
            "kc인증번호": row.get("kc인증번호"),
            "기타인증":  row.get("기타인증"),
        },
        "가격": {
            "온라인판매가격": row.get("온라인판매가격"),
            "소매가":         row.get("소매가"),
            "도매가":         row.get("도매가"),
            "실제받는가격":   row.get("실제받는가격"),
            "평균입고가":     row.get("평균입고가"),
        },
        "재고": {
            "실시간재고": row.get("실시간재고"),
            "처리후재고": row.get("처리후재고"),
            "재고수량":  row.get("재고수량"),
            "재입고예정": row.get("재입고예정"),
            "단종여부":  row.get("단종여부"),
            "온라인판매가능": row.get("온라인판매가능"),
        },
        "제품특징_bullet": row.get("제품특징_bullet") or [],
        "제품특징_추가":   row.get("제품특징_추가"),
        "판매자특성_선택": row.get("판매자특성_선택") or [],
        "키워드":         row.get("키워드"),
        "검수완료":       row.get("검수완료"),
        "검수메모":       row.get("검수메모"),
    }


# ── 파일 조회 ─────────────────────────────────────────────

def get_files(상품_id: int) -> list[dict]:
    """상품_파일에서 상품_id에 연결된 파일 목록."""
    try:
        res = (
            _client()
            .table("상품_파일")
            .select("*")
            .eq("상품_id", 상품_id)
            .execute()
        )
        return res.data or []
    except Exception:
        return []


def get_thumbnail_url(드라이브_파일_id: str, size: int = 400) -> str:
    """Google Drive 썸네일 URL 생성."""
    return f"https://drive.google.com/thumbnail?id={드라이브_파일_id}&sz=w{size}"


# ── 상품 CRUD ────────────────────────────────────────────

def insert_상품(data: dict) -> dict:
    """상품 신규 등록. 생성된 행 반환."""
    res = _client().table("상품").insert(data).execute()
    return res.data[0] if res.data else {}


def update_상품(
    상품_id: int,
    data: dict,
    original_수정일: str | None = None,
) -> bool:
    """상품 필드 업데이트.

    낙관적 락:
        original_수정일이 주어지면 `수정일`이 일치하는 row만 update (동시편집 충돌 감지).
        - 매칭되어 1행 이상 update되면 True
        - 매칭 실패(다른 사용자가 먼저 수정함)면 False
        - original_수정일=None이면 기존 동작 그대로 (항상 True)

    수정일 자동 갱신:
        DB 트리거(상품_수정일_갱신)가 모든 UPDATE에서 NEW.수정일 = NOW()로 강제.
        호출 측에서 data["수정일"]을 명시할 필요 없음 (지정해도 트리거에 덮어씌워짐).
    """
    q = _client().table("상품").update(data).eq("id", 상품_id)
    if original_수정일 is not None:
        q = q.eq("수정일", original_수정일)
    res = q.execute()
    if original_수정일 is not None:
        return bool(res.data)
    return True


def get_account_folder(상품_id: int, 계정: str) -> str | None:
    """상품의 특정 계정에 매핑된 Drive 폴더 ID 반환. 없으면 None.

    계정별_폴더_ids JSON에서 조회. 마이그레이션 안 된 옛 row면 드라이브_폴더_id로 fallback 안 함
    (어느 계정 폴더인지 모르므로 호출 측에서 새로 생성).
    """
    p = get_product(상품_id)
    if not p:
        return None
    folders = p.get("계정별_폴더_ids") or {}
    return folders.get(계정)


def set_account_folder(상품_id: int, 계정: str, folder_id: str) -> dict:
    """상품의 계정별_폴더_ids에 (계정 → folder_id) 매핑 추가/갱신.

    하위 호환: 매핑이 비어 있던 경우 단일 컬럼 드라이브_폴더_id도 함께 업데이트
              (다른 페이지/스크립트가 아직 옛 컬럼을 읽을 수 있어 보존).

    Returns: 갱신된 계정별_폴더_ids dict
    """
    p = get_product(상품_id) or {}
    folders = dict(p.get("계정별_폴더_ids") or {})
    folders[계정] = folder_id

    payload: dict = {"계정별_폴더_ids": folders}
    if not p.get("드라이브_폴더_id"):
        payload["드라이브_폴더_id"] = folder_id

    update_상품(상품_id, payload)
    return folders


def list_account_folders(상품: dict) -> dict:
    """상품 row에서 계정별_폴더_ids dict 반환 (None이면 빈 dict).

    마이그레이션 안 된 row 호환: 계정별_폴더_ids가 비어 있고 드라이브_폴더_id만 있으면
    호출 측에서 사용 가능한 정보 부족으로 빈 dict 반환 (계정 추정 불가).
    """
    return dict(상품.get("계정별_폴더_ids") or {})


def delete_상품(상품_id: int) -> None:
    """상품 삭제 (연결된 상품_파일은 ON DELETE CASCADE로 함께 삭제)."""
    _client().table("상품").delete().eq("id", 상품_id).execute()


def delete_임시_products(exclude_id: int | None = None) -> int:
    """제품명이 '임시_'로 시작하는 모든 레코드 삭제. 삭제 개수 반환.

    exclude_id가 주어지면 그 id는 보존 (현재 편집 중인 임시 레코드 보호용).
    """
    res = (
        _client()
        .table("상품")
        .select("id, 제품명")
        .ilike("제품명", "임시%")
        .execute()
    )
    rows = res.data or []
    count = 0
    for r in rows:
        if not (r.get("제품명") or "").startswith("임시_"):
            continue
        if exclude_id is not None and r["id"] == exclude_id:
            continue
        try:
            delete_상품(r["id"])
            count += 1
        except Exception:
            pass
    return count


# ── 엠군작업대상 토글 ────────────────────────────────────────

def set_엠군작업대상(상품_id: int, value: bool) -> None:
    """상품.엠군작업대상 값을 설정한다."""
    _client().table("상품").update({"엠군작업대상": value}).eq("id", 상품_id).execute()


# ── is_test 토글 (테스트 레코드 구분) ─────────────────────────

def set_is_test(상품_id: int, value: bool) -> None:
    """상품.is_test 값을 설정한다. True면 테스트 레코드로 격리."""
    _client().table("상품").update({"is_test": value}).eq("id", 상품_id).execute()


# ── 엠군상태 업데이트 ─────────────────────────────────────

def update_엠군상태(상품_id: int, 상태: str) -> None:
    """엠군 파이프라인 진행 상태 업데이트. (미시작 / 진행중 / 완료)"""
    _client().table("상품").update({"엠군상태": 상태}).eq("id", 상품_id).execute()


# ── 워크플로 토글 + 변경 감지 (snapshot 박제) ─────────────
#
# 박제 대상 필드/단계 정의는 `pipeline.snapshot_schema`에 단일 소스로 모여 있다.
# 새 그룹/필드/엠군 단계 추가 시 snapshot_schema.py만 갱신하면 박제·UI·diff 모두 자동 반영.


def _extract_snapshot_field(row: dict, field: str, 상품_id: int) -> object:
    """단일 필드 → snapshot에 박제할 값.

    분기:
      - SNAPSHOT_GROUPS의 그룹명     → dict (그룹 내부 컬럼들)
      - SNAPSHOT_FILE_FIELDS의 키    → [{"id":..., "name":...}, ...] (정렬)
      - 엠군_SNAPSHOT_STAGES의 키    → 단계별 리스트 (FK 타입에 따라 호출 분기)
      - 그 외                        → row[field] 단일 컬럼
    """
    from . import snapshot_schema as _ss

    # 1) 그룹 필드
    if field in _ss.SNAPSHOT_GROUPS:
        return {k: row.get(k) for k in _ss.SNAPSHOT_GROUPS[field]}

    # 2) 파일 추적 가상 필드
    kind = _ss.파일_field_kind(field)
    if kind is not None:
        files = get_files(상품_id)
        items = [
            {"id": f.get("드라이브_파일_id"), "name": f.get("파일명")}
            for f in files
            if f.get("파일_유형") == kind and f.get("드라이브_파일_id")
        ]
        items.sort(key=lambda x: (x["id"] or ""))
        return items

    # 3) 엠군 단계별 박제
    if _ss.엠군_stage_info(field) is not None:
        return _build_엠군_stage_snapshot(상품_id, field)

    # 4) (구버전 호환) 통합 runs — 더 이상 권장 X. 단일 키만 있는 구 snapshot 비교용.
    if field == "runs":
        return _build_엠군_legacy_runs_snapshot(상품_id)

    # 5) 단일 컬럼
    return row.get(field)


def _build_엠군_stage_snapshot(상품_id: int, stage_key: str) -> list[dict]:
    """엠군 단계별 결과 박제 — FK 타입에 따라 호출 분기.

    반환 구조 (FK 타입별):
      - "run"    → [{"run_id":..., "data": list[dict]}, ...]
      - "target" → [{"run_id":..., "target_id":..., "data": list[dict]}, ...]
      - "detail" → [{"run_id":..., "target_id":..., "detail_id":..., "data": list[dict]}, ...]

    storage.py 인터페이스 변경 시 snapshot_schema.엠군_SNAPSHOT_STAGES도 같이 갱신해야 한다.
    매니페스트에 없는 단계는 박제 안 됨 (safe fallback).
    """
    from . import snapshot_schema as _ss
    from .storage import get_storage

    info = _ss.엠군_stage_info(stage_key)
    if info is None:
        return []
    _label, fk_type, method_name = info

    stg = get_storage()
    method = getattr(stg, method_name, None)
    if method is None:
        return []

    try:
        runs = stg.list_runs_by_product(상품_id)
    except Exception:
        return []

    out: list[dict] = []
    for r in runs:
        run_id = r.get("id")

        # FK = run → 메서드 1회 호출
        if fk_type == "run":
            try:
                data = method(run_id)
            except Exception:
                data = []
            out.append({"run_id": run_id, "data": _normalize_엠군_data(data)})
            continue

        # FK = target 또는 detail → 타겟 순회 필요
        try:
            targets = stg.get_targets(run_id)
        except Exception:
            targets = []

        for t in targets:
            tid = t.get("id")
            if fk_type == "target":
                try:
                    data = method(tid)
                except Exception:
                    data = []
                out.append({
                    "run_id":    run_id,
                    "target_id": tid,
                    "data":      _normalize_엠군_data(data),
                })
                continue

            # FK = detail → 타겟의 상세페이지 순회 후 그 id로 호출
            if fk_type == "detail":
                try:
                    details = stg.get_상세페이지(tid)
                except Exception:
                    details = []
                for d in details:
                    detail_id = d.get("id")
                    try:
                        data = method(detail_id)
                    except Exception:
                        data = []
                    out.append({
                        "run_id":    run_id,
                        "target_id": tid,
                        "detail_id": detail_id,
                        "data":      _normalize_엠군_data(data),
                    })

    return out


def _normalize_엠군_data(data: list[dict]) -> list[dict]:
    """엠군 단계 결과 list[dict]에서 비교에 유의미한 필드만 추출.

    storage가 반환하는 row에는 id·생성일 등 부수 메타가 섞여 있다.
    이를 그대로 박제하면 매번 생성일 차이로 false positive가 난다.
    여기서는 (모델, 원본_출력)만 추려 비교에 안정적인 형태로 정규화한다.

    storage.py에 새 단계가 추가되어 원본_출력 외 다른 핵심 필드가 생기면
    이 함수도 업데이트해야 정확한 변경 감지가 된다. (안 해도 raw 출력 비교는 동작)
    """
    out: list[dict] = []
    for d in data or []:
        out.append({
            "모델":     d.get("모델"),
            "원본_출력": d.get("원본_출력"),
        })
    return out


def _build_엠군_legacy_runs_snapshot(상품_id: int) -> list[dict]:
    """[하위 호환] 'runs' 단일 키로 박제한 구 snapshot을 다시 만들 때 사용.

    신규 박제는 엠군_SNAPSHOT_STAGES 키별로 분리 저장되지만, 기존에 'runs' 키로
    저장된 snapshot과 비교할 때는 이 함수가 같은 형식의 현재 값을 반환해야
    diff가 정상 작동한다.
    """
    from .storage import get_storage

    stg = get_storage()
    try:
        runs = stg.list_runs_by_product(상품_id)
    except Exception:
        return []

    out: list[dict] = []
    for r in runs:
        run_id = r.get("id")
        try:
            targets = stg.get_targets(run_id)
        except Exception:
            targets = []
        targets_out: list[dict] = []
        for t in targets:
            tid = t.get("id")
            try:
                pos = stg.get_positioning(tid)
                det = stg.get_상세페이지(tid)
                img = stg.get_이미지디렉션(tid)
                ch  = stg.get_채널(tid)
            except Exception:
                pos = det = img = ch = []
            targets_out.append({
                "타겟_id": tid,
                "모델":    t.get("모델"),
                "라벨":    t.get("라벨"),
                "캐릭터":  t.get("캐릭터"),
                "결핍":    t.get("핵심_결핍"),
                "선택됨":  bool(t.get("선택됨")),
                "결과": {
                    "포지셔닝":     [(p.get("모델"), p.get("원본_출력")) for p in pos],
                    "상세페이지":   [(p.get("모델"), p.get("원본_출력")) for p in det],
                    "이미지디렉션": [(p.get("모델"), p.get("원본_출력")) for p in img],
                    "채널":         [(p.get("모델"), p.get("원본_출력")) for p in ch],
                },
            })
        out.append({
            "run_id": run_id,
            "생성일": r.get("생성일"),
            "타겟들": targets_out,
        })
    return out


def _build_snapshot_payload(상품_id: int, stage: str) -> dict:
    """단계별 snapshot dict 생성 — settings.snapshot_fields_<stage>에 등재된 필드만 포함.

    상세페이지 단계는 등재 필드가 비어 있으면 빈 dict 반환 (현재 후속 작업자 없음).
    """
    from .settings import snapshot_fields_for_stage

    row = get_product(상품_id) or {}
    fields = snapshot_fields_for_stage(stage)
    payload: dict = {}
    for f in fields:
        payload[f] = _extract_snapshot_field(row, f, 상품_id)
    return payload


# 단계 → (at 컬럼명, snapshot 컬럼명)
_WORKFLOW_COLS: dict[str, tuple[str, str]] = {
    "기초입력":   ("기초입력_완료_at",   "기초입력_완료_snapshot"),
    "엠군":       ("엠군_완료_at",       "엠군_완료_snapshot"),
    "상세페이지": ("상세페이지_완료_at", "상세페이지_완료_snapshot"),
}


def set_워크플로_토글(상품_id: int, stage: str, on: bool) -> None:
    """워크플로 단계 토글 ON/OFF.

    - ON: at = NOW(), snapshot = 현재 시점 박제 dict.
    - OFF: at = NULL, snapshot = NULL (양쪽 모두 비움).
    """
    if stage not in _WORKFLOW_COLS:
        raise ValueError(f"알 수 없는 워크플로 단계: {stage}")
    at_col, snap_col = _WORKFLOW_COLS[stage]

    if on:
        from datetime import datetime, timezone
        payload = {
            at_col:   datetime.now(timezone.utc).isoformat(),
            snap_col: _build_snapshot_payload(상품_id, stage),
        }
    else:
        payload = {at_col: None, snap_col: None}

    _client().table("상품").update(payload).eq("id", 상품_id).execute()


def acknowledge_변경(상품_id: int, stage: str) -> None:
    """후속 작업자가 [✓ 확인했음] 버튼 클릭 시 호출.

    동작: 본인 단계 토글의 at + snapshot 재갱신 (= set_워크플로_토글(.., True) 재호출).
    효과: diff 사라짐 → 🔄 뱃지 사라짐.
    """
    set_워크플로_토글(상품_id, stage, on=True)


# 박스 키 (UI 박스 헤더와 일치)
WORKFLOW_BOX_NONE   = "일반"
WORKFLOW_BOX_BASIC  = "기초입력완료"
WORKFLOW_BOX_MGOON  = "엠군완료"
WORKFLOW_BOX_DETAIL = "상세완료"


def compute_워크플로_단계(row: dict) -> str:
    """상품 row의 토글 조합 → 박스 키 반환.

    우선순위(상위 → 하위): 상세페이지 → 엠군 → 기초입력 → 일반.
    """
    if row.get("상세페이지_완료_at"):
        return WORKFLOW_BOX_DETAIL
    if row.get("엠군_완료_at"):
        return WORKFLOW_BOX_MGOON
    if row.get("기초입력_완료_at"):
        return WORKFLOW_BOX_BASIC
    return WORKFLOW_BOX_NONE


def compute_변경_diff(row: dict, stage: str) -> list[dict]:
    """행의 stage snapshot vs 현재 값 비교 → 변경된 필드 리스트.

    반환 형식: [{"field": "카테고리", "old": "...", "new": "..."}, ...]
    snapshot이 NULL이면 빈 리스트 (= 토글 OFF 상태이므로 변경 감지 자체가 무의미).

    비교 강건성 규칙:
      - snapshot에 없는 키(현재 필드 목록에 새로 추가된 필드)는 비교 제외 → false positive 회피.
      - snapshot에 있고 현재 추출 값에 없는 키는 None vs None으로 떨어져 자동 무시.
    """
    if stage not in _WORKFLOW_COLS:
        return []
    _, snap_col = _WORKFLOW_COLS[stage]
    snap = row.get(snap_col)
    if not snap:
        return []

    상품_id = row["id"]
    current = _build_snapshot_payload(상품_id, stage)

    out: list[dict] = []
    # 비교 대상은 snapshot에 있는 키 ∩ 현재 추출 키 (둘 중 하나에만 있으면 무시)
    for f, old in snap.items():
        if f not in current:
            continue
        new = current[f]
        if _is_changed(old, new):
            out.append({"field": f, "old": old, "new": new})
    return out


def _is_changed(old: object, new: object) -> bool:
    """비교 헬퍼 — JSON 표현 동등성 기준.

    list/dict 비교 시 키 정렬 문제 회피를 위해 json.dumps(sort_keys=True) 직렬화 후 비교.
    """
    import json as _json
    try:
        a = _json.dumps(old, ensure_ascii=False, sort_keys=True, default=str)
        b = _json.dumps(new, ensure_ascii=False, sort_keys=True, default=str)
        return a != b
    except Exception:
        return old != new


def 다음_단계_액션(box: str) -> str | None:
    """박스 키 → 후속 작업자가 해야 할 액션명. 알림 배너용.

    🟠 기초입력완료 → "엠군 파이프라인 실행"
    🔵 엠군완료     → "상세페이지 제작"
    ✅ 상세완료    → None (현재 후속 작업 없음)
    """
    if box == WORKFLOW_BOX_BASIC:
        return "엠군 파이프라인 실행"
    if box == WORKFLOW_BOX_MGOON:
        return "상세페이지 제작"
    return None


# ── 시각설명 업데이트 (Vision Pass 결과 저장) ──────────────

def update_시각설명(상품_id: int, 시각설명: str) -> None:
    """Vision Pass 결과를 상품.시각설명에 저장."""
    _client().table("상품").update({"시각설명": 시각설명}).eq("id", 상품_id).execute()


# ── 비전패스_이력 CRUD ────────────────────────────────────

def insert_비전패스_이력(
    상품_id: int,
    파일_id: str | None,
    모델명: str,
    프롬프트: str,
    결과: str,
    실행_모드: str = "single",
) -> dict:
    """Vision Pass 실행 결과를 이력 테이블에 영구 저장.

    Args:
        파일_id: 드라이브 파일 ID. 일괄실행 결과면 None.
        실행_모드: 'single' (이미지별) | 'bulk' (일괄)

    Returns: 생성된 행 (id 포함).
    """
    res = _client().table("비전패스_이력").insert({
        "상품_id":   상품_id,
        "파일_id":   파일_id,
        "모델명":    모델명,
        "프롬프트":  프롬프트,
        "결과":      결과,
        "실행_모드": 실행_모드,
    }).execute()
    return res.data[0] if res.data else {}


def list_비전패스_이력(상품_id: int, 파일_id: str | None = None) -> list[dict]:
    """상품의 Vision Pass 이력 조회. 파일_id 지정 시 해당 이미지 이력만.

    최신순 정렬.
    """
    q = (
        _client()
        .table("비전패스_이력")
        .select("*")
        .eq("상품_id", 상품_id)
        .order("생성일", desc=True)
    )
    if 파일_id is not None:
        q = q.eq("파일_id", 파일_id)
    return q.execute().data or []


def delete_비전패스_이력(이력_id: int) -> None:
    """이력 1건 삭제."""
    _client().table("비전패스_이력").delete().eq("id", 이력_id).execute()


# ── 갤러리 관련 ────────────────────────────────────────────

def list_all_images(search: str = "", 계정: str | None = None, limit: int = 500) -> list[dict]:
    """상품_파일에서 이미지 전체 조회. 상품명 JOIN 포함."""
    q = (
        _client()
        .table("상품_파일")
        .select("id, 상품_id, 파일명, 드라이브_파일_id, 드라이브_url, 계정, 상품(id, 제품명)")
        .eq("파일_유형", "image")
        .not_.is_("드라이브_파일_id", "null")
        .order("상품_id")
        .limit(limit)
    )
    if 계정:
        q = q.eq("계정", 계정)
    rows = q.execute().data or []
    result = []
    for r in rows:
        flat = dict(r)
        product = flat.pop("상품", None) or {}
        flat["제품명"] = product.get("제품명", "")
        result.append(flat)
    return result


def list_all_files(
    계정: str | None = None,
    파일_유형: str | None = None,
    limit: int = 500,
) -> list[dict]:
    """상품_파일에서 전체 파일 조회 (이미지/동영상/기타 모두). 상품명 JOIN 포함.

    파일_유형: "image" / "video" / None(전체). None이면 모든 유형 반환.
    """
    q = (
        _client()
        .table("상품_파일")
        .select("id, 상품_id, 파일명, 파일_유형, 드라이브_파일_id, 드라이브_url, 계정, 상품(id, 제품명)")
        .not_.is_("드라이브_파일_id", "null")
        .order("상품_id")
        .limit(limit)
    )
    if 계정:
        q = q.eq("계정", 계정)
    if 파일_유형:
        q = q.eq("파일_유형", 파일_유형)
    rows = q.execute().data or []
    result = []
    for r in rows:
        flat = dict(r)
        product = flat.pop("상품", None) or {}
        flat["제품명"] = product.get("제품명", "")
        result.append(flat)
    return result


def get_image_counts() -> dict[int, int]:
    """상품별 이미지 수 딕셔너리 반환. {상품_id: count}"""
    try:
        res = (
            _client()
            .table("상품_파일")
            .select("상품_id")
            .eq("파일_유형", "image")
            .execute()
        )
        counts: dict[int, int] = {}
        for row in res.data or []:
            pid = row["상품_id"]
            counts[pid] = counts.get(pid, 0) + 1
        return counts
    except Exception:
        return {}


def get_file_counts_by_type() -> dict[int, dict[str, int]]:
    """상품별 파일 유형 카운트. {상품_id: {"image": N, "video": N, "etc": N}}

    "etc"는 image/video 외 모든 파일_유형의 합 (예: doc/pdf/audio/null 등).
    """
    try:
        res = (
            _client()
            .table("상품_파일")
            .select("상품_id, 파일_유형")
            .execute()
        )
        counts: dict[int, dict[str, int]] = {}
        for row in res.data or []:
            pid = row["상품_id"]
            kind = row.get("파일_유형")
            bucket = "image" if kind == "image" else ("video" if kind == "video" else "etc")
            d = counts.setdefault(pid, {"image": 0, "video": 0, "etc": 0})
            d[bucket] += 1
        return counts
    except Exception:
        return {}


def format_file_counts(c: dict[str, int]) -> str:
    """파일 카운트를 '📷9 🎬2 📄1' 형식으로 표시 (0인 항목은 생략)."""
    parts: list[str] = []
    if c.get("image", 0) > 0:
        parts.append(f"📷{c['image']}")
    if c.get("video", 0) > 0:
        parts.append(f"🎬{c['video']}")
    if c.get("etc", 0) > 0:
        parts.append(f"📄{c['etc']}")
    return " ".join(parts)


def list_계정_values() -> list[str]:
    """상품_파일에 등록된 계정 목록."""
    try:
        res = (
            _client()
            .table("상품_파일")
            .select("계정")
            .not_.is_("계정", "null")
            .execute()
        )
        seen = set()
        result = []
        for row in res.data or []:
            v = row.get("계정")
            if v and v not in seen:
                seen.add(v)
                result.append(v)
        return sorted(result)
    except Exception:
        return []


def count_파일_by_계정() -> dict[str, int]:
    """상품_파일 테이블의 계정별 파일 수 dict. {계정: count}.

    Drive 대시보드 카드의 "이 계정에 업로드된 파일 수" 표시용.
    """
    try:
        res = _client().table("상품_파일").select("계정").execute()
        counts: dict[str, int] = {}
        for row in res.data or []:
            v = row.get("계정")
            if v:
                counts[v] = counts.get(v, 0) + 1
        return counts
    except Exception:
        return {}


def delete_파일(파일_id: int) -> None:
    """상품_파일 레코드 삭제."""
    _client().table("상품_파일").delete().eq("id", 파일_id).execute()


# ── drive_auth (OAuth 토큰 DB 동기화) ─────────────────────

def get_drive_token(account_name: str) -> dict | None:
    """drive_auth 테이블에서 토큰 정보 조회. 없으면 None.

    반환 dict 키: account_name, refresh_token, client_id, client_secret, token_uri, scopes, updated_at.
    """
    try:
        res = (
            _client()
            .table("drive_auth")
            .select("*")
            .eq("account_name", account_name)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception:
        return None


def upsert_drive_token(account_name: str, token_data: dict) -> dict:
    """drive_auth UPSERT. account_name 기준 충돌 해소.

    token_data 인식 키: refresh_token, client_id, client_secret, token_uri, scopes.
    updated_at은 자동으로 현재 시각으로 설정.
    """
    from datetime import datetime, timezone

    payload: dict = {"account_name": account_name}
    for k in ("refresh_token", "client_id", "client_secret", "token_uri", "scopes"):
        if k in token_data and token_data[k] is not None:
            payload[k] = token_data[k]
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()

    res = (
        _client()
        .table("drive_auth")
        .upsert(payload, on_conflict="account_name")
        .execute()
    )
    return res.data[0] if res.data else {}


# ── 편집_세션 (동시편집 보호 — 사회적 조정) ────────────────

def upsert_편집_세션(상품_id: int, 사용자명: str) -> None:
    """편집 세션 UPSERT — (상품_id, 사용자명) 충돌 시 마지막_활동시각만 갱신."""
    from datetime import datetime, timezone

    _client().table("편집_세션").upsert({
        "상품_id": 상품_id,
        "사용자명": 사용자명,
        "마지막_활동시각": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="상품_id,사용자명").execute()


def get_active_편집_세션(
    상품_id: int,
    exclude_사용자명: str | None = None,
    ttl_min: int = 5,
) -> list[dict]:
    """ttl_min 분 이내 활성 편집 세션 목록. exclude_사용자명은 결과에서 제외.

    동시편집 배지(상단 알림)용 — 다른 사용자가 같은 상품을 편집 중인지 확인.
    """
    from datetime import datetime, timezone, timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=ttl_min)).isoformat()
    q = (
        _client()
        .table("편집_세션")
        .select("*")
        .eq("상품_id", 상품_id)
        .gte("마지막_활동시각", cutoff)
    )
    if exclude_사용자명:
        q = q.neq("사용자명", exclude_사용자명)
    return q.execute().data or []


def delete_편집_세션(상품_id: int, 사용자명: str) -> None:
    """편집 세션 row 즉시 삭제 — 페이지 명시적 종료 시 호출.

    상대편 화면에서 ttl 기다리지 않고 즉시 "편집 중 아님"으로 반영되게.
    """
    _client().table("편집_세션").delete().eq("상품_id", 상품_id).eq("사용자명", 사용자명).execute()


def upsert_파일(상품_id: int, files: list[dict], 계정: str) -> int:
    """Drive 스캔 결과를 상품_파일에 upsert. 드라이브_파일_id 기준 중복 방지.

    files: [{"파일명": str, "파일_유형": str, "드라이브_파일_id": str, "드라이브_url": str, "업로드일": str|None}]
    반환: upsert된 행 수
    """
    if not files:
        return 0
    rows = [
        {
            "상품_id": 상품_id,
            "파일명": f.get("파일명"),
            "파일_유형": f.get("파일_유형", "image"),
            "드라이브_파일_id": f.get("드라이브_파일_id"),
            "드라이브_url": f.get("드라이브_url"),
            "상태": "uploaded",
            "업로드일": f.get("업로드일"),
            "계정": 계정,
        }
        for f in files
        if f.get("드라이브_파일_id")
    ]
    if not rows:
        return 0
    _client().table("상품_파일").upsert(rows, on_conflict="드라이브_파일_id").execute()
    return len(rows)
