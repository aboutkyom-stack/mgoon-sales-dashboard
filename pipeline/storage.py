"""엠군 파이프라인 결과 저장소 — 한글 테이블(엠군_실행 / 엠군_타겟 / 엠군_포지셔닝).

설계
- 한 실행(엠군_실행)에 두 모델(claude / gemini)의 모든 타겟 후보를
  엠군_타겟에 다 저장한다 (모델별 N개 행, 보통 모델당 3~4개).
- 사용자가 02로 진행한 타겟 1개만 `선택됨=true`로 마크.
- 02 결과는 그 선택 타겟에 매달려 모델별 1행씩 엠군_포지셔닝에 저장.
- 인터페이스 메서드명은 영어, 컬럼/필드는 한글.
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
    def save_positioning(self, target_id: int, model: str, raw_output: str) -> int: ...

    @abstractmethod
    def get_positioning(self, target_id: int) -> list[dict]: ...

    @abstractmethod
    def save_상세페이지(self, target_id: int, model: str, raw_output: str) -> int: ...

    @abstractmethod
    def get_상세페이지(self, target_id: int) -> list[dict]: ...

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

    def save_positioning(self, target_id: int, model: str, raw_output: str) -> int:
        res = _db().table("엠군_포지셔닝").insert({
            "타겟_id": target_id,
            "모델": model,
            "원본_출력": raw_output,
        }).execute()
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
    def save_상세페이지(self, target_id: int, model: str, raw_output: str) -> int:
        res = _db().table("엠군_상세페이지").insert({
            "타겟_id": target_id,
            "모델": model,
            "원본_출력": raw_output,
        }).execute()
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
        """실행 1건의 요약: 선택된 타겟 + 02/04/05/03 결과 유무.

        반환: {
          "selected_target": {라벨, 모델, 순위, ...} | None,
          "has_positioning": bool,
          "has_상세페이지": bool,
          "has_채널": bool,
          "has_네이밍": bool,
          "target_count": int,
        }
        """
        targets = self.get_targets(run_id)
        selected = next((t for t in targets if t.get("선택됨")), None)
        has_positioning = False
        has_detail = False
        has_channel = False
        has_naming = False
        if selected:
            tid = selected["id"]
            pos = self.get_positioning(tid)
            has_positioning = bool(pos and any(p.get("원본_출력") for p in pos))
            det = self.get_상세페이지(tid)
            has_detail = bool(det and any(p.get("원본_출력") for p in det))
            ch = self.get_채널(tid)
            has_channel = bool(ch and any(p.get("원본_출력") for p in ch))
            nm = self.get_네이밍(tid)
            has_naming = bool(nm and any(p.get("원본_출력") for p in nm))
        return {
            "selected_target": selected,
            "has_positioning": has_positioning,
            "has_상세페이지": has_detail,
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


def get_storage() -> Storage:
    return SupabaseStorage()
