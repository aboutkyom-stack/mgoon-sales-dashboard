"""자동 파이프라인 실행 — 01부터 05까지 논스톱 또는 멀티 타겟 일괄 실행.

수동 모드(`pages/2_pipeline.py`의 인라인 코드)와 별개로, 자동 모드 전용
단계 실행 함수를 모은다. 각 함수는 LLM 호출 + DB 저장까지 책임지고
결과 dict를 반환한다.

자동 모드 범위: 01, 02, 04, 05 (03 네이밍은 분기·DB 구조가 달라 제외)
"""
from __future__ import annotations

import json
import re
import sys

from .lint import cross_lint_both
from .llm import generate_both
from .supabase_read import update_엠군상태
from .loader import (
    build_user_input_01,
    build_user_input_02,
    build_user_input_04,
    build_user_input_04_1,
    build_user_input_05,
    load_agent_prompt,
)


def _extract_targets_json(text: str) -> dict | None:
    """01 결과 텍스트에서 ---TARGETS_JSON--- 블록을 파싱."""
    if not text:
        return None
    m = re.search(
        r"---TARGETS_JSON---\s*(.*?)\s*---END_TARGETS_JSON---",
        text,
        re.DOTALL,
    )
    if not m:
        return None
    raw = m.group(1).strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except Exception:
        return None


def _extract_sections_json(text: str) -> dict | None:
    """04-1 결과 텍스트에서 ---SECTIONS_JSON--- 블록을 파싱.

    반환: {"selection_method", "selection_reason", "design_system",
           "canvas_default", "sections": [...]} 또는 None.
    """
    if not text:
        return None
    m = re.search(
        r"---SECTIONS_JSON---\s*(.*?)\s*---END_SECTIONS_JSON---",
        text,
        re.DOTALL,
    )
    if not m:
        # 닫는 마커 없는 경우 — 시작 마커부터 끝까지 시도
        m = re.search(r"---SECTIONS_JSON---\s*(.*?)$", text, re.DOTALL)
    if not m:
        return None
    raw = m.group(1).strip()
    # 코드 펜스 다양한 형태 제거
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
        raw = re.sub(r"\n?\s*```\s*$", "", raw)
    raw = raw.strip()
    # 1차 시도: 직접 파싱
    try:
        return json.loads(raw)
    except Exception as e:
        print(f"[_extract_sections_json] 1차 파싱 실패: {type(e).__name__}: {e}", file=sys.stderr)
    # 2차 시도: 가장 바깥 중괄호 경계만 추출 (모델이 여분 텍스트 포함 시)
    brace_start = raw.find("{")
    brace_end = raw.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        try:
            return json.loads(raw[brace_start : brace_end + 1])
        except Exception as e2:
            print(f"[_extract_sections_json] 2차 파싱 실패: {type(e2).__name__}: {e2}", file=sys.stderr)
    return None


def _build_target_description(t: dict) -> str:
    """타겟 dict → 02/04/05에 넘길 사람이 읽기 쉬운 멀티라인 텍스트."""
    parts = []
    if t.get("character"):
        parts.append(f"직업/나이/상황: {t['character']}")
    if t.get("deficit"):
        parts.append(f"핵심 결핍: {t['deficit']}")
    if t.get("deficit_source"):
        parts.append(f"결핍 원천: {t['deficit_source']}")
    if t.get("benefit_type"):
        parts.append(f"구매편익 유형: {t['benefit_type']}")
    if t.get("involvement") not in (None, ""):
        parts.append(f"관여도: {t['involvement']}")
    if t.get("channel"):
        parts.append(f"주요 채널: {t['channel']}")
    if t.get("buyer_user_split"):
        parts.append(f"구매자/이용자 분리: {t['buyer_user_split']}")
    if t.get("wants_3tier"):
        parts.append(f"욕구깡패: {t['wants_3tier']}")
    if t.get("note"):
        parts.append(f"비고: {t['note']}")
    return "\n".join(parts)


