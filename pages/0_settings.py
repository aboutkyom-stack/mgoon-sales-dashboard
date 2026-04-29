"""페이지 0 — 모델 설정.

01 단계(결핍·타겟)와 02 단계(포지셔닝)에 쓸 Claude / Gemini 모델을
각각 선택하고 settings.json에 저장.
"""
from __future__ import annotations

import streamlit as st

from pipeline.settings import CLAUDE_MODELS, GEMINI_MODELS, load, save

st.title("⚙️ 모델 설정")
st.caption("단계별 AI 모델을 설정합니다. 저장하면 settings.json에 기록됩니다.")
st.caption("🗄️ DB — settings.json (로컬 파일)")

cfg = load()

st.subheader("00 단계 · Vision Pass (이미지 분석)")
with st.container(border=True):
    c1, c2 = st.columns(2)
    with c1:
        claude_00 = st.selectbox(
            "Claude 모델",
            CLAUDE_MODELS,
            index=CLAUDE_MODELS.index(cfg["claude_model_00"])
            if cfg["claude_model_00"] in CLAUDE_MODELS
            else 1,
            key="sel_claude_00",
        )
    with c2:
        gemini_00 = st.selectbox(
            "Gemini 모델",
            GEMINI_MODELS,
            index=GEMINI_MODELS.index(cfg["gemini_model_00"])
            if cfg["gemini_model_00"] in GEMINI_MODELS
            else 0,
            key="sel_gemini_00",
        )

st.subheader("01 단계 · 결핍·타겟")
with st.container(border=True):
    c1, c2 = st.columns(2)
    with c1:
        claude_01 = st.selectbox(
            "Claude 모델",
            CLAUDE_MODELS,
            index=CLAUDE_MODELS.index(cfg["claude_model_01"])
            if cfg["claude_model_01"] in CLAUDE_MODELS
            else 1,
            key="sel_claude_01",
        )
    with c2:
        gemini_01 = st.selectbox(
            "Gemini 모델",
            GEMINI_MODELS,
            index=GEMINI_MODELS.index(cfg["gemini_model_01"])
            if cfg["gemini_model_01"] in GEMINI_MODELS
            else 0,
            key="sel_gemini_01",
        )

st.subheader("02 단계 · 포지셔닝")
with st.container(border=True):
    c1, c2 = st.columns(2)
    with c1:
        claude_02 = st.selectbox(
            "Claude 모델",
            CLAUDE_MODELS,
            index=CLAUDE_MODELS.index(cfg["claude_model_02"])
            if cfg["claude_model_02"] in CLAUDE_MODELS
            else 1,
            key="sel_claude_02",
        )
    with c2:
        gemini_02 = st.selectbox(
            "Gemini 모델",
            GEMINI_MODELS,
            index=GEMINI_MODELS.index(cfg["gemini_model_02"])
            if cfg["gemini_model_02"] in GEMINI_MODELS
            else 0,
            key="sel_gemini_02",
        )

st.divider()
if st.button("💾 저장", type="primary", use_container_width=True):
    save(
        {
            "claude_model_00": claude_00,
            "claude_model_01": claude_01,
            "claude_model_02": claude_02,
            "gemini_model_00": gemini_00,
            "gemini_model_01": gemini_01,
            "gemini_model_02": gemini_02,
        }
    )
    st.success("저장 완료!")

st.divider()
st.subheader("현재 설정")
st.json(load())

st.caption(
    "**모델 비용 참고**\n"
    "- Gemini 2.5 Flash: 저비용, 엠군 01/02 정상 작동 (추천 기본값)\n"
    "- Gemini 2.5 Pro: 고비용, 창의적 표현이 중요한 최종 검수 시 사용\n"
    "- Claude Sonnet: 비용/성능 균형\n"
    "- Claude Opus: 가장 고비용, 중요 제품 최종 확인용"
)
