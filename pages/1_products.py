"""페이지 1 — 상품 조회.

- 완성/진행중/미완성 3개 테이블로 분리 조회.
- 각 테이블 검색(이름·id selectbox) + 엠군상태 필터.
- 세 테이블 공통의 컬럼 표시 설정.
- 행 선택 → 상세 영역. 다른 테이블에서 선택 시 이전 선택 자동 해제.
- "이 제품으로 파이프라인 실행" 버튼.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from pipeline.supabase_read import (
    delete_임시_products,
    get_image_counts,
    list_products,
    list_엠군상태_values,
)

_COL_PREFS_FILE = Path(__file__).parent.parent / "settings_columns.json"

_COMP_DONE = "✅ 완성"
_COMP_PROG = "🟡 진행중"
_COMP_TODO = "⬛ 미완성"

_HELP_엠군상태 = (
    "**엠군상태** — `상품.엠군상태` 컬럼 값입니다.\n\n"
    "- **미시작** : 신규 등록 직후, 또는 자동 파이프라인을 한 번도 실행하지 않음 (NULL 포함)\n"
    "- **진행중** : 자동 파이프라인 실행 시작 시점에 자동 설정\n"
    "- **완료** : 자동 파이프라인이 마지막 단계까지 통과해 자동 설정\n\n"
    "제품 편집에서 수동으로도 바꿀 수 있습니다."
)

_HELP_완성도 = (
    "**완성도 기준** — 이미지·핵심 필드 입력 여부로 자동 판정합니다.\n\n"
    f"- {_COMP_DONE} : 이미지 1장 이상 + 카테고리 + 제품특징_bullet 모두 입력\n"
    f"- {_COMP_PROG} : 이미지는 있으나 카테고리·제품특징_bullet 중 하나 이상 비어 있음\n"
    f"- {_COMP_TODO} : 이미지 0장"
)


def _completeness(row: dict, image_count: int) -> str:
    has_image = image_count > 0
    if not has_image:
        return _COMP_TODO
    if bool(row.get("카테고리")) and bool(row.get("제품특징_bullet")):
        return _COMP_DONE
    return _COMP_PROG


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

# ── 데이터 로드 (페이지네이션으로 전체) ─────────────────
try:
    rows = list_products()
except Exception as e:
    st.error(f"Supabase 조회 실패: {type(e).__name__}: {e}")
    st.stop()

if not rows:
    st.warning("등록된 제품이 없습니다.")
    st.stop()

image_counts = get_image_counts()
for r in rows:
    r["_완성도"] = _completeness(r, image_counts.get(r["id"], 0))

n_done = sum(1 for r in rows if r["_완성도"] == _COMP_DONE)
n_prog = sum(1 for r in rows if r["_완성도"] == _COMP_PROG)
n_todo = sum(1 for r in rows if r["_완성도"] == _COMP_TODO)

st.write(
    f"총 **{len(rows)}**개  ·  "
    f"{_COMP_DONE} **{n_done}** · {_COMP_PROG} **{n_prog}** · {_COMP_TODO} **{n_todo}**"
)

# ── DataFrame 빌드 ────────────────────────────────────────
df_all = pd.DataFrame(rows)
df_all.insert(1, "🖼️이미지", df_all["id"].apply(lambda x: image_counts.get(x, 0)))
df_all.insert(2, "완성도", df_all["_완성도"])

visible_data_cols = [c for c in df_all.columns if not c.startswith("_")]
for col in visible_data_cols:
    if df_all[col].apply(lambda x: isinstance(x, (dict, list))).any():
        df_all[col] = df_all[col].apply(
            lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, (dict, list)) else x
        )

all_cols = visible_data_cols

# ── 컬럼 체크박스 초기화 (세션 첫 진입 시) ──
if "col_prefs_loaded" not in st.session_state:
    saved = _load_col_prefs()
    visible_set = set(saved) if saved is not None else set(all_cols)
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


# ── 공통 컬럼 표시 설정 ──
with st.expander("🔧 컬럼 표시 설정 (세 테이블에 공통 적용)", expanded=False):
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

visible_cols = [c for c in all_cols if st.session_state.get(f"col_check_{c}", True)]
if not visible_cols:
    visible_cols = all_cols

# 완성도 기준 안내 (popover)
with st.popover("❓ 완성도 기준 보기"):
    st.markdown(_HELP_완성도)

# ── 테이블별 데이터 분리 ──
df_done = df_all[df_all["완성도"] == _COMP_DONE].reset_index(drop=True)
df_prog = df_all[df_all["완성도"] == _COMP_PROG].reset_index(drop=True)
df_todo = df_all[df_all["완성도"] == _COMP_TODO].reset_index(drop=True)

# ── 행 선택 동기화용 세션 상태 ──
if "_prod_selections" not in st.session_state:
    st.session_state._prod_selections = {"done": [], "prog": [], "todo": []}
if "_prod_table_keys" not in st.session_state:
    st.session_state._prod_table_keys = {"done": 0, "prog": 0, "todo": 0}


def _render_table(df_sub: pd.DataFrame, key: str, title: str):
    """1개 완성도 그룹 테이블 렌더. (event, filtered_view) 반환. 빈 결과는 (None, view)."""
    with st.container(border=True):
        st.markdown(f"### {title}  ·  {len(df_sub)}건")

        ids = df_sub["id"].tolist() if not df_sub.empty else []
        name_map = (
            df_sub.set_index("id")["제품명"].fillna("").to_dict()
            if not df_sub.empty else {}
        )
        options = [None] + ids

        def _fmt(pid):
            if pid is None:
                return ""
            return f"[{pid}] {name_map.get(pid, '')}"

        c1, c2 = st.columns([3, 1])
        with c1:
            sel_id = st.selectbox(
                "🔍 검색 (제품명 또는 id 일부 입력)",
                options=options,
                format_func=_fmt,
                key=f"search_{key}",
            )
        with c2:
            status = st.selectbox(
                "엠군상태",
                list_엠군상태_values(),
                key=f"status_{key}",
                help=_HELP_엠군상태,
            )

        view = df_sub
        if sel_id is not None:
            view = view[view["id"] == sel_id]
        if status and status != "전체":
            if status == "미시작":
                view = view[(view["엠군상태"] == "미시작") | (view["엠군상태"].isna())]
            else:
                view = view[view["엠군상태"] == status]
        view = view.reset_index(drop=True)

        if view.empty:
            st.caption("조건에 맞는 제품이 없습니다.")
            return None, view

        df_key = f"df_{key}_v{st.session_state._prod_table_keys[key]}"
        event = st.dataframe(
            view[visible_cols],
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key=df_key,
            height=420,
        )
        return event, view


event_done, view_done = _render_table(df_done, "done", _COMP_DONE)
event_prog, view_prog = _render_table(df_prog, "prog", _COMP_PROG)
event_todo, view_todo = _render_table(df_todo, "todo", _COMP_TODO)

# ── 행 클릭 = 자동 편집 페이지 전환 ──
prev_sel = dict(st.session_state._prod_selections)
curr_sel = {
    "done": list(event_done.selection.rows) if event_done is not None else [],
    "prog": list(event_prog.selection.rows) if event_prog is not None else [],
    "todo": list(event_todo.selection.rows) if event_todo is not None else [],
}
view_map = {"done": view_done, "prog": view_prog, "todo": view_todo}

# 새로 selection이 생긴 (이전과 다르고 비어있지 않은) 테이블 찾기
changed = [
    k for k in ("done", "prog", "todo")
    if curr_sel[k] != prev_sel[k] and curr_sel[k]
]

if changed:
    active_table = changed[0]
    view = view_map[active_table]
    if view is not None and not view.empty:
        chosen_id = int(view.iloc[curr_sel[active_table][0]]["id"])
        # 다음 페이지 진입 시 새 dataframe key로 그려져 selection 자동 클리어
        for k in ("done", "prog", "todo"):
            st.session_state._prod_table_keys[k] += 1
        st.session_state._prod_selections = {"done": [], "prog": [], "todo": []}
        st.session_state["edit_mode"] = "edit"
        st.session_state["edit_product_id"] = chosen_id
        st.switch_page("pages/2_product_edit.py")
else:
    st.session_state._prod_selections = curr_sel

st.caption("💡 위 테이블에서 행을 클릭하면 해당 제품의 편집 페이지로 이동합니다.")
