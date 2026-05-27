"""agents + _공통 두뇌 통합 로더 + 프롬프트 조립.

각 에이전트 폴더에 존재하는 MD를 정해진 순서로 합쳐 시스템 프롬프트 생성.
- 사고 파일(core·examples·expressions)은 `_공통 두뇌/{slug}/`에서 로드 (대화형과 공유)
- 인터페이스 파일(qa_checklist)은 `자동화형/agents/{slug}/`에서 로드 (자동화 전용)
- `_shared/data_contract.md`는 자동화형 agents/_shared 그대로 (자동화 전용 권위 규약)
"""
from __future__ import annotations

import json
from pathlib import Path

from .settings import excluded_fields_for_stage

AGENTS_DIR = Path(__file__).parent.parent / "agents"
BRAIN_DIR = Path(__file__).parent.parent.parent / "_공통 두뇌"

AGENT_KEYS = {
    "vision_pass":     "00_vision_pass",
    "deficit_target":  "01_deficit_target",
    "positioning":     "02_positioning",
    "naming":          "03_naming",
    "detail_page":     "04_a_writing",       # 04 콘티 생성 (자동화 04 단계 본 작업)
    "detail_review":   "04_b_review",        # 04 검수 (별도 호출용, 04_a 결과 검수)
    "image_direction": "04_1_image_direction",
    "channel":         "05_channel",
}

# 합치기 순서. 폴더에 존재하는 파일만 골라서 합친다.
PROMPT_PART_ORDER = ("core.md", "examples.md", "expressions.md", "qa_checklist.md")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _filter_product(product: dict, stage: str, cfg: dict | None = None) -> dict:
    """settings에서 해당 단계의 excluded_fields를 읽어 product dict에서 제거한 복사본 반환."""
    excluded = set(excluded_fields_for_stage(stage, cfg))
    if not excluded:
        return product
    return {k: v for k, v in product.items() if k not in excluded}


def load_agent_prompt(agent: str) -> str:
    """`_공통 두뇌/{slug}/`(사고) + `agents/{slug}/`(인터페이스)의 표준 MD들을
    PROMPT_PART_ORDER 순서로 합쳐 반환.

    - 사고 파일(core·examples·expressions): `_공통 두뇌/{slug}/`에서 로드 (대화형과 공유)
    - 인터페이스 파일(qa_checklist): `자동화형/agents/{slug}/`에서 로드 (자동화 전용)
    - 존재하지 않는 파일은 건너뛴다 (02는 expressions.md 없음).
    - `_shared/data_contract.md`(자동화형 agents/_shared)가 존재하면 모든 단계 맨 앞에 prepend.
    """
    slug = AGENT_KEYS.get(agent)
    if not slug:
        raise ValueError(f"unknown agent: {agent}")

    chunks: list[str] = []

    shared_contract = AGENTS_DIR / "_shared" / "data_contract.md"
    if shared_contract.exists():
        chunks.append(f"=== agents/_shared/data_contract.md ===\n{_read(shared_contract)}")

    brain_base = BRAIN_DIR / slug
    auto_base = AGENTS_DIR / slug
    for fname in PROMPT_PART_ORDER:
        if fname == "qa_checklist.md":
            path = auto_base / fname
            label = f"agents/{slug}/{fname}"
        else:
            path = brain_base / fname
            label = f"_공통 두뇌/{slug}/{fname}"
        if not path.exists():
            continue
        prefix = ("\n\n" if chunks else "") + f"=== {label} ===\n"
        chunks.append(prefix + _read(path))
    if not chunks:
        raise FileNotFoundError(f"no prompt MD found in {brain_base} or {auto_base}")
    return "".join(chunks)


def load_vision_prompt(engine: str = "claude") -> str:
    """Vision Pass 시스템 프롬프트.

    엔진별 분기 파일(core_{engine}.md)이 있으면 우선 사용.
    공용 core.md는 `_공통 두뇌/00_vision_pass/`에서 로드 (대화형과 공유).
    엔진별 분기 파일도 일단 `_공통 두뇌` → `agents` 순으로 탐색.
    """
    for base in (BRAIN_DIR / "00_vision_pass", AGENTS_DIR / "00_vision_pass"):
        specific = base / f"core_{engine}.md"
        if specific.exists():
            return _read(specific)
    return _read(BRAIN_DIR / "00_vision_pass" / "core.md")


