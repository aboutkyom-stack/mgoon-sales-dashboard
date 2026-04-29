"""페이지 4 — 상품_파일 테이블 뷰어."""
from __future__ import annotations

import streamlit as st
import pandas as pd
from pipeline.supabase_read import _client, get_thumbnail_url

st.title("🗂️ 상품_파일 테이블")
st.caption("🗄️ DB — 상품_파일 테이블")

try:
    res = _client().table("상품_파일").select("*").order("상품_id").limit(2000).execute()
    data = res.data or []
except Exception as e:
    st.error(f"조회 실패: {e}")
    st.stop()

if not data:
    st.info("등록된 파일이 없습니다.")
    st.stop()

df = pd.DataFrame(data)
total = len(df)
img_cnt = df[df["파일_유형"] == "image"].shape[0]
prod_cnt = df["상품_id"].nunique()

c1, c2, c3 = st.columns(3)
c1.metric("전체 파일", total)
c2.metric("이미지", img_cnt)
c3.metric("연결된 상품 수", prod_cnt)

# ── 필터 ──────────────────────────────────────────────────
with st.container(border=True):
    col1, col2 = st.columns(2)
    with col1:
        pid_filter = st.text_input("상품_id 필터", placeholder="숫자 입력")
    with col2:
        type_options = ["전체"] + sorted(df["파일_유형"].dropna().unique().tolist())
        type_filter = st.selectbox("파일 유형", type_options)

view = df.copy()
if pid_filter.strip():
    try:
        view = view[view["상품_id"] == int(pid_filter.strip())]
    except ValueError:
        pass
if type_filter != "전체":
    view = view[view["파일_유형"] == type_filter]

st.caption(f"표시: {len(view)}건")
st.dataframe(view, use_container_width=True, hide_index=True)

# ── 이미지 미리보기 ───────────────────────────────────────
st.divider()
img_rows = view[view["파일_유형"] == "image"].dropna(subset=["드라이브_파일_id"])

if not img_rows.empty:
    st.subheader(f"이미지 미리보기 ({len(img_rows)}장)")
    cols = st.columns(5)
    for i, (_, row) in enumerate(img_rows.iterrows()):
        with cols[i % 5]:
            fid = row["드라이브_파일_id"]
            st.image(get_thumbnail_url(fid, 200), use_container_width=True)
            st.caption(f"[{row['상품_id']}] {row.get('파일명','')}")
