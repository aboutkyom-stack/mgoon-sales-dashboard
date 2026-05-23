"""교차 LLM 린터.

본 호출 모델이 만든 출력을 다른 모델이 검수한다.
- Claude builder → Gemini reviewer
- Gemini builder → Claude reviewer

자가검수 편향(같은 모델이 자기 결과 자기가 검수하면 편향) 줄이기 +
미묘한 논리 결함·사실 비약 감지가 목적.

린터에 주는 system prompt = `_shared/data_contract.md` + 단계별 `qa_checklist.md`만.
강의 코어(core/examples/expressions)는 안 넣음 — 검수자에겐 "기준만" 주고
"창작 어휘"는 안 보여줌으로써 객관성 ↑.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .llm import generate_claude, generate_gemini

AGENTS_DIR = Path(__file__).parent.parent / "agents"

AGENT_SLUG = {
    "deficit_target":  "01_deficit_target",
    "positioning":     "02_positioning",
    "naming":          "03_naming",
    "detail_page":     "04_a_writing",       # 04 콘티 생성 (자동화 04 단계 본 작업)
    "detail_review":   "04_b_review",        # 04 검수 (별도 호출용)
    "image_direction": "04_1_image_direction",
    "channel":         "05_channel",
}


def _build_lint_system_prompt(agent: str) -> str:
    """린터용 system prompt. data_contract + qa_checklist만 합침."""
    parts: list[str] = []

    shared = AGENTS_DIR / "_shared" / "data_contract.md"
    if shared.exists():
        parts.append(f"=== _shared/data_contract.md ===\n{shared.read_text(encoding='utf-8')}")

    slug = AGENT_SLUG.get(agent)
    if slug:
        qa = AGENTS_DIR / slug / "qa_checklist.md"
        if qa.exists():
            parts.append(f"=== {slug}/qa_checklist.md ===\n{qa.read_text(encoding='utf-8')}")

    rules = "\n\n".join(parts) if parts else "(검수 기준 파일 없음)"

    return f"""당신은 자동화 판매 파이프라인의 외부 린터다.
다른 LLM이 작성한 출력을 아래 데이터 권위 규약과 체크리스트 기준으로 검수한다.
**자가 작성한 결과가 아니므로 편향 없이 객관적으로 평가하라.**

{rules}

[출력 형식 — 엄수]
첫 줄: 다음 중 하나
  - `[STATUS] PASS`           모든 항목 통과
  - `[STATUS] WARN:N`         약함·애매·개선 여지 N건 (위반은 아님)
  - `[STATUS] FAIL:N`         사실 비약·데이터 권위 위반·규약 명시 위반 N건

둘째 줄부터 — **STATUS와 무관하게 항상 출력** (검토 흔적 가시화):
  - 검수 기준 파일에 있는 모든 규칙ID(R-01, R-02 ... / D-01 ...)에 대해 각각 한 줄
  - 형식: `- [규칙ID] (PASS|WARN|FAIL) 한 줄 평가 (WARN/FAIL이면 인용: "...")`
  - PASS 항목도 "무엇을 어떻게 확인했는지" 한 줄 명시 (단순 "통과"만은 금지)
  - WARN/FAIL 인용은 검수 대상에서 그대로 발췌, 창작 금지

[판단 원칙]
- FAIL: data_contract 위반(가격·인증 권위 무시 등), 사실 비약, qa_checklist 명시 항목 위반
- WARN: 논리가 약함·결함 카테고리 중복·창의성 부족 등 개선 여지
- PASS: 위 둘 다 없음

가짜로 결함을 만들지 마라. 진짜 보이는 것만 지적하라.
검수 대상이 빈 텍스트면 `[STATUS] PASS\\n(빈 출력)`로 답하라.
"""


def _lint_one(agent: str, output_text: str, reviewer: str,
              claude_model: str | None = None,
              gemini_model: str | None = None) -> str:
    """한 출력을 한 reviewer로 린트. 결과 텍스트 반환."""
    if not output_text.strip():
        return "[STATUS] PASS\n(빈 출력 — 검수 대상 없음)"

    system_prompt = _build_lint_system_prompt(agent)
    user_input = f"[검수 대상 출력]\n{output_text}"

    if reviewer == "claude":
        return generate_claude(system_prompt, user_input, max_tokens=4096,
                               model=claude_model)
    if reviewer == "gemini":
        return generate_gemini(system_prompt, user_input, model=gemini_model)
    raise ValueError(f"unknown reviewer: {reviewer}")


def cross_lint_both(
    agent: str,
    claude_output: str,
    gemini_output: str,
    claude_model: str | None = None,
    gemini_model: str | None = None,
) -> dict[str, str]:
    """교차 린터 — builder 결과를 다른 family가 검수.

    Claude 출력은 Gemini가 검수, Gemini 출력은 Claude가 검수 (병렬).
    검수자 모델이 None이거나 builder 결과가 비어있으면 해당 키는 빈 문자열.

    반환: {"claude": "Gemini가 검수한 텍스트", "gemini": "Claude가 검수한 텍스트"}
    """
    results: dict[str, str] = {"claude": "", "gemini": ""}
    with ThreadPoolExecutor(max_workers=2) as ex:
        # Claude builder 결과는 Gemini가 검수 (gemini_model 필요)
        fut_c = (
            ex.submit(_lint_one, agent, claude_output, "gemini",
                      claude_model, gemini_model)
            if claude_output and gemini_model else None
        )
        # Gemini builder 결과는 Claude가 검수 (claude_model 필요)
        fut_g = (
            ex.submit(_lint_one, agent, gemini_output, "claude",
                      claude_model, gemini_model)
            if gemini_output and claude_model else None
        )
        if fut_c is not None:
            try:
                results["claude"] = fut_c.result()
            except Exception as e:
                results["claude"] = f"[STATUS] ERROR\n린터 호출 실패: {type(e).__name__}: {e}"
        if fut_g is not None:
            try:
                results["gemini"] = fut_g.result()
            except Exception as e:
                results["gemini"] = f"[STATUS] ERROR\n린터 호출 실패: {type(e).__name__}: {e}"
    return results


_STATUS_RE = re.compile(r"\[STATUS\]\s+(PASS|WARN|FAIL|ERROR)(?::(\d+))?")


def parse_lint_status(lint_text: str) -> tuple[str, int]:
    """첫 줄 [STATUS] 파싱. 반환: (status, count).

    status ∈ {PASS, WARN, FAIL, ERROR, UNKNOWN}.
    UNKNOWN은 첫 줄 형식이 [STATUS] ... 가 아닐 때 (린터가 형식을 어겼을 때).
    """
    if not lint_text:
        return ("UNKNOWN", 0)
    first_line = lint_text.split("\n", 1)[0].strip()
    m = _STATUS_RE.match(first_line)
    if not m:
        return ("UNKNOWN", 0)
    status = m.group(1)
    count = int(m.group(2)) if m.group(2) else 0
    return (status, count)