def build_vision_input(product: dict, cfg: dict | None = None) -> str:
    """Vision Pass 유저 텍스트. 이미지는 llm.py에서 별도 전달."""
    product = _filter_product(product, "00", cfg)
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


def load_instruction(agent: str, variant: str | None = None) -> str:
    """단계별 user_input 템플릿(instruction.md) 로드.

    - agent: AGENT_KEYS의 키 (deficit_target/positioning/detail_page/channel/naming)
    - variant: 03_naming은 "제품명"|"브랜드명"으로 분기 (instruction_{variant}.md)
    """
    slug = AGENT_KEYS.get(agent)
    if not slug:
        raise ValueError(f"unknown agent: {agent}")
    base = AGENTS_DIR / slug
    if variant:
        path = base / f"instruction_{variant}.md"
    else:
        path = base / "instruction.md"
    if not path.exists():
        raise FileNotFoundError(f"instruction not found: {path}")
    return _read(path)


def save_instruction(agent: str, content: str, variant: str | None = None) -> None:
    """instruction.md 저장 (settings 페이지에서 편집한 내용 영속화)."""
    slug = AGENT_KEYS.get(agent)
    if not slug:
        raise ValueError(f"unknown agent: {agent}")
    base = AGENTS_DIR / slug
    if variant:
        path = base / f"instruction_{variant}.md"
    else:
        path = base / "instruction.md"
    path.write_text(content, encoding="utf-8")


def _apply_with_fallback(template: str, sections: list[tuple[str, str, str]]) -> str:
    """instruction.md 템플릿에 placeholder를 치환하되, 없으면 끝에 섹션으로 추가.

    sections: [(placeholder_key, fallback_title, value), ...]
      - placeholder_key: 중괄호 빼고 (예: 'product')
      - fallback_title: placeholder 부재 시 추가할 섹션 제목 (예: '[제품 정보]'). 빈 문자면 fallback 안 함 (label류)
      - value: 치환·삽입할 값

    settings UI에서 사용자가 placeholder를 박은 경우 그쪽이 우선.
    placeholder 안 박힌 경우(자동화 운영 안정성)에도 동작하도록 끝에 명시적 prepend.
    """
    out = template
    appendix: list[str] = []
    for key, title, value in sections:
        ph = "{" + key + "}"
        if ph in out:
            out = out.replace(ph, value)
        elif title and value:
            appendix.append(f"{title}\n{value}")
    if appendix:
        out = out.rstrip() + "\n\n" + "\n\n".join(appendix)
    return out


def build_user_input_01(product: dict, cfg: dict | None = None) -> str:
    """01_deficit_target용 유저 프롬프트. 정적 지시문은 instruction.md에서 로드."""
    product_block = json.dumps(_filter_product(product, "01", cfg), ensure_ascii=False, indent=2)
    template = load_instruction("deficit_target")
    return _apply_with_fallback(template, [
        ("product", "[제품 정보]", product_block),
    ])


def build_user_input_02(product: dict, target: dict, cfg: dict | None = None) -> str:
    """02_positioning용 유저 프롬프트. 01에서 선택된 타겟에 대한 포지셔닝 플랜."""
    product_block = json.dumps(_filter_product(product, "02", cfg), ensure_ascii=False, indent=2)
    target_block = json.dumps(target, ensure_ascii=False, indent=2)
    template = load_instruction("positioning")
    return _apply_with_fallback(template, [
        ("product", "[제품 정보]", product_block),
        ("target", "[01에서 확정된 타겟]", target_block),
    ])