def run_stage_01(
    spec: dict,
    storage,
    claude_model: str | None,
    gemini_model: str | None,
    lint_claude_model: str | None = None,
    lint_gemini_model: str | None = None,
) -> dict:
    """01 결핍·타겟 자동 실행.

    lint_*_model이 둘 다 None이면 린터 호출 자체를 생략 (비용 0).
    호출자가 settings.lint_enabled_for_stage 체크 후 인자 결정.

    Returns:
        {
            "run_id": int,
            "raw": {"claude": str, "gemini": str},
            "lint": {"claude": str, "gemini": str},
            "parsed_with_ids": {"claude": [target_dict, ...], "gemini": [...]},
        }
    """
    if spec.get("id"):
        try:
            update_엠군상태(spec["id"], "진행중")
        except Exception:
            pass

    system_prompt = load_agent_prompt("deficit_target")
    user_input = build_user_input_01(spec)
    raw = generate_both(
        system_prompt, user_input,
        claude_model=claude_model,
        gemini_model=gemini_model,
    )
    if lint_claude_model or lint_gemini_model:
        lint = cross_lint_both(
            "deficit_target",
            raw.get("claude", ""),
            raw.get("gemini", ""),
            claude_model=lint_claude_model,
            gemini_model=lint_gemini_model,
        )
    else:
        lint = {"claude": "", "gemini": ""}

    run_id = storage.create_run(spec, source_product_id=spec.get("id"))
    parsed_with_ids: dict[str, list[dict]] = {"claude": [], "gemini": []}

    for model in ("claude", "gemini"):
        text = raw.get(model) or ""
        parsed = _extract_targets_json(text)
        if parsed and parsed.get("targets"):
            tlist = parsed["targets"]
            rec_rank = parsed.get("recommended_rank")
            ids = storage.save_targets(
                run_id=run_id,
                targets=tlist,
                model=model,
                raw_output=text,
                recommended_rank=rec_rank,
            )
            enriched = []
            for t, db_id in zip(tlist, ids):
                t = dict(t)
                t["db_id"] = db_id
                t["is_recommended"] = (
                    rec_rank is not None and t.get("rank") == rec_rank
                )
                enriched.append(t)
            parsed_with_ids[model] = enriched
        elif text:
            storage.save_targets(
                run_id=run_id,
                targets=[{
                    "rank": 1,
                    "label": f"(파싱 실패) {model}",
                    "note": "JSON 블록 누락 또는 파싱 실패 — 원본_출력 컬럼 참고",
                }],
                model=model,
                raw_output=text,
                recommended_rank=None,
            )

    return {
        "run_id": run_id,
        "raw": raw,
        "lint": lint,
        "parsed_with_ids": parsed_with_ids,
    }


def run_stage_02(
    spec: dict,
    target: dict,
    basis: str,
    storage,
    target_db_id: int,
    run_id: int,
    claude_model: str | None,
    gemini_model: str | None,
    lint_claude_model: str | None = None,
    lint_gemini_model: str | None = None,
) -> dict:
    """02 포지셔닝 자동 실행.

    target_db_id를 selected로 마크 (run 단위에서 기존 selected는 해제).
    lint_*_model이 둘 다 None이면 린터 호출 생략.

    Returns:
        {"raw": {claude, gemini}, "lint": {claude, gemini}}
    """
    system_prompt = load_agent_prompt("positioning")
    target_dict = {
        "source_model": basis,
        "label": target.get("label") or "",
        "description": _build_target_description(target),
    }
    user_input = build_user_input_02(spec, target_dict)
    raw = generate_both(
        system_prompt, user_input,
        claude_model=claude_model,
        gemini_model=gemini_model,
    )
    if lint_claude_model or lint_gemini_model:
        lint = cross_lint_both(
            "positioning",
            raw.get("claude", ""),
            raw.get("gemini", ""),
            claude_model=lint_claude_model,
            gemini_model=lint_gemini_model,
        )
    else:
        lint = {"claude": "", "gemini": ""}

    storage.clear_selected_in_run(run_id)
    storage.mark_target_selected(target_db_id, True)
    for m in ("claude", "gemini"):
        storage.save_positioning(
            target_id=target_db_id,
            model=m,
            raw_output=raw.get(m, ""),
        )
    return {"raw": raw, "lint": lint}


def run_stage_04(
    spec: dict,
    target: dict,
    positioning_text: str,
    positioning_basis: str,
    storage,
    target_db_id: int,
    claude_model: str | None,
    gemini_model: str | None,
    lint_claude_model: str | None = None,
    lint_gemini_model: str | None = None,
) -> dict:
    """04 상세페이지 자동 실행. lint_*_model 둘 다 None이면 린터 생략."""
    system_prompt = load_agent_prompt("detail_page")
    target_dict = {
        "label": target.get("label") or "",
        "description": _build_target_description(target),
    }
    user_input = build_user_input_04(
        spec, target_dict, positioning_text, positioning_basis,
    )
    raw = generate_both(
        system_prompt, user_input,
        claude_model=claude_model,
        gemini_model=gemini_model,
    )
    if lint_claude_model or lint_gemini_model:
        lint = cross_lint_both(
            "detail_page",
            raw.get("claude", ""),
            raw.get("gemini", ""),
            claude_model=lint_claude_model,
            gemini_model=lint_gemini_model,
        )
    else:
        lint = {"claude": "", "gemini": ""}
    for m in ("claude", "gemini"):
        storage.save_상세페이지(
            target_id=target_db_id, model=m,
            raw_output=raw.get(m, ""),
        )
    return {"raw": raw, "lint": lint}


