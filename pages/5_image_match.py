"""페이지 5 — 이미지-상품 매칭.

상품_id가 NULL인 미매칭 이미지를 상품에 연결하거나,
잘못 연결된 이미지의 상품_id를 변경합니다.
"""
from __future__ import annotations

import streamlit as st

from pipeline.supabase_read import _client, get_thumbnail_url

st.title("🔗 이미지-상품 매칭")
st.caption("🗄️ DB — 상품_파일 테이블의 상품_id 수정")

COLS = 4


# ── 헬퍼 ────────────────────────────────────────────────────

def _chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def _load_unmatched() -> list[dict]:
    res = (
        _client()
        .table("상품_파일")
        .select("id, 파일명, 드라이브_파일_id, 계정")
        .eq("파일_유형", "image")
        .is_("상품_id", "null")
        .not_.is_("드라이브_파일_id", "null")
        .order("id")
        .execute()
    )
    return res.data or []


def _load_all_images(limit: int = 500) -> list[dict]:
    res = (
        _client()
        .table("상품_파일")
        .select("id, 상품_id, 파일명, 드라이브_파일_id, 계정, 상품(id, 제품명)")
        .eq("파일_유형", "image")
        .not_.is_("드라이브_파일_id", "null")
        .order("id")
        .limit(limit)
        .execute()
    )
    rows = res.data or []
    result = []
    for r in rows:
        flat = dict(r)
        product = flat.pop("상품", None) or {}
        flat["제품명"] = product.get("제품명", "")
        result.append(flat)
    return result


def _update_match(파일_ids: list[int], 상품_id: int) -> None:
    _client().table("상품_파일").update({"상품_id": 상품_id}).in_("id", 파일_ids).execute()


def _clear_match(파일_ids: list[int]) -> None:
    _client().table("상품_파일").update({"상품_id": None}).in_("id", 파일_ids).execute()


# ── 상품 목록 캐싱 ──────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _cached_products() -> list[dict]:
    """매칭 드롭다운용 전체 상품 목록 (id 오름차순). 1,000행 제한 우회 페이지네이션."""
    rows, start, CHUNK = [], 0, 1000
    while True:
        batch = (
            _client()
            .table("상품")
            .select("id, 제품명")
            .order("id")
            .range(start, start + CHUNK - 1)
            .execute()
            .data
            or []
        )
        rows.extend(batch)
        if len(batch) < CHUNK:
            break
        start += CHUNK
    return rows


products      = _cached_products()
# selectbox용 options: None은 "선택 안 함"
pid_options   = [None] + [p["id"] for p in products]
pid_label_map = {p["id"]: f"[{p['id']}] {p.get('제품명', '')}" for p in products}


def _fmt(pid):
    if pid is None:
        return "— 선택 안 함 —"
    return pid_label_map.get(pid, f"ID {pid}")


# ── 탭 ──────────────────────────────────────────────────────

tab_unmatched, tab_all = st.tabs(["❌ 미매칭", "🔄 전체 재매칭"])


