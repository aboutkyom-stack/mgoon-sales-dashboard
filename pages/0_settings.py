"""페이지 0 — 모델 설정.

단계 00~05 각각에 주 사용 모델 + 비교 모델(on/off)을 설정해
settings.json에 저장한다.
"""
from __future__ import annotations

import streamlit as st

from pipeline.settings import (
    DEFAULT_EXCLUDED_FIELDS,
    MODELS_ORDERED,
    STAGES,
    load,
    save,
    load_판매자특성_활용,
    load_판매자특성_메모,
)
from pipeline.loader import load_instruction, save_instruction

# LLM 프롬프트에서 제외 선택 가능한 제품 필드 목록 (id·제품명은 항상 포함)
_EXCLUDABLE_FIELDS: list[str] = [
    "카테고리", "서브카테고리", "엠군상태",
    "시각설명",
    "스펙", "인증", "가격", "재고", "판매조건",
    "제품특징_bullet", "제품특징_추가", "판매자특성_선택",
    "판매자메모", "주의사항",
    "검수완료", "검수메모",
]

STAGE_LABELS: dict[str, str] = {
    "00": "00 단계 · Vision Pass (이미지 분석)",
    "01": "01 단계 · 결핍·타겟",
    "02": "02 단계 · 포지셔닝",
    "03": "03 단계 · 네이밍",
    "04": "04 단계 · 상세페이지",
    "04_1": "04-1 단계 · 이미지 디렉션",
    "05": "05 단계 · 채널",
}


st.title("⚙️ 모델 설정")
st.caption("단계별 주 사용 모델 + 비교 모델(on/off)을 설정합니다. 저장하면 settings.json에 기록됩니다.")
st.caption("🗄️ DB — settings.json (로컬 파일)")

cfg = load()

# 폼 입력값을 모아둘 dict
new_values: dict = {}

for stage in STAGES:
    st.subheader(STAGE_LABELS[stage])
    with st.container(border=True):
        primary_key  = f"primary_model_{stage}"
        compare_key  = f"compare_model_{stage}"
        enabled_key  = f"compare_enabled_{stage}"
        lint_key     = f"lint_enabled_{stage}"

        primary_default = cfg.get(primary_key, MODELS_ORDERED[0])
        compare_default = cfg.get(compare_key, MODELS_ORDERED[0])
        enabled_default = bool(cfg.get(enabled_key, True))
        lint_default = bool(cfg.get(lint_key, False))

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**주 사용 모델**")
            primary = st.selectbox(
                "primary",
                MODELS_ORDERED,
                index=MODELS_ORDERED.index(primary_default)
                if primary_default in MODELS_ORDERED
                else 0,
                key=f"sel_primary_{stage}",
                label_visibility="collapsed",
            )
        with c2:
            st.markdown("**비교 모델** — 아래 두 옵션 중 선택")
            compare = st.selectbox(
                "compare",
                MODELS_ORDERED,
                index=MODELS_ORDERED.index(compare_default)
                if compare_default in MODELS_ORDERED
                else 0,
                key=f"sel_compare_{stage}",
                label_visibility="collapsed",
            )
            enabled = st.checkbox(
                "비교 모델로 **결과 나란히 생성** (양쪽 호출 — 품질 비교용)",
                value=enabled_default,
                key=f"chk_compare_{stage}",
                help=(
                    "ON: 주 모델·비교 모델 둘 다 호출해 결과를 두 컬럼으로 표시. "
                    "OFF: 주 모델 결과만 표시 (비용 절감)."
                ),
            )
            lint_enabled = st.checkbox(
                "비교 모델이 **주 모델 결과를 검수** (외부 린터 — 비용 발생)",
                value=lint_default,
                key=f"chk_lint_{stage}",
                help=(
                    "ON: 비교 모델이 주 모델의 출력을 qa_checklist 기준으로 검수해 "
                    "PASS/WARN/FAIL을 알려줌. 결과 비교 옵션과 독립적."
                ),
            )

        if enabled and primary == compare:
            st.warning("주 모델과 비교 모델이 동일합니다. 비교 효과가 없습니다.")

        # 린터는 다른 family가 있어야 동작 — 같은 family면 안내
        if lint_enabled:
            from pipeline.models_config import family_of as _fam_of
            if _fam_of(primary) == _fam_of(compare):
                st.warning(
                    "외부 린터가 ON이지만 주/비교 모델이 같은 family입니다. "
                    "교차 검수가 자동 무력화됩니다 (자가 편향 회피)."
                )

        new_values[primary_key] = primary
        new_values[compare_key] = compare
        new_values[enabled_key] = enabled
        new_values[lint_key] = lint_enabled

st.divider()
st.subheader("🔍 참고 필드 관리")
st.caption(
    "LLM에 제품 정보를 넘길 때 각 단계에서 **제외할 필드**를 선택합니다. "
    "선택된 필드는 해당 단계의 프롬프트에서 빠집니다."
)

