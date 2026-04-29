"""agents/0N_*/*.md 로더 + 프롬프트 조립.

01은 core + examples + qa_checklist 3개, 02도 동일 3개.
로드한 MD를 하나의 시스템 프롬프트로 합쳐서 반환.
"""
from __future__ import annotations

import json
from pathlib import Path

AGENTS_DIR = Path(__file__).parent.parent / "agents"

AGENT_KEYS = {
    "vision_pass":    "00_vision_pass",
    "deficit_target": "01_deficit_target",
    "positioning":    "02_positioning",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_agent_prompt(agent: str) -> str:
    """agents/{slug}/{core,examples,qa_checklist}.md → 합친 시스템 프롬프트."""
    slug = AGENT_KEYS.get(agent)
    if not slug:
        raise ValueError(f"unknown agent: {agent}")
    base = AGENTS_DIR / slug
    parts = [
        f"=== {slug}/core.md ===\n" + _read(base / "core.md"),
        f"\n\n=== {slug}/examples.md ===\n" + _read(base / "examples.md"),
        f"\n\n=== {slug}/qa_checklist.md ===\n" + _read(base / "qa_checklist.md"),
    ]
    return "".join(parts)


def load_vision_prompt(engine: str = "claude") -> str:
    """Vision Pass 시스템 프롬프트.

    engine에 맞는 core_{engine}.md를 우선 로드.
    없으면 공용 core.md로 fallback.
    """
    base = AGENTS_DIR / "00_vision_pass"
    specific = base / f"core_{engine}.md"
    if specific.exists():
        return _read(specific)
    return _read(base / "core.md")


def build_vision_input(product: dict) -> str:
    """Vision Pass 유저 텍스트. 이미지는 llm.py에서 별도 전달."""
    spec = {
        k: v for k, v in product.items()
        if k in ["제품명", "카테고리", "서브카테고리", "모델명",
                 "재질", "색상", "구성품", "특징", "키워드"]
        and v
    }
    return f"""다음 제품 이미지를 분석하여 core.md 형식에 맞게 시각설명을 작성하라.

[제품명] {product.get('제품명', '(미입력)')}

[텍스트 스펙 참고 — 이미 알고 있는 정보이므로 반복하지 말 것]
{json.dumps(spec, ensure_ascii=False, indent=2)}"""


def build_user_input_01(product: dict) -> str:
    """01_deficit_target용 유저 프롬프트. 제품 스펙을 MD에 정의된 출력 형식으로 요청."""
    product_block = json.dumps(product, ensure_ascii=False, indent=2)
    return f"""다음 제품에 대해 결핍·타겟 분석을 수행하라.

[제품 정보]
{product_block}

[지시]
- 위 시스템 프롬프트(core.md)에 정의된 출력 형식을 엄수하라.
- 타겟 후보는 3개 이상 뽑되, 각 타겟이 서로 구분되는 결핍 각도여야 한다.
- 각 타겟에 대해: 직업+나이+상황, 핵심 결핍 한 줄, 결핍 원천(부족/불편/불안/욕망),
  구매편익(기능/경험/상징), 간호도(0~10), 주요 채널(구체 커뮤니티/카페 이름까지), 비고.
- 추천 타겟 1개를 뽑고 그 타겟의 욕구깡패 3차 욕구까지 기술하라.
- 등가교환 경고, 이상한 대안 힌트, 제로마케팅 적용 가능성도 마지막에 포함.
- qa_checklist.md 규칙을 위반하지 마라."""


def build_user_input_02(product: dict, target: dict) -> str:
    """02_positioning용 유저 프롬프트. 01에서 선택된 타겟에 대한 포지셔닝 플랜."""
    product_block = json.dumps(product, ensure_ascii=False, indent=2)
    target_block = json.dumps(target, ensure_ascii=False, indent=2)
    return f"""다음 타겟에 대한 포지셔닝 플랜을 수립하라.

[제품 정보]
{product_block}

[01에서 확정된 타겟]
{target_block}

[지시]
- core.md 출력 형식(■1~6)을 엄수하라.
- 구매 CV는 판매자 시각이 아닌 타겟의 시각으로 뽑아라.
- 포지셔닝 맵의 두 축은 서로 구분되는 개념이어야 한다.
- "두 개 까고 두 개 넣기"는 실제 경쟁사·경쟁 유형을 특정해서 구체적으로 써라.
- 상세페이지 오프닝 초안은 카피로 바로 쓸 수 있는 문장이어야 한다.
- 가치더하기는 억지스러운 모듈화·알파벳 남용 금지.
- qa_checklist.md 규칙을 위반하지 마라."""