def run_stage_04_1(
    spec: dict,
    target: dict,
    positioning_text: str,
    positioning_basis: str,
    detail_text: str,
    detail_basis: str,
    storage,
    target_db_id: int,
    claude_model: str | None,
    gemini_model: str | None,
    lint_claude_model: str | None = None,
    lint_gemini_model: str | None = None,
) -> dict:
    """04-1 이미지 디렉션 자동 실행.

    04 콘티(detail_text)를 입력으로 받아 각 섹션을 이미지 1장 단위
    확정 디렉션으로 변환한다. 결과 JSON 블록(`---SECTIONS_JSON---`)을
    파싱해 섹션·디자인 시스템을 분리 저장한다.

    Returns:
        {
            "raw": {"claude": str, "gemini": str},
            "lint": {"claude": str, "gemini": str},
            "parsed": {
                "claude": {"sections": [...], "design_system": {...}, "selection_method": str} | None,
                "gemini": ...,
            },
        }
    """
    system_prompt = load_agent_prompt("image_direction")
    target_dict = {
        "label": target.get("label") or "",
        "description": _build_target_description(target),
    }
    user_input = build_user_input_04_1(
        spec, target_dict, positioning_text, detail_text,
        positioning_basis=positioning_basis,
        detail_basis=detail_basis,
    )
    raw = generate_both(
        system_prompt, user_input,
        claude_model=claude_model,
        gemini_model=gemini_model,
        max_tokens=16384,
    )
    if lint_claude_model or lint_gemini_model:
        lint = cross_lint_both(
            "image_direction",
            raw.get("claude", ""),
            raw.get("gemini", ""),
            claude_model=lint_claude_model,
            gemini_model=lint_gemini_model,
        )
    else:
        lint = {"claude": "", "gemini": ""}

    parsed: dict[str, dict | None] = {"claude": None, "gemini": None}
    for m in ("claude", "gemini"):
        text = raw.get(m, "") or ""
        sections_json = _extract_sections_json(text)
        sections = (sections_json or {}).get("sections")
        design_system = (sections_json or {}).get("design_system")
        selection_method = (sections_json or {}).get("selection_method")
        parsed[m] = sections_json
        # 파싱 실패해도 raw_output은 저장 (디버깅용)
        storage.save_이미지디렉션(
            target_id=target_db_id,
            model=m,
            raw_output=text,
            sections=sections if isinstance(sections, list) else None,
            design_system=design_system if isinstance(design_system, dict) else None,
            selection_method=selection_method if isinstance(selection_method, str) else None,
        )
    return {"raw": raw, "lint": lint, "parsed": parsed}


def run_stage_05(
    spec: dict,
    target: dict,
    positioning_text: str,
    positioning_basis: str,
    storage,
    target_db_id: int,
    claude_model: str | None,
    gemini_model: str | None,
    lint_claude_model: str | None = None,
    lint_gemini_model: str | None = None,
) -> dict:
    """05 채널·물길 자동 실행. lint_*_model 둘 다 None이면 린터 생략."""
    system_prompt = load_agent_prompt("channel")
    target_dict = {
        "label": target.get("label") or "",
        "description": _build_target_description(target),
    }
    user_input = build_user_input_05(
        spec, target_dict, positioning_text, positioning_basis,
    )
    raw = generate_both(
        system_prompt, user_input,
        claude_model=claude_model,
        gemini_model=gemini_model,
    )
    if lint_claude_model or lint_gemini_model:
        lint = cross_lint_both(
            "channel",
            raw.get("claude", ""),
            raw.get("gemini", ""),
            claude_model=lint_claude_model,
            gemini_model=lint_gemini_model,
        )
    else:
        lint = {"claude": "", "gemini": ""}
    for m in ("claude", "gemini"):
        storage.save_채널(
            target_id=target_db_id, model=m,
            raw_output=raw.get(m, ""),
        )

    if spec.get("id"):
        try:
            update_엠군상태(spec["id"], "완료")
        except Exception:
            pass

    return {"raw": raw, "lint": lint}
