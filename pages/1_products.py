"""페이지 1 — 상품 조회.

- 워크플로 단계별 4개 박스 + 테스트 박스로 분리 조회.
  · ⬛ 일반 / 🟠 기초자료 입력완료 / 🔵 엠군 작업 완료 / ✅ 상세페이지 생성 완료 / 🧪 테스트
- 박스 분류는 `상품` 테이블의 `*_완료_at` 토글로 결정 (`pipeline.supabase_read.compute_워크플로_단계`).
- 각 박스마다 🔄 변경 감지 컬럼 + 자동 정렬 (변경된 행 상단).
- 페이지 상단에 다음 단계 액션 대기 카운트 배너.
- 행 선택 → 편집 페이지 자동 이동.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from pipeline.supabase_read import (
    WORKFLOW_BOX_BASIC,
    WORKFLOW_BOX_DETAIL,
    WORKFLOW_BOX_MGOON,
    WORKFLOW_BOX_NONE,
    compute_변경_diff,
    compute_워크플로_단계,
    delete_임시_products,
    format_file_counts,
    get_file_counts_by_type,
    get_files_by_products,
    get_run_counts_by_product,
    list_products,
    list_엠군상태_values,
    set_엠군작업대상,
    set_is_test,
)

_COL_PREFS_FILE = Path(__file__).parent.parent / "settings_columns.json"

# 워크플로 박스 라벨 (compute_워크플로_단계 반환 키와 동일 매핑)
_BOX_TODO   = f"⬛ 일반"
_BOX_BASIC  = f"🟠 기초자료 입력완료"
_BOX_MGOON  = f"🔵 엠군 작업 완료"
_BOX_DETAIL = f"✅ 상세페이지 생성 완료"
_BOX_TEST   = f"🧪 테스트"

# 박스 → (compute_워크플로_단계 키, 다음 단계 액션명 또는 None)
_BOX_TABLE: list[tuple[str, str, str | None]] = [
    (_BOX_TODO,   WORKFLOW_BOX_NONE,   None),
    (_BOX_BASIC,  WORKFLOW_BOX_BASIC,  "엠군 파이프라인 실행"),
    (_BOX_MGOON,  WORKFLOW_BOX_MGOON,  "상세페이지 제작"),
    (_BOX_DETAIL, WORKFLOW_BOX_DETAIL, None),
]
# 행 데이터에 부여할 박스 키 컬럼명 (내부 분류용 — 화면 노출 X)
_STAGE_KEY = "_단계"
# 단계 → 직전 단계(snapshot 비교 기준). 후속작업자 관점에서 자기 박스의 "이전 단계 snapshot" 변화를 본다.
#   - 🟠 박스 = 다음 작업 = 엠군 돌리는 사람 → 본인이 봐야 할 변동 = 기초입력 snapshot
#   - 🔵 박스 = 다음 작업 = 상세페이지 만드는 사람 → 엠군 snapshot 변동
#   - ✅ 박스 = 현재 후속자 없음 → 상세페이지 snapshot (향후 채널 단계에서 사용)
#   - ⬛ 박스 = 토글 OFF → 비교 대상 없음
_BOX_TO_SNAPSHOT_STAGE: dict[str, str | None] = {
    WORKFLOW_BOX_NONE:   None,
    WORKFLOW_BOX_BASIC:  "기초입력",
    WORKFLOW_BOX_MGOON:  "엠군",
    WORKFLOW_BOX_DETAIL: "상세페이지",
}

# 화면에 노출하지 않는 컬럼 (DB 원본 또는 표시용으로 대체된 컬럼)
_HIDDEN_COLS = {
    "엠군작업대상", "is_test",
    "기초입력_완료_at", "기초입력_완료_snapshot",
    "엠군_완료_at", "엠군_완료_snapshot",
    "상세페이지_완료_at", "상세페이지_완료_snapshot",
    _STAGE_KEY,
}

_HELP_엠군상태 = (
    "**엠군상태** — `상품.엠군상태` 컬럼 값입니다.\n\n"
    "- **미시작** : 신규 등록 직후, 또는 자동 파이프라인을 한 번도 실행하지 않음 (NULL 포함)\n"
    "- **진행중** : 자동 파이프라인 실행 시작 시점에 자동 설정\n"
    "- **완료** : 자동 파이프라인이 마지막 단계까지 통과해 자동 설정\n\n"
    "제품 편집에서 수동으로도 바꿀 수 있습니다."
)

_HELP_워크플로 = (
    "**워크플로 단계 박스** — 토글로 단계 진행을 명시합니다.\n\n"
    f"- {_BOX_TODO} : 모든 토글 OFF (작업 시작 전)\n"
    f"- {_BOX_BASIC} : 기초입력 토글 ON · 엠군 토글 OFF → **다음 작업 = 엠군 파이프라인 실행**\n"
    f"- {_BOX_MGOON} : 엠군 토글 ON · 상세페이지 토글 OFF → **다음 작업 = 상세페이지 제작**\n"
    f"- {_BOX_DETAIL} : 상세페이지 토글 ON\n"
    f"- {_BOX_TEST} : `is_test=True` (운영 자료와 분리)\n\n"
    "각 토글 ON 시점의 핵심 필드를 박제(snapshot)해서, 이후 값이 바뀌면 "
    "후속 작업자 화면에 🔄 변경 알림이 표시됩니다."
)


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


def _load_box_order_reversed() -> bool:
    # 기본값 True = 역배열 (✅ 상세 → 🔵 엠군 → 🟠 기초 → ⬛ 일반).
    # 후행 단계(완료된 작업)가 위로 가는 게 운영 직관에 더 자연스럽다는 사용자 결정.
    try:
        data = json.loads(_COL_PREFS_FILE.read_text(encoding="utf-8"))
        return bool(data.get("products_box_order_reversed", True))
    except Exception:
        return True


def _save_box_order_reversed(val: bool) -> None:
    try:
        existing: dict = {}
        if _COL_PREFS_FILE.exists():
            existing = json.loads(_COL_PREFS_FILE.read_text(encoding="utf-8"))
        existing["products_box_order_reversed"] = bool(val)
        _COL_PREFS_FILE.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


# ── 진입 시 고아 임시 레코드 자동 정리 ──────────────────────
# 매 rerun마다 '임시%' 스캔 쿼리가 나가던 걸, 세션 첫 진입 1회 + 본 세션에서 임시 제품을
# 만든 흔적(_temp_product_id)이 있을 때만 실행하도록 제한 (버튼 클릭 등 잦은 rerun 비용 절감).
if (not st.session_state.get("_temp_cleanup_done")) or st.session_state.get("_temp_product_id"):
    try:
        _deleted_temp = delete_임시_products()
        st.session_state["_temp_cleanup_done"] = True
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

file_counts = get_file_counts_by_type()
run_counts = get_run_counts_by_product()

# 변경감지가 돌 active 제품(토글 ON·비테스트)의 파일을 미리 묶음 조회 → 제품별 get_files N+1 회피.
# (기초입력 단계 snapshot의 파일 필드용. 엠군/상세 단계는 파일을 안 써 빈 리스트라도 무방.)
_active_ids = [
    r["id"] for r in rows
    if _BOX_TO_SNAPSHOT_STAGE.get(compute_워크플로_단계(r)) and not r.get("is_test")
]
files_map = get_files_by_products(_active_ids)

# 워크플로 박스 분류 + 행별 🔄 변경 감지 + 🚀 run 처리대기
for r in rows:
    box_key = compute_워크플로_단계(r)
    r[_STAGE_KEY] = box_key
    snap_stage = _BOX_TO_SNAPSHOT_STAGE.get(box_key)
    if snap_stage and not r.get("is_test"):
        try:
            r["_변경_diff"] = compute_변경_diff(r, snap_stage, files=files_map.get(r["id"], []))
        except Exception:
            r["_변경_diff"] = []
    else:
        r["_변경_diff"] = []
    r["_변경_여부"] = bool(r["_변경_diff"])

    # 🚀 run: 엠군 실행 개수. 🟠 기초자료 박스(기초입력 ON·엠군 OFF)인데 run이
    # 이미 있으면 = 엠군완료 토글을 안 켠 '처리 대기' 상태.
    r["_run_count"] = run_counts.get(r["id"], 0)
    r["_run_pending"] = (
        box_key == WORKFLOW_BOX_BASIC
        and r["_run_count"] >= 1
        and not r.get("is_test")
    )

# 박스별 카운트 (테스트는 별도)
def _count_box(box_key: str) -> int:
    return sum(1 for r in rows if r[_STAGE_KEY] == box_key and not r.get("is_test"))

n_todo   = _count_box(WORKFLOW_BOX_NONE)
n_basic  = _count_box(WORKFLOW_BOX_BASIC)
n_mgoon  = _count_box(WORKFLOW_BOX_MGOON)
n_detail = _count_box(WORKFLOW_BOX_DETAIL)
n_test   = sum(1 for r in rows if r.get("is_test"))

st.write(
    f"총 **{len(rows)}**개  ·  "
    f"{_BOX_TODO} **{n_todo}** · {_BOX_BASIC} **{n_basic}** · "
    f"{_BOX_MGOON} **{n_mgoon}** · {_BOX_DETAIL} **{n_detail}** · "
    f"{_BOX_TEST} **{n_test}**"
)

# ── 🔔 다음 단계 액션 대기 배너 ──
# 인칭 표현 없이 단계 액션명으로 표현.
_pending_msgs: list[str] = []
if n_basic > 0:
    _pending_msgs.append(f"엠군 파이프라인 실행 대기: **{n_basic}**건")
if n_mgoon > 0:
    _pending_msgs.append(f"상세페이지 제작 대기: **{n_mgoon}**건")
if _pending_msgs:
    st.info("🔔 " + "  ·  ".join(_pending_msgs))

# ── DataFrame 빌드 ────────────────────────────────────────
df_all = pd.DataFrame(rows)
df_all.insert(
    1,
    "📁파일",
    df_all["id"].apply(
        lambda x: format_file_counts(file_counts.get(x, {"image": 0, "video": 0, "etc": 0}))
    ),
)
# 🔄 변경 감지 컬럼 — diff가 있으면 🔄 표시, 없으면 빈 칸
df_all.insert(2, "🔄 변동", df_all["_변경_여부"].apply(lambda x: "🔄" if x else ""))
# 🚀 run 컬럼 — 엠군 실행(run) 개수. 0이면 빈 칸.
df_all.insert(3, "🚀 run", df_all["_run_count"].apply(lambda n: f"🚀{n}" if n else ""))
if "엠군작업대상" in df_all.columns:
    df_all.insert(4, "🎯엠군 대상", df_all["엠군작업대상"].apply(
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
    _saved_curated = bool(saved)  # 비어있지 않은 저장본 = 사용자가 직접 큐레이션함
    visible_set = set(saved) if saved is not None else set(all_cols)
    for col in all_cols:
        key = f"col_check_{col}"
        if key not in st.session_state:
            # 신규 컬럼(🚀 run)은 큐레이션된 저장본에 없어도 기본 표시.
            # (저장본이 이 컬럼 생기기 전 것일 수 있음. 빈 저장본 [] 은 아래 fallback이
            #  전체 표시로 처리하므로 여기서 건드리지 않는다 — 영구저장도 하지 않는다.)
            if col == "🚀 run" and _saved_curated and col not in saved:
                st.session_state[key] = True
            else:
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

# ── 워크플로 박스 안내 + 박스 순서 토글 ──
# 박스 순서는 settings_columns.json에 영속 저장 (한 번 정하면 다음 진입에도 유지).
# 🧪 테스트는 항상 하단 (정/역배열 영향 X).
if "_box_order_reversed" not in st.session_state:
    st.session_state["_box_order_reversed"] = _load_box_order_reversed()
_box_reversed = bool(st.session_state["_box_order_reversed"])
_order_caption = "상세 → 일반" if _box_reversed else "일반 → 상세"

_help_col, _order_col, _spacer_col = st.columns([2, 3, 5])
with _help_col:
    with st.popover("❓ 워크플로 박스 안내"):
        st.markdown(_HELP_워크플로)
with _order_col:
    if st.button(
        f"🔁 박스 순서 뒤집기 (현재: {_order_caption})",
        key="btn_box_order_toggle",
        help="박스 표시 순서를 정배열↔역배열로 토글합니다. 🧪 테스트 박스는 항상 하단 유지.",
        use_container_width=True,
    ):
        new_val = not _box_reversed
        st.session_state["_box_order_reversed"] = new_val
        _save_box_order_reversed(new_val)
        st.rerun()

# ── 테이블별 데이터 분리 ──
# 테스트 레코드는 워크플로 박스에서 제외하고 테스트 박스에만 표시
if "is_test" in df_all.columns:
    _is_test = df_all["is_test"] == True
else:
    _is_test = pd.Series([False] * len(df_all), index=df_all.index)


def _df_for_box(box_key: str) -> pd.DataFrame:
    """박스 키로 필터한 DataFrame. 처리대기·변경된 행 자동 상단 정렬."""
    sub = df_all[~_is_test & (df_all[_STAGE_KEY] == box_key)].copy()
    # 🟠 기초자료 박스: 엠군완료 처리 대기(run 있음) → 변동 순으로 상단 정렬.
    # 그 외 박스: 변동만 상단 정렬.
    sort_cols: list[str] = []
    if box_key == WORKFLOW_BOX_BASIC and "_run_pending" in sub.columns:
        sort_cols.append("_run_pending")
    if "_변경_여부" in sub.columns:
        sort_cols.append("_변경_여부")
    if sort_cols:
        sub = sub.sort_values(by=sort_cols, ascending=False, kind="stable")
    return sub.reset_index(drop=True)


df_todo   = _df_for_box(WORKFLOW_BOX_NONE)
df_basic  = _df_for_box(WORKFLOW_BOX_BASIC)
df_mgoon  = _df_for_box(WORKFLOW_BOX_MGOON)
df_detail = _df_for_box(WORKFLOW_BOX_DETAIL)
df_test   = df_all[_is_test].reset_index(drop=True)

_TABLE_KEYS = ("todo", "basic", "mgoon", "detail", "test")

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


def _rescan_products(product_ids: list[int], progress_label: str = "재스캔") -> tuple[int, list[str]]:
    """제품 리스트의 매핑된 Drive 폴더를 모두 재스캔.

    Returns:
        (total_upsert: 총 upsert된 row 수, errors: 에러 메시지 리스트)
    """
    try:
        from pipeline.drive_client import build_service, scan_folder_to_파일_rows
        from pipeline.supabase_read import get_product, list_account_folders, upsert_파일
    except ImportError as e:
        st.error(f"클라이언트 로드 실패: {e}")
        return 0, []

    total_upsert = 0
    errors: list[str] = []
    service_cache: dict[str, object] = {}  # 계정당 service 1회만 빌드

    n = len(product_ids)
    if n == 0:
        return 0, []

    prog = st.progress(0.0, text=f"{progress_label} 준비 중… 0/{n}")

    for i, pid in enumerate(product_ids):
        try:
            p = get_product(pid)
            if not p:
                continue
            folders = list_account_folders(p)
            if not folders:
                # 매핑된 폴더 없으면 스킵 (에러는 아님)
                prog.progress((i + 1) / n, text=f"{progress_label} 폴더 없음 스킵… {i+1}/{n}")
                continue

            pname = (p.get("제품명") or "")[:20]
            prog.progress(i / n, text=f"{progress_label}: [{pid}] {pname}  ({i+1}/{n})")

            for acc_label, folder_id in folders.items():
                if not folder_id:
                    continue
                try:
                    if acc_label not in service_cache:
                        service_cache[acc_label] = build_service(acc_label)
                    svc = service_cache[acc_label]
                    rows = scan_folder_to_파일_rows(svc, folder_id)
                    cnt = upsert_파일(pid, rows, acc_label)
                    total_upsert += cnt
                except Exception as e:
                    errors.append(f"[제품 {pid}, {acc_label}] {type(e).__name__}: {e}")
        except Exception as e:
            errors.append(f"[제품 {pid}] {type(e).__name__}: {e}")

    prog.progress(1.0, text=f"{progress_label} 완료 ({n}/{n})")
    prog.empty()
    return total_upsert, errors


def _render_table(df_sub: pd.DataFrame, key: str, title: str):
    """1개 박스 테이블 렌더. (event, filtered_view) 반환. 빈 결과는 (None, view)."""
    n_changed = (
        int(df_sub["_변경_여부"].sum())
        if "_변경_여부" in df_sub.columns and not df_sub.empty
        else 0
    )
    # 🚀 처리 대기(run 있는데 엠군완료 OFF) — 🟠 기초자료 박스에서만 1 이상.
    n_pending = (
        int(df_sub["_run_pending"].sum())
        if "_run_pending" in df_sub.columns and not df_sub.empty
        else 0
    )
    header = f"### {title}  ·  {len(df_sub)}건"
    if n_pending > 0:
        header += f"  🚀 **{n_pending}건 엠군완료 처리 대기**"
    if n_changed > 0:
        header += f"  ⚠️ **{n_changed}건 변동 있음**"
    with st.container(border=True):
        st.markdown(header)

        # 직전 재스캔 결과 메시지 (한 번만 표시 후 소비)
        _rs_msg = st.session_state.pop(f"_rescan_msg_{key}", None)
        _rs_errs = st.session_state.pop(f"_rescan_errors_{key}", None)
        if _rs_msg:
            st.success(_rs_msg)
            if _rs_errs:
                with st.expander(f"⚠️ 에러 {len(_rs_errs)}건"):
                    for _e in _rs_errs:
                        st.caption(_e)

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

        # ── Drive 폴더 일괄 재스캔 (현재 필터된 제품 대상) ──
        _rs_col1, _rs_col2 = st.columns([5, 2])
        with _rs_col2:
            if st.button(
                f"🔍 {len(view)}개 Drive 재스캔",
                key=f"btn_rescan_table_{key}",
                help="현재 필터된 제품들의 매핑된 Drive 폴더를 모두 재스캔해서 새 파일을 DB에 등록합니다. "
                     "제품 수가 많으면 시간이 좀 걸립니다.",
                use_container_width=True,
            ):
                _ids = view["id"].tolist()
                _total, _errors = _rescan_products(_ids, progress_label=f"{title} 재스캔")
                _msg = f"✅ {_total}개 파일 동기화됨 (중복 자동 스킵)"
                if _errors:
                    _msg += f"  ·  ⚠️ 에러 {len(_errors)}건"
                st.session_state[f"_rescan_msg_{key}"] = _msg
                st.session_state[f"_rescan_errors_{key}"] = _errors
                try:
                    st.cache_data.clear()
                except Exception:
                    pass
                st.rerun()

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


# ── 박스 렌더링 (정/역배열 토글) ──
# 🧪 테스트는 항상 마지막 — 정/역배열 영향 X.
_workflow_box_specs = [
    ("todo",   df_todo,   _BOX_TODO),
    ("basic",  df_basic,  _BOX_BASIC),
    ("mgoon",  df_mgoon,  _BOX_MGOON),
    ("detail", df_detail, _BOX_DETAIL),
]
if st.session_state.get("_box_order_reversed"):
    _workflow_box_specs = list(reversed(_workflow_box_specs))

_events: dict = {}
view_map: dict = {}
for _k, _df_sub, _title in _workflow_box_specs:
    _ev, _vw = _render_table(_df_sub, _k, _title)
    _events[_k] = _ev
    view_map[_k] = _vw

# 테스트는 항상 하단
_ev_test, _vw_test = _render_table(df_test, "test", _BOX_TEST)
_events["test"] = _ev_test
view_map["test"] = _vw_test

# ── 행 클릭 = 자동 편집 페이지 전환 ──
prev_sel = dict(st.session_state._prod_selections)
curr_sel = {
    k: (list(ev.selection.rows) if ev is not None else [])
    for k, ev in _events.items()
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
