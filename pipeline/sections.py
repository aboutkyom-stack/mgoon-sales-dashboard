"""마크다운 섹션 분리·교체 + 부분 재생성 헬퍼.

agents/0N/core.md 출력 형식 기준으로 섹션 단위 처리.
  - 02 포지셔닝: `■ N. ...` 마커
  - 04 상세페이지·05 채널: `[키워드]:` 마커

워크플로우:
  1) split_sections(text, marker_style)  → [(header, body), ...]
  2) UI에서 섹션 선택 + 피드백 입력
  3) regenerate_section(...)             → 새 섹션 텍스트 (헤더 포함)
  4) replace_section(...)                → 원본에 부분 교체된 전체 텍스트
"""
from __future__ import annotations

import re

from .llm import generate_claude, generate_gemini
from .loader import load_agent_prompt

# 02용 `■ N. ...` 마커 (앞에 # 0~3개 허용 — Claude는 ## ■, Gemini는 ■만 쓰는 등 차이 흡수)
SECTION_HEADER_DOT_RE = re.compile(
    r"^(#{0,3}\s*■\s*\d+\.\s*[^\n]+)$",
    re.MULTILINE,
)

# 04·05용 `[키워드]:` 마커 (콜론 + 부연 `(블로그 초기 전략 시)` 같은 줄 끝까지 잡음)
SECTION_HEADER_BRACKET_RE = re.compile(
    r"^(\[[^\]\n]+\][^\n]*)$",
    re.MULTILINE,
)


def split_sections(text: str, marker_style: str = "auto") -> list[tuple[str, str]]:
    """마크다운을 섹션 단위로 분리.

    marker_style:
      - "dot":     `■ N.` 마커만 매칭 (02 포지셔닝)
      - "bracket": `[키워드]:` 마커만 매칭 (04 상세페이지, 05 채널)
      - "auto":    두 정규식 매칭 카운트 비교 → 더 많은 쪽 선택.
                   동률·둘 다 0이면 dot 우선 (02 호환).

    반환: [(header_line, body), ...]
      - 첫 마커 이전에 텍스트가 있으면 ("(인트로)", body)로 포함
      - 마커가 하나도 없으면 [("(전체)", text)] 단일 항목 (파싱 실패)
    """
    if not text:
        return []
    if marker_style == "dot":
        regex = SECTION_HEADER_DOT_RE
    elif marker_style == "bracket":
        regex = SECTION_HEADER_BRACKET_RE
    else:  # auto
        dot_count = len(SECTION_HEADER_DOT_RE.findall(text))
        bracket_count = len(SECTION_HEADER_BRACKET_RE.findall(text))
        regex = (
            SECTION_HEADER_BRACKET_RE if bracket_count > dot_count
            else SECTION_HEADER_DOT_RE
        )
    matches = list(regex.finditer(text))
    if not matches:
        return [("(전체)", text.strip())]

    sections: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        intro = text[:matches[0].start()].strip()
        if intro:
            sections.append(("(인트로)", intro))

    for i, m in enumerate(matches):
        header = m.group(1).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        sections.append((header, body))

    return sections


def replace_section(full_text: str, section_index: int, new_section_text: str) -> str:
    """원본 텍스트의 N번째 섹션(split_sections 결과 인덱스)을 new_section_text로 교체.

    new_section_text는 헤더(■ N. ...)부터 시작하는 전체 섹션 텍스트.
    인트로/전체는 그대로 유지.
    """
    sections = split_sections(full_text)
    if not sections or section_index < 0 or section_index >= len(sections):
        return full_text

    header, _old_body = sections[section_index]
    if header in ("(전체)", "(인트로)"):
        # 인트로/전체를 부분 교체하는 건 의미 모호 — 그냥 무시
        return full_text

    # new_section_text를 한 섹션으로 다시 split해서 검증
    new_split = split_sections(new_section_text)
    if not new_split:
        return full_text
    # 첫 매칭 섹션의 (header, body) 사용
    new_header, new_body = next(
        ((h, b) for h, b in new_split if h not in ("(전체)", "(인트로)")),
        new_split[0],
    )

    # 헤더 모양으로 자동 분기:
    # - [라벨] 형식이면 첫 ']'까지의 라벨이 같지 않으면 원본 헤더 사용
    #   (부연 `(블로그 초기 전략 시)`이 LLM 출력에서 빠져도 라벨만 일치하면 그대로 채택)
    # - ■ N. 형식이면 헤더 자체가 다르면 원본 사용 (■ 3.인데 LLM이 ■ 1.로 답해도 원본 유지)
    if header.lstrip("#").strip().startswith("["):
        def _label(h: str) -> str:
            stripped = h.lstrip("#").strip()
            end = stripped.find("]")
            return stripped[:end + 1] if end >= 0 else stripped
        if _label(new_header) != _label(header):
            new_header = header
    else:
        if new_header != header:
            new_header = header

    sections[section_index] = (new_header, new_body)

    parts: list[str] = []
    for hdr, body in sections:
        if hdr in ("(전체)", "(인트로)"):
            parts.append(body)
        else:
            parts.append(f"{hdr}\n\n{body}")
    return "\n\n".join(parts).rstrip() + "\n"


def regenerate_section(
    agent: str,
    base_user_input: str,
    full_text: str,
    section_header: str,
    user_feedback: str,
    builder_model: str,
    model_id: str | None = None,
) -> str:
    """특정 섹션만 재생성. 새 섹션 텍스트(헤더 포함) 반환.

    매개변수
    --------
    agent: "positioning"·"detail_page"·"channel" 등 (load_agent_prompt 키)
    base_user_input: 원래 단계 호출 시 쓰던 user input (build_user_input_NN 결과)
    full_text: 이전 전체 출력 (섹션 머지 컨텍스트)
    section_header: 재생성할 섹션 헤더 (예: "■ 3. 전략: 두 개 까고 두 개 넣기")
    user_feedback: 사용자가 입력한 자연어 피드백
    builder_model: "claude" 또는 "gemini"
    model_id: cfg에서 가져온 구체 모델 ID (claude-sonnet-4-6 등)
    """
    system_prompt = load_agent_prompt(agent)

    user_input = f"""{base_user_input}

---

[이전 전체 출력]
{full_text}

[사용자 피드백]
{user_feedback}

[부분 재생성 지시]
- 위 이전 출력 전체를 참고하되, **다음 섹션만** 재작성하라:
  ▶ **{section_header}**
- 다른 섹션은 절대 출력하지 마라.
- 오직 위 섹션의 헤더 한 줄과 그 본문만 출력.
- 사용자 피드백을 충실히 반영하되, 단계의 핵심 사고 프레임워크와 출력 형식은 유지하라.
- 다른 섹션과의 일관성(타겟·CV·포지셔닝 흐름)도 유지하라.
- 코드 펜스(```), 추가 인사말 없이 바로 섹션 헤더로 시작하라.
- 헤더는 원본과 동일하게 유지하라 (예: ■ 3.이면 ■ 3. 그대로, [사은품 전략]:이면 [사은품 전략]: 그대로).
"""

    if builder_model == "claude":
        return generate_claude(system_prompt, user_input,
                               max_tokens=3000, model=model_id)
    if builder_model == "gemini":
        return generate_gemini(system_prompt, user_input, model=model_id)
    raise ValueError(f"unknown builder: {builder_model}")
