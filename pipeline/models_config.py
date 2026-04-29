"""AI 모델 목록 단일 소스.

모델 폐기/추가 시 이 파일 또는 .env만 수정하면 모든 페이지에 반영됨.
.env에서 override 가능 → 코드 재배포 없이 실시간 갱신.

.env 키:
    CLAUDE_VP_MODELS=claude-sonnet-4-6,claude-opus-4-7,claude-haiku-4-5-20251001
    GEMINI_VP_MODELS=gemini-2.5-flash,gemini-2.5-pro
    MERGE_MODEL=claude-sonnet-4-6
    EXTRACT_MODEL=claude-sonnet-4-6
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _split_env(key: str, default: str) -> list[str]:
    raw = os.getenv(key, default)
    return [m.strip() for m in raw.split(",") if m.strip()]


# Vision Pass에서 사용 가능한 모델 (이미지별/일괄 실행 dropdown)
CLAUDE_VP_MODELS: list[str] = _split_env(
    "CLAUDE_VP_MODELS",
    "claude-sonnet-4-6,claude-opus-4-7,claude-haiku-4-5-20251001",
)
GEMINI_VP_MODELS: list[str] = _split_env(
    "GEMINI_VP_MODELS",
    "gemini-2.5-flash,gemini-2.5-pro",
)
ALL_VP_MODELS: list[str] = CLAUDE_VP_MODELS + GEMINI_VP_MODELS

# 합성/추출 LLM 기본 모델 (사용자가 UI에서 변경 가능)
DEFAULT_MERGE_MODEL: str = os.getenv("MERGE_MODEL", "claude-sonnet-4-6").strip()
DEFAULT_EXTRACT_MODEL: str = os.getenv("EXTRACT_MODEL", "claude-sonnet-4-6").strip()


def family_of(model: str) -> str:
    """모델명에서 family 판별."""
    return "gemini" if model.startswith("gemini") else "claude"
