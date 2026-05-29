"""엠군 파이프라인 결과 저장소 — 한글 테이블(엠군_실행 / 엠군_타겟 / 엠군_포지셔닝).

설계
- 한 실행(엠군_실행)에 두 모델(claude / gemini)의 모든 타겟 후보를
  엠군_타겟에 다 저장한다 (모델별 N개 행, 보통 모델당 3~4개).
- 사용자가 02로 진행한 타겟 1개만 `선택됨=true`로 마크.
- 02 결과는 그 선택 타겟에 매달려 모델별 1행씩 엠군_포지셔닝에 저장.
- 인터페이스 메서드명은 영어, 컬럼/필드는 한글.

⚠️ 변경 감지 매니페스트 동기화 규약
================================================================
새 엠군 단계 메서드 (`get_*` 패턴) 를 이 파일에 추가할 때는,
반드시 `pipeline/snapshot_schema.py`의 `엠군_SNAPSHOT_STAGES` 리스트에도
한 줄을 추가해야 한다. 매니페스트에 없으면 변경 감지(snapshot) 박제에서
그 단계가 누락된다 (조용히 빠짐 — 기존 단계 동작에는 영향 X).

추가할 정보:
    ("엠군_<코드>_<이름>", "<UI 라벨>", "<run|target|detail>", "get_<메서드명>")

예시:
    ("엠군_06_새단계", "06 새 단계 설명", "target", "get_새단계")

다른 채팅방에서 작업하는 클로드도 이 규약을 같이 지켜야 한다.
이 docstring + snapshot_schema.py 머리 코멘트가 단일 소스 안내.
================================================================
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@lru_cache(maxsize=1)
def _db():
    from supabase import create_client
    url = os.getenv("MY_SUPABASE_URL", "").strip()
    key = (os.getenv("MY_SUPABASE_SERVICE_KEY") or os.getenv("MY_SUPABASE_ANON_KEY", "")).strip()
    if not url or not key:
        raise RuntimeError(".env에 MY_SUPABASE_URL과 MY_SUPABASE_SERVICE_KEY를 설정하세요.")
    return create_client(url, key)


class Storage(ABC):
    @abstractmethod
    def create_run(self, product_snapshot: dict, source_product_id: int | None) -> int: ...

    @abstractmethod
    def save_targets(
        self,
        run_id: int,
        targets: list[dict],
        model: str,
        raw_output: str,
        recommended_rank: int | None = None,
    ) -> list[int]: ...

    @abstractmethod
    def get_targets(self, run_id: int) -> list[dict]: ...

    @abstractmethod
    def mark_target_selected(self, target_id: int, selected: bool = True) -> None: ...

    @abstractmethod
    def clear_selected_in_run(self, run_id: int) -> None: ...

    @abstractmethod
    def save_positioning(
        self,
        target_id: int,
        model: str,
        raw_output: str,
        category_objections: list | None = None,
        rule_engine_inputs: dict | None = None,
        rule_engine_flags: dict | None = None,
        persuasion_method_candidates: list | None = None,
    ) -> int: ...

    @abstractmethod
    def get_positioning(self, target_id: int) -> list[dict]: ...

    @abstractmethod
    def save_상세페이지(
        self,
        target_id: int,
        model: str,
        raw_output: str,
        engine_plan: dict | None = None,
        한_축_사슬: str | None = None,
        설득_방식_주: str | None = None,
        설득_방식_보조: list | None = None,
    ) -> int: ...

    @abstractmethod
    def get_상세페이지(self, target_id: int) -> list[dict]: ...

    # ── 04_b 상세페이지 검수 (옵션 3 토글 호출) ───────────
    @abstractmethod
    def save_상세페이지_검수(
        self,
        detail_id: int,
        model: str,
        raw_output: str,
        검수_보고서: str | None = None,
        다듬은_콘티: str | None = None,
    ) -> int: ...

    @abstractmethod
    def get_상세페이지_검수(self, detail_id: int) -> list[dict]: ...

    @abstractmethod
    def delete_상세페이지_검수(self, review_id: int) -> None: ...

    @abstractmethod
    def save_이미지디렉션(
        self,
        target_id: int,
        model: str,
        raw_output: str,
        sections: list[dict] | None = None,
        design_system: dict | None = None,
        selection_method: str | None = None,
    ) -> int: ...

    @abstractmethod
    def get_이미지디렉션(self, target_id: int) -> list[dict]: ...

    @abstractmethod
    def save_채널(self, target_id: int, model: str, raw_output: str) -> int: ...

    @abstractmethod
    def get_채널(self, target_id: int) -> list[dict]: ...

    @abstractmethod
    def save_네이밍(self, target_id: int, model: str, raw_output: str,
                   분류: str = "") -> int: ...

    @abstractmethod
    def get_네이밍(self, target_id: int) -> list[dict]: ...

    @abstractmethod
    def list_runs(self, limit: int = 50) -> list[dict]: ...

    @abstractmethod
    def list_runs_by_product(self, product_id: int) -> list[dict]: ...

    @abstractmethod
    def get_run(self, run_id: int) -> dict | None: ...

    @abstractmethod
    def delete_run(self, run_id: int) -> None: ...

    @abstractmethod
    def get_run_summary(self, run_id: int) -> dict: ...

    # ── 작업 C: 타겟별 작업 이력 bulk 조회 ──────────────────
    @abstractmethod
    def get_result_summary_for_targets(
        self, target_ids: list[int]
    ) -> dict[int, set[str]]: ...

    # ── 작업 D: 단계별 버전 이력 ────────────────────────────
    @abstractmethod
    def get_positioning_versions(
        self, target_id: int, model: str
    ) -> list[dict]: ...

    @abstractmethod
    def delete_positioning(self, positioning_id: int) -> None: ...

    @abstractmethod
    def get_상세페이지_versions(
        self, target_id: int, model: str
    ) -> list[dict]: ...

    @abstractmethod
    def delete_상세페이지(self, detail_id: int) -> None: ...

    @abstractmethod
    def get_이미지디렉션_versions(
        self, target_id: int, model: str
    ) -> list[dict]: ...

    @abstractmethod
    def delete_이미지디렉션(self, direction_id: int) -> None: ...

    @abstractmethod
    def get_채널_versions(
        self, target_id: int, model: str
    ) -> list[dict]: ...

    @abstractmethod
    def delete_채널(self, channel_id: int) -> None: ...


class SupabaseStorage(Storage):

    def create_run(self, product_snapshot: dict, source_product_id: int | None) -> int:
        name = product_snapshot.get("제품명") or "(이름 없음)"
        res = _db().table("엠군_실행").insert({
            "상품_id": source_product_id,
            "제품명": name,
            "제품_스냅샷": json.dumps(product_snapshot, ensure_ascii=False),
        }).execute()
        return res.data[0]["id"]

    def save_targets(
        self,
        run_id: int,
        targets: list[dict],
        model: str,
        raw_output: str,
        recommended_rank: int | None = None,
    ) -> list[int]:
        """01 결과의 타겟 후보들을 일괄 저장.

        targets: 각 dict는 _extract_targets_json 결과의 한 항목 형식.
                 { rank, label, character, deficit, deficit_source,
                   benefit_type, involvement, channel, buyer_user_split,
                   wants_3tier, note }
        """
        ids: list[int] = []
        for t in targets:
            rank = t.get("rank")
            involvement_raw = t.get("involvement")
            try:
                involvement = int(involvement_raw) if involvement_raw not in (None, "") else None
            except (TypeError, ValueError):
                involvement = None
            if involvement == 0:
                involvement = 1
            res = _db().table("엠군_타겟").insert({
                "실행_id": run_id,
                "모델": model,
                "순위": rank,
                "라벨": t.get("label"),
                "캐릭터": t.get("character"),
                "핵심_결핍": t.get("deficit"),
                "결핍_원천": t.get("deficit_source"),
                "구매편익": t.get("benefit_type"),
                "관여도": involvement,
                "주요_채널": t.get("channel"),
                "구매자_이용자_분리": t.get("buyer_user_split"),
                "욕구깡패": t.get("wants_3tier"),
                "비고": t.get("note"),
                "추천_여부": (recommended_rank is not None and rank == recommended_rank),
                "원본_출력": raw_output,
            }).execute()
            ids.append(res.data[0]["id"])
        return ids

    def get_targets(self, run_id: int) -> list[dict]:
        res = (
            _db().table("엠군_타겟")
            .select("*")
            .eq("실행_id", run_id)
            .order("모델")
            .order("순위")
            .execute()
        )
        return res.data or []

    def mark_target_selected(self, target_id: int, selected: bool = True) -> None:
        _db().table("엠군_타겟").update({"선택됨": selected}).eq("id", target_id).execute()

    def clear_selected_in_run(self, run_id: int) -> None:
        _db().table("엠군_타겟").update({"선택됨": False}).eq("실행_id", run_id).execute()

    def save_positioning(
        self,
        target_id: int,
        model: str,
        raw_output: str,
        category_objections: list | None = None,
        rule_engine_inputs: dict | None = None,
        rule_engine_flags: dict | None = None,
        persuasion_method_candidates: list | None = None,
    ) -> int:
        payload: dict = {
            "타겟_id": target_id,
            "모델": model,
            "원본_출력": raw_output,
        }
        if category_objections is not None:
            payload["category_objections"] = json.dumps(category_objections, ensure_ascii=False)
        if rule_engine_inputs is not None:
            payload["rule_engine_inputs"] = json.dumps(rule_engine_inputs, ensure_ascii=False)
        if rule_engine_flags is not None:
            payload["rule_engine_flags"] = json.dumps(rule_engine_flags, ensure_ascii=False)
        if persuasion_method_candidates is not None:
            payload["persuasion_method_candidates"] = json.dumps(persuasion_method_candidates, ensure_ascii=False)
        res = _db().table("엠군_포지셔닝").insert(payload).execute()
        return res.data[0]["id"]

    def get_positioning(self, target_id: int) -> list[dict]:
        res = (
            _db().table("엠군_포지셔닝")
            .select("*")
            .eq("타겟_id", target_id)
            .order("모델")
            .execute()
        )
        return res.data or []

    # ── 04 상세페이지 ─────────────────────────────────────
    def save_상세페이지(
        self,
        target_id: int,
        model: str,
        raw_output: str,
        engine_plan: dict | None = None,
        한_축_사슬: str | None = None,
        설득_방식_주: str | None = None,
        설득_방식_보조: list | None = None,
    ) -> int:
        payload: dict = {
            "타겟_id": target_id,
            "모델": model,
            "원본_출력": raw_output,
        }
        if engine_plan is not None:
            payload["engine_plan"] = json.dumps(engine_plan, ensure_ascii=False)
        if 한_축_사슬 is not None:
            payload["한_축_사슬"] = 한_축_사슬
        if 설득_방식_주 is not None:
            payload["설득_방식_주"] = 설득_방식_주
        if 설득_방식_보조 is not None:
            payload["설득_방식_보조"] = json.dumps(설득_방식_보조, ensure_ascii=False)
        res = _db().table("엠군_상세페이지").insert(payload).execute()
        return res.data[0]["id"]

    def get_상세페이지(self, target_id: int) -> list[dict]:
        res = (
            _db().table("엠군_상세페이지")
            .select("*")
            .eq("타겟_id", target_id)
            .order("모델")
            .execute()
        )
        return res.data or []

    # ── 04_b 상세페이지 검수 (옵션 3 토글 호출) ───────────
    def save_상세페이지_검수(
        self,
        detail_id: int,
        model: str,
        raw_output: str,
        검수_보고서: str | None = None,
        다듬은_콘티: str | None = None,
    ) -> int:
        payload: dict = {
            "상세페이지_id": detail_id,
            "모델": model,
            "원본_출력": raw_output,
        }
        if 검수_보고서 is not None:
            payload["검수_보고서"] = 검수_보고서
        if 다듬은_콘티 is not None:
            payload["다듬은_콘티"] = 다듬은_콘티
        res = _db().table("엠군_상세페이지_검수").insert(payload).execute()
        return res.data[0]["id"]

    def get_상세페이지_검수(self, detail_id: int) -> list[dict]:
        res = (
            _db().table("엠군_상세페이지_검수")
            .select("*")
            .eq("상세페이지_id", detail_id)
            .order("id", desc=True)
            .execute()
        )
        return res.data or []

    def delete_상세페이지_검수(self, review_id: int) -> None:
        _db().table("엠군_상세페이지_검수").delete().eq("id", review_id).execute()

    # ── 04-1 이미지 디렉션 ─────────────────────────────────
    def save_이미지디렉션(
        self,
        target_id: int,
        model: str,
        raw_output: str,
        sections: list[dict] | None = None,
        design_system: dict | None = None,
        selection_method: str | None = None,
    ) -> int:
        payload: dict = {
            "타겟_id": target_id,
            "모델": model,
            "원본_출력": raw_output,
        }
        if sections is not None:
            payload["섹션들"] = json.dumps(sections, ensure_ascii=False)
        if design_system is not None:
            payload["디자인시스템"] = json.dumps(design_system, ensure_ascii=False)
        if selection_method is not None:
            payload["선택_방식"] = selection_method
        res = _db().table("엠군_이미지디렉션").insert(payload).execute()
        return res.data[0]["id"]

    def get_이미지디렉션(self, target_id: int) -> list[dict]:
        res = (
            _db().table("엠군_이미지디렉션")
            .select("*")
            .eq("타겟_id", target_id)
            .order("모델")
            .execute()
        )
        return res.data or []

    # ── 05 채널 ──────────────────────────────────────────
    def save_채널(self, target_id: int, model: str, raw_output: str) -> int:
        res = _db().table("엠군_채널").insert({
            "타겟_id": target_id,
            "모델": model,
            "원본_출력": raw_output,
        }).execute()
        return res.data[0]["id"]

    def get_채널(self, target_id: int) -> list[dict]:
        res = (
            _db().table("엠군_채널")
            .select("*")
            .eq("타겟_id", target_id)
            .order("모델")
            .execute()
        )
        return res.data or []

    # ── 03 네이밍 (별도 페이지에서 호출) ───────────────────
    def save_네이밍(self, target_id: int, model: str, raw_output: str,
                   분류: str = "") -> int:
        res = _db().table("엠군_네이밍").insert({
            "타겟_id": target_id,
            "모델": model,
            "원본_출력": raw_output,
            "분류": 분류 or None,
        }).execute()
        return res.data[0]["id"]

    def get_네이밍(self, target_id: int) -> list[dict]:
        res = (
            _db().table("엠군_네이밍")
            .select("*")
            .eq("타겟_id", target_id)
            .order("모델")
            .execute()
        )
        return res.data or []

    def list_runs(self, limit: int = 50) -> list[dict]:
        res = (
            _db().table("엠군_실행")
            .select("id, 상품_id, 제품명, 생성일")
            .order("id", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []

    def list_runs_by_product(self, product_id: int) -> list[dict]:
        """특정 상품의 모든 엠군 실행 (최신순)."""
        res = (
            _db().table("엠군_실행")
            .select("id, 상품_id, 제품명, 생성일")
            .eq("상품_id", product_id)
            .order("id", desc=True)
            .execute()
        )
        return res.data or []

    def delete_run(self, run_id: int) -> None:
        """실행 삭제. FK CASCADE로 엠군_타겟·엠군_포지셔닝도 함께 정리됨."""
        _db().table("엠군_실행").delete().eq("id", run_id).execute()

    def get_run_summary(self, run_id: int) -> dict:
        """실행 1건의 요약: 선택된 타겟 + 02/04/04-1/05/03 결과 유무.

        반환: {
          "selected_target": {라벨, 모델, 순위, ...} | None,
          "has_positioning": bool,
          "has_상세페이지": bool,
          "has_이미지디렉션": bool,
          "has_채널": bool,
          "has_네이밍": bool,
          "target_count": int,
        }
        """
        targets = self.get_targets(run_id)
        selected = next((t for t in targets if t.get("선택됨")), None)
        has_positioning = False
        has_detail = False
        has_image_dir = False
        has_channel = False
        has_naming = False
        if selected:
            tid = selected["id"]
            pos = self.get_positioning(tid)
            has_positioning = bool(pos and any(p.get("원본_출력") for p in pos))
            det = self.get_상세페이지(tid)
            has_detail = bool(det and any(p.get("원본_출력") for p in det))
            img = self.get_이미지디렉션(tid)
            has_image_dir = bool(img and any(p.get("원본_출력") for p in img))
            ch = self.get_채널(tid)
            has_channel = bool(ch and any(p.get("원본_출력") for p in ch))
            nm = self.get_네이밍(tid)
            has_naming = bool(nm and any(p.get("원본_출력") for p in nm))
        return {
            "selected_target": selected,
            "has_positioning": has_positioning,
            "has_상세페이지": has_detail,
            "has_이미지디렉션": has_image_dir,
            "has_채널": has_channel,
            "has_네이밍": has_naming,
            "target_count": len(targets),
        }

    def get_run(self, run_id: int) -> dict | None:
        res = _db().table("엠군_실행").select("*").eq("id", run_id).limit(1).execute()
        if not res.data:
            return None
        d = res.data[0]
        snapshot_raw = d.get("제품_스냅샷")
        if isinstance(snapshot_raw, str):
            try:
                d["제품_스냅샷"] = json.loads(snapshot_raw)
            except Exception:
                pass
        return d

    # ── 작업 C: 타겟별 작업 이력 bulk 조회 ──────────────────
    def get_result_summary_for_targets(
        self, target_ids: list[int]
    ) -> dict[int, set[str]]:
        """여러 타겟에 대해 어떤 단계 결과를 갖는지 한 번에 조회.

        반환: {target_db_id: {"02", "04", "05", "03"}}
              결과가 없는 타겟도 빈 set으로 포함.
        """
        out: dict[int, set[str]] = {tid: set() for tid in target_ids}
        if not target_ids:
            return out

        # 각 테이블에서 타겟_id만 조회 (원본_출력은 가져오지 않음 — 가벼움)
        for table, stage_code in (
            ("엠군_포지셔닝", "02"),
            ("엠군_상세페이지", "04"),
            ("엠군_이미지디렉션", "04_1"),
            ("엠군_채널", "05"),
            ("엠군_네이밍", "03"),
        ):
            res = (
                _db().table(table)
                .select("타겟_id, 원본_출력")
                .in_("타겟_id", target_ids)
                .execute()
            )
            for row in (res.data or []):
                if row.get("원본_출력"):
                    tid = row.get("타겟_id")
                    if tid in out:
                        out[tid].add(stage_code)
        return out

    # ── 작업 D: 단계별 버전 이력 ────────────────────────────
    def get_positioning_versions(
        self, target_id: int, model: str
    ) -> list[dict]:
        """특정 타겟·모델의 02 포지셔닝 모든 버전을 최신순으로 반환."""
        res = (
            _db().table("엠군_포지셔닝")
            .select("id, 모델, 원본_출력, 생성일")
            .eq("타겟_id", target_id)
            .eq("모델", model)
            .order("id", desc=True)
            .execute()
        )
        return res.data or []

    def delete_positioning(self, positioning_id: int) -> None:
        _db().table("엠군_포지셔닝").delete().eq("id", positioning_id).execute()

    def get_상세페이지_versions(
        self, target_id: int, model: str
    ) -> list[dict]:
        res = (
            _db().table("엠군_상세페이지")
            .select("id, 모델, 원본_출력, 생성일")
            .eq("타겟_id", target_id)
            .eq("모델", model)
            .order("id", desc=True)
            .execute()
        )
        return res.data or []

    def delete_상세페이지(self, detail_id: int) -> None:
        _db().table("엠군_상세페이지").delete().eq("id", detail_id).execute()

    def get_이미지디렉션_versions(
        self, target_id: int, model: str
    ) -> list[dict]:
        res = (
            _db().table("엠군_이미지디렉션")
            .select("id, 모델, 원본_출력, 섹션들, 디자인시스템, 선택_방식, 생성일")
            .eq("타겟_id", target_id)
            .eq("모델", model)
            .order("id", desc=True)
            .execute()
        )
        return res.data or []

    def delete_이미지디렉션(self, direction_id: int) -> None:
        _db().table("엠군_이미지디렉션").delete().eq("id", direction_id).execute()

    def get_채널_versions(
        self, target_id: int, model: str
    ) -> list[dict]:
        res = (
            _db().table("엠군_채널")
            .select("id, 모델, 원본_출력, 생성일")
            .eq("타겟_id", target_id)
            .eq("모델", model)
            .order("id", desc=True)
            .execute()
        )
        return res.data or []

    def delete_채널(self, channel_id: int) -> None:
        _db().table("엠군_채널").delete().eq("id", channel_id).execute()


def get_storage() -> Storage:
    return SupabaseStorage()
