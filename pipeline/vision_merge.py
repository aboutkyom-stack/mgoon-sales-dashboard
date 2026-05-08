"""Vision Pass 결과 합성/추출 LLM 호출.

- compare_시각설명: 비포/애프터 시각설명 비교 → {일치, 충돌[]}
- extract_스펙:     시각설명 → 구조화된 스펙 JSON

두 함수 모두 LLM이 JSON을 반환하도록 프롬프트 설계.
JSON 파싱 실패 시 raw 응답을 함께 반환해 디버깅 가능.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .llm import generate_claude, generate_gemini
from .models_config import DEFAULT_EXTRACT_MODEL, DEFAULT_MERGE_MODEL, family_of
from .spec_schema import SPEC_FIELDS, build_extraction_schema_text, field_names

_PROMPT_DIR = Path(__file__).parent.parent / "agents" / "00_vision_pass"


def _load_prompt(name: str) -> str:
    return (_PROMPT_DIR / name).read_text(encoding="utf-8")


def _generate(system_prompt: str, user_input: str, model: str) -> str:
    if family_of(model) == "claude":
        return generate_claude(system_prompt, user_input, model=model)
    return generate_gemini(system_prompt, user_input, model=model)


def _parse_json(raw: str) -> dict | list | None:
    """LLM 응답에서 JSON 추출. 코드펜스/잡음 제거 후 파싱."""
    if not raw:
        return None
    txt = raw.strip()
    # 코드펜스 제거
    txt = re.sub(r"^```(?:json)?\s*", "", txt)
    txt = re.sub(r"\s*```$", "", txt)
    # 첫 { 또는 [ 부터 마지막 } 또는 ] 까지만
    m = re.search(r"[\{\[]", txt)
    if m:
        txt = txt[m.start():]
    txt = txt.rstrip().rstrip(",")
    # 마지막 } 또는 ]까지
    last = max(txt.rfind("}"), txt.rfind("]"))
    if last >= 0:
        txt = txt[:last + 1]
    try:
        return json.loads(txt)
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────
# 비포/애프터 비교
# ──────────────────────────────────────────────────────────────

def compare_시각설명(
    기존: str,
    신규: str | list[tuple[str, str]],
    model: str | None = None,
) -> dict:
    """기존 시각설명 vs 신규 시각설명(들) 비교.

    Args:
        기존: DB에 저장된 기존 시각설명. 빈 문자열이면 비교 없이 신규 반환.
        신규: 단일 텍스트(str) 또는 [(라벨, 텍스트), ...] 리스트.
              리스트면 3-way 이상 비교 (예: [("메인", ...), ("서브", ...)]).
        model: 비교에 사용할 LLM 모델. 미지정 시 DEFAULT_MERGE_MODEL.

    Returns:
        {"일치": str, "충돌": [{"항목": str, "기존": str, "신규": str, "메모": str}, ...]}
        파싱 실패 시 {"일치": "", "충돌": [], "_error": "...", "_raw": "..."}.
    """
    model = model or DEFAULT_MERGE_MODEL
    system_prompt = _load_prompt("merge.md")

    # 신규를 통일된 형식으로
    if isinstance(신규, str):
        신규_부분 = f"[신규]\n{신규}"
    else:
        신규_부분 = "\n\n".join(f"[신규: {label}]\n{text}" for label, text in 신규)

    user_input = (
        f"[기존]\n{기존 or '(없음)'}\n\n"
        f"{신규_부분}\n\n"
        "위 텍스트들을 비교해 일치 항목과 충돌 항목을 JSON으로 반환하세요."
    )

    raw = _generate(system_prompt, user_input, model)
    parsed = _parse_json(raw)
    if not isinstance(parsed, dict):
        return {"일치": "", "충돌": [], "_error": "JSON parse failed", "_raw": raw}
    parsed.setdefault("일치", "")
    parsed.setdefault("충돌", [])
    if not isinstance(parsed["충돌"], list):
        parsed["충돌"] = []
    return parsed


# ──────────────────────────────────────────────────────────────
# 스펙 추출
# ──────────────────────────────────────────────────────────────

# bullet 기준은 extract_spec.md에 통합됨 (별도 인라인 가이드 제거)


def extract_스펙(시각설명: str, model: str | None = None) -> dict:
    """시각설명에서 SPEC_FIELDS + 기타 제품 특징(bullet)을 한 번의 호출로 함께 추출.

    spec_schema.SPEC_FIELDS 정의 기반의 구조화 필드 + 그 외 판매 소구 포인트를
    `_특징_bullet` 키로 함께 반환한다. 추출 못한 필드는 None.

    Returns:
        {필드명: 값 or None, ..., "_특징_bullet": ["...", ...]}.
        파싱 실패 시 {"_error": "...", "_raw": "..."}.
    """
    if not 시각설명 or not 시각설명.strip():
        out: dict = {f["name"]: None for f in SPEC_FIELDS}
        out["_특징_bullet"] = []
        return out

    model = model or DEFAULT_EXTRACT_MODEL
    template = _load_prompt("extract_spec.md")
    system_prompt = template.replace("{SPEC_FIELDS_GUIDE}", build_extraction_schema_text())

    user_input = (
        f"[시각설명]\n{시각설명}\n\n"
        "위에서 스펙 필드와 `_특징_bullet`을 함께 JSON으로 반환하세요."
    )

    raw = _generate(system_prompt, user_input, model)
    parsed = _parse_json(raw)
    if not isinstance(parsed, dict):
        return {"_error": "JSON parse failed", "_raw": raw}

    # 정의된 필드만 필터 + 누락 필드는 None
    result: dict = {}
    for f in SPEC_FIELDS:
        v = parsed.get(f["name"])
        # number 타입은 숫자 강제
        if f["type"] == "number" and v is not None:
            try:
                v = float(v) if "." in str(v) else int(v)
            except Exception:
                v = None
        # 빈 문자열은 None으로
        if isinstance(v, str) and not v.strip():
            v = None
        result[f["name"]] = v

    # bullet 배열 정규화
    bullets = parsed.get("_특징_bullet")
    if isinstance(bullets, list):
        result["_특징_bullet"] = [str(x).strip() for x in bullets if str(x).strip()]
    else:
        result["_특징_bullet"] = []

    return result


# 외부에서 필드 이름만 필요한 경우용 re-export
__all__ = ["compare_시각설명", "extract_스펙", "field_names"]