def build_user_input_04(product: dict, target: dict, positioning_text: str,
                        positioning_basis: str = "", cfg: dict | None = None) -> str:
    """04_detail_page용 유저 프롬프트.

    입력: 제품 + 01 선택 타겟 + 02 포지셔닝 결과(사용자가 고른 basis 모델 1개).
    """
    product_block = json.dumps(_filter_product(product, "04", cfg), ensure_ascii=False, indent=2)
    target_block = json.dumps(target, ensure_ascii=False, indent=2)
    basis_label = f" (기준: {positioning_basis})" if positioning_basis else ""
    template = load_instruction("detail_page")
    return _apply_with_fallback(template, [
        ("product", "[제품 정보]", product_block),
        ("target", "[01에서 확정된 타겟]", target_block),
        ("positioning_basis_label", "", basis_label),  # label류 — fallback 안 함
        ("positioning", f"[02 포지셔닝 결과{basis_label}]", positioning_text),
    ])


def build_user_input_04_b(
    product: dict,
    target: dict,
    positioning_text: str,
    detail_text: str,
    positioning_basis: str = "",
    detail_basis: str = "",
    cfg: dict | None = None,
) -> str:
    """04_b_review용 유저 프롬프트.

    입력: 제품 + 01 선택 타겟 + 02 포지셔닝(basis 1개) + 04_a 콘티(basis 1개, 검수 대상).
    04_a가 뱉은 콘티를 풀세트 + ENGINE_PLAN 기준으로 검수하고 다듬은 콘티를 반환한다.
    """
    product_block = json.dumps(_filter_product(product, "04", cfg), ensure_ascii=False, indent=2)
    target_block = json.dumps(target, ensure_ascii=False, indent=2)
    pos_label = f" (기준: {positioning_basis})" if positioning_basis else ""
    det_label = f" (기준: {detail_basis})" if detail_basis else ""
    template = load_instruction("detail_review")
    return _apply_with_fallback(template, [
        ("product", "[제품 정보]", product_block),
        ("target", "[01에서 확정된 타겟]", target_block),
        ("positioning_basis_label", "", pos_label),
        ("positioning", f"[02 포지셔닝 결과{pos_label}]", positioning_text),
        ("detail_basis_label", "", det_label),
        ("detail", f"[04_a 상세페이지 콘티 (검수 대상){det_label}]", detail_text),
    ])


def build_user_input_04_1(
    product: dict,
    target: dict,
    positioning_text: str,
    detail_text: str,
    positioning_basis: str = "",
    detail_basis: str = "",
    cfg: dict | None = None,
) -> str:
    """04_1_image_direction용 유저 프롬프트.

    입력: 제품 + 01 선택 타겟 + 02 포지셔닝(basis 1개) + 04 상세페이지 콘티(basis 1개).
    04 콘티의 각 섹션을 이미지 1장 단위 확정 디렉션으로 변환한다.
    """
    product_block = json.dumps(_filter_product(product, "04_1", cfg), ensure_ascii=False, indent=2)
    target_block = json.dumps(target, ensure_ascii=False, indent=2)
    pos_label = f" (기준: {positioning_basis})" if positioning_basis else ""
    det_label = f" (기준: {detail_basis})" if detail_basis else ""
    template = load_instruction("image_direction")
    return _apply_with_fallback(template, [
        ("product", "[제품 정보]", product_block),
        ("target", "[01에서 확정된 타겟]", target_block),
        ("positioning_basis_label", "", pos_label),
        ("positioning", f"[02 포지셔닝 결과{pos_label}]", positioning_text),
        ("detail_basis_label", "", det_label),
        ("detail", f"[04 상세페이지 콘티{det_label}]", detail_text),
    ])


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
    cfg: dict | None = None,
) -> str:
    """03_naming용 유저 프롬프트.

    네이밍은 제품·타겟·02·04·05 결과를 종합해 호출되는 별도 단계.
    04/05 결과는 옵션(빈 문자열이면 미포함). 02는 필수.

    naming_type:
      - "제품명": 이 제품 하나의 고유 이름. 상표권 등록 대상.
      - "브랜드명": 회사·라인의 우산 이름. 여러 제품을 묶는 상위 정체성.
    각 분류는 사고 결이 달라 한 번 호출에 한 분류만 깊이 있게 다룬다.
    템플릿은 instruction_{naming_type}.md에서 로드.
    """
    product_block = json.dumps(_filter_product(product, "03", cfg), ensure_ascii=False, indent=2)
    target_block = json.dumps(target, ensure_ascii=False, indent=2)
    pos_label = f" (기준: {positioning_basis})" if positioning_basis else ""

    detail_section = ""
    if detail_text.strip():
        det_label = f" (기준: {detail_basis})" if detail_basis else ""
        detail_section = f"\n\n[04 상세페이지 콘티{det_label}]\n{detail_text}"

    channel_section = ""
    if channel_text.strip():
        ch_label = f" (기준: {channel_basis})" if channel_basis else ""
        channel_section = f"\n\n[05 채널·물길 전략{ch_label}]\n{channel_text}"

    # 03은 variant 분기 (제품명/브랜드명). 변형 파일 없으면 기본 instruction.md로 fallback
    try:
        template = load_instruction("naming", variant=naming_type)
    except FileNotFoundError:
        template = load_instruction("naming")

    return _apply_with_fallback(template, [
        ("product", "[제품 정보]", product_block),
        ("target", "[01에서 확정된 타겟]", target_block),
        ("positioning_basis_label", "", pos_label),
        ("positioning", f"[02 포지셔닝 결과{pos_label}]", positioning_text),
        ("detail_section", "", detail_section),  # 이미 빈 문자열이면 안 들어감
        ("channel_section", "", channel_section),
    ])


