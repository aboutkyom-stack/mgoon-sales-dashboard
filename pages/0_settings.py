"""페이지 0 — 모델 설정.

단계 00~05 각각에 주 사용 모델 + 비교 모델(on/off)을 설정해
settings.json에 저장한다.
"""
from __future__ import annotations

import streamlit as st

from pipeline.settings import DEFAULT_EXCLUDED_FIELDS, MODELS_ORDERED, STAGES, load, save, load_판매자특성

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

        primary_default = cfg.get(primary_key, MODELS_ORDERED[0])
        compare_default = cfg.get(compare_key, MODELS_ORDERED[0])
        enabled_default = bool(cfg.get(enabled_key, True))

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
            top_l, top_r = st.columns([3, 2])
            with top_l:
                st.markdown("**비교 모델**")
            with top_r:
                enabled = st.checkbox(
                    "사용",
                    value=enabled_default,
                    key=f"chk_compare_{stage}",
                )
            compare = st.selectbox(
                "compare",
                MODELS_ORDERED,
                index=MODELS_ORDERED.index(compare_default)
                if compare_default in MODELS_ORDERED
                else 0,
                key=f"sel_compare_{stage}",
                label_visibility="collapsed",
                disabled=not enabled,
            )

        if enabled and primary == compare:
            st.warning("주 모델과 비교 모델이 동일합니다. 비교 효과가 없습니다.")

        new_values[primary_key] = primary
        new_values[compare_key] = compare
        new_values[enabled_key] = enabled

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
st.subheader("🏪 판매자 특성")
st.caption(
    "이 셀러만의 운영 방식·강점을 **한 줄에 하나씩** 적어두면, "
    "개별 제품 스펙 탭에서 체크박스로 선택해 01~05 단계에 전달됩니다.\n\n"
    "예:\n"
    "- 친환경 포장 (주변 상권에서 수거한 박스 재활용)\n"
    "- 직접 포장·발송 — 소량도 꼼꼼하게\n"
    "- 국내 A/S 가능"
)

_특성_current = load_판매자특성()
_특성_text = st.text_area(
    "판매자 특성 목록 (한 줄에 하나)",
    value="\n".join(_특성_current),
    height=180,
    placeholder="한 줄에 하나씩 입력하세요.\n저장 후 제품 스펙 탭에서 체크박스로 나타납니다.",
    key="ta_판매자특성",
    label_visibility="collapsed",
)
new_values["판매자특성"] = [
    line.strip() for line in _특성_text.splitlines() if line.strip()
]

st.divider()
if st.button("💾 저장", type="primary", use_container_width=True):
    save(new_values)
    st.success("저장 완료!")

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
