"""엠군 파이프라인 전용 Streamlit 엔트리."""
from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="엠군 파이프라인", page_icon="🎯", layout="wide")

pg = st.navigation(
    {
        "메인": [st.Page("pages/home.py", title="🏠 홈", default=True)],
        "제품": [
            st.Page("pages/1_products.py",      title="📦 제품 조회"),
            st.Page("pages/2_product_edit.py",  title="✏️ 제품 등록/수정"),
            st.Page("pages/2_pipeline.py",      title="🧪 파이프라인"),
            st.Page("pages/3_gallery.py",       title="🖼️ 이미지 갤러리"),
            st.Page("pages/4_files.py",         title="🗂️ 상품 파일"),
        ],
        "시스템": [
            st.Page("pages/0_settings.py", title="⚙️ 설정"),
        ],
        "테스트": [
            st.Page("pages/9_vision_test.py", title="🔬 Vision Pass 테스트"),
        ],
    }
)
pg.run()
