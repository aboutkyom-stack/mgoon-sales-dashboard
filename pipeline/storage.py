"""엠군 파이프라인 결과 저장소. 인터페이스 + Supabase 구현.

Supabase(MY_SUPABASE_SERVICE_KEY)에 mgoon_runs/targets/positioning 저장.
공용화 시점에 동료 DB로 추가하려면 새 구현체를 Storage에서 상속하면 됨.
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
    def save_targets(self, run_id: int, targets: list[dict], model: str, raw_output: str) -> list[int]: ...

    @abstractmethod
    def get_targets(self, run_id: int) -> list[dict]: ...

    @abstractmethod
    def mark_target_selected(self, target_id: int, selected: bool = True) -> None: ...

    @abstractmethod
    def save_positioning(self, target_id: int, result: dict, model: str, raw_output: str) -> int: ...

    @abstractmethod
    def get_positioning(self, target_id: int) -> list[dict]: ...

    @abstractmethod
    def list_runs(self, limit: int = 50) -> list[dict]: ...

    @abstractmethod
    def get_run(self, run_id: int) -> dict | None: ...


class SupabaseStorage(Storage):

    def create_run(self, product_snapshot: dict, source_product_id: int | None) -> int:
        name = product_snapshot.get("제품명") or product_snapshot.get("name", "(이름 없음)")
        res = _db().table("mgoon_runs").insert({
            "source_product_id": source_product_id,
            "product_name": name,
            "product_snapshot": json.dumps(product_snapshot, ensure_ascii=False),
        }).execute()
        return res.data[0]["id"]

    def save_targets(self, run_id: int, targets: list[dict], model: str, raw_output: str) -> list[int]:
        ids = []
        for t in targets:
            res = _db().table("mgoon_targets").insert({
                "run_id": run_id,
                "rank": t.get("rank"),
                "character": t.get("character"),
                "deficit": t.get("deficit"),
                "deficit_source": t.get("deficit_source"),
                "purchase_benefit": t.get("purchase_benefit"),
                "urgency": t.get("urgency"),
                "channel": t.get("channel"),
                "note": t.get("note"),
                "desire_layer3": t.get("desire_layer3"),
                "raw_output": raw_output,
                "model": model,
            }).execute()
            ids.append(res.data[0]["id"])
        return ids

    def get_targets(self, run_id: int) -> list[dict]:
        res = (
            _db().table("mgoon_targets")
            .select("*")
            .eq("run_id", run_id)
            .order("model")
            .order("rank")
            .execute()
        )
        return res.data or []

    def mark_target_selected(self, target_id: int, selected: bool = True) -> None:
        _db().table("mgoon_targets").update({"selected": selected}).eq("id", target_id).execute()

    def save_positioning(self, target_id: int, result: dict, model: str, raw_output: str) -> int:
        res = _db().table("mgoon_positioning").insert({
            "target_id": target_id,
            "cv_analysis": result.get("cv_analysis"),
            "positioning_map": result.get("positioning_map"),
            "two_down_two_up": result.get("two_down_two_up"),
            "opening_copy": result.get("opening_copy"),
            "value_additions": result.get("value_additions"),
            "product_essence": result.get("product_essence"),
            "raw_output": raw_output,
            "model": model,
        }).execute()
        return res.data[0]["id"]

    def get_positioning(self, target_id: int) -> list[dict]:
        res = (
            _db().table("mgoon_positioning")
            .select("*")
            .eq("target_id", target_id)
            .order("model")
            .execute()
        )
        return res.data or []

    def list_runs(self, limit: int = 50) -> list[dict]:
        res = (
            _db().table("mgoon_runs")
            .select("id, source_product_id, product_name, created_at")
            .order("id", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []

    def get_run(self, run_id: int) -> dict | None:
        res = _db().table("mgoon_runs").select("*").eq("id", run_id).limit(1).execute()
        if not res.data:
            return None
        d = res.data[0]
        d["product_snapshot"] = json.loads(d["product_snapshot"])
        return d


def get_storage() -> Storage:
    return SupabaseStorage()
