"""페이지 3 — 이미지 갤러리.

탭 구조:
- 공통 상단: Drive 저장공간
- Tab 1 (DB 이미지): DB에 저장된 이미지 그리드 + 필터
- Tab 2 (Drive 탐색): 계정 선택 → 폴더 트리 → 파일 그리드 네비게이션 + Drive 동기화
"""
from __future__ import annotations

import streamlit as st

from pipeline.account_ui import account_badge
from pipeline.supabase_read import (
    get_thumbnail_url,
    list_all_images,
    list_계정_values,
    upsert_파일,
)

st.title("🖼️ 이미지 갤러리")
st.caption("🗄️ DB — 상품_파일, 상품 테이블")

# ── Drive 클라이언트 로드 ──────────────────────────────────
try:
    from pipeline.drive_client import (
        ACCOUNTS,
        build_service,
        get_all_quota_info,
        list_files_in_folder,
        list_subfolders,
        scan_folder_to_파일_rows,
    )
    _drive_available = True
except ImportError:
    _drive_available = False

# ── Drive API 캐싱 함수 (모듈 레벨) ───────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _cached_subfolders(account_label: str, folder_id: str) -> list[dict]:
    svc = build_service(account_label)
    return list_subfolders(svc, folder_id)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_files(account_label: str, folder_id: str) -> list[dict]:
    svc = build_service(account_label)
    return list_files_in_folder(svc, folder_id)


@st.cache_data(ttl=1800, show_spinner=False)
def _cached_quota() -> list[dict]:
    return get_all_quota_info()


# ── Drive 저장공간 (공통 상단) ────────────────────────────
with st.expander("💾 Drive 저장공간", expanded=False):
    if not _drive_available:
        st.warning("Drive 클라이언트를 불러올 수 없습니다. 패키지를 설치하세요.")
    else:
        if st.button("🔄 사용량 새로고침", key="btn_quota_refresh"):
            st.cache_data.clear()

        with st.spinner("Drive 사용량 조회 중…"):
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
                    bar_color = "🟢" if pct < 0.7 else ("🟡" if pct < 0.9 else "🔴")
                    st.progress(pct)
                    st.caption(
                        f"{bar_color} **{used_gb:.2f} GB** / {limit_gb:.0f} GB"
                        f"　({pct * 100:.1f}%)"
                    )

st.divider()

# ── 탭 ───────────────────────────────────────────────────
tab_db, tab_drive = st.tabs(["🗄️ DB 이미지", "📁 Drive 탐색"])


# ═══════════════════════════════════════════════════════════
# Tab 1 — DB 이미지
# ═══════════════════════════════════════════════════════════
with tab_db:
    with st.container(border=True):
        c1, c2, c3 = st.columns([3, 1, 1])
        with c1:
            search = st.text_input("제품명 검색", placeholder="제품명 일부 입력", key="db_search")
        with c2:
            accounts = ["전체"] + list_계정_values()
            account_filter = st.selectbox(
                "구글 계정",
                accounts,
                format_func=lambda x: ("전체" if x == "전체" else account_badge(x)),
                key="db_account_filter",
            )
        with c3:
            limit = st.number_input(
                "최대 이미지 수", min_value=50, max_value=2000, value=300, step=50,
                key="db_limit",
            )

    images = list_all_images(
        계정=account_filter if account_filter != "전체" else None,
        limit=int(limit),
    )
    if search:
        images = [img for img in images if search.lower() in (img.get("제품명") or "").lower()]

    st.write(f"총 **{len(images)}**장")

    if not images:
        st.info("등록된 이미지가 없습니다. [Drive 탐색] 탭의 동기화를 통해 이미지를 추가하세요.")
    else:
        COLS = 5
        cols = st.columns(COLS)
        for i, img in enumerate(images):
            fid = img.get("드라이브_파일_id")
            product_name = img.get("제품명") or ""
            product_id   = img.get("상품_id")
            계정          = img.get("계정") or ""
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


