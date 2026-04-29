"""페이지 3 — 이미지 갤러리.

- 상품_파일의 이미지 전체 그리드 뷰
- 계정별 필터
- Drive 폴더 동기화 UI (drive_client.py 호출)
"""
from __future__ import annotations

import streamlit as st

from pipeline.account_ui import account_badge, account_short_name
from pipeline.supabase_read import (
    get_thumbnail_url,
    list_all_images,
    list_계정_values,
    upsert_파일,
)

st.title("🖼️ 이미지 갤러리")
st.caption("🗄️ DB — 상품_파일, 상품 테이블")

# ── Drive 저장공간 ─────────────────────────────────────────
try:
    from pipeline.drive_client import ACCOUNTS, get_all_quota_info
    _drive_available = True
except ImportError:
    _drive_available = False

with st.expander("💾 Drive 저장공간", expanded=True):
    if not _drive_available:
        st.warning("Drive 클라이언트를 불러올 수 없습니다. 패키지를 설치하세요.")
    else:
        if st.button("🔄 사용량 새로고침", key="btn_quota_refresh"):
            st.cache_data.clear()

        with st.spinner("Drive 사용량 조회 중…"):
            @st.cache_data(ttl=1800, show_spinner=False)
            def _cached_quota():
                return get_all_quota_info()

            quota_list = _cached_quota()

        cols = st.columns(len(quota_list)) if quota_list else []
        for i, q in enumerate(quota_list):
            with cols[i]:
                st.markdown(f"**{q['name']}**")
                if q["error"]:
                    st.warning(f"조회 실패\n\n`{q['error'][:80]}`")
                else:
                    used_gb  = q["used_bytes"]  / 1024 ** 3
                    limit_gb = q["limit_bytes"] / 1024 ** 3
                    pct      = q["pct"]
                    # 사용률에 따라 색상 구분
                    bar_color = "🟢" if pct < 0.7 else ("🟡" if pct < 0.9 else "🔴")
                    st.progress(pct)
                    st.caption(
                        f"{bar_color} **{used_gb:.2f} GB** / {limit_gb:.0f} GB"
                        f"　({pct * 100:.1f}%)"
                    )

st.divider()

# ── 필터 ──────────────────────────────────────────────────
with st.container(border=True):
    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        search = st.text_input("제품명 검색", placeholder="제품명 일부 입력")
    with c2:
        accounts = ["전체"] + list_계정_values()
        account_filter = st.selectbox(
            "구글 계정",
            accounts,
            format_func=lambda x: ("전체" if x == "전체" else account_badge(x)),
        )
    with c3:
        limit = st.number_input("최대 이미지 수", min_value=50, max_value=2000, value=300, step=50)

# ── 이미지 조회 ───────────────────────────────────────────
images = list_all_images(
    계정=account_filter if account_filter != "전체" else None,
    limit=int(limit),
)

# 제품명 검색 필터 (클라이언트 사이드)
if search:
    images = [img for img in images if search.lower() in (img.get("제품명") or "").lower()]

st.write(f"총 **{len(images)}**장")

if not images:
    st.info("등록된 이미지가 없습니다. 아래 Drive 동기화를 통해 이미지를 추가하세요.")
else:
    # ── 그리드 ────────────────────────────────────────────
    COLS = 5
    cols = st.columns(COLS)
    for i, img in enumerate(images):
        fid = img.get("드라이브_파일_id")
        product_name = img.get("제품명") or ""
        product_id = img.get("상품_id")
        계정 = img.get("계정") or ""
        파일명 = img.get("파일명") or ""

        with cols[i % COLS]:
            if fid:
                try:
                    st.image(get_thumbnail_url(fid, 300), use_container_width=True)
                except Exception:
                    st.caption("로드 실패")
            badge = account_badge(계정) if 계정 else ""
            st.caption(f"**[{product_id}]** {product_name}  \n{badge}")
            if fid:
                st.markdown(
                    f"[원본](https://drive.google.com/uc?export=view&id={fid})"
                    f" · [제품 보기](1_products)"
                )

st.divider()

# ── Drive 동기화 ──────────────────────────────────────────
st.subheader("🔄 Drive 폴더 동기화")
st.caption("Google Drive 폴더를 스캔해 이미지를 DB에 등록합니다.")

with st.expander("동기화 실행", expanded=False):
    try:
        from pipeline.drive_client import ACCOUNTS, scan_folder_to_파일_rows, build_service
        drive_available = True
    except ImportError as e:
        drive_available = False
        st.warning(f"Drive 클라이언트 로드 실패: {e}\n\nrequirements.txt의 google 패키지를 설치하세요.")

    if drive_available:
        d1, d2 = st.columns(2)
        with d1:
            account_options = {a["label"]: a for a in ACCOUNTS}
            sel_account = st.selectbox(
                "계정 선택",
                list(account_options.keys()),
                key="sync_account",
                format_func=account_badge,
            )
        with d2:
            folder_url = st.text_input(
                "Drive 폴더 URL 또는 ID",
                placeholder="https://drive.google.com/drive/folders/... 또는 폴더 ID",
                key="sync_folder",
            )

        # 제품 연결
        from pipeline.supabase_read import list_products
        products = list_products(limit=1200)
        product_options = {f"[{p['id']}] {p.get('제품명','')}": p["id"] for p in products}
        sel_product_label = st.selectbox("연결할 제품", list(product_options.keys()), key="sync_product")
        sel_product_id = product_options[sel_product_label]

        if st.button("🔍 스캔 미리보기", use_container_width=True, key="btn_scan"):
            # 폴더 ID 파싱
            folder_id = folder_url.strip()
            if "folders/" in folder_id:
                folder_id = folder_id.split("folders/")[-1].split("?")[0].strip()

            if not folder_id:
                st.error("폴더 URL 또는 ID를 입력하세요.")
            else:
                acc = account_options[sel_account]
                with st.spinner(f"{acc['label']} Drive 스캔 중…"):
                    try:
                        svc = build_service(acc["label"])
                        rows = scan_folder_to_파일_rows(svc, folder_id)
                        st.session_state["scan_rows"] = rows
                        st.session_state["scan_account"] = acc["label"]
                        st.session_state["scan_product_id"] = sel_product_id
                        st.success(f"{len(rows)}개 이미지 발견")
                        # 미리보기
                        if rows:
                            PREV = 10
                            pcols = st.columns(min(len(rows), PREV))
                            for j, r in enumerate(rows[:PREV]):
                                fid2 = r.get("드라이브_파일_id")
                                with pcols[j]:
                                    if fid2:
                                        st.image(get_thumbnail_url(fid2, 200), use_container_width=True)
                                    st.caption(r.get("파일명", ""))
                    except Exception as e:
                        st.error(f"스캔 실패: {type(e).__name__}: {e}")

        scan_rows = st.session_state.get("scan_rows")
        if scan_rows and st.session_state.get("scan_product_id") == sel_product_id:
            if st.button(
                f"💾 {len(scan_rows)}개 DB 저장",
                type="primary",
                use_container_width=True,
                key="btn_save_scan",
            ):
                n = upsert_파일(
                    sel_product_id,
                    scan_rows,
                    st.session_state["scan_account"],
                )
                st.success(f"{n}개 저장 완료! (중복은 자동 스킵)")
                st.session_state.pop("scan_rows", None)
                st.rerun()