for stage in STAGES:
    excl_key = f"excluded_fields_{stage}"
    current_excl: list[str] = cfg.get(excl_key, list(DEFAULT_EXCLUDED_FIELDS))
    # 저장된 값 중 현재 목록에 없는 항목 제거 (구버전 호환)
    current_excl = [f for f in current_excl if f in _EXCLUDABLE_FIELDS]
    excluded = st.multiselect(
        STAGE_LABELS[stage],
        options=_EXCLUDABLE_FIELDS,
        default=current_excl,
        key=f"excl_{stage}",
    )
    new_values[excl_key] = excluded

st.divider()
st.subheader("🏪 판매자 특성 (파이프라인 활용형)")
st.caption(
    "이 셀러만의 운영 방식·강점을 **한 줄에 하나씩** 적어두면, "
    "개별 제품 스펙 탭에서 체크박스로 선택해 **01~05 단계에 전달**됩니다.\n\n"
    "예:\n"
    "- 친환경 포장 (주변 상권에서 수거한 박스 재활용)\n"
    "- 직접 포장·발송 — 소량도 꼼꼼하게\n"
    "- 국내 A/S 가능\n"
    "- 100% 환불 보장 상품\n"
    "- 무료 배송"
)

_활용_current = load_판매자특성_활용()
_활용_text = st.text_area(
    "판매자 특성 (파이프라인 활용형)",
    value="\n".join(_활용_current),
    height=180,
    placeholder="한 줄에 하나씩 입력하세요.\n저장 후 제품 스펙 탭에서 체크박스로 나타납니다.",
    key="ta_판매자특성_활용",
    label_visibility="collapsed",
)
new_values["판매자특성_활용"] = [
    line.strip() for line in _활용_text.splitlines() if line.strip()
]

st.divider()
st.subheader("📝 판매자 특성 (개인 메모용)")
st.caption(
    "판매자만 참고하는 운영 라벨. **파이프라인(01~05) 미참조** — 카피·이미지 생성에 영향 없음.\n\n"
    "예:\n"
    "- 합포장 가능\n"
    "- 수기 검수 필요\n"
    "- 9월 입고분만 핸들링 주의"
)

_메모_current = load_판매자특성_메모()
_메모_text = st.text_area(
    "판매자 특성 (개인 메모용)",
    value="\n".join(_메모_current),
    height=140,
    placeholder="한 줄에 하나씩 입력하세요.\n저장 후 제품 스펙 탭에서 체크박스로 나타납니다.",
    key="ta_판매자특성_메모",
    label_visibility="collapsed",
)
new_values["판매자특성_메모"] = [
    line.strip() for line in _메모_text.splitlines() if line.strip()
]

st.divider()
if st.button("💾 저장", type="primary", use_container_width=True):
    save(new_values)
    st.success("저장 완료!")

st.divider()
st.subheader("📝 입력 프롬프트 편집 (instruction.md)")
st.caption(
    "각 단계에서 AI에게 보내는 **유저 프롬프트(지시문)**입니다. "
    "core.md(강의 핵심본)는 건드리지 않고, 이 지시문만 편집해 호출 품질을 조정합니다.\n\n"
    "⚠️ 중괄호 placeholder(`{product}`, `{target}`, `{positioning}`, `{positioning_basis_label}`, "
    "`{detail_section}`, `{channel_section}`)는 그대로 두세요. 실행 시 실제 데이터로 치환됩니다."
)

INSTRUCTION_TARGETS: list[tuple[str, str, str | None]] = [
    ("01 결핍·타겟",        "deficit_target",  None),
    ("02 포지셔닝",         "positioning",     None),
    ("03 네이밍 (제품명)",  "naming",          "제품명"),
    ("03 네이밍 (브랜드명)", "naming",          "브랜드명"),
    ("04 상세페이지",       "detail_page",     None),
    ("04-1 이미지 디렉션",  "image_direction", None),
    ("05 채널",             "channel",         None),
]

for label, agent, variant in INSTRUCTION_TARGETS:
    suffix = f"_{variant}" if variant else ""
    sk_loaded = f"instr_loaded_{agent}{suffix}"
    sk_value  = f"instr_value_{agent}{suffix}"
    if sk_loaded not in st.session_state:
        try:
            st.session_state[sk_value] = load_instruction(agent, variant)
        except FileNotFoundError:
            st.session_state[sk_value] = ""
        st.session_state[sk_loaded] = True

    with st.expander(f"📄 {label}", expanded=False):
        edited = st.text_area(
            label,
            value=st.session_state[sk_value],
            height=320,
            key=f"editor_{agent}{suffix}",
            label_visibility="collapsed",
        )
        if st.button(f"💾 {label} 저장", key=f"btn_save_instr_{agent}{suffix}"):
            save_instruction(agent, edited, variant)
            st.session_state[sk_value] = edited
            st.success(f"{label} 저장 완료!")

st.divider()
st.subheader("현재 설정")
st.json(load())

st.caption(
    "**모델 비용 참고**\n"
    "- claude-sonnet-4-6: 비용/성능 균형 (기본값)\n"
    "- claude-opus-4-7: 가장 고비용, 중요 제품 최종 확인용\n"
    "- claude-haiku-4-5-20251001: 가장 저비용, 단순 작업용\n"
    "- gemini-2.5-flash: 저비용, 비전·요약 무난\n"
    "- gemini-2.5-pro: 고비용, 창의적 표현이 중요한 단계용"
)
