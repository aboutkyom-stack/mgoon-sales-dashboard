"""홈 페이지 — 최근 실행 목록 + 시작 가이드."""
from __future__ import annotations

import streamlit as st

from pipeline.storage import get_storage

st.title("🎯 엠군 파이프라인")
st.caption("제품 스펙(동료 Supabase, read-only) → 01 결핍·타겟 → 02 포지셔닝.")
st.caption("🗄️ DB — mgoon_runs 테이블")

st.divider()

col_a, col_b = st.columns([1, 1])
with col_a:
    st.subheader("시작하기")
    st.markdown(
        "- **제품 조회** 페이지에서 동료 DB의 제품을 고른 뒤 '이 제품으로 파이프라인 실행'\n"
        "- **파이프라인** 페이지에서 01 → 타겟 선택 → 02를 차례로 실행\n"
        "- Claude / Gemini 결과를 나란히 비교 (교차검증)"
    )
    st.page_link("pages/1_products.py", label="📦 제품 조회로 이동", icon="➡️")
    st.page_link("pages/2_pipeline.py", label="🧪 파이프라인으로 이동", icon="➡️")

with col_b:
    st.subheader("최근 실행")
    try:
        storage = get_storage()
        runs = storage.list_runs(limit=20)
    except Exception as e:
        st.error(f"DB 연결 실패: {type(e).__name__}: {e}")
        runs = []

    if not runs:
        st.info("아직 실행된 파이프라인이 없습니다.")
    else:
        for r in runs:
            with st.container(border=True):
                st.markdown(
                    f"**#{r['id']} · {r['product_name']}**  \n"
                    f"source_product_id: `{r.get('source_product_id')}`  \n"
                    f"created: {r['created_at']}"
                )
                if st.button("이 run으로 이동", key=f"go_run_{r['id']}"):
                    st.session_state["current_run_id"] = r["id"]
                    st.switch_page("pages/2_pipeline.py")
