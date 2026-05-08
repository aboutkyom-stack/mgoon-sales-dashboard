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
from pathlib import Path

from .models_config import family_of

SETTINGS_PATH = Path(__file__).parent.parent / "settings.json"

# UI 노출 순서. 첫 항목이 기본값.
MODELS_ORDERED = [
    "claude-sonnet-4-6",
    "claude-opus-4-7",
    "claude-haiku-4-5-20251001",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
]

STAGES = ("00", "01", "02", "03", "04", "05")

_DEFAULT_PRIMARY = "claude-sonnet-4-6"
_DEFAULT_COMPARE = "gemini-2.5-flash"

# LLM 프롬프트에서 기본 제외할 제품 필드 (재고 그룹 + 내부 관리 필드)
DEFAULT_EXCLUDED_FIELDS: list[str] = ["재고", "판매자메모", "검수완료", "검수메모", "엠군상태"]

# 전역 판매자 특성 기본값 (settings.json에 저장)
DEFAULT_판매자특성: list[str] = []


def _build_defaults() -> dict:
    out: dict = {"판매자특성": list(DEFAULT_판매자특성)}
    for s in STAGES:
        out[f"primary_model_{s}"] = _DEFAULT_PRIMARY
        out[f"compare_model_{s}"] = _DEFAULT_COMPARE
        out[f"compare_enabled_{s}"] = True
        out[f"excluded_fields_{s}"] = list(DEFAULT_EXCLUDED_FIELDS)
    return out


DEFAULTS: dict = _build_defaults()


def load() -> dict:
    """settings.json 로드 + DEFAULTS 병합. 구 키(claude_model_*/gemini_model_*)는 무시."""
    if SETTINGS_PATH.exists():
        try:
            saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            # 신 키만 채택 (구 키는 사일런트 폐기)
            saved_clean = {k: v for k, v in saved.items() if k in DEFAULTS}
            return {**DEFAULTS, **saved_clean}
        except Exception:
            pass
    return dict(DEFAULTS)


def load_판매자특성() -> list[str]:
    """전역 판매자 특성 목록 반환."""
    cfg = load()
    val = cfg.get("판매자특성", [])
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    return []


def save(settings: dict) -> None:
    SETTINGS_PATH.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8"
    )


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
