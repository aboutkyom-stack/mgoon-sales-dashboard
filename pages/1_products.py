"""페이지 1 — 상품 조회.

- 상품 테이블 전체 조회. 엠군상태·이름 검색 필터.
- 제품 선택 → 상세 + 이미지(상품_파일)
- "이 제품으로 파이프라인 실행" 버튼
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from pipeline.supabase_read import (
    delete_임시_products,
    get_files,
    get_image_counts,
    get_product_spec,
    get_thumbnail_url,
    list_products,
    list_엠군상태_values,
)

# 컬럼 가시성 설정 파일
_COL_PREFS_FILE = Path(__file__).parent.parent / "settings_columns.json"
_HIDDEN_BY_DEFAULT = {"구_카탈로그_id", "구_v2_id"}


def _load_col_prefs() -> list[str] | None:
    try:
        data = json.loads(_COL_PREFS_FILE.read_text(encoding="utf-8"))
        return data.get("products_visible")
    except Exception:
        return None


def _save_col_prefs(cols: list[str]) -> None:
    try:
        existing: dict = {}
        if _COL_PREFS_FILE.exists():
            existing = json.loads(_COL_PREFS_FILE.read_text(encoding="utf-8"))
        existing["products_visible"] = cols
        _COL_PREFS_FILE.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


# ── 진입 시 고아 임시 레코드 자동 정리 ──────────────────────
# 신규 등록 페이지에서 저장 없이 이탈한 임시 제품들을 모두 삭제.
# 편집 세션도 함께 초기화 (현재 편집 중이던 임시 제품도 삭제됐을 수 있음).
try:
    _deleted_temp = delete_임시_products()
    if _deleted_temp > 0:
        st.session_state.pop("_temp_product_id", None)
        st.session_state.pop("edit_product_id", None)
        st.session_state.pop("edit_mode", None)
        st.toast(f"🧹 임시 제품 {_deleted_temp}개 정리됨")
except Exception:
    pass

st.title("📦 제품 조회")
st.caption("🗄️ DB — 상품, 상품_파일 테이블")

if st.button("➕ 신규 제품 등록", type="primary"):
    st.session_state["edit_mode"] = "new"
    st.session_state.pop("edit_product_id", None)
    st.switch_page("pages/2_product_edit.py")

# ── 필터 ──────────────────────────────────────────────────
with st.container(border=True):
    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        search = st.text_input("이름 검색", placeholder="제품명 일부")
    with c2:
        mgoon_status = st.selectbox("엠군상태", list_엠군상태_values())
    with c3:
        limit = st.number_input("최대 개수", min_value=50, max_value=1200, value=1200, step=50)

# ── 조회 ──────────────────────────────────────────────────
try:
    rows = list_products(
        search=search,
        엠군상태=mgoon_status if mgoon_status != "전체" else None,
        limit=int(limit),
    )
except Exception as e:
    st.error(f"Supabase 조회 실패: {type(e).__name__}: {e}")
    st.stop()

if not rows:
    st.warning("조건에 맞는 제품이 없습니다.")
    st.stop()

# ── 이미지 수 배지 ────────────────────────────────────────
image_counts = get_image_counts()

st.write(f"총 **{len(rows)}**개  ·  이미지 있는 상품: **{len(image_counts)}**개")

# ── 전체 목록 dataframe 빌드 ──────────────────────────────
df = pd.DataFrame(rows)
df.insert(1, "🖼️이미지", df["id"].apply(lambda x: image_counts.get(x, 0)))
for col in df.columns:
    if df[col].apply(lambda x: isinstance(x, (dict, list))).any():
        df[col] = df[col].apply(
            lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, (dict, list)) else x
        )

all_cols = df.columns.tolist()

# ── 컬럼 체크박스 초기화 (세션 첫 진입 시 파일 → 없으면 기본값) ──
if "col_prefs_loaded" not in st.session_state:
    saved = _load_col_prefs()
    visible_set = set(saved) if saved is not None else set(all_cols) - _HIDDEN_BY_DEFAULT
    for col in all_cols:
        key = f"col_check_{col}"
        if key not in st.session_state:
            st.session_state[key] = col in visible_set
    st.session_state["col_prefs_loaded"] = True


def _on_col_change() -> None:
    new_vis = [c for c in all_cols if st.session_state.get(f"col_check_{c}", True)]
    _save_col_prefs(new_vis)


def _select_all() -> None:
    for col in all_cols:
        st.session_state[f"col_check_{col}"] = True
    _save_col_prefs(all_cols)


def _deselect_all() -> None:
    for col in all_cols:
        st.session_state[f"col_check_{col}"] = False
    _save_col_prefs([])


# ── 컬럼 표시 설정 UI (체크박스 그리드) ──────────────────
with st.expander("🔧 컬럼 표시 설정", expanded=False):
    b1, b2, _ = st.columns([1, 1, 6])
    b1.button("전체 선택", on_click=_select_all, key="col_all")
    b2.button("전체 해제", on_click=_deselect_all, key="col_none")
    st.divider()
    NCOLS = 6
    for i in range(0, len(all_cols), NCOLS):
        chunk = all_cols[i : i + NCOLS]
        row_cols = st.columns(NCOLS)
        for j, col in enumerate(chunk):
            row_cols[j].checkbox(col, key=f"col_check_{col}", on_change=_on_col_change)

# ── 가시 컬럼 필터 후 dataframe 렌더 ─────────────────────
visible_cols = [c for c in all_cols if st.session_state.get(f"col_check_{c}", True)]
if not visible_cols:
    visible_cols = all_cols  # 전체 해제 시 안전 fallback

df_view = df[visible_cols]

event = st.dataframe(
    df_view, use_container_width=True, hide_index=True,
    on_select="rerun", selection_mode="single-row",
)
st.caption(
    "ℹ️ 기본 숨김 컬럼: **구_카탈로그_id** (동료 DB `product_catalog.id` 원본 추적) · "
    "**구_v2_id** (동료 DB `products_v2.id` 원본 추적) — "
    "마이그레이션 스크립트(db/run_migration.py) 1회 실행 시에만 사용. "
    "현재 어떤 페이지나 동료 프로그램에서도 읽지 않음."
)

st.divider()

selected_rows = event.selection.rows
if not selected_rows:
    st.info("👆 위 테이블에서 행을 클릭하면 상세 정보를 확인할 수 있습니다.")
    st.stop()

chosen_idx = selected_rows[0]
chosen_row = rows[chosen_idx]
chosen_id = int(chosen_row["id"])

img_count = image_counts.get(chosen_id, 0)
img_badge = f"  ·  🖼️ 이미지 {img_count}장" if img_count else "  ·  이미지 없음"
st.subheader(f"#{chosen_id} · {chosen_row.get('제품명')}{img_badge}")

# ── 제품 액션 버튼 ────────────────────────────────────────
a1, a2, _ = st.columns([1, 1, 4])
if a1.button("✏️ 스펙 수정", type="primary", use_container_width=True, key="btn_edit_product"):
    st.session_state["edit_mode"]       = "edit"
    st.session_state["edit_product_id"] = chosen_id
    st.switch_page("pages/2_product_edit.py")

# ── 상세 스펙 조회 (파이프라인 진입용) ─────────────────────
try:
    spec = get_product_spec(chosen_id)
except Exception as e:
    st.error(f"상세 조회 실패: {type(e).__name__}: {e}")
    spec = None

# ── 이미지 / 파일 ─────────────────────────────────────────
drive_files = get_files(chosen_id)
images = [f for f in drive_files if f.get("파일_유형") == "image" and f.get("드라이브_파일_id")]
others = [f for f in drive_files if f not in images]

if images:
    st.markdown(f"**이미지 ({len(images)}장)**")
    cols = st.columns(min(len(images), 4))
    for i, f in enumerate(images):
        fid = f["드라이브_파일_id"]
        with cols[i % 4]:
            try:
                st.image(
                    get_thumbnail_url(fid, 400),
                    caption=f.get("파일명", ""),
                    use_container_width=True,
                )
                st.markdown(f"[원본](https://drive.google.com/uc?export=view&id={fid})")
            except Exception:
                st.caption(f"로드 실패: {fid}")

if others:
    st.markdown("**기타 파일**")
    for f in others:
        url = f.get("드라이브_url")
        label = f"`{f.get('파일명')}` · {f.get('파일_유형')} · 상태={f.get('상태')}"
        st.markdown(f"{label} → [Drive 열기]({url})" if url else label)

if not drive_files:
    st.caption("등록된 파일 없음  ·  [🖼️ 갤러리](3_gallery)에서 Drive 동기화 가능")

# ── 파이프라인 진입 ───────────────────────────────────────
st.divider()
if st.button("🧪 이 제품으로 파이프라인 실행", type="primary", use_container_width=True):
    st.session_state["pipeline_product_id"] = chosen_id
    st.session_state["pipeline_product_spec"] = spec or chosen_row
    for k in ("current_run_id", "targets_01", "selected_target", "positioning_02"):
        st.session_state.pop(k, None)
    st.switch_page("pages/2_pipeline.py")
