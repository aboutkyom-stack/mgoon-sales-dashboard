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
    get_account_folder,
    get_thumbnail_url,
    list_all_files,
    list_계정_values,
    set_account_folder,
    upsert_파일,
)
from pipeline.image_actions import (
    bulk_download_zip,
    file_icon_card,
    image_with_fallback,
    individual_download_link,
    original_view_url,
    refresh_button,
    video_thumb_with_play_overlay,
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
            # 에러 결과는 캐시에 박히지 않도록 — 토큰 회복 시 다음 진입 때 즉시 반영
            if any(q.get("error") for q in quota_list):
                _cached_quota.clear()

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
tab_db, tab_drive = st.tabs(["🗄️ DB 파일", "📁 Drive 탐색"])


# ═══════════════════════════════════════════════════════════
# Tab 1 — DB 파일 (이미지 / 동영상 / 기타)
# ═══════════════════════════════════════════════════════════
with tab_db:
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
        with c1:
            search = st.text_input(
                "검색 (제품명 / 제품 ID / 파일명)",
                placeholder="예: 타워크레인, 1703, .mp4, crop1",
                key="db_search",
            )
        with c2:
            accounts = ["전체"] + list_계정_values()
            account_filter = st.selectbox(
                "구글 계정",
                accounts,
                format_func=lambda x: ("전체" if x == "전체" else account_badge(x)),
                key="db_account_filter",
            )
        with c3:
            type_filter = st.selectbox(
                "유형",
                ["전체", "📷 이미지", "🎬 동영상", "📄 기타"],
                key="db_type_filter",
            )
        with c4:
            limit = st.number_input(
                "최대 파일 수", min_value=50, max_value=2000, value=300, step=50,
                key="db_limit",
            )

    _type_arg = {
        "📷 이미지": "image",
        "🎬 동영상": "video",
    }.get(type_filter)  # 전체/기타는 None → 후처리에서 필터

    files = list_all_files(
        계정=account_filter if account_filter != "전체" else None,
        파일_유형=_type_arg,
        limit=int(limit),
    )
    if type_filter == "📄 기타":
        files = [f for f in files if f.get("파일_유형") not in ("image", "video")]
    if search:
        _s = search.strip().lower()
        def _match(f):
            return (
                _s in (f.get("제품명") or "").lower()
                or _s in str(f.get("상품_id") or "")
                or _s in (f.get("파일명") or "").lower()
            )
        files = [f for f in files if _match(f)]

    # 유형별 분류
    db_images = [f for f in files if f.get("파일_유형") == "image"]
    db_videos = [f for f in files if f.get("파일_유형") == "video"]
    db_others = [f for f in files if f.get("파일_유형") not in ("image", "video")]

    _cnt_col, _refresh_col = st.columns([5, 1])
    with _cnt_col:
        _cnt_parts = []
        if db_images: _cnt_parts.append(f"📷 {len(db_images)}")
        if db_videos: _cnt_parts.append(f"🎬 {len(db_videos)}")
        if db_others: _cnt_parts.append(f"📄 {len(db_others)}")
        _cnt_text = "  ·  ".join(_cnt_parts) if _cnt_parts else "0"
        st.write(f"총 **{len(files)}**개  —  {_cnt_text}")
    with _refresh_col:
        refresh_button(
            scope_key="gallery_db",
            label="🔄 새로고침",
            help="DB 다시 조회 + 깨진 썸네일 강제 재요청",
            use_container_width=True,
        )

    if not files:
        st.info("등록된 파일이 없습니다. [Drive 탐색] 탭의 동기화를 통해 추가하세요.")
    else:
        # 일괄 ZIP 다운로드 (이미지 기본, 동영상 토글)
        if db_images or db_videos:
            bulk_download_zip(
                files=db_images,
                scope_key="gallery_db",
                zip_name_prefix="gallery_db_files",
                extra_files=db_videos if db_videos else None,
                extra_label="동영상",
            )

        COLS = 5
        cols = st.columns(COLS)
        for i, fobj in enumerate(files):
            fid = fobj.get("드라이브_파일_id")
            fname = fobj.get("파일명") or ""
            ftype = fobj.get("파일_유형") or ""
            product_name = fobj.get("제품명") or ""
            product_id   = fobj.get("상품_id")
            계정          = fobj.get("계정") or ""
            with cols[i % COLS]:
                if fid:
                    try:
                        if ftype == "image":
                            image_with_fallback(fid, size=300, scope_key="gallery_db", alt=product_name)
                        elif ftype == "video":
                            video_thumb_with_play_overlay(fid, size=300, scope_key="gallery_db", alt=fname)
                        else:
                            file_icon_card(fid, fname)
                    except Exception:
                        st.caption("로드 실패")
                badge = account_badge(계정) if 계정 else ""
                st.caption(f"**[{product_id}]** {product_name}  \n{badge} · {fname}")
                if fid:
                    st.markdown(
                        f"[원본]({original_view_url(fid)})"
                        f" · {individual_download_link(fid)}"
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
            refresh_button(
                scope_key="gallery_drive",
                label="🔄",
                help="폴더 목록 + 깨진 썸네일 새로고침",
                use_container_width=True,
            )

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

        # ── 빠른 동기화 (루트든 폴더 안이든 항상 노출) ───
        # 루트: 현재 위치의 서브폴더 중 하나를 선택
        # 폴더 안: 현재 폴더가 자동 선택됨
        _can_quick_sync = (folder_id != "root") or bool(subfolders)
        if _can_quick_sync:
            from pipeline.supabase_read import (
                list_products as _list_products_qs,
                get_account_folder as _get_acc_folder_qs,
                set_account_folder as _set_acc_folder_qs,
            )

            with st.container(border=True):
                st.markdown("### 📌 빠른 동기화 — 폴더를 제품에 연결")

                if folder_id != "root":
                    # 폴더 안 상태: 현재 폴더 자동 사용
                    _qs_folder_id = folder_id
                    _qs_folder_name = breadcrumb[-1]["name"] if breadcrumb else ""
                    st.caption(
                        f"📁 현재 폴더 **`{_qs_folder_name}`** ({account_badge(account_label)})를 "
                        f"제품에 연결합니다."
                    )
                else:
                    # 루트 상태: 서브폴더 selectbox로 선택
                    st.caption(
                        f"📁 ({account_badge(account_label)}) 루트의 폴더 중 하나를 선택해 제품에 연결합니다. "
                        f"(폴더 안으로 들어가서 파일을 확인 후 동기화하는 것도 가능)"
                    )
                    _qs_folder_labels = ["(폴더 선택)"] + [s["name"] for s in sorted(subfolders, key=lambda x: x["name"])]
                    _qs_folder_choice = st.selectbox(
                        "동기화할 폴더",
                        _qs_folder_labels,
                        key="qs_root_folder_choice",
                    )
                    if _qs_folder_choice != "(폴더 선택)":
                        _qs_folder_id = next(
                            s["id"] for s in subfolders if s["name"] == _qs_folder_choice
                        )
                        _qs_folder_name = _qs_folder_choice
                    else:
                        _qs_folder_id = None
                        _qs_folder_name = None

                if _qs_folder_id:
                    # 제품 목록 로드 + 폴더명과 일치하는 제품 자동 추천
                    _qs_products = _list_products_qs(limit=2000)
                    _qs_options = {
                        f"[{p['id']}] {p.get('제품명', '')}": p["id"]
                        for p in _qs_products
                    }
                    _qs_labels = list(_qs_options.keys())

                    _default_idx = 0
                    for _i, _p in enumerate(_qs_products):
                        if (_p.get("제품명") or "").strip() == (_qs_folder_name or "").strip():
                            _lbl = f"[{_p['id']}] {_p.get('제품명', '')}"
                            if _lbl in _qs_labels:
                                _default_idx = _qs_labels.index(_lbl)
                                break

                    _qsc1, _qsc2 = st.columns([4, 1])
                    with _qsc1:
                        _qs_sel = st.selectbox(
                            "연결할 제품 (폴더명과 일치하는 제품이 자동 추천됨)",
                            _qs_labels,
                            index=_default_idx if _qs_labels else 0,
                            key=f"qs_product_{_qs_folder_id}",
                        )
                    with _qsc2:
                        st.markdown("&nbsp;", unsafe_allow_html=True)
                        _qs_run = st.button(
                            "📥 연결 + 동기화",
                            key=f"qs_btn_{_qs_folder_id}",
                            type="primary",
                            use_container_width=True,
                        )

                    if _qs_run and _qs_sel:
                        _qs_pid = _qs_options[_qs_sel]
                        try:
                            with st.spinner(f"폴더 스캔 + DB 등록 중… (`{_qs_folder_name}`)"):
                                _qs_svc = build_service(account_label)
                                _qs_rows = scan_folder_to_파일_rows(_qs_svc, _qs_folder_id)
                                _qs_n = upsert_파일(_qs_pid, _qs_rows, account_label)
                                _qs_mapping_added = False
                                if not _get_acc_folder_qs(_qs_pid, account_label):
                                    _set_acc_folder_qs(_qs_pid, account_label, _qs_folder_id)
                                    _qs_mapping_added = True
                            _qs_msg = f"✅ {_qs_n}개 파일 동기화됨 (중복 자동 스킵)"
                            if _qs_mapping_added:
                                _qs_msg += f" · 매핑 추가됨"
                            else:
                                _qs_msg += f" · 매핑은 이미 존재 (덮어쓰지 않음)"
                            st.success(_qs_msg)
                        except Exception as _qse:
                            st.error(f"동기화 실패: {type(_qse).__name__}: {_qse}")

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

        # ── 파일 그리드 (이미지 / 동영상 / 기타 통합) ────────
        _IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp"}
        img_files   = [f for f in all_files if f.get("mimeType") in _IMAGE_MIMES]
        video_files = [f for f in all_files if (f.get("mimeType") or "").startswith("video/")]
        other_files = [
            f for f in all_files
            if f.get("mimeType") not in _IMAGE_MIMES
            and not (f.get("mimeType") or "").startswith("video/")
        ]

        if all_files:
            _cnt_parts = []
            if img_files:   _cnt_parts.append(f"📷 {len(img_files)}")
            if video_files: _cnt_parts.append(f"🎬 {len(video_files)}")
            if other_files: _cnt_parts.append(f"📄 {len(other_files)}")
            st.markdown(f"**🗂️ 파일** ({len(all_files)}개)  —  {'  ·  '.join(_cnt_parts)}")

            # 일괄 ZIP 다운로드 — 이미지 기본, 동영상 토글
            if img_files or video_files:
                bulk_download_zip(
                    files=img_files,
                    scope_key=f"gallery_drive_{account_label}_{folder_id}",
                    zip_name_prefix=f"drive_{account_label}",
                    default_account=account_label,
                    extra_files=video_files if video_files else None,
                    extra_label="동영상",
                )

            # 통합 그리드 — 이미지 → 동영상 → 기타 순으로 표시
            ordered = img_files + video_files + other_files
            ICOLS = 5
            i_cols = st.columns(ICOLS)
            for i, f in enumerate(ordered):
                fid  = f.get("id", "")
                name = f.get("name", "")
                mime = f.get("mimeType", "") or ""
                link = f.get("webViewLink", "")
                with i_cols[i % ICOLS]:
                    try:
                        if mime in _IMAGE_MIMES:
                            image_with_fallback(fid, size=300, scope_key="gallery_drive", alt=name)
                        elif mime.startswith("video/"):
                            video_thumb_with_play_overlay(fid, size=300, scope_key="gallery_drive", alt=name)
                        else:
                            file_icon_card(fid, name)
                    except Exception:
                        st.caption("로드 실패")
                    if link:
                        st.markdown(f"[{name}]({link})", help=name)
                    else:
                        st.caption(name)
                    if fid:
                        st.markdown(individual_download_link(fid))

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
                            st.session_state["scan_folder_id"] = folder_id_sync
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
                    _scan_acc    = st.session_state["scan_account"]
                    _scan_folder = st.session_state.get("scan_folder_id")
                    n = upsert_파일(sel_product_id, scan_rows, _scan_acc)

                    # 계정별_폴더_ids 매핑 동기화 — 이 계정에 매핑이 없으면 추가 (덮어쓰지 않음)
                    _mapping_added = False
                    if _scan_folder and not get_account_folder(sel_product_id, _scan_acc):
                        set_account_folder(sel_product_id, _scan_acc, _scan_folder)
                        _mapping_added = True

                    _msg = f"{n}개 저장 완료! (중복은 자동 스킵)"
                    if _mapping_added:
                        _msg += f" · 매핑 추가: {_scan_acc} → 이 폴더"
                    st.success(_msg)
                    st.session_state.pop("scan_rows", None)
                    st.session_state.pop("scan_folder_id", None)
                    st.rerun()
