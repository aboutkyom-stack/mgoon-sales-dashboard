"""페이지 1 — 상품 조회.

- 완성/진행중/일반/테스트 4개 테이블로 분리 조회. (테스트 = is_test=True)
- 각 테이블 검색(이름·id selectbox) + 엠군상태 필터.
- 전체 테이블 공통의 컬럼 표시 설정.
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
    set_엠군작업대상,
    set_is_test,
)

_COL_PREFS_FILE = Path(__file__).parent.parent / "settings_columns.json"

_COMP_DONE = "✅ 완성"
_COMP_PROG = "🟡 진행중"
_COMP_TODO = "⬛ 일반"
_COMP_TEST = "🧪 테스트"

# 화면에 노출하지 않는 컬럼 (DB 원본 또는 표시용으로 대체된 컬럼)
_HIDDEN_COLS = {"엠군작업대상", "is_test"}

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
    f"- {_COMP_TODO} : 이미지 0장 (아직 작업 시작 전)"
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

n_done = sum(1 for r in rows if r["_완성도"] == _COMP_DONE and not r.get("is_test"))
n_prog = sum(1 for r in rows if r["_완성도"] == _COMP_PROG and not r.get("is_test"))
n_todo = sum(1 for r in rows if r["_완성도"] == _COMP_TODO and not r.get("is_test"))
n_test = sum(1 for r in rows if r.get("is_test"))

st.write(
    f"총 **{len(rows)}**개  ·  "
    f"{_COMP_DONE} **{n_done}** · {_COMP_PROG} **{n_prog}** · {_COMP_TODO} **{n_todo}** · "
    f"{_COMP_TEST} **{n_test}**"
)

# ── DataFrame 빌드 ────────────────────────────────────────
df_all = pd.DataFrame(rows)
df_all.insert(1, "🖼️이미지", df_all["id"].apply(lambda x: image_counts.get(x, 0)))
df_all.insert(2, "완성도", df_all["_완성도"])
if "엠군작업대상" in df_all.columns:
    df_all.insert(3, "🎯엠군 대상", df_all["엠군작업대상"].apply(
        lambda x: "✅" if x else "⬛"
    ))

visible_data_cols = [
    c for c in df_all.columns
    if not c.startswith("_") and c not in _HIDDEN_COLS
]
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
with st.expander("🔧 컬럼 표시 설정 (전체 테이블에 공통 적용)", expanded=False):
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
# 테스트 레코드는 완성/진행중/일반에서 제외하고 테스트 박스에만 표시
if "is_test" in df_all.columns:
    _is_test = df_all["is_test"] == True
else:
    _is_test = pd.Series([False] * len(df_all), index=df_all.index)

df_done = df_all[~_is_test & (df_all["완성도"] == _COMP_DONE)].reset_index(drop=True)
df_prog = df_all[~_is_test & (df_all["완성도"] == _COMP_PROG)].reset_index(drop=True)
df_todo = df_all[~_is_test & (df_all["완성도"] == _COMP_TODO)].reset_index(drop=True)
df_test = df_all[_is_test].reset_index(drop=True)

_TABLE_KEYS = ("done", "prog", "todo", "test")

# ── 행 선택 동기화용 세션 상태 ──
if "_prod_selections" not in st.session_state:
    st.session_state._prod_selections = {k: [] for k in _TABLE_KEYS}
else:
    for k in _TABLE_KEYS:
        st.session_state._prod_selections.setdefault(k, [])
if "_prod_table_keys" not in st.session_state:
    st.session_state._prod_table_keys = {k: 0 for k in _TABLE_KEYS}
else:
    for k in _TABLE_KEYS:
        st.session_state._prod_table_keys.setdefault(k, 0)

# ─── D안: 일괄 작업대상 토글 — multiselect 카운터 (이 블록 통째로 삭제 가능) ───
if "_toggle_counter" not in st.session_state:
    st.session_state._toggle_counter = {k: 0 for k in _TABLE_KEYS}
else:
    for k in _TABLE_KEYS:
        st.session_state._toggle_counter.setdefault(k, 0)
# ─── /D안 끝 ───

# ─── 🧪 테스트 일괄 토글 — multiselect 카운터 ───
if "_test_toggle_counter" not in st.session_state:
    st.session_state._test_toggle_counter = {k: 0 for k in _TABLE_KEYS}
else:
    for k in _TABLE_KEYS:
        st.session_state._test_toggle_counter.setdefault(k, 0)


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

        c1, c2, c3 = st.columns([3, 1, 1])
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
        with c3:
            작업대상_filter = st.selectbox(
                "🎯엠군 대상",
                ["전체", "✅ 대상", "⬛ 제외"],
                key=f"작업대상_{key}",
            )

        view = df_sub
        if sel_id is not None:
            view = view[view["id"] == sel_id]
        if status and status != "전체":
            if status == "미시작":
                view = view[(view["엠군상태"] == "미시작") | (view["엠군상태"].isna())]
            else:
                view = view[view["엠군상태"] == status]
        if 작업대상_filter == "✅ 대상" and "엠군작업대상" in view.columns:
            view = view[view["엠군작업대상"] == True]
        elif 작업대상_filter == "⬛ 제외" and "엠군작업대상" in view.columns:
            view = view[(view["엠군작업대상"] == False) | (view["엠군작업대상"].isna())]
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

        # ─── D안: 일괄 엠군 대상 토글 (이 블록 통째로 삭제 가능) ───
        if "엠군작업대상" in view.columns:
            with st.expander("🎯 엠군 대상 일괄 토글", expanded=(key == "todo")):
                option_ids = view["id"].tolist()
                name_local = view.set_index("id")["제품명"].fillna("").to_dict()
                on_set = set(view[view["엠군작업대상"] == True]["id"].tolist())

                def _fmt_toggle(pid: int) -> str:
                    mark = "✅" if pid in on_set else "⬛"
                    return f"{mark} [{pid}] {name_local.get(pid, '')}"

                ms_key = f"toggle_ms_{key}_v{st.session_state._toggle_counter[key]}"
                selected = st.multiselect(
                    "토글할 제품 선택 (제품명 일부 입력 가능)",
                    options=option_ids,
                    format_func=_fmt_toggle,
                    key=ms_key,
                )
                bc1, bc2, _ = st.columns([1, 1, 4])
                if bc1.button(
                    "✅ 일괄 ON",
                    key=f"toggle_on_{key}",
                    disabled=not selected,
                    type="primary",
                ):
                    for pid in selected:
                        set_엠군작업대상(int(pid), True)
                    st.toast(f"✅ {len(selected)}개 엠군 대상 ON")
                    st.session_state._toggle_counter[key] += 1
                    st.rerun()
                if bc2.button(
                    "⬛ 일괄 OFF",
                    key=f"toggle_off_{key}",
                    disabled=not selected,
                ):
                    for pid in selected:
                        set_엠군작업대상(int(pid), False)
                    st.toast(f"⬛ {len(selected)}개 엠군 대상 OFF")
                    st.session_state._toggle_counter[key] += 1
                    st.rerun()
        # ─── /D안 끝 ───

        # ─── 🧪 테스트 레코드 일괄 토글 ───
        if "is_test" in view.columns:
            _expand_test = (key == "test")  # 테스트 박스에서는 펼쳐서 OFF(운영 승격) 편하게
            with st.expander("🧪 테스트 레코드 일괄 토글", expanded=_expand_test):
                t_option_ids = view["id"].tolist()
                t_name_local = view.set_index("id")["제품명"].fillna("").to_dict()
                t_on_set = set(view[view["is_test"] == True]["id"].tolist())

                def _fmt_test_toggle(pid: int) -> str:
                    mark = "🧪" if pid in t_on_set else "⬛"
                    return f"{mark} [{pid}] {t_name_local.get(pid, '')}"

                tms_key = f"test_toggle_ms_{key}_v{st.session_state._test_toggle_counter[key]}"
                t_selected = st.multiselect(
                    "토글할 제품 선택 (제품명 일부 입력 가능)",
                    options=t_option_ids,
                    format_func=_fmt_test_toggle,
                    key=tms_key,
                )
                tc1, tc2, _ = st.columns([1, 1, 4])
                if tc1.button(
                    "🧪 테스트로 이동",
                    key=f"test_on_{key}",
                    disabled=not t_selected,
                    type="primary",
                    help="선택한 제품의 is_test=True → 🧪 테스트 박스로 이동",
                ):
                    for pid in t_selected:
                        set_is_test(int(pid), True)
                    st.toast(f"🧪 {len(t_selected)}개 테스트로 이동")
                    st.session_state._test_toggle_counter[key] += 1
                    st.rerun()
                if tc2.button(
                    "⬛ 운영으로 복귀",
                    key=f"test_off_{key}",
                    disabled=not t_selected,
                    help="선택한 제품의 is_test=False → 완성/진행중/일반 박스로 복귀",
                ):
                    for pid in t_selected:
                        set_is_test(int(pid), False)
                    st.toast(f"⬛ {len(t_selected)}개 운영으로 복귀")
                    st.session_state._test_toggle_counter[key] += 1
                    st.rerun()

        return event, view


event_done, view_done = _render_table(df_done, "done", _COMP_DONE)
event_prog, view_prog = _render_table(df_prog, "prog", _COMP_PROG)
event_todo, view_todo = _render_table(df_todo, "todo", _COMP_TODO)
event_test, view_test = _render_table(df_test, "test", _COMP_TEST)

# ── 행 클릭 = 자동 편집 페이지 전환 ──
prev_sel = dict(st.session_state._prod_selections)
_events = {
    "done": event_done,
    "prog": event_prog,
    "todo": event_todo,
    "test": event_test,
}
curr_sel = {
    k: (list(ev.selection.rows) if ev is not None else [])
    for k, ev in _events.items()
}
view_map = {
    "done": view_done,
    "prog": view_prog,
    "todo": view_todo,
    "test": view_test,
}

# 새로 selection이 생긴 (이전과 다르고 비어있지 않은) 테이블 찾기
changed = [
    k for k in _TABLE_KEYS
    if curr_sel[k] != prev_sel.get(k, []) and curr_sel[k]
]

if changed:
    active_table = changed[0]
    view = view_map[active_table]
    if view is not None and not view.empty:
        chosen_id = int(view.iloc[curr_sel[active_table][0]]["id"])
        # 다음 페이지 진입 시 새 dataframe key로 그려져 selection 자동 클리어
        for k in _TABLE_KEYS:
            st.session_state._prod_table_keys[k] += 1
        st.session_state._prod_selections = {k: [] for k in _TABLE_KEYS}
        st.session_state["edit_mode"] = "edit"
        st.session_state["edit_product_id"] = chosen_id
        st.switch_page("pages/2_product_edit.py")
else:
    st.session_state._prod_selections = curr_sel

st.caption("💡 위 테이블에서 행을 클릭하면 해당 제품의 편집 페이지로 이동합니다.")