def build_user_input_05(product: dict, target: dict, positioning_text: str,
                        positioning_basis: str = "", cfg: dict | None = None) -> str:
    """05_channel용 유저 프롬프트.

    입력: 제품 + 01 선택 타겟 + 02 포지셔닝 결과(basis 1개).
    """
    product_block = json.dumps(_filter_product(product, "05", cfg), ensure_ascii=False, indent=2)
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


def load_listing_name_prompt() -> str:
    """05 채널 페이지의 보조 작업(상품명·브랜드명)용 시스템 프롬프트.

    05 본체(채널 분석)와 다른 별도 호출. agents/05_channel/listing_name_instruction.md.
    """
    path = AGENTS_DIR / "05_channel" / "listing_name_instruction.md"
    return _read(path)


def build_user_input_listing_name(
    product: dict,
    target: dict,
    positioning_text: str,
    product_name: str,
    channel_text: str,
    channel_target: str = "전체 추천 채널",
    want_brand: bool = False,
    cfg: dict | None = None,
) -> str:
    """05 페이지 보조 작업(상품명·브랜드명)용 유저 프롬프트.

    입력:
    - product: 제품 정보 (05 단계 excluded_fields 적용 후 사용)
    - target: 01에서 확정된 타겟 dict
    - positioning_text: 02 포지셔닝 결과 본문
    - product_name: 03에서 확정된 제품명 (자유 텍스트, 사용자가 골라 입력)
    - channel_text: 05 채널 결과 본문 (추천 채널 순위·허브 키워드 등)
    - channel_target: 어느 채널을 대상으로 할지 ("스마트스토어"/"쿠팡"/"전체 추천 채널" 등)
    - want_brand: 브랜드명도 같이 생성할지
    """
    product_block = json.dumps(_filter_product(product, "05", cfg), ensure_ascii=False, indent=2)
    target_block = json.dumps(target, ensure_ascii=False, indent=2)
    brand_flag = "true" if want_brand else "false"
    return f"""아래 입력을 바탕으로 상품명(채널 리스팅 제목){' 및 브랜드명' if want_brand else ''}을 생성하라.

[제품 정보]
{product_block}

[01에서 확정된 타겟]
{target_block}

[02 포지셔닝 결과]
{positioning_text}

[03에서 확정된 제품명]
{product_name or '(미입력 — 03 단계에서 확정 후 다시 호출 권고)'}

[05 채널 결과]
{channel_text or '(미입력)'}

[호출 옵션]
- 대상 채널: {channel_target}
- 브랜드명_생성: {brand_flag}

[지시]
- listing_name_instruction.md 형식을 그대로 따르라.
- 상품명은 대상 채널의 SEO 가이드를 우선 적용하라.
- 03 제품명을 상품명 안에 자연스럽게 포함시키되, 채널 SEO 규격에 맞게 키워드와 조합하라.
- 브랜드명_생성=false이면 브랜드명 절은 통째로 생략하라.
- "홍보합니다"식 광고 문구 금지."""
