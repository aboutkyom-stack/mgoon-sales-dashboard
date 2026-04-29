"""파이프라인 모델 설정 관리. settings.json에 영속 저장."""
from __future__ import annotations

import json
from pathlib import Path

SETTINGS_PATH = Path(__file__).parent.parent / "settings.json"

CLAUDE_MODELS = [
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-7",
]
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
]

DEFAULTS: dict[str, str] = {
    "claude_model_00": "claude-sonnet-4-6",   # Vision Pass
    "claude_model_01": "claude-sonnet-4-6",
    "claude_model_02": "claude-sonnet-4-6",
    "gemini_model_00": "gemini-2.5-flash",    # Vision Pass
    "gemini_model_01": "gemini-2.5-flash",
    "gemini_model_02": "gemini-2.5-flash",
}


def load() -> dict[str, str]:
    if SETTINGS_PATH.exists():
        try:
            saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            return {**DEFAULTS, **saved}
        except Exception:
            pass
    return dict(DEFAULTS)


def save(settings: dict[str, str]) -> None:
    SETTINGS_PATH.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8"
    )