# ═══════════════════════════════════════════════════════════
# Tab 2 — Drive 탐색
# ═══════════════════════════════════════════════════════════
with tab_drive:
    if not _drive_available:
        st.warning("Drive 클라이언트를 불러올 수 없습니다. `pip install google-auth google-api-python-client`")
    else:
        # ── 세션 상태 초기화 ──────────────────────────────
        _default_account = ACCOUNTS[0]["label"] if ACCOUNTS else ""
        if "gb_account" not in st.session_state:
            st.session_state["gb_account"] = _default_account
        if "gb_folder_id" not in st.session_state:
            st.session_state["gb_folder_id"] = "root"
        if "gb_breadcrumb" not in st.session_state:
            st.session_state["gb_breadcrumb"] = [{"id": "root", "name": "루트"}]

        # ── 계정 선택 ────────────────────────────────────
        acc_labels = [a["label"] for a in ACCOUNTS]
        acc_names  = [account_badge(a["label"]) for a in ACCOUNTS]

        prev_account = st.session_state["gb_account"]
        sel_idx = acc_labels.index(prev_account) if prev_account in acc_labels else 0

        chosen_idx = st.radio(
            "계정",
            range(len(acc_labels)),
            index=sel_idx,
            format_func=lambda i: acc_names[i],
            horizontal=True,
            key="gb_account_radio",
        )
        chosen_account = acc_labels[chosen_idx]

        # 계정 변경 시 네비게이션 리셋
        if chosen_account != st.session_state["gb_account"]:
            st.session_state["gb_account"] = chosen_account
            st.session_state["gb_folder_id"] = "root"
            st.session_state["gb_breadcrumb"] = [{"id": "root", "name": "루트"}]
            st.rerun()

        account_label = st.session_state["gb_account"]
        folder_id     = st.session_state["gb_folder_id"]
        breadcrumb    = st.session_state["gb_breadcrumb"]

        # ── 브레드크럼 + 새로고침 ─────────────────────────
        bc_col, refresh_col = st.columns([6, 1])
        with bc_col:
            path_txt = " / ".join(item["name"] for item in breadcrumb)
            st.markdown(f"📁 {path_txt}")
        with refresh_col:
            if st.button("🔄", key="gb_refresh", help="폴더 목록 새로고침"):
                st.cache_data.clear()
                st.rerun()

        # 상위 폴더 버튼 (루트가 아닐 때)
        if len(breadcrumb) > 1:
            if st.button("⬆️ 상위 폴더로", key="gb_up"):
                new_bc = breadcrumb[:-1]
                st.session_state["gb_breadcrumb"] = new_bc
                st.session_state["gb_folder_id"]  = new_bc[-1]["id"]
                st.rerun()

        st.divider()

        # ── 서브폴더 + 파일 조회 ──────────────────────────
        try:
            with st.spinner("폴더 목록 조회 중…"):
                subfolders = _cached_subfolders(account_label, folder_id)
            with st.spinner("파일 목록 조회 중…"):
                all_files = _cached_files(account_label, folder_id)
        except Exception as e:
            st.error(f"Drive 조회 실패: {type(e).__name__}: {e}")
            subfolders = []
            all_files  = []

        # ── 서브폴더 그리드 ───────────────────────────────
        if subfolders:
            st.markdown(f"**📂 폴더** ({len(subfolders)}개)")
            FCOLS = 4
            f_cols = st.columns(FCOLS)
            for i, sub in enumerate(sorted(subfolders, key=lambda x: x["name"])):
                with f_cols[i % FCOLS]:
                    if st.button(
                        f"📁 {sub['name']}",
                        key=f"gb_folder_{sub['id']}",
                        use_container_width=True,
                    ):
                        new_bc = breadcrumb + [{"id": sub["id"], "name": sub["name"]}]
                        st.session_state["gb_breadcrumb"] = new_bc
                        st.session_state["gb_folder_id"]  = sub["id"]
                        st.rerun()

        # ── 이미지 파일 그리드 ────────────────────────────
        _IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp"}
        img_files = [f for f in all_files if f.get("mimeType") in _IMAGE_MIMES]
        other_files = [f for f in all_files if f.get("mimeType") not in _IMAGE_MIMES]

        if img_files:
            st.markdown(f"**🖼️ 이미지** ({len(img_files)}장)")
            ICOLS = 5
            i_cols = st.columns(ICOLS)
            for i, f in enumerate(img_files):
                fid  = f.get("id", "")
                name = f.get("name", "")
                link = f.get("webViewLink", "")
                with i_cols[i % ICOLS]:
                    try:
                        st.image(get_thumbnail_url(fid, 300), use_container_width=True)
                    except Exception:
                        st.caption("로드 실패")
                    if link:
                        st.markdown(f"[{name}]({link})", help=name)
                    else:
                        st.caption(name)

        if other_files:
            with st.expander(f"기타 파일 ({len(other_files)}개)"):
                for f in other_files:
                    link = f.get("webViewLink", "")
                    name = f.get("name", "")
                    mime = f.get("mimeType", "")
                    if link:
                        st.markdown(f"- [{name}]({link}) `{mime}`")
                    else:
                        st.markdown(f"- {name} `{mime}`")

        if not subfolders and not all_files:
            st.info("이 폴더는 비어 있습니다.")

        st.divider()

        # ── Drive 동기화 ──────────────────────────────────
        st.subheader("🔄 Drive 폴더 동기화")
        st.caption("Google Drive 폴더를 스캔해 이미지를 DB에 등록합니다.")

        with st.expander("동기화 실행", expanded=False):
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

            from pipeline.supabase_read import list_products
            products = list_products(limit=1200)
            product_options = {f"[{p['id']}] {p.get('제품명', '')}": p["id"] for p in products}
            sel_product_label = st.selectbox(
                "연결할 제품", list(product_options.keys()), key="sync_product"
            )
            sel_product_id = product_options[sel_product_label]

            if st.button("🔍 스캔 미리보기", use_container_width=True, key="btn_scan"):
                folder_id_sync = folder_url.strip()
                if "folders/" in folder_id_sync:
                    folder_id_sync = folder_id_sync.split("folders/")[-1].split("?")[0].strip()

                if not folder_id_sync:
                    st.error("폴더 URL 또는 ID를 입력하세요.")
                else:
                    acc = account_options[sel_account]
                    with st.spinner(f"{acc['label']} Drive 스캔 중…"):
                        try:
                            svc = build_service(acc["label"])
                            rows = scan_folder_to_파일_rows(svc, folder_id_sync)
                            st.session_state["scan_rows"] = rows
                            st.session_state["scan_account"] = acc["label"]
                            st.session_state["scan_product_id"] = sel_product_id
                            st.success(f"{len(rows)}개 이미지 발견")
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
