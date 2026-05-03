"""agents/0N_*/*.md 로더 + 프롬프트 조립.

각 에이전트 폴더에 존재하는 MD를 정해진 순서로 합쳐 시스템 프롬프트 생성.
- 01/02: core + examples + qa_checklist (3종)
- 03/04/05: core + examples + expressions + qa_checklist (4종)
"""
from __future__ import annotations

import json
from pathlib import Path

AGENTS_DIR = Path(__file__).parent.parent / "agents"

AGENT_KEYS = {
    "vision_pass":    "00_vision_pass",
    "deficit_target": "01_deficit_target",
    "positioning":    "02_positioning",
    "naming":         "03_naming",
    "detail_page":    "04_detail_page",
    "channel":        "05_channel",
}

# 합치기 순서. 폴더에 존재하는 파일만 골라서 합친다.
PROMPT_PART_ORDER = ("core.md", "examples.md", "expressions.md", "qa_checklist.md")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_agent_prompt(agent: str) -> str:
    """agents/{slug}/ 안의 표준 MD들을 PROMPT_PART_ORDER 순서로 합쳐 반환.

    존재하지 않는 파일은 건너뛴다 (02는 expressions.md 없음).
    `_shared/data_contract.md`가 존재하면 모든 단계의 맨 앞에 prepend
    (가격 권위·시각설명 처리 등 단계 공통 데이터 규약).
    """
    slug = AGENT_KEYS.get(agent)
    if not slug:
        raise ValueError(f"unknown agent: {agent}")

    chunks: list[str] = []

    shared_contract = AGENTS_DIR / "_shared" / "data_contract.md"
    if shared_contract.exists():
        chunks.append(f"=== _shared/data_contract.md ===\n{_read(shared_contract)}")

    base = AGENTS_DIR / slug
    for fname in PROMPT_PART_ORDER:
        path = base / fname
        if not path.exists():
            continue
        prefix = ("\n\n" if chunks else "") + f"=== {slug}/{fname} ===\n"
        chunks.append(prefix + _read(path))
    if not chunks:
        raise FileNotFoundError(f"no prompt MD found in {base}")
    return "".join(chunks)


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
  구매편익(기능/경험/상징), 관여도(1~10), 주요 채널(구체 커뮤니티/카페 이름까지), 비고.
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


def build_user_input_04(product: dict, target: dict, positioning_text: str,
                        positioning_basis: str = "") -> str:
    """04_detail_page용 유저 프롬프트.

    입력: 제품 + 01 선택 타겟 + 02 포지셔닝 결과(사용자가 고른 basis 모델 1개).
    """
    product_block = json.dumps(product, ensure_ascii=False, indent=2)
    target_block = json.dumps(target, ensure_ascii=False, indent=2)
    basis_label = f" (기준: {positioning_basis})" if positioning_basis else ""
    return f"""다음 타겟·포지셔닝을 바탕으로 상세페이지 콘티를 작성하라.

[제품 정보]
{product_block}

[01에서 확정된 타겟]
{target_block}

[02 포지셔닝 결과{basis_label}]
{positioning_text}

[지시]
- core.md 출력 형식을 엄수하라 (선택 방식 + 콘티 표 + 사은품 전략 + 디자인 주의사항).
- 5가지 설득 방식 중 이 제품·타겟에 가장 적합한 주 방식 1개를 선택하고 이유를 한 줄로 명시하라.
- 오프닝(섹션 1) 카피는 "스킵존" 금지. 결핍 직격 카피로 바로 쓸 수 있는 문장이어야 한다.
- 비판한 것은 반드시 즉각 해소하라 (개연성 법칙).
- 후기는 3개 이내, 핵심 결핍 해소 후기로 한정하라.
- 화자는 "저" 또는 "저희" 중 하나로 일관되게 가라.
- 02 포지셔닝의 CV·오프닝 초안·가치더하기를 콘티에 자연스럽게 녹여라.
- qa_checklist.md 규칙을 위반하지 마라."""


