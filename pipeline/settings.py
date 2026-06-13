"""파이프라인 모델 설정 관리. settings.json에 영속 저장.

스키마:
- 단계: 00 Vision Pass / 01 결핍·타겟 / 02 포지셔닝 / 03 네이밍 / 04 상세페이지 / 05 채널
- 단계별로 주 사용 모델 + 비교 모델(on/off) 1쌍씩 보관.
- 모델 후보는 Claude/Gemini를 한 리스트(MODELS_ORDERED)에 통합.

기존 호출부 호환을 위해 `models_for_stage(stage)`는 (claude_model, gemini_model)
튜플을 반환한다. primary와 compare를 family로 자동 분배하며, compare_enabled가
False이면 compare는 None으로 처리.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .models_config import family_of

# 전역 설정의 진실의 원천은 Supabase `app_settings` 테이블(단일 행).
# 이 로컬 파일은 오프라인/DB 장애 시의 폴백 캐시 겸 백업으로만 유지된다.
SETTINGS_PATH = Path(__file__).parent.parent / "settings.json"

# UI 노출 순서. 첫 항목이 기본값.
MODELS_ORDERED = [
    "claude-sonnet-4-6",
    "claude-opus-4-7",
    "claude-haiku-4-5-20251001",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
]

STAGES = ("00", "01", "02", "03", "04", "04_1", "05")

_DEFAULT_PRIMARY = "claude-sonnet-4-6"
_DEFAULT_COMPARE = "gemini-2.5-flash"

# LLM 프롬프트에서 기본 제외할 제품 필드 (재고 그룹 + 내부 관리 필드)
DEFAULT_EXCLUDED_FIELDS: list[str] = ["재고", "판매자메모", "검수완료", "검수메모", "엠군상태"]

# 전역 판매자 특성 기본값 (settings.json에 저장)
# 두 카테고리로 분리:
#  - 판매자특성_활용: 01~05 파이프라인이 참조 (조건부 활용)
#  - 판매자특성_메모: 판매자 본인만 참고, 파이프라인 미참조
DEFAULT_판매자특성_활용: list[str] = []
DEFAULT_판매자특성_메모: list[str] = []

# 워크플로 토글 단계 키 (상품 컬럼 prefix와 일치: 기초입력_완료_at 등)
WORKFLOW_STAGES: tuple[str, ...] = ("기초입력", "엠군", "상세페이지")

# snapshot 박제 후보/기본값은 `pipeline.snapshot_schema`를 단일 소스로 사용.
# 그룹/필드/엠군 단계 추가는 그 모듈에서만 하면 여기와 설정 페이지까지 자동 반영.
from . import snapshot_schema as _snap_schema

# 설정 페이지(0_settings.py)에서 사용자가 켜고 끌 수 있는 후보 필드 목록.
# 단일 소스(snapshot_schema)에서 동적으로 생성 — 매니페스트 갱신 시 즉시 반영.
SNAPSHOT_FIELD_CANDIDATES: dict[str, list[str]] = {
    "기초입력":   _snap_schema.기초입력_candidates(),
    "엠군":       _snap_schema.엠군_candidates(),
    "상세페이지": _snap_schema.상세페이지_candidates(),
}

# 기본값 — 모든 후보를 기본 ON. 사용자가 필요 시 0_settings에서 OFF.
DEFAULT_SNAPSHOT_FIELDS: dict[str, list[str]] = {
    ws: list(SNAPSHOT_FIELD_CANDIDATES.get(ws, []))
    for ws in WORKFLOW_STAGES
}


def _build_defaults() -> dict:
    out: dict = {
        "판매자특성_활용": list(DEFAULT_판매자특성_활용),
        "판매자특성_메모": list(DEFAULT_판매자특성_메모),
    }
    for s in STAGES:
        out[f"primary_model_{s}"] = _DEFAULT_PRIMARY
        out[f"compare_model_{s}"] = _DEFAULT_COMPARE
        out[f"compare_enabled_{s}"] = True
        out[f"lint_enabled_{s}"] = False  # 외부 린터(교차 검수) — 비용 발생, 기본 off
        out[f"excluded_fields_{s}"] = list(DEFAULT_EXCLUDED_FIELDS)
    for ws in WORKFLOW_STAGES:
        out[f"snapshot_fields_{ws}"] = list(DEFAULT_SNAPSHOT_FIELDS[ws])
    return out


DEFAULTS: dict = _build_defaults()

# ── 전역 설정 영속화 (Supabase app_settings ↔ 로컬 파일 폴백) ──
# Streamlit은 인터랙션마다 스크립트를 전체 재실행하므로 load()가 한 번의
# 렌더에서 여러 번 호출된다. 짧은 메모리 캐시로 중복 DB 조회를 막는다.
_CACHE: dict = {"data": None, "ts": 0.0}
_CACHE_TTL = 3.0  # 초 — 동료 변경은 최대 이 시간 후 반영(허용 범위)


def _merge_defaults(saved: dict) -> dict:
    """구 키 마이그레이션 + DEFAULTS 병합. 신 키만 채택."""
    if "판매자특성" in saved and "판매자특성_활용" not in saved:
        saved = dict(saved)
        saved["판매자특성_활용"] = saved.pop("판매자특성")
    saved_clean = {k: v for k, v in saved.items() if k in DEFAULTS}
    return {**DEFAULTS, **saved_clean}


def _read_file() -> dict | None:
    """로컬 settings.json 읽기 (DB 폴백). 없거나 깨졌으면 None."""
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _write_file(settings: dict) -> None:
    """로컬 settings.json 미러 (오프라인 백업). 실패는 무시."""
    try:
        SETTINGS_PATH.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def load(force: bool = False) -> dict:
    """전역 설정 로드 + DEFAULTS 병합.

    우선순위: Supabase app_settings → 로컬 settings.json(폴백) → DEFAULTS.
    DB가 진실의 원천이며, 짧은 메모리 캐시(_CACHE_TTL)로 중복 조회를 막는다.
    force=True면 캐시를 무시하고 즉시 재조회.
    """
    now = time.time()
    if not force and _CACHE["data"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL:
        return dict(_CACHE["data"])

    saved: dict | None = None
    try:
        from .supabase_read import get_app_settings
        saved = get_app_settings()  # 조회 실패 시 None
    except Exception:
        saved = None
    if saved is None:
        saved = _read_file()  # DB 실패 → 로컬 폴백
    if saved is None:
        saved = {}

    merged = _merge_defaults(saved)
    _CACHE["data"] = merged
    _CACHE["ts"] = now
    return dict(merged)


def _coerce_list(val) -> list[str]:
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    return []


def load_판매자특성_활용() -> list[str]:
    """파이프라인 활용형 판매자 특성 목록. 01~05가 조건부 참조."""
    cfg = load()
    return _coerce_list(cfg.get("판매자특성_활용", []))


def load_판매자특성_메모() -> list[str]:
    """개인 메모용 판매자 특성 목록. 파이프라인 미참조."""
    cfg = load()
    return _coerce_list(cfg.get("판매자특성_메모", []))


def load_판매자특성() -> list[str]:
    """[하위 호환] 활용형만 반환. 신규 코드는 load_판매자특성_활용() 사용."""
    return load_판매자특성_활용()


def save(settings: dict) -> None:
    """전역 설정 저장 — Supabase app_settings에 통째 upsert + 로컬 미러.

    last-write-wins: 저장 시점의 전체 설정으로 DB 단일 행을 교체한다.
    로컬 미러·캐시는 먼저 확정하고, DB upsert는 마지막에 시도한다.
    DB 저장이 실패하면 예외를 전파해 호출부가 사용자에게 알릴 수 있게 한다
    (로컬에는 이미 저장된 상태).
    """
    _write_file(settings)
    _CACHE["data"] = _merge_defaults(settings)
    _CACHE["ts"] = time.time()

    from .supabase_read import upsert_app_settings
    upsert_app_settings(settings)  # 실패 시 예외 전파


def models_for_stage(stage: str, cfg: dict | None = None) -> tuple[str | None, str | None]:
    """단계별 (claude_model, gemini_model) 튜플 반환 (기존 호출부 호환).

    primary와 compare를 family에 따라 분배:
    - primary가 claude면 claude_model = primary, gemini_model = compare(gemini family일 때만)
    - primary가 gemini면 그 반대
    - compare_enabled=False면 compare 무시
    - primary와 compare가 같은 family면 primary만 사용 (비교 모델 무시)
    """
    cfg = cfg or load()
    primary = cfg.get(f"primary_model_{stage}") or _DEFAULT_PRIMARY
    compare = cfg.get(f"compare_model_{stage}")
    enabled = bool(cfg.get(f"compare_enabled_{stage}", True))

    pf = family_of(primary)
    claude_model: str | None = primary if pf == "claude" else None
    gemini_model: str | None = primary if pf == "gemini" else None

    if enabled and compare:
        cf = family_of(compare)
        if cf != pf:  # 다른 family일 때만 비교 모델로 채택
            if cf == "claude":
                claude_model = compare
            elif cf == "gemini":
                gemini_model = compare

    return claude_model, gemini_model


def model_for_family(family: str, stage: str, cfg: dict | None = None) -> str | None:
    """단계별 family('claude'|'gemini')에 해당하는 모델 ID 반환. 없으면 None."""
    cm, gm = models_for_stage(stage, cfg)
    if family == "claude":
        return cm
    if family == "gemini":
        return gm
    return None


def lint_enabled_for_stage(stage: str, cfg: dict | None = None) -> bool:
    """단계별 외부 린터(교차 검수) 사용 여부.

    비교 모델 토글과 독립적으로 운영. 비용이 발생하므로 기본값은 False.
    """
    cfg = cfg or load()
    return bool(cfg.get(f"lint_enabled_{stage}", False))


def lint_models_for_stage(
    stage: str, cfg: dict | None = None
) -> tuple[str | None, str | None]:
    """린터(교차 검수)에 쓰일 (claude_model, gemini_model) 반환.

    `models_for_stage`와 달리 compare_enabled를 무시하고 항상 두 family를 노출.
    같은 family인 비교 모델은 자가 편향 회피 위해 무시.

    primary와 compare가 다른 family일 때만 두 슬롯이 채워진다.
    """
    cfg = cfg or load()
    primary = cfg.get(f"primary_model_{stage}") or _DEFAULT_PRIMARY
    compare = cfg.get(f"compare_model_{stage}")

    pf = family_of(primary)
    claude_m: str | None = primary if pf == "claude" else None
    gemini_m: str | None = primary if pf == "gemini" else None

    if compare:
        cf = family_of(compare)
        if cf != pf:
            if cf == "claude":
                claude_m = compare
            elif cf == "gemini":
                gemini_m = compare

    return claude_m, gemini_m


def caption_for_stage(stage: str, cfg: dict | None = None) -> str:
    """단계별 모델 캡션. 페이지 상단에 노출."""
    cfg = cfg or load()
    primary = cfg.get(f"primary_model_{stage}", "?")
    enabled = bool(cfg.get(f"compare_enabled_{stage}", True))
    compare = cfg.get(f"compare_model_{stage}") if enabled else None
    if compare:
        return f"주: `{primary}` · 비교: `{compare}`  ([⚙️ 설정](0_settings)에서 변경)"
    return f"주: `{primary}` (비교 off)  ([⚙️ 설정](0_settings)에서 변경)"


def excluded_fields_for_stage(stage: str, cfg: dict | None = None) -> list[str]:
    """단계별 LLM 프롬프트 제외 필드 목록."""
    cfg = cfg or load()
    return list(cfg.get(f"excluded_fields_{stage}", DEFAULT_EXCLUDED_FIELDS))


def snapshot_fields_for_stage(stage: str, cfg: dict | None = None) -> list[str]:
    """워크플로 단계(기초입력/엠군/상세페이지)의 snapshot 박제 필드 목록.

    토글 ON 시점에 박제하고, 페이지 로드 시 현재 값과 비교해 후속 작업자에게
    🔄 변경 알림을 노출한다. 사용자는 `pages/0_settings.py`에서 단계별로 켜고 끌 수 있다.
    """
    cfg = cfg or load()
    return list(cfg.get(f"snapshot_fields_{stage}", DEFAULT_SNAPSHOT_FIELDS.get(stage, [])))