# ═══════════════════════════════════════════════════════════
# Tab 1 — 미매칭
# ═══════════════════════════════════════════════════════════
with tab_unmatched:
    col_h, col_r = st.columns([5, 1])
    with col_r:
        if st.button("🔄 새로고침", key="btn_refresh_un"):
            st.cache_data.clear()
            st.rerun()

    images = _load_unmatched()

    if not images:
        st.success("미매칭 이미지가 없습니다. 🎉")
    else:
        st.info(f"미매칭 이미지: **{len(images)}**건 — 체크박스로 선택 후 상품 지정")

        # 일괄 매칭 컨트롤
        with st.container(border=True):
            c1, c2 = st.columns([4, 2])
            with c1:
                bulk_pid = st.selectbox(
                    "매칭할 상품",
                    options=pid_options,
                    format_func=_fmt,
                    key="bulk_pid",
                )
            with c2:
                st.write("")  # 높이 맞춤
                bulk_btn = st.button(
                    "✅ 선택 이미지 일괄 매칭",
                    key="btn_bulk",
                    type="primary",
                    use_container_width=True,
                )

        # 이미지 그리드
        selected_ids: list[int] = []
        for chunk in _chunks(images, COLS):
            cols = st.columns(COLS)
            for j, img in enumerate(chunk):
                fid      = img["id"]
                fname    = img.get("파일명") or f"파일_{fid}"
                drive_id = img.get("드라이브_파일_id", "")
                with cols[j]:
                    if drive_id:
                        st.image(get_thumbnail_url(drive_id, 200), use_container_width=True)
                    else:
                        st.markdown("*(미리보기 없음)*")
                    checked = st.checkbox(fname[:28], key=f"chk_{fid}")
                    if checked:
                        selected_ids.append(fid)
                    if img.get("계정"):
                        st.caption(f"📧 {img['계정']}")

        if bulk_btn:
            if not selected_ids:
                st.warning("이미지를 먼저 선택하세요.")
            elif bulk_pid is None:
                st.warning("매칭할 상품을 선택하세요.")
            else:
                with st.spinner("저장 중…"):
                    _update_match(selected_ids, bulk_pid)
                st.success(f"{len(selected_ids)}건 → [{bulk_pid}] {pid_label_map.get(bulk_pid, '')} 매칭 완료!")
                st.cache_data.clear()
                st.rerun()


# ═══════════════════════════════════════════════════════════
# Tab 2 — 전체 재매칭
# ═══════════════════════════════════════════════════════════
with tab_all:
    col_h2, col_r2 = st.columns([5, 1])
    with col_r2:
        if st.button("🔄 새로고침", key="btn_refresh_all"):
            st.cache_data.clear()
            st.rerun()

    st.caption("현재 연결된 상품을 변경하거나 연결을 해제할 수 있습니다.")

    # 필터
    with st.container(border=True):
        cf1, cf2 = st.columns(2)
        with cf1:
            kw = st.text_input("파일명 / 제품명 검색", key="all_kw")
        with cf2:
            mf = st.selectbox("매칭 상태", ["전체", "매칭됨", "미매칭"], key="all_mf")

    all_images = _load_all_images()

    view = all_images.copy()
    if kw:
        lo = kw.lower()
        view = [i for i in view if lo in (i.get("파일명") or "").lower() or lo in (i.get("제품명") or "").lower()]
    if mf == "매칭됨":
        view = [i for i in view if i.get("상품_id")]
    elif mf == "미매칭":
        view = [i for i in view if not i.get("상품_id")]

    st.write(f"표시: **{len(view)}**건")

    for chunk in _chunks(view, COLS):
        cols = st.columns(COLS)
        for j, img in enumerate(chunk):
            fid         = img["id"]
            fname       = img.get("파일명") or f"파일_{fid}"
            drive_id    = img.get("드라이브_파일_id", "")
            current_pid = img.get("상품_id")
            current_nm  = img.get("제품명") or "미매칭"

            with cols[j]:
                if drive_id:
                    st.image(get_thumbnail_url(drive_id, 200), use_container_width=True)
                else:
                    st.markdown("*(미리보기 없음)*")

                st.caption(fname[:28])
                if current_pid:
                    st.caption(f"현재: **[{current_pid}]** {current_nm}")
                else:
                    st.caption("현재: *미매칭*")

                default_idx = next(
                    (k for k, pid in enumerate(pid_options) if pid == current_pid),
                    0,
                )
                new_pid = st.selectbox(
                    "상품",
                    options=pid_options,
                    index=default_idx,
                    format_func=_fmt,
                    key=f"sel_{fid}",
                    label_visibility="collapsed",
                )
                if st.button("저장", key=f"save_{fid}", use_container_width=True):
                    if new_pid == current_pid:
                        st.info("변경 없음")
                    elif new_pid is None:
                        _clear_match([fid])
                        st.success("연결 해제됨")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        _update_match([fid], new_pid)
                        st.success("저장!")
                        st.cache_data.clear()
                        st.rerun()
