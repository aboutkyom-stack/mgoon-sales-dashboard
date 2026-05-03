"""홈 페이지 — 시작 가이드.

파이프라인 실행 이력은 제품 단위로 [제품 등록/수정] 페이지의
"🧪 엠군 파이프라인" 탭에서 조회한다 (홈에는 두지 않음).
"""
from __future__ import annotations

import streamlit as st

st.title("🎯 엠군 파이프라인")
st.caption("제품 스펙(상품 테이블) → 01 결핍·타겟 → 02 포지셔닝.")

st.divider()

st.subheader("시작하기")
st.markdown(
    "- **제품 조회** 페이지에서 제품을 고른 뒤 '✏️ 작업'으로 상세 진입\n"
    "- **🧪 엠군 파이프라인** 탭에서 '🚀 새 실행 시작' → 파이프라인 페이지로 이동\n"
    "- 파이프라인 페이지에서 01 → 타겟 선택 → 02를 차례로 실행\n"
    "- 누적된 실행 이력은 다시 제품 상세의 **🧪 엠군 파이프라인** 탭에서 언제든 열람·삭제"
)

st.page_link("pages/1_products.py", label="📦 제품 조회로 이동", icon="➡️")
st.page_link("pages/2_pipeline.py", label="🧪 파이프라인으로 이동 (제품 선택 후)", icon="➡️")