def build_user_input_03(
    product: dict,
    target: dict,
    positioning_text: str,
    positioning_basis: str = "",
    detail_text: str = "",
    detail_basis: str = "",
    channel_text: str = "",
    channel_basis: str = "",
    naming_type: str = "제품명",
) -> str:
    """03_naming용 유저 프롬프트.

    네이밍은 제품·타겟·02·04·05 결과를 종합해 호출되는 별도 단계.
    04/05 결과는 옵션(빈 문자열이면 미포함). 02는 필수.

    naming_type:
      - "제품명": 이 제품 하나의 고유 이름. 상표권 등록 대상.
      - "브랜드명": 회사·라인의 우산 이름. 여러 제품을 묶는 상위 정체성.
    각 분류는 사고 결이 달라 한 번 호출에 한 분류만 깊이 있게 다룬다.
    """
    product_block = json.dumps(product, ensure_ascii=False, indent=2)
    target_block = json.dumps(target, ensure_ascii=False, indent=2)
    pos_label = f" (기준: {positioning_basis})" if positioning_basis else ""

    sections = [
        f"이번 호출의 분류는 **{naming_type}**이다. 이 분류만 깊이 있게 다루고,",
        "다른 분류(블로그 제목·스마트스토어 상품명 등)의 후보는 출력하지 말 것.",
        "",
        "[제품 정보]",
        product_block,
        "",
        "[01에서 확정된 타겟]",
        target_block,
        "",
        f"[02 포지셔닝 결과{pos_label}]",
        positioning_text,
    ]
    if detail_text.strip():
        det_label = f" (기준: {detail_basis})" if detail_basis else ""
        sections.extend([
            "",
            f"[04 상세페이지 콘티{det_label}]",
            detail_text,
        ])
    if channel_text.strip():
        ch_label = f" (기준: {channel_basis})" if channel_basis else ""
        sections.extend([
            "",
            f"[05 채널·물길 전략{ch_label}]",
            channel_text,
        ])

    # 공통 지시
    common = [
        "",
        "[공통 지시]",
        "- core.md 출력 형식을 엄수하되, 분류 칸은 위에서 지정한 단일 분류로 고정하라.",
        "- 후보는 5개 이상 제시하고, 서로 구분되는 전략(위치·부위형 / CV 직결형 / 타겟 지목형 / 가치 더하기형 등)으로 다양화하라.",
        "- 신규 진입 제품은 무조건 유형 2(포지셔닝 중심). 유형 1(브랜드 파워 의존)은 금지.",
        "- 후보의 '타겟 언어 반영' 컬럼은 02 포지셔닝의 CV·오프닝 카피, (있다면) 05 채널의 허브·세부 키워드를 근거로만 채워라. 임의 단어 금지.",
        "- qa_checklist.md 규칙을 위반하지 마라.",
    ]
    sections.extend(common)

    # 분류별 강조
    if naming_type == "제품명":
        sections.extend([
            "",
            "[제품명 추가 지시]",
            "- 목표는 **상표권 등록 가능한 단일 단어 또는 짧은 합성어/신조어**다 (키미테, 하나로, 탑블로, 돼지코팩, 가그린 패턴).",
            "- 검색 SEO형 긴 문장(예: '뒤집혀도 달리는 어린이 RC카 양면주행 360도회전…')은 절대 금지. 그건 오픈마켓 상품명·블로그 제목 영역이다.",
            "- 발음 용이성·기억 용이성·연상 명확성을 모든 후보에서 검토하라.",
            "- 시리즈 확장 가능 구조면 반드시 명시하라 (눈엔 → 무릎엔 → 두피열엔 패턴).",
            "- 출력 마지막에 **[사용자 직접 검증 항목]** 섹션을 추가하라:",
            "    1) KIPRIS(키프리스) 상표 검색 — 동일·유사 상표 등록 여부 확인",
            "    2) 네이버 자동완성·연관검색어 — 후보가 이미 다른 의미로 통용되는지 확인",
            "    3) 도메인(.com/.kr) 및 SNS 핸들(인스타·유튜브) 가용성",
            "    4) 외국어 의미 충돌 점검 (의도치 않은 부정적 의미 가능성)",
        ])
    elif naming_type == "브랜드명":
        sections.extend([
            "",
            "[브랜드명 추가 지시]",
            "- 목표는 **여러 제품을 통합할 우산 정체성**이다. 단일 제품 카테고리에 종속되지 않는 확장성을 가져야 한다 (다이슨, 무신사, 배달의민족, 오뚜기 패턴).",
            "- 후보는 카테고리 의존성을 낮추되, 회사가 추구하는 가치·태도·세계관이 드러나야 한다.",
            "- 현재 제품(스턴트카 RC 등)에만 잘 맞는 이름이 아니라, **앞으로 출시할 제품 라인업에도 자연스럽게 적용 가능한 이름**이어야 한다.",
            "- 발음 용이성·기억 용이성·국제 표기 가능성(영문 표기)을 모든 후보에서 검토하라.",
            "- 출력 마지막에 **[사용자 직접 검증 항목]** 섹션을 추가하라:",
            "    1) KIPRIS(키프리스) 상표 검색 — 회사·서비스명 등록 여부",
            "    2) 사업자등록증·법인명 사용 가능성 (한글·영문 표기 모두)",
            "    3) 도메인 및 SNS 핸들 가용성",
            "    4) 외국어 의미 충돌 점검",
            "    5) 추후 출시 가능 제품 카테고리 3~5개 가정 → 각 카테고리에서 이 브랜드명이 자연스러운지 시뮬레이션",
        ])
    return "\n".join(sections)


def build_user_input_05(product: dict, target: dict, positioning_text: str,
                        positioning_basis: str = "") -> str:
    """05_channel용 유저 프롬프트.

    입력: 제품 + 01 선택 타겟 + 02 포지셔닝 결과(basis 1개).
    """
    product_block = json.dumps(product, ensure_ascii=False, indent=2)
    target_block = json.dumps(target, ensure_ascii=False, indent=2)
    basis_label = f" (기준: {positioning_basis})" if positioning_basis else ""
    return f"""다음 타겟·포지셔닝을 바탕으로 채널·물길 전략을 수립하라.

[제품 정보]
{product_block}

[01에서 확정된 타겟]
{target_block}

[02 포지셔닝 결과{basis_label}]
{positioning_text}

[지시]
- core.md 출력 형식을 엄수하라 (추천 채널 순위 표 + 허브 키워드 + 채널별 세부 전략 + 지역 키워드 + 대체재 힌트).
- 채널 순위는 이 타겟의 접촉 지점·관여도·주요 채널을 근거로 정하라.
- 허브 키워드는 의심받지 않는 정보성 + 독식 가능성을 갖춘 후보로 제시하라.
- 채널별 세부 전략은 "홍보합니다"식 문구 금지, 타겟의 욕구·결핍에 닿는 접근으로 써라.
- 지역 키워드는 검색량과 경쟁 강도를 함께 가늠해서 3~5개 제시하라.
- 대체재 전략은 적용 가능할 때만 제시하라 (강제 X).
- qa_checklist.md 규칙을 위반하지 마라."""
