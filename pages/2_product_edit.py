"""페이지 2 — 제품 등록 / 수정.

신규 등록 흐름:
  1. 1_products.py에서 session_state["edit_mode"] = "new" 설정 후 이 페이지 진입
  2. 이 페이지 진입 즉시 임시 레코드 자동 생성 → edit 모드로 전환
     (이전 세션에서 만든 임시 레코드가 남아 있으면 재사용, 새로 안 만듦)
  3. 이미지 탭에서 바로 업로드 + Vision Pass 실행 가능
  4. 스펙 탭에서 VP 결과 참고해 필드 채움 → 저장

수정: session_state["edit_mode"] = "edit"  +  session_state["edit_product_id"] = int

⚠️ 변경 감지 매니페스트 동기화 규약
   스펙 탭의 `st.subheader` 텍스트(기본 정보 / 재고 / 가격 / 치수 / 무게 / 소재 / 색상 /
   인증 / 검수)를 바꾸거나 새 그룹을 추가하면, `pipeline/snapshot_schema.py`의
   `SNAPSHOT_GROUPS` 키도 같이 갱신해야 한다. 변경 감지 박제·UI 후보·diff 표시가
   거기서 단일 소스로 관리된다.
"""
from __future__ import annotations

import io
import json
from datetime import datetime
from pathlib import Path

import streamlit as st

try:
    from streamlit_paste_button import paste_image_button as _paste_image_button
    _PASTE_OK = True
except ImportError:
    _PASTE_OK = False

from pipeline.account_ui import (
    account_badge,
    account_color_dot,
    account_short_name,
)
from pipeline.supabase_read import (
    WORKFLOW_BOX_BASIC,
    WORKFLOW_BOX_DETAIL,
    WORKFLOW_BOX_MGOON,
    WORKFLOW_BOX_NONE,
    acknowledge_변경,
    compute_변경_diff,
    compute_워크플로_단계,
    delete_비전패스_이력,
    delete_파일,
    delete_상품,
    delete_편집_세션,
    get_active_편집_세션,
    get_files,
    get_product,
    get_product_spec,
    get_thumbnail_url,
    insert_비전패스_이력,
    insert_상품,
    list_account_folders,
    list_비전패스_이력,
    set_account_folder,
    set_워크플로_토글,
    set_엠군작업대상,
    set_is_test,
    update_상품,
    update_시각설명,
    upsert_편집_세션,
    upsert_파일,
)
from pipeline.role import current_username, is_owner
from pipeline.models_config import (
    ALL_VP_MODELS,
    CLAUDE_VP_MODELS,
    DEFAULT_EXTRACT_MODEL,
    GEMINI_VP_MODELS,
    family_of as _vp_family_of,
)
from pipeline.spec_schema import SPEC_FIELDS
from pipeline.storage import get_storage
from pipeline.settings import load_판매자특성_활용, load_판매자특성_메모
from pipeline.snapshot_schema import (
    파일_field_kind,
    엠군_stage_info,
    엠군_stage_label,
)
from pipeline.image_actions import (
    bulk_download_zip,
    image_with_fallback,
    individual_download_link,
    original_view_url,
    refresh_button,
    video_thumb_with_play_overlay,
)

# ── 모드 결정 / 임시 레코드 자동 생성 ────────────────────────
_mode_raw  = st.session_state.get("edit_mode", "new")
product_id = st.session_state.get("edit_product_id")

if _mode_raw == "new":
    # 이미 만들어 둔 임시 레코드가 있으면 재사용 (중복 방지 — Q1)
    _prev_temp = st.session_state.get("_temp_product_id")
    _reused = False
    if _prev_temp:
        _check = get_product(_prev_temp)
        if _check and _check.get("제품명", "").startswith("임시_"):
            st.session_state["edit_mode"]       = "edit"
            st.session_state["edit_product_id"] = _prev_temp
            _reused = True
            st.rerun()

    if not _reused:
        with st.spinner("제품 공간 생성 중…"):
            _tmp_name = f"임시_{datetime.now().strftime('%m%d_%H%M%S')}"
            _created  = insert_상품({"제품명": _tmp_name, "엠군상태": "미시작"})
        _new_id = _created.get("id")
        st.session_state["_temp_product_id"] = _new_id
        st.session_state["edit_mode"]        = "edit"
        st.session_state["edit_product_id"]  = _new_id
        st.rerun()

# 이후 항상 edit 모드
product_id = st.session_state.get("edit_product_id")
row        = get_product(product_id) or {}
_is_temp   = row.get("제품명", "").startswith("임시_")

# ── 낙관적 락 — _orig_ts ────────────────────────────────
# 페이지 진입 시 row.수정일을 session_state에 락으로 저장.
# 같은 페이지에 머무는 중에는 락을 갱신하지 않아야 진짜 낙관적 락이 동작한다 (동료
# 변경 감지). 그러나 사용자가 페이지를 떠났다가 (사이드바 이동 등) 다시 들어와서
# row.수정일이 락과 달라졌다면 = 사용자가 새 값을 직접 보고 있는 상태 → 락을 자동
# 갱신하고 stale conflict 플래그도 클리어 (사용자가 새로고침/목록 우회하지 않아도
# 자연스럽게 동기화).
_lock_key = f"_lock_orig_ts__{product_id}" if product_id else None
_conflict_key = f"_save_conflict__{product_id}" if product_id else None
if not _is_temp and _lock_key:
    _new_ts = row.get("수정일")
    if _lock_key not in st.session_state:
        st.session_state[_lock_key] = _new_ts
    elif st.session_state[_lock_key] != _new_ts:
        # 페이지 재진입 — 화면이 새 값을 보여주는 시점에 락도 함께 갱신
        st.session_state[_lock_key] = _new_ts
        if _conflict_key:
            st.session_state.pop(_conflict_key, None)

if _is_temp:
    st.title(f"🆕 신규 제품 등록 — #{product_id}")
    st.caption("🗄️ DB — 상품 테이블  ·  **임시 저장 상태** (스펙 탭에서 제품명 수정 후 저장하세요)")
else:
    st.title(f"✏️ 제품 수정 — #{product_id}")
    st.caption("🗄️ DB — 상품 테이블")

# 저장 충돌 배너 — _save 직후뿐 아니라 이후 rerun에서도 유지
if not _is_temp and _conflict_key and st.session_state.get(_conflict_key):
    st.warning(
        "⚠️ 다른 사용자가 먼저 저장했습니다.\n\n"
        "안전을 위해 당신이 수정/입력한 값은 저장되지 않았습니다.\n\n"
        "페이지를 새로고침하여 최신 값을 불러온 후 다시 시도하세요.\n\n"
        "(페이지를 이탈하면 값이 사라지니 수정한 필드 값은 따로 메모해두세요.)\n\n"
        "(페이지를 새로고침 해도 되고, 다른 페이지에 다녀와도 됩니다.)"
    )
    # 명시적 "다시 시도" 버튼 — 페이지 이탈 없이 동료 최신값 받아 락 갱신
    if st.button(
        "🔄 동료 최신값 받기 / 다시 시도",
        key="btn_accept_others_save",
        help="DB의 최신 수정일로 락을 다시 잡습니다. 화면 위쪽 필드 값들도 동료의 최신값으로 갱신됩니다. "
             "(주의: 화면에서 직접 입력한 값은 사라지니 먼저 메모하세요.)",
    ):
        st.session_state.pop(_lock_key, None)
        st.session_state.pop(_conflict_key, None)
        st.rerun()

# ── 동시편집 보호 (사회적 조정 + 낙관적 락은 _save 등에서) ──
# 임시 레코드는 한 사용자만 다루므로 편집 세션 등록 skip
_current_username = current_username()
if not _is_temp:
    import time as _time
    _last_upsert = st.session_state.get("_edit_session_last_upsert", 0)
    if _time.time() - _last_upsert > 30:
        try:
            upsert_편집_세션(product_id, _current_username)
            st.session_state["_edit_session_last_upsert"] = _time.time()
        except Exception:
            pass

    try:
        # ttl 1분 — 활동 중인 사용자는 30초 debounce 안에 다시 upsert되어 안 사라짐.
        # 사이드바 등으로 페이지를 떠나 비활성 상태가 1분 지나면 상대편에서 사라짐.
        _others = get_active_편집_세션(product_id, exclude_사용자명=_current_username, ttl_min=1)
    except Exception:
        _others = []
    if _others:
        _ot = _others[0]
        _ot_name = _ot.get("사용자명", "타사용자")
        _ot_at_raw = _ot.get("마지막_활동시각", "") or ""
        try:
            _ot_at = datetime.fromisoformat(_ot_at_raw.replace("Z", "+00:00")).strftime("%m-%d %H:%M")
        except Exception:
            _ot_at = _ot_at_raw[:16] if _ot_at_raw else "?"
        st.warning(f"⚠️ 지금 **{_ot_name}** 이(가) 편집 중입니다 · 최근 활동 {_ot_at}")

_btn_col1, _btn_col2, _btn_col3 = st.columns([1, 2, 2])
with _btn_col1:
    if st.button("← 목록으로", key="back_btn"):
        if _is_temp:
            try:
                delete_상품(product_id)
            except Exception:
                pass
            st.session_state.pop("_temp_product_id", None)
        # 페이지 이탈 — 락/충돌 플래그 정리 (다음 진입 시 새 row 수정일로 락 재설정)
        if product_id:
            st.session_state.pop(f"_lock_orig_ts__{product_id}", None)
            st.session_state.pop(f"_save_conflict__{product_id}", None)
            # 편집_세션 row 즉시 삭제 — 상대편에서 ttl 기다리지 않고 즉시 반영
            if not _is_temp:
                try:
                    delete_편집_세션(product_id, _current_username)
                    st.session_state.pop("_edit_session_last_upsert", None)
                except Exception:
                    pass
        st.session_state.pop("edit_product_id", None)
        st.session_state.pop("edit_mode", None)
        st.switch_page("pages/1_products.py")

# ── 🔄 변경 감지 카드용 분리 표시 헬퍼 ─────────────────────
# (변경 감지 카드 코드보다 위쪽에 정의 — Python은 호출 시점 정의 필요)

def _render_file_diff_card(old_items: list[dict], new_items: list[dict]) -> None:
    """파일 필드 변동을 ➕ 추가 / 🗑️ 삭제 / 📝 이름 변경으로 분리 표시.

    each item: {"id": 드라이브_파일_id, "name": 파일명}
    동일 id에서 name만 다르면 → 이름 변경. id 자체가 추가/삭제되면 → 추가/삭제.
    """
    old_map = {it.get("id"): it.get("name") for it in old_items if it.get("id")}
    new_map = {it.get("id"): it.get("name") for it in new_items if it.get("id")}

    added_ids   = sorted(set(new_map) - set(old_map))
    removed_ids = sorted(set(old_map) - set(new_map))
    common      = set(old_map) & set(new_map)
    renamed     = sorted(
        [(i, old_map[i], new_map[i]) for i in common if old_map[i] != new_map[i]],
        key=lambda x: x[0],
    )

    if added_ids:
        st.markdown(f"➕ **추가됨 ({len(added_ids)}개)**")
        for i in added_ids:
            st.markdown(f"- `{new_map[i] or '(이름 없음)'}`")
    if removed_ids:
        st.markdown(f"🗑️ **삭제됨 ({len(removed_ids)}개)**")
        for i in removed_ids:
            st.markdown(f"- `{old_map[i] or '(이름 없음)'}`")
    if renamed:
        st.markdown(f"📝 **이름 변경 ({len(renamed)}개)**")
        for _i, _on, _nn in renamed:
            st.markdown(f"- `{_on}` → **`{_nn}`**")
    if not (added_ids or removed_ids or renamed):
        st.caption("(파일 변동 없음 — 비교 정렬 차이 가능성)")


def _render_엠군_diff_card(old_items: list[dict], new_items: list[dict]) -> None:
    """엠군 단계 변동을 ➕ 신규 / 🗑️ 삭제 / ✏️ 내용 변경으로 분리 표시.

    each item: {"run_id":..., "target_id":..., "detail_id":..., "data": [...]}
    (target_id/detail_id는 FK 타입에 따라 없을 수 있음)
    """
    def _entry_key(it: dict) -> tuple:
        return (it.get("run_id"), it.get("target_id"), it.get("detail_id"))

    def _label(k: tuple) -> str:
        run_id, target_id, detail_id = k
        parts = []
        if run_id    is not None: parts.append(f"run #{run_id}")
        if target_id is not None: parts.append(f"target #{target_id}")
        if detail_id is not None: parts.append(f"detail #{detail_id}")
        return " · ".join(parts) if parts else "(unknown)"

    old_map = {_entry_key(it): it.get("data") for it in old_items}
    new_map = {_entry_key(it): it.get("data") for it in new_items}

    added    = sorted(set(new_map) - set(old_map))
    removed  = sorted(set(old_map) - set(new_map))
    common   = set(old_map) & set(new_map)
    modified = sorted([k for k in common if old_map[k] != new_map[k]])

    if added:
        st.markdown(f"➕ **신규 항목 ({len(added)}개)**")
        for _k in added:
            st.markdown(f"- {_label(_k)}")
    if removed:
        st.markdown(f"🗑️ **삭제된 항목 ({len(removed)}개)**")
        for _k in removed:
            st.markdown(f"- {_label(_k)}")
    if modified:
        st.markdown(f"✏️ **내용 변경 ({len(modified)}개)**")
        for _k in modified:
            st.markdown(f"- {_label(_k)}")
    if not (added or removed or modified):
        st.caption("(엠군 단계 변동 없음)")


# ── 엠군 작업대상 토글 (임시 레코드 제외, owner/partner 모두 가능) ──
def _clear_lock_after_self_edit() -> None:
    """본인 토글 후 호출 — 락/충돌 플래그 클리어.
    rerun 시 105-106 라인에서 최신 row.수정일로 락이 자동 재설정되어 가짜 충돌 방지.
    근본 원인: DB 트리거 `상품_수정일_갱신`이 UPDATE마다 수정일을 NOW()로 갱신하므로,
    토글(=self-edit)도 락과 DB 수정일을 불일치 상태로 만든다.
    """
    if _lock_key:
        st.session_state.pop(_lock_key, None)
    if _conflict_key:
        st.session_state.pop(_conflict_key, None)


if not _is_temp and product_id:
    _작업대상_현재 = bool(row.get("엠군작업대상", False))
    with _btn_col2:
        _label = "✅ 엠군 대상 (ON)" if _작업대상_현재 else "⬛ 엠군 대상 (OFF)"
        _btn_type = "primary" if _작업대상_현재 else "secondary"
        if st.button(_label, key="작업대상_toggle_btn", type=_btn_type,
                     help="클릭하면 ON/OFF가 전환됩니다."):
            set_엠군작업대상(product_id, not _작업대상_현재)
            _clear_lock_after_self_edit()
            st.rerun()

    # ── 🧪 테스트 레코드 토글 ──
    _is_test_현재 = bool(row.get("is_test", False))
    with _btn_col3:
        _t_label = "🧪 테스트 레코드 (ON)" if _is_test_현재 else "⬛ 테스트 레코드 (OFF)"
        _t_type = "primary" if _is_test_현재 else "secondary"
        if st.button(_t_label, key="is_test_toggle_btn", type=_t_type,
                     help="ON이면 제품 조회의 🧪 테스트 박스에만 표시되어 운영 자료와 분리됩니다."):
            set_is_test(product_id, not _is_test_현재)
            _clear_lock_after_self_edit()
            st.rerun()

    # ── 워크플로 단계 토글 3개 (한 줄 아래 새 columns) ──
    # 토글 ON 시점에 단계별 핵심 필드를 snapshot으로 박제 → 후속 작업자에게 🔄 변경 알림.
    # 토글 OFF 시 snapshot도 NULL로 클리어. 순서 강제 없음 (운영해보고 필요하면 추가).
    _wf_col1, _wf_col2, _wf_col3 = st.columns(3)
    _wf_specs = [
        (_wf_col1, "기초입력",   "🟠 기초입력 완료",    "기초입력_완료_at",
         "동료가 기초자료(카테고리·이미지·시각설명·가격 등) 입력을 끝냈음을 표시합니다. "
         "ON 시점의 핵심 필드를 박제 → 이후 변경되면 엠군 돌리는 사람에게 🔄 표시."),
        (_wf_col2, "엠군",       "🔵 엠군 작업 완료",   "엠군_완료_at",
         "엠군 파이프라인 결과를 동료에게 넘기기 적합한 상태임을 표시합니다. "
         "ON 시점의 엠군 결과(runs)를 박제 → 이후 변경되면 상세페이지 만드는 사람에게 🔄 표시."),
        (_wf_col3, "상세페이지", "✅ 상세페이지 완료",  "상세페이지_완료_at",
         "상세페이지 생성이 끝났음을 표시합니다. "
         "(현재 후속 작업자 없음 — 향후 채널 단계 작업자 도입 시 활용)"),
    ]
    for _col, _stage, _label_base, _at_col, _help_text in _wf_specs:
        _on = bool(row.get(_at_col))
        with _col:
            _label = f"{_label_base} (ON)" if _on else f"⬛ {_label_base.split(' ', 1)[1]} (OFF)"
            _type = "primary" if _on else "secondary"
            if st.button(_label, key=f"wf_toggle_{_stage}", type=_type, help=_help_text,
                         use_container_width=True):
                set_워크플로_토글(product_id, _stage, not _on)
                _clear_lock_after_self_edit()
                st.rerun()

    # ── 💾 상단 저장 placeholder ──
    # 스펙 탭의 폼 위젯들이 mount된 뒤(=페이지 코드 후반부)에 이 자리에 저장/취소 버튼이 그려진다.
    # st.empty()는 위치만 예약. 단일 패스 렌더링이라 사용자는 채워진 상태로만 보게 됨.
    _save_top_placeholder = st.empty()

    # ── 🔄 변경 감지 카드 ──
    # 박스를 만든 마지막 ON 토글의 snapshot vs 현재 비교.
    # 박스 ⬛(일반)이면 비교 대상 없음 → 카드 표시 안 함.
    _box_key = compute_워크플로_단계(row)
    _BOX_TO_STAGE = {
        WORKFLOW_BOX_BASIC:  ("기초입력",   "🟠 기초입력 완료",   "엠군 파이프라인 실행"),
        WORKFLOW_BOX_MGOON:  ("엠군",       "🔵 엠군 작업 완료",  "상세페이지 제작"),
        WORKFLOW_BOX_DETAIL: ("상세페이지", "✅ 상세페이지 완료", None),
    }
    _stage_info = _BOX_TO_STAGE.get(_box_key)
    if _stage_info:
        _snap_stage, _stage_label, _next_action = _stage_info
        try:
            _diffs = compute_변경_diff(row, _snap_stage)
        except Exception:
            _diffs = []
        if _diffs:
            with st.container(border=True):
                _next_caption = (
                    f"  ·  다음 작업: **{_next_action}**" if _next_action else ""
                )
                st.markdown(
                    f"### 🔄 변경 감지 — {_stage_label} 토글 이후 "
                    f"**{len(_diffs)}개 필드** 변경됨{_next_caption}"
                )
                st.caption(
                    "토글을 켠 시점에 박제된 값과 현재 값이 다릅니다. "
                    "본인 작업 결과물에 반영했거나 무시하기로 했다면 [✓ 확인했음]을 눌러 "
                    "이 시점의 값을 다시 박제하세요."
                )
                with st.expander(f"📋 변경 내역 ({len(_diffs)}건)", expanded=True):
                    for d in _diffs:
                        _f = d.get("field", "?")
                        _old = d.get("old")
                        _new = d.get("new")

                        # 라벨 — 엠군 단계 키는 사람이 읽는 라벨로 변환
                        _is_엠군 = 엠군_stage_info(_f) is not None
                        _is_파일 = 파일_field_kind(_f) is not None
                        _heading = (
                            f"**🔸 {엠군_stage_label(_f)}**" if _is_엠군
                            else f"**🔸 {_f}**"
                        )
                        st.markdown(_heading)

                        # 파일 필드 — 추가/삭제/이름변경 분리 표시
                        if _is_파일:
                            _render_file_diff_card(_old or [], _new or [])

                        # 엠군 단계 필드 — 신규/삭제/변경 항목 분리 표시
                        elif _is_엠군:
                            _render_엠군_diff_card(_old or [], _new or [])

                        # 그룹 dict (예: 가격/치수 / 무게/인증) — 변경된 하위 키만 한 줄씩
                        elif isinstance(_old, dict) or isinstance(_new, dict):
                            _old_d = _old if isinstance(_old, dict) else {}
                            _new_d = _new if isinstance(_new, dict) else {}
                            _keys = list(dict.fromkeys(list(_old_d.keys()) + list(_new_d.keys())))
                            _sub_lines = []
                            for _k in _keys:
                                _ov, _nv = _old_d.get(_k), _new_d.get(_k)
                                if _ov != _nv:
                                    _os = "(없음)" if _ov is None else str(_ov)
                                    _ns = "(없음)" if _nv is None else str(_nv)
                                    _sub_lines.append(f"- `{_k}` : {_os}  →  **{_ns}**")
                            if _sub_lines:
                                st.markdown("\n".join(_sub_lines))
                            else:
                                st.caption("(하위 필드 변동 없음 — 키 추가/삭제만)")

                        # 그 외 리스트 (예: 제품특징_bullet, 판매자특성_선택) — 좌우 컬럼
                        elif isinstance(_old, list) or isinstance(_new, list):
                            try:
                                _old_s = json.dumps(_old or [], ensure_ascii=False, indent=2)
                                _new_s = json.dumps(_new or [], ensure_ascii=False, indent=2)
                            except Exception:
                                _old_s, _new_s = str(_old), str(_new)
                            _c1, _c2 = st.columns(2)
                            with _c1:
                                st.caption("이전 (박제 시점)")
                                st.code(_old_s, language="json")
                            with _c2:
                                st.caption("현재")
                                st.code(_new_s, language="json")

                        # 단일 스칼라 값 — 한 줄
                        else:
                            _os = "(없음)" if _old is None else str(_old)
                            _ns = "(없음)" if _new is None else str(_new)
                            st.markdown(f"{_os}  →  **{_ns}**")
                        st.markdown("")  # 항목 사이 여백
                if st.button(
                    "✓ 확인했음",
                    key="wf_ack_btn",
                    type="primary",
                    help=f"{_stage_label} 토글의 박제값을 현재 값으로 갱신합니다. "
                         f"🔄 알림이 사라집니다.",
                ):
                    acknowledge_변경(product_id, _snap_stage)
                    _clear_lock_after_self_edit()
                    st.rerun()

st.divider()

# ── Vision Pass 공통 상수/유틸 ────────────────────────────
# 사고(core·core_*)는 _공통 두뇌, 자동화 전용 분기 파일이 있으면 agents fallback.
_AGENTS_DIR    = Path(__file__).parent.parent / "agents" / "00_vision_pass"
_BRAIN_VP_DIR  = Path(__file__).parent.parent.parent / "_공통 두뇌" / "00_vision_pass"
# 모델 목록은 pipeline.models_config 에서 import (단일 소스)
_CLAUDE_MODELS = CLAUDE_VP_MODELS
_GEMINI_MODELS = GEMINI_VP_MODELS
_ALL_VP_MODELS = ALL_VP_MODELS


def _vp_family(model: str) -> str:
    return _vp_family_of(model)


def _vp_resolve(filename: str) -> Path:
    """파일을 _공통 두뇌 우선, 자동화형 agents fallback으로 해석."""
    p = _BRAIN_VP_DIR / filename
    if p.exists():
        return p
    return _AGENTS_DIR / filename


def _vp_prompt_path(model: str) -> Path:
    fam = _vp_family(model)
    p = _vp_resolve(f"core_{fam}.md")
    return p if p.exists() else _vp_resolve("core.md")


def _vp_load_prompt(model: str) -> str:
    return _vp_prompt_path(model).read_text(encoding="utf-8")


def _vp_video_prompt_path() -> Path:
    """동영상 비전패스 전용 프롬프트 경로. 파일 없으면 이미지 Gemini 프롬프트로 폴백."""
    p = _vp_resolve("core_gemini_video.md")
    return p if p.exists() else _vp_resolve("core_gemini.md")


def _vp_load_video_prompt() -> str:
    return _vp_video_prompt_path().read_text(encoding="utf-8")


def _fmt_dt(ts: str | None) -> str:
    """ISO timestamp → 'MM-DD HH:MM' 짧은 표시."""
    if not ts:
        return ""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%m-%d %H:%M")
    except Exception:
        return ts[:16]


# ── 공통 저장/취소 유틸 ──────────────────────────────────
def _save(payload: dict) -> None:
    """스펙·판매자정보 payload를 DB에 저장. 낙관적 락(임시 레코드 제외).

    _orig_ts는 페이지 첫 로드 시 session_state에 저장된 값을 고정 사용한다
    (`_lock_orig_ts__{pid}`). 저장 성공 시 락 키를 삭제해 다음 rerun에서
    새 row의 수정일로 다시 락이 잡히게 한다.
    """
    if not payload.get("제품명", "").strip():
        st.error("제품명은 필수입니다.")
        return
    # 임시 레코드는 한 사용자만 다루므로 락 생략
    if _is_temp:
        _orig_ts = None
    else:
        # 락 키가 없으면(예외적 경로) row.수정일을 fallback으로 사용
        _orig_ts = st.session_state.get(_lock_key) if _lock_key else None
        if _orig_ts is None:
            _orig_ts = row.get("수정일")
    try:
        ok = update_상품(product_id, payload, original_수정일=_orig_ts)
        if not ok:
            # 충돌 플래그 — 이번 호출 직후 + 이후 rerun 모두에서 배너 유지
            if product_id:
                st.session_state[f"_save_conflict__{product_id}"] = True
            # 토스트 — 화면 어디에 있든 우상단에 즉시 알림
            st.toast("⚠️ 저장 실패 — 다른 사용자가 먼저 저장했습니다.", icon="⚠️")
            st.warning(
                "⚠️ 다른 사용자가 먼저 저장했습니다.\n\n"
                "안전을 위해 당신이 수정/입력한 값은 저장되지 않았습니다.\n\n"
                "페이지를 새로고침하여 최신 값을 불러온 후 다시 시도하세요.\n\n"
                "(페이지를 이탈하면 값이 사라지니 수정한 필드 값은 따로 메모해두세요.)\n\n"
                "(페이지를 새로고침 해도 되고, 다른 페이지에 다녀와도 됩니다.)"
            )
            # 인라인 "다시 시도" 버튼 — 페이지 상단 버튼과 동일 동작.
            # _save() 안에서는 st.rerun() 없이 return하므로, 이 버튼이 없으면
            # 상단 배너+버튼이 보이지 않아 사용자가 다음 액션을 못 한다.
            if st.button(
                "🔄 동료 최신값 받기 / 다시 시도",
                key=f"btn_accept_others_save_inline_{product_id}",
                help="DB의 최신 수정일로 락을 다시 잡습니다. 화면 위쪽 필드 값들도 동료의 최신값으로 갱신됩니다. "
                     "(주의: 화면에서 직접 입력한 값은 사라지니 먼저 메모하세요.)",
            ):
                if _lock_key:
                    st.session_state.pop(_lock_key, None)
                if product_id:
                    st.session_state.pop(f"_save_conflict__{product_id}", None)
                st.rerun()
            return
        if not payload["제품명"].startswith("임시_"):
            st.session_state.pop("_temp_product_id", None)
        st.session_state.pop("_spec_override", None)
        # 저장 성공 — 락/충돌 플래그 클리어 (다음 rerun에서 새 수정일로 락 재설정)
        if _lock_key:
            st.session_state.pop(_lock_key, None)
        if product_id:
            st.session_state.pop(f"_save_conflict__{product_id}", None)
        st.success("저장 완료!")
        st.rerun()
    except Exception as _se:
        st.error(f"저장 실패: {type(_se).__name__}: {_se}")


def _auto_apply_after_vision(pid: int, 시각설명_text: str) -> tuple[int, int]:
    """시각설명 저장 직후 자동으로 SPEC_FIELDS + 제품특징_bullet 추출 → 빈 필드만 채우기.

    이미 손으로 채워진 필드는 건드리지 않는다 (안전). bullet은 기존 항목과 중복 제거 후 추가.

    Returns:
        (반영된 SPEC 필드 수, 추가된 bullet 수). LLM 실패 시 (0, 0).
    """
    import json as _json

    from pipeline.settings import load as _load_settings
    from pipeline.vision_merge import extract_스펙

    if not 시각설명_text or not 시각설명_text.strip():
        return (0, 0)

    cfg = _load_settings()
    primary_model = cfg.get("primary_model_00") or "claude-sonnet-4-6"

    try:
        extracted = extract_스펙(시각설명_text, model=primary_model)
    except Exception as _ee:
        st.warning(f"자동 추출 실패: {type(_ee).__name__}: {_ee}")
        return (0, 0)

    if not isinstance(extracted, dict) or extracted.get("_error"):
        return (0, 0)

    cur = get_product(pid) or {}
    payload: dict = {}

    # SPEC_FIELDS — 빈 필드만 채우기
    for f in SPEC_FIELDS:
        new_v = extracted.get(f["name"])
        cur_v = cur.get(f["name"])
        if new_v is not None and cur_v in (None, "", 0):
            payload[f["name"]] = new_v
    # 인증번호 텍스트가 채워지면 짝 boolean 플래그도 동반 (빈 필드일 때만)
    for num_key, bool_key in (("kc인증번호", "kc인증"), ("전파인증번호", "전파인증")):
        if payload.get(num_key) and not cur.get(bool_key):
            payload[bool_key] = True

    spec_count = sum(1 for k in payload if k in {f["name"] for f in SPEC_FIELDS})

    # bullet — 기존 항목과 중복 제거 후 추가
    bullets_new = extracted.get("_특징_bullet") or []
    bullet_added = 0
    if bullets_new:
        existing = cur.get("제품특징_bullet") or []
        if isinstance(existing, str):
            try:
                existing = _json.loads(existing)
            except Exception:
                existing = []
        if not isinstance(existing, list):
            existing = []
        existing_set = set(existing)
        new_only = [b for b in bullets_new if b not in existing_set]
        if new_only:
            payload["제품특징_bullet"] = list(existing) + new_only
            bullet_added = len(new_only)

    if payload:
        try:
            # 백그라운드 자동 반영 — 다른 사용자가 먼저 저장했으면 silent skip
            ok = update_상품(pid, payload, original_수정일=cur.get("수정일"))
            if not ok:
                return (0, 0)
        except Exception as _ue:
            st.warning(f"자동 반영 DB 저장 실패: {type(_ue).__name__}: {_ue}")
            return (0, 0)

    return (spec_count, bullet_added)


def _cancel() -> None:
    """편집 취소 — 임시 레코드이면 삭제 후 목록으로."""
    if _is_temp:
        try:
            delete_상품(product_id)
        except Exception:
            pass
    st.session_state.pop("_temp_product_id", None)
    # 페이지 이탈 — 락/충돌 플래그 정리 + 편집_세션 row 즉시 삭제
    if product_id:
        st.session_state.pop(f"_lock_orig_ts__{product_id}", None)
        st.session_state.pop(f"_save_conflict__{product_id}", None)
        if not _is_temp:
            try:
                delete_편집_세션(product_id, _current_username)
                st.session_state.pop("_edit_session_last_upsert", None)
            except Exception:
                pass
    st.session_state.pop("edit_product_id", None)
    st.session_state.pop("edit_mode", None)
    st.switch_page("pages/1_products.py")


# ── 탭 구성 ──────────────────────────────────────────────
# 신규 등록(임시) 모드: 이미지부터 → 스펙 → 엠군
# 수정 모드: 스펙부터 → 이미지 → 엠군 (스펙 편집이 가장 잦은 작업)
# 첫 번째 탭이 자동 활성화되는 Streamlit 특성 활용.
if _is_temp:
    tab_이미지, tab_스펙, tab_엠군 = st.tabs(
        ["📁 이미지 & Vision Pass", "📐 스펙", "🧪 엠군 파이프라인"]
    )
else:
    tab_스펙, tab_이미지, tab_엠군 = st.tabs(
        ["📐 스펙", "📁 이미지 & Vision Pass", "🧪 엠군 파이프라인"]
    )

# ─────────────────────────────────────────────────────────
# 탭 — 이미지 + Vision Pass
# ─────────────────────────────────────────────────────────
with tab_이미지:
    # ── 등록된 이미지 / 동영상 조회 ───────────────────────
    drive_files = get_files(product_id)
    images = [f for f in drive_files if f.get("파일_유형") == "image" and f.get("드라이브_파일_id")]
    videos = [f for f in drive_files if f.get("파일_유형") == "video" and f.get("드라이브_파일_id")]

    # ── Drive 폴더 재스캔 (매핑된 폴더 있을 때) ────────────
    _mapped_folders = list_account_folders(row)
    if _mapped_folders:
        _rs1, _rs2 = st.columns([5, 2])
        with _rs2:
            if st.button(
                f"🔍 Drive 폴더 재스캔 ({len(_mapped_folders)}개 계정)",
                key=f"btn_rescan_{product_id}",
                help="이 제품에 매핑된 Drive 폴더(들)를 다시 스캔해서 새 파일을 DB에 등록합니다. "
                     "기존에 등록된 파일은 중복 스킵.",
                use_container_width=True,
            ):
                try:
                    from pipeline.drive_client import build_service, scan_folder_to_파일_rows
                    _drive_rescan_ok = True
                except ImportError as _e:
                    _drive_rescan_ok = False
                    st.error(f"Drive 클라이언트 로드 실패: {_e}")

                if _drive_rescan_ok:
                    _before_count = len(get_files(product_id))
                    _processed = 0
                    _scan_errors: list[str] = []
                    with st.spinner(f"Drive 스캔 중… ({len(_mapped_folders)}개 폴더)"):
                        for _acc_label, _folder_id in _mapped_folders.items():
                            if not _folder_id:
                                continue
                            try:
                                _svc = build_service(_acc_label)
                                _rows = scan_folder_to_파일_rows(_svc, _folder_id)
                                _n = upsert_파일(product_id, _rows, _acc_label)
                                _processed += _n
                            except Exception as _se:
                                _scan_errors.append(
                                    f"[{_acc_label}] {type(_se).__name__}: {_se}"
                                )
                    _after_count = len(get_files(product_id))
                    _new_count = _after_count - _before_count
                    if _scan_errors:
                        for _err in _scan_errors:
                            st.warning(_err)
                    st.success(
                        f"✅ {_processed}개 파일 동기화됨"
                        f" (신규 등록: {_new_count}개, 중복 스킵 포함)"
                    )
                    # 썸네일 cache-bust + DB 캐시 클리어
                    _tk = f"_thumb_ver_product_edit_{product_id}"
                    st.session_state[_tk] = st.session_state.get(_tk, 0) + 1
                    try:
                        st.cache_data.clear()
                    except Exception:
                        pass
                    st.rerun()

    if images:
        # 계정별 카운트 요약 (헤더에 표기)
        _img_acc_counts: dict[str, int] = {}
        for _imf in images:
            _img_acc_counts[_imf.get("계정") or ""] = _img_acc_counts.get(_imf.get("계정") or "", 0) + 1
        _acc_summary = " · ".join(
            f"{account_badge(acc) if acc else '⚫ 미지정'} {cnt}장"
            for acc, cnt in sorted(_img_acc_counts.items(), key=lambda x: -x[1])
        )
        _hdr_col1, _hdr_col2 = st.columns([5, 1])
        with _hdr_col1:
            st.markdown(f"**등록된 이미지 ({len(images)}장)** — {_acc_summary}")
        with _hdr_col2:
            refresh_button(
                scope_key=f"product_edit_{product_id}",
                label="🔄 새로고침",
                help="DB 다시 조회 + 깨진 썸네일 강제 재요청",
                use_container_width=True,
            )

        # 일괄 ZIP 다운로드 버튼 (동영상 포함 토글 — 동영상 있을 때만 노출)
        bulk_download_zip(
            files=images,
            scope_key=f"product_edit_{product_id}",
            zip_name_prefix=f"product_{product_id}_files",
            extra_files=videos if videos else None,
            extra_label="동영상",
        )

        cols = st.columns(min(len(images), 4))
        for i, f in enumerate(images):
            fid = f["드라이브_파일_id"]
            _f_acc = f.get("계정")
            with cols[i % 4]:
                try:
                    image_with_fallback(
                        fid,
                        size=400,
                        scope_key=f"product_edit_{product_id}",
                        alt=f.get("파일명", ""),
                    )
                    # 계정 배지 + 파일명
                    st.caption(f"{account_badge(_f_acc)} · {f.get('파일명', '')}")
                    _btn_del, _btn_orig, _btn_dl = st.columns([1, 1, 1])
                    with _btn_del:
                        # Q3: 개별 이미지 삭제 버튼
                        if st.button("🗑️", key=f"del_img_{f['id']}", help="이 이미지 삭제"):
                            delete_파일(f["id"])
                            st.rerun()
                    with _btn_orig:
                        st.markdown(f"[원본]({original_view_url(fid)})")
                    with _btn_dl:
                        st.markdown(individual_download_link(fid))
                except Exception:
                    st.caption(f"로드 실패: {fid}")
    else:
        st.info("등록된 이미지가 없습니다. 아래에서 업로드하세요.")

    # ── 등록된 동영상 ──────────────────────────────────────
    if videos:
        st.markdown("")  # spacer
        _vid_acc_counts: dict[str, int] = {}
        for _vf in videos:
            _vid_acc_counts[_vf.get("계정") or ""] = _vid_acc_counts.get(_vf.get("계정") or "", 0) + 1
        _vid_acc_summary = " · ".join(
            f"{account_badge(acc) if acc else '⚫ 미지정'} {cnt}개"
            for acc, cnt in sorted(_vid_acc_counts.items(), key=lambda x: -x[1])
        )
        st.markdown(f"**🎬 등록된 동영상 ({len(videos)}개)** — {_vid_acc_summary}")

        v_cols = st.columns(min(len(videos), 4))
        for i, vf in enumerate(videos):
            v_fid  = vf["드라이브_파일_id"]
            _v_acc = vf.get("계정")
            with v_cols[i % 4]:
                try:
                    video_thumb_with_play_overlay(
                        v_fid,
                        size=400,
                        scope_key=f"product_edit_{product_id}",
                        alt=vf.get("파일명", ""),
                    )
                    st.caption(f"{account_badge(_v_acc)} · {vf.get('파일명', '')}")
                    _vb_del, _vb_orig, _vb_dl = st.columns([1, 1, 1])
                    with _vb_del:
                        if st.button("🗑️", key=f"del_vid_{vf['id']}", help="이 동영상 삭제"):
                            delete_파일(vf["id"])
                            st.rerun()
                    with _vb_orig:
                        st.markdown(f"[원본]({original_view_url(v_fid)})")
                    with _vb_dl:
                        st.markdown(individual_download_link(v_fid))
                except Exception:
                    st.caption(f"로드 실패: {v_fid}")

    st.divider()

    # ── 업로드 UI ─────────────────────────────────────────
    try:
        from pipeline.drive_client import (
            ACCOUNTS, build_service, get_or_create_folder, list_subfolders,
            parse_folder_id, upload_file, _guess_type,
        )
        _drive_ok = True
    except ImportError as _e:
        _drive_ok = False
        st.warning(f"Drive 클라이언트 로드 실패: {_e}")

    if _drive_ok:
        st.subheader("📤 이미지 업로드")

        # 상품에 매핑된 계정별 폴더 (계정별_폴더_ids JSON)
        _account_folders = list_account_folders(row)

        # 기본 계정: 이미 파일이 가장 많이 올라간 계정 → 없으면 ACCOUNTS[0]
        _existing_files  = get_files(product_id) if product_id else []
        _used_accounts   = [f.get("계정") for f in _existing_files if f.get("계정")]
        _default_account = (
            max(set(_used_accounts), key=_used_accounts.count)
            if _used_accounts else ACCOUNTS[0]["label"]
        )
        _account_labels  = [a["label"] for a in ACCOUNTS]
        _default_idx     = _account_labels.index(_default_account) if _default_account in _account_labels else 0

        # 계정 selectbox 라벨에 색상 배지 표시
        def _fmt_account_option(label: str) -> str:
            badge = account_badge(label, with_full=False)
            if label in _account_folders:
                return f"{badge} · 폴더 있음"
            return f"{badge} · 신규 생성"

        u1, u2 = st.columns([2, 3])
        with u1:
            sel_account = st.selectbox(
                "구글 계정",
                _account_labels,
                index=_default_idx,
                key="upload_account",
                format_func=_fmt_account_option,
                help="계정마다 독립된 Drive 폴더가 자동 생성됩니다. 이미 폴더가 있으면 그 폴더에 누적 업로드됩니다.",
            )
        with u2:
            _account_folder = _account_folders.get(sel_account, "")
            if _account_folder:
                st.text_input(
                    f"Drive 폴더 ID — {account_badge(sel_account)} (기존)",
                    value=_account_folder,
                    disabled=True,
                    key="upload_folder_display",
                )
                _root_folder_input = ""
            else:
                # 폴더 브라우저에서 선택한 값을 위젯에 반영 (위젯 렌더링 전에 적용)
                if "_picked_folder_id" in st.session_state:
                    st.session_state["upload_root_folder"] = st.session_state.pop("_picked_folder_id")
                _ic1, _ic2 = st.columns([4, 1])
                with _ic1:
                    _root_folder_input = st.text_input(
                        f"상위 Drive 폴더 URL/ID — {account_badge(sel_account)} (신규 생성)",
                        placeholder="https://drive.google.com/drive/folders/...",
                        key="upload_root_folder",
                        help="이 계정에 신규 폴더를 만들 상위 폴더. 비우면 Drive 루트에 생성됩니다.",
                    )
                with _ic2:
                    st.markdown("&nbsp;", unsafe_allow_html=True)  # 라벨 정렬용
                    if st.button("📁 찾기", key="btn_open_folder_browser", use_container_width=True):
                        st.session_state["show_folder_browser"] = not st.session_state.get("show_folder_browser", False)
                        st.rerun()

        # 계정별 폴더 매핑 요약 (모든 계정의 폴더 ID 한눈에)
        if _account_folders:
            with st.container(border=True):
                _summary_lines = []
                for _acc_lbl, _f_id in _account_folders.items():
                    _is_current = "  ← 현재 선택" if _acc_lbl == sel_account else ""
                    _summary_lines.append(
                        f"{account_badge(_acc_lbl)}: `{_f_id}`{_is_current}"
                    )
                st.markdown("**📁 이 상품의 계정별 폴더 매핑**")
                for _line in _summary_lines:
                    st.markdown(f"- {_line}")

        # ── Drive 폴더 브라우저 ────────────────────────────
        if not _account_folder and st.session_state.get("show_folder_browser", False):
            with st.container(border=True):
                st.markdown("**📁 Drive 폴더 브라우저** — 클릭해서 탐색, 원하는 폴더에서 [✓ 이 폴더 선택]")

                # 계정별 네비게이션 스택 (계정 변경 시 자동 초기화)
                _nav_key = f"folder_nav_{sel_account}"
                if _nav_key not in st.session_state:
                    st.session_state[_nav_key] = [{"id": "root", "name": "내 드라이브"}]
                _nav_stack = st.session_state[_nav_key]
                _current = _nav_stack[-1]

                # Breadcrumb
                _crumb_text = " / ".join(f"📁 {n['name']}" for n in _nav_stack)
                st.caption(_crumb_text)

                # 액션 바
                _ab1, _ab2, _ab3, _ab4 = st.columns([1, 1, 1, 3])
                with _ab1:
                    if st.button("← 상위", key="btn_nav_up",
                                 disabled=(len(_nav_stack) <= 1), use_container_width=True):
                        st.session_state[_nav_key] = _nav_stack[:-1]
                        st.rerun()
                with _ab2:
                    if st.button("🏠 루트", key="btn_nav_home",
                                 disabled=(len(_nav_stack) <= 1), use_container_width=True):
                        st.session_state[_nav_key] = [{"id": "root", "name": "내 드라이브"}]
                        st.rerun()
                with _ab3:
                    if st.button("✓ 이 폴더 선택", type="primary",
                                 key="btn_pick_folder", use_container_width=True):
                        # root이면 빈 문자열(루트 업로드), 아니면 폴더 ID
                        st.session_state["_picked_folder_id"] = "" if _current["id"] == "root" else _current["id"]
                        st.session_state["show_folder_browser"] = False
                        st.rerun()
                with _ab4:
                    if st.button("✕ 닫기", key="btn_close_browser"):
                        st.session_state["show_folder_browser"] = False
                        st.rerun()

                # 서브폴더 목록
                try:
                    with st.spinner("폴더 목록 조회 중…"):
                        _svc_browse = build_service(sel_account)
                        _subs = list_subfolders(_svc_browse, _current["id"])
                    if not _subs:
                        st.caption("ℹ️ 이 폴더에는 하위 폴더가 없습니다. [✓ 이 폴더 선택]을 누르면 여기를 상위 폴더로 사용합니다.")
                    else:
                        _subs_sorted = sorted(_subs, key=lambda x: x["name"].lower())
                        _COL_N = 3
                        for _row_start in range(0, len(_subs_sorted), _COL_N):
                            _grid = st.columns(_COL_N)
                            for _j, _sub in enumerate(_subs_sorted[_row_start:_row_start + _COL_N]):
                                with _grid[_j]:
                                    if st.button(f"📁 {_sub['name']}",
                                                 key=f"sub_{_sub['id']}", use_container_width=True):
                                        st.session_state[_nav_key] = _nav_stack + [{"id": _sub["id"], "name": _sub["name"]}]
                                        st.rerun()
                except Exception as _be:
                    st.error(f"폴더 조회 실패: {type(_be).__name__}: {_be}")

        # Q2: upload_key 카운터로 업로드 후 위젯 초기화
        _upload_key = st.session_state.get("upload_key", 0)
        uploaded_files = st.file_uploader(
            "이미지/영상 선택 (여러 장 가능)",
            type=["jpg", "jpeg", "png", "webp", "gif", "bmp", "mp4", "mov", "webm"],
            accept_multiple_files=True,
            key=f"file_uploader_{_upload_key}",
            help="이미지 + GIF + 동영상(mp4/mov/webm) 업로드 가능. 동영상 Vision Pass는 Gemini로만 가능.",
        )

        # 클립보드 붙여넣기 — 스크린샷·복사한 이미지 누적 후 함께 업로드
        if _PASTE_OK:
            _paste_key = st.session_state.get("paste_key", 0)
            _pc1, _pc2 = st.columns([1, 3])
            with _pc1:
                _paste_result = _paste_image_button(
                    label="📋 클립보드 붙여넣기",
                    key=f"paste_btn_{_paste_key}",
                    errors="ignore",
                )
            with _pc2:
                st.caption("버튼 클릭 후 **Ctrl+V** — 캡처/복사한 이미지가 PNG로 누적됩니다.")
            if _paste_result.image_data is not None:
                st.session_state.setdefault("pasted_images", [])
                _ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                st.session_state["pasted_images"].append({
                    "name": f"paste_{_ts}.png",
                    "image": _paste_result.image_data,
                })
                st.session_state["paste_key"] = _paste_key + 1
                st.rerun()
        else:
            st.caption("ℹ️ `streamlit-paste-button` 미설치 — 붙여넣기 비활성. `pip install streamlit-paste-button` 후 재시작.")

        # 누적된 붙여넣기 이미지 미리보기
        _pasted = st.session_state.get("pasted_images", [])
        if _pasted:
            st.markdown(f"**📋 붙여넣기 누적: {len(_pasted)}장**")
            _cols = st.columns(min(4, len(_pasted)))
            for _i, _p in enumerate(_pasted):
                with _cols[_i % len(_cols)]:
                    st.image(_p["image"], caption=_p["name"], use_container_width=True)
                    if st.button("🗑️", key=f"del_paste_{_i}"):
                        st.session_state["pasted_images"].pop(_i)
                        st.rerun()
            if st.button("🧹 붙여넣기 전체 비우기", key="btn_clear_pasted"):
                st.session_state["pasted_images"] = []
                st.rerun()

        # 업로드 대상 통합 (file_uploader + 붙여넣기 이미지)
        _total_count = len(uploaded_files or []) + len(_pasted)

        if _total_count and st.button(
            f"☁️ {_total_count}개 {account_badge(sel_account)} Drive 업로드",
            type="primary", key="btn_drive_upload",
        ):
            try:
                svc = build_service(sel_account)
                if _account_folder:
                    folder_id = _account_folder
                else:
                    parent_id    = parse_folder_id(_root_folder_input) if _root_folder_input.strip() else None
                    product_name = row.get("제품명") or f"product_{product_id}"
                    with st.spinner(
                        f"{account_badge(sel_account)} Drive에 폴더 생성 중 — '{product_name}'…"
                    ):
                        folder_id = get_or_create_folder(svc, product_name, parent_id)
                    # 계정별_폴더_ids JSON에 저장 (드라이브_폴더_id 호환 컬럼도 함께 갱신)
                    set_account_folder(product_id, sel_account, folder_id)
                    st.info(f"{account_badge(sel_account)} 폴더 생성 완료: `{folder_id}`")

                # 업로드 입력 정규화: {name, bytes} 통일
                _normalized: list[dict] = []
                if uploaded_files:
                    for uf in uploaded_files:
                        _normalized.append({"name": uf.name, "bytes": uf.read()})
                for _p in _pasted:
                    _buf = io.BytesIO()
                    _p["image"].save(_buf, format="PNG")
                    _normalized.append({"name": _p["name"], "bytes": _buf.getvalue()})

                # Q2: 중복 파일명 체크
                _existing_names = {f.get("파일명") for f in get_files(product_id)}
                _new_files = [n for n in _normalized if n["name"] not in _existing_names]
                _dup_files = [n for n in _normalized if n["name"] in _existing_names]
                if _dup_files:
                    st.warning(
                        f"이미 등록된 파일 {len(_dup_files)}개 건너뜀: "
                        + ", ".join(f"`{n['name']}`" for n in _dup_files)
                    )

                success, fail = 0, 0
                if _new_files:
                    prog = st.progress(0, text="업로드 중…")
                    for i, n in enumerate(_new_files):
                        try:
                            result = upload_file(svc, n["bytes"], n["name"], folder_id)
                            upsert_파일(
                                product_id,
                                [{"파일명": result["name"], "파일_유형": _guess_type(n["name"]),
                                  "드라이브_파일_id": result["id"], "드라이브_url": result.get("webViewLink"),
                                  "업로드일": None}],
                                sel_account,
                            )
                            success += 1
                        except Exception as _upload_err:
                            st.warning(f"실패: {n['name']} — {_upload_err}")
                            fail += 1
                        prog.progress((i + 1) / len(_new_files), text=f"{i+1}/{len(_new_files)} 처리 중…")
                    prog.empty()

                if success:
                    st.success(f"✅ {success}개 업로드 완료!" + (f" ({fail}개 실패)" if fail else ""))
                    # Q2: 업로드 성공 후 파일 선택기 초기화 + 붙여넣기 비우기
                    st.session_state["upload_key"] = _upload_key + 1
                    st.session_state["pasted_images"] = []
                    st.rerun()
                elif not _dup_files:
                    st.error("업로드된 파일이 없습니다.")
            except Exception as _err:
                st.error(f"업로드 실패: {type(_err).__name__}: {_err}")

    # ── Vision Pass ───────────────────────────────────────
    _vp_images = [
        f for f in get_files(product_id)
        if f.get("파일_유형") == "image" and f.get("드라이브_파일_id")
    ]

    st.divider()

    _vp_exp_label = (
        f"🔍 Vision Pass — {len(_vp_images)}장 분석 가능"
        if _vp_images else "🔍 Vision Pass (이미지 없음 — 먼저 업로드)"
    )
    with st.expander(_vp_exp_label, expanded=bool(_vp_images) and is_owner()):
        if not is_owner():
            st.info("🔒 Vision Pass 실행은 owner 전용입니다. 저장된 이력만 조회할 수 있습니다.")
        elif not _vp_images:
            st.caption("이미지를 업로드하면 Vision Pass를 실행할 수 있습니다.")
        else:
            # Q4: 실행 모드 선택
            _vp_mode = st.radio(
                "실행 모드",
                ["일괄 실행 (전체 이미지 → 1회 호출)", "이미지별 실행 (이미지마다 개별 모델 선택)"],
                horizontal=True,
                key="vp_mode",
            )

            # ── 공통 프롬프트 편집 (체크박스 토글 — expander 중첩 불가) ──
            if st.checkbox("📄 프롬프트 편집", value=False, key="vp_show_prompt"):
                _fam_main_chk = _vp_family(
                    st.session_state.get("vp_main_model", _ALL_VP_MODELS[0])
                )
                _fam_sub_chk = _vp_family(
                    st.session_state.get("vp_sub_model", _ALL_VP_MODELS[len(_CLAUDE_MODELS)])
                )
                _pp1, _pp2 = st.columns(2)
                with _pp1:
                    st.markdown(f"**Claude 프롬프트** (`core_claude.md`)")
                    _sk_claude = "vp_prompt_claude"
                    if _sk_claude not in st.session_state:
                        st.session_state[_sk_claude] = _vp_load_prompt("claude-sonnet-4-6")
                    _claude_prompt_val = st.text_area(
                        "Claude", value=st.session_state[_sk_claude],
                        height=180, key="vp_editor_claude",
                        label_visibility="collapsed",
                    )
                    if st.button("💾 Claude 프롬프트 저장", key="vp_btn_save_claude"):
                        _vp_prompt_path("claude-sonnet-4-6").write_text(_claude_prompt_val, encoding="utf-8")
                        st.session_state[_sk_claude] = _claude_prompt_val
                        st.success("저장!")
                with _pp2:
                    st.markdown(f"**Gemini 프롬프트** (`core_gemini.md`)")
                    _sk_gemini = "vp_prompt_gemini"
                    if _sk_gemini not in st.session_state:
                        st.session_state[_sk_gemini] = _vp_load_prompt("gemini-2.5-flash")
                    _gemini_prompt_val = st.text_area(
                        "Gemini", value=st.session_state[_sk_gemini],
                        height=180, key="vp_editor_gemini",
                        label_visibility="collapsed",
                    )
                    if st.button("💾 Gemini 프롬프트 저장", key="vp_btn_save_gemini"):
                        _vp_prompt_path("gemini-2.5-flash").write_text(_gemini_prompt_val, encoding="utf-8")
                        st.session_state[_sk_gemini] = _gemini_prompt_val
                        st.success("저장!")

            st.divider()

            # ════════════════════════════════════════════════
            # 모드 A: 일괄 실행
            # ════════════════════════════════════════════════
            if _vp_mode.startswith("일괄"):
                st.caption(
                    "모든 이미지를 **1번의 API 호출**로 묶어 전송 → 이미지 전체를 종합한 "
                    "시각설명 **1개** 생성. 빠르고 통합적인 결과가 필요할 때 사용하세요."
                )

                # ── 엔진 선택 영속화: app_settings의 단계 00 키와 양방향 바인딩 ──
                # 첫 진입 시 설정 → session_state 초기화. 이후 변경은 on_change로 settings에 저장(DB 동기화).
                from pipeline.settings import load as _vp_settings_load, save as _vp_settings_save

                _cfg_init = _vp_settings_load()
                if "vp_main_model" not in st.session_state:
                    _v = _cfg_init.get("primary_model_00") or _ALL_VP_MODELS[0]
                    st.session_state["vp_main_model"] = _v if _v in _ALL_VP_MODELS else _ALL_VP_MODELS[0]
                if "vp_sub_model" not in st.session_state:
                    _v = _cfg_init.get("compare_model_00") or "gemini-2.5-flash"
                    _fallback_sub = (
                        _ALL_VP_MODELS[len(_CLAUDE_MODELS)]
                        if len(_CLAUDE_MODELS) < len(_ALL_VP_MODELS) else _ALL_VP_MODELS[0]
                    )
                    st.session_state["vp_sub_model"] = _v if _v in _ALL_VP_MODELS else _fallback_sub
                if "vp_sub_on" not in st.session_state:
                    st.session_state["vp_sub_on"] = bool(_cfg_init.get("compare_enabled_00", True))

                def _persist_vp_engines() -> None:
                    _cfg = _vp_settings_load()
                    _cfg["primary_model_00"]   = st.session_state.get("vp_main_model", _ALL_VP_MODELS[0])
                    _cfg["compare_model_00"]   = st.session_state.get("vp_sub_model", _ALL_VP_MODELS[0])
                    _cfg["compare_enabled_00"] = bool(st.session_state.get("vp_sub_on", True))
                    try:
                        _vp_settings_save(_cfg)
                    except Exception:
                        # DB 동기화 실패 — 로컬엔 이미 저장됨. 엔진 선택은 부수 기능이라 조용히 알림.
                        st.toast("⚠️ 엔진 설정 DB 동기화 실패 (로컬 저장됨)", icon="⚠️")

                _ec1, _ec2 = st.columns(2)
                with _ec1:
                    st.markdown("**메인 엔진**")
                    _vp_main_model = st.selectbox(
                        "메인 모델", _ALL_VP_MODELS,
                        key="vp_main_model", label_visibility="collapsed",
                        on_change=_persist_vp_engines,
                    )
                with _ec2:
                    st.markdown("**서브 엔진**")
                    _sub_c = st.columns([3, 1])
                    with _sub_c[0]:
                        _vp_sub_model = st.selectbox(
                            "서브 모델", _ALL_VP_MODELS,
                            key="vp_sub_model", label_visibility="collapsed",
                            on_change=_persist_vp_engines,
                        )
                    with _sub_c[1]:
                        _vp_sub_on = st.toggle(
                            "ON", key="vp_sub_on",
                            on_change=_persist_vp_engines,
                        )

                _run_label = (
                    f"🔍 일괄 실행 ({_vp_main_model}"
                    + (f" + {_vp_sub_model}" if _vp_sub_on else "")
                    + f", {len(_vp_images)}장)"
                )
                if st.button(_run_label, type="primary", key="btn_vp_run_bulk"):
                    try:
                        import threading

                        from pipeline.drive_client import ACCOUNTS as _ACCTS, build_service as _bsvc, download_file as _dlf
                        from pipeline.llm import (
                            generate_vision_claude,
                            generate_vision_claude_stream,
                            generate_vision_gemini,
                            generate_vision_gemini_stream,
                        )
                        from pipeline.loader import build_vision_input

                        _acct_label = _vp_images[0].get("계정") or _ACCTS[0]["label"]
                        _svc = _bsvc(_acct_label)

                        _image_data: list[tuple[bytes, str]] = []
                        _dl_prog = st.progress(0, text="이미지 다운로드 중…")
                        for _i, _f in enumerate(_vp_images):
                            _img_bytes, _mime = _dlf(_svc, _f["드라이브_파일_id"])
                            _image_data.append((_img_bytes, _mime))
                            _dl_prog.progress((_i + 1) / len(_vp_images), text=f"다운로드 {_i+1}/{len(_vp_images)}")
                        _dl_prog.empty()

                        _user_text = build_vision_input(row)
                        _fam_main  = _vp_family(_vp_main_model)
                        _fam_sub   = _vp_family(_vp_sub_model)
                        _cur_main  = st.session_state.get("vp_editor_claude" if _fam_main == "claude" else "vp_editor_gemini") or _vp_load_prompt(_vp_main_model)
                        _cur_sub   = st.session_state.get("vp_editor_claude" if _fam_sub == "claude" else "vp_editor_gemini") or _vp_load_prompt(_vp_sub_model)

                        def _stream_engine(model: str, prompt: str):
                            if _vp_family(model) == "claude":
                                yield from generate_vision_claude_stream(
                                    prompt, _image_data, _user_text, model=model,
                                )
                            else:
                                yield from generate_vision_gemini_stream(
                                    prompt, _image_data, _user_text, model=model,
                                )

                        def _run_engine_sync(model: str, prompt: str) -> str:
                            if _vp_family(model) == "claude":
                                return generate_vision_claude(prompt, _image_data, _user_text, model=model)
                            return generate_vision_gemini(prompt, _image_data, _user_text, model=model)

                        _vp_res: dict[str, str] = {}

                        # 서브 ON이면 백그라운드 thread로 비스트리밍 호출 (UI는 메인 스트리밍만 표시)
                        _sub_state: dict = {"text": "", "err": None, "done": False}
                        _sub_thread = None
                        if _vp_sub_on:
                            def _run_sub():
                                try:
                                    _sub_state["text"] = _run_engine_sync(_vp_sub_model, _cur_sub)
                                except Exception as _se:
                                    _sub_state["err"] = f"[ERROR] {type(_se).__name__}: {_se}"
                                finally:
                                    _sub_state["done"] = True
                            _sub_thread = threading.Thread(target=_run_sub, daemon=True)
                            _sub_thread.start()

                        # 메인 스트리밍 표시
                        with st.container(border=True):
                            st.caption(f"🟢 **{_vp_main_model}** 분석 중 — 응답을 실시간으로 받는 중")
                            _live_area = st.empty()
                        _main_acc = ""
                        _last_render_len = 0
                        try:
                            for _chunk in _stream_engine(_vp_main_model, _cur_main):
                                _main_acc += _chunk
                                # 30자 또는 줄바꿈마다 갱신 (너무 잦은 갱신 방지)
                                if (len(_main_acc) - _last_render_len) >= 30 or _chunk.endswith("\n"):
                                    _live_area.markdown(
                                        f"```\n{_main_acc}\n```"
                                    )
                                    _last_render_len = len(_main_acc)
                            _live_area.markdown(f"```\n{_main_acc}\n```")
                            _vp_res["main"] = _main_acc
                        except Exception as _e:
                            _vp_res["main"] = f"[ERROR] {type(_e).__name__}: {_e}"
                            st.error(f"메인 엔진 실패: {_e}")

                        # 서브 결과 대기
                        if _sub_thread is not None:
                            with st.spinner(f"⏳ 서브 엔진 **{_vp_sub_model}** 결과 대기 중…"):
                                _sub_thread.join()
                            if _sub_state["err"]:
                                _vp_res["sub"] = _sub_state["err"]
                            else:
                                _vp_res["sub"] = _sub_state["text"]

                        st.session_state["vp_results"]    = _vp_res
                        st.session_state["vp_main_label"] = _vp_main_model
                        st.session_state["vp_sub_label"]  = _vp_sub_model if _vp_sub_on else None

                        # 일괄실행 결과를 DB 이력에 저장 (파일_id=None, 실행_모드='bulk')
                        try:
                            if _vp_res.get("main") and not _vp_res["main"].startswith("[ERROR]"):
                                insert_비전패스_이력(
                                    상품_id=product_id, 파일_id=None,
                                    모델명=_vp_main_model, 프롬프트=_cur_main,
                                    결과=_vp_res["main"], 실행_모드="bulk",
                                )
                            if _vp_sub_on and _vp_res.get("sub") and not _vp_res["sub"].startswith("[ERROR]"):
                                insert_비전패스_이력(
                                    상품_id=product_id, 파일_id=None,
                                    모델명=_vp_sub_model, 프롬프트=_cur_sub,
                                    결과=_vp_res["sub"], 실행_모드="bulk",
                                )
                        except Exception as _hist_err:
                            st.warning(f"이력 저장 실패 (결과는 정상): {_hist_err}")

                        st.success("분석 완료! 스펙 탭에서 결과를 참고해 필드를 채우세요.")

                    except Exception as _vp_err:
                        st.error(f"Vision Pass 실패: {type(_vp_err).__name__}: {_vp_err}")

                # 결과 표시
                _vp_stored   = st.session_state.get("vp_results", {})
                _vp_main_lbl = st.session_state.get("vp_main_label", "")
                _vp_sub_lbl  = st.session_state.get("vp_sub_label")

                if _vp_stored:
                    st.divider()
                    st.caption("📥 = 시각설명에 반영 (페이지 하단 충돌 해소 패널에서 검토 후 최종 저장)")
                    if _vp_sub_lbl:
                        _r1, _r2 = st.columns(2)
                        with _r1:
                            st.markdown(f"**메인 — {_vp_main_lbl}**")
                            st.text_area("메인 결과", value=_vp_stored.get("main", ""), height=260,
                                         key="vp_view_main", disabled=True,
                                         label_visibility="collapsed")
                            if st.button("📥 메인 반영", key="vp_btn_use_main"):
                                st.session_state["vp_pending"] = {
                                    "items": [(_vp_main_lbl, _vp_stored.get("main", ""))],
                                    "mode": "bulk",
                                }
                                st.rerun()
                        with _r2:
                            st.markdown(f"**서브 — {_vp_sub_lbl}**")
                            st.text_area("서브 결과", value=_vp_stored.get("sub", ""), height=260,
                                         key="vp_view_sub", disabled=True,
                                         label_visibility="collapsed")
                            if st.button("📥 서브 반영", key="vp_btn_use_sub"):
                                st.session_state["vp_pending"] = {
                                    "items": [(_vp_sub_lbl, _vp_stored.get("sub", ""))],
                                    "mode": "bulk",
                                }
                                st.rerun()
                        # 3-way: 메인+서브 동시 반영
                        if st.button("📥📥 메인+서브 동시 반영 (3-way 비교)",
                                     key="vp_btn_use_both", use_container_width=True):
                            st.session_state["vp_pending"] = {
                                "items": [
                                    (_vp_main_lbl, _vp_stored.get("main", "")),
                                    (_vp_sub_lbl,  _vp_stored.get("sub", "")),
                                ],
                                "mode": "bulk",
                            }
                            st.rerun()
                    else:
                        st.markdown(f"**{_vp_main_lbl}**")
                        st.text_area("결과", value=_vp_stored.get("main", ""), height=260,
                                     key="vp_view_main_only", disabled=True,
                                     label_visibility="collapsed")
                        if st.button("📥 결과 반영", key="vp_btn_use_main_only"):
                            st.session_state["vp_pending"] = {
                                "items": [(_vp_main_lbl, _vp_stored.get("main", ""))],
                                "mode": "bulk",
                            }
                            st.rerun()

            # ════════════════════════════════════════════════
            # 모드 B: 이미지별 실행 (Q4)
            # ════════════════════════════════════════════════
            else:
                st.caption(
                    "이미지마다 **별도 API 호출** → 각 이미지별 결과를 이력으로 저장. "
                    "어떤 이미지에서 어떤 정보가 나왔는지 추적하거나, "
                    "결과를 선별해 시각설명에 반영할 때 사용하세요."
                )

                # ── 전체 이미지 병렬 실행 ──────────────────
                # Streamlit은 버튼 동시 클릭을 지원하지 않으므로
                # 개별 버튼 대신 여기서 ThreadPoolExecutor로 한 번에 처리
                _default_para_model = (
                    "gemini-2.5-flash"
                    if "gemini-2.5-flash" in _ALL_VP_MODELS
                    else _ALL_VP_MODELS[0]
                )
                _para_c1, _para_c2 = st.columns([3, 1])
                with _para_c1:
                    _para_model = st.selectbox(
                        "전체 병렬 실행 모델",
                        _ALL_VP_MODELS,
                        index=_ALL_VP_MODELS.index(_default_para_model),
                        key="vp_img_para_model",
                        help="아래 이미지 전체를 이 모델로 동시에 실행합니다.",
                    )
                with _para_c2:
                    _do_para = st.button(
                        f"⚡ 전체 {len(_vp_images)}장 병렬 실행",
                        type="primary",
                        use_container_width=True,
                        key="btn_vp_para_all",
                    )

                if _do_para:
                    try:
                        from pipeline.drive_client import ACCOUNTS as _ACCTS3, build_service as _bsvc3, download_file as _dlf3
                        from pipeline.llm import generate_vision_claude, generate_vision_gemini
                        from pipeline.loader import build_vision_input
                        from concurrent.futures import ThreadPoolExecutor, as_completed

                        _fam3 = _vp_family(_para_model)
                        _prompt3 = st.session_state.get(
                            "vp_editor_claude" if _fam3 == "claude" else "vp_editor_gemini"
                        ) or _vp_load_prompt(_para_model)
                        _acct3 = _vp_images[0].get("계정") or _ACCTS3[0]["label"]
                        _svc3  = _bsvc3(_acct3)

                        def _run_single_img(img_f: dict) -> tuple[dict, str]:
                            _b3, _m3 = _dlf3(_svc3, img_f["드라이브_파일_id"])
                            if _fam3 == "claude":
                                _r3 = generate_vision_claude(_prompt3, [(_b3, _m3)], build_vision_input(row), model=_para_model)
                            else:
                                _r3 = generate_vision_gemini(_prompt3, [(_b3, _m3)], build_vision_input(row), model=_para_model)
                            return img_f, _r3

                        _para_results: list[tuple[dict, str]] = []
                        _para_errors:  list[str] = []
                        _max_workers = min(len(_vp_images), 5)
                        _para_prog = st.progress(
                            0, text=f"{_para_model} — 0/{len(_vp_images)} 완료"
                        )
                        _done_n = 0
                        with ThreadPoolExecutor(max_workers=_max_workers) as _ex3:
                            _futs = {_ex3.submit(_run_single_img, f): f for f in _vp_images}
                            for _fut in as_completed(_futs):
                                try:
                                    _para_results.append(_fut.result())
                                except Exception as _fe:
                                    _para_errors.append(f"{_futs[_fut].get('파일명', '?')}: {_fe}")
                                _done_n += 1
                                _para_prog.progress(
                                    _done_n / len(_vp_images),
                                    text=f"{_para_model} — {_done_n}/{len(_vp_images)} 완료",
                                )
                        _para_prog.empty()

                        # DB 이력 저장
                        _para_saved = 0
                        for _pf, _pr in _para_results:
                            try:
                                insert_비전패스_이력(
                                    상품_id=product_id,
                                    파일_id=_pf["드라이브_파일_id"],
                                    모델명=_para_model,
                                    프롬프트=_prompt3,
                                    결과=_pr,
                                    실행_모드="single",
                                )
                                _para_saved += 1
                            except Exception as _pe:
                                _para_errors.append(f"이력저장 실패 ({_pf.get('파일명', '?')}): {_pe}")

                        for _err_msg in _para_errors:
                            st.warning(_err_msg)
                        st.success(f"✅ {_para_saved}/{len(_vp_images)}장 완료! 아래 이력을 확인하세요.")
                        st.rerun()
                    except Exception as _para_err:
                        st.error(f"병렬 실행 실패: {type(_para_err).__name__}: {_para_err}")

                st.divider()

                # 이 상품의 모든 개별 실행 이력을 한 번에 조회 (파일별 그룹화)
                _all_history = list_비전패스_이력(product_id)
                _hist_by_fid: dict[str, list[dict]] = {}
                for _h in _all_history:
                    if _h.get("실행_모드") == "single" and _h.get("파일_id"):
                        _hist_by_fid.setdefault(_h["파일_id"], []).append(_h)

                for _img_f in _vp_images:
                    _fid   = _img_f["드라이브_파일_id"]
                    _fname = _img_f.get("파일명", _fid)
                    _img_history = _hist_by_fid.get(_fid, [])
                    with st.container(border=True):
                        _ic1, _ic2, _ic3 = st.columns([2, 3, 4])
                        with _ic1:
                            try:
                                image_with_fallback(
                                    _fid,
                                    size=200,
                                    scope_key=f"product_edit_{product_id}",
                                    alt=_fname,
                                )
                            except Exception:
                                pass
                            st.caption(_fname)
                        with _ic2:
                            _img_model = st.selectbox(
                                "모델",
                                _ALL_VP_MODELS,
                                index=_ALL_VP_MODELS.index("gemini-2.5-flash")
                                      if "gemini-2.5-flash" in _ALL_VP_MODELS else 0,
                                key=f"vp_img_model_{_fid}",
                                label_visibility="collapsed",
                            )
                            if st.button("▶ 실행", key=f"vp_img_run_{_fid}", use_container_width=True):
                                try:
                                    from pipeline.drive_client import ACCOUNTS as _ACCTS2, build_service as _bsvc2, download_file as _dlf2
                                    from pipeline.llm import (
                                        generate_vision_claude_stream,
                                        generate_vision_gemini_stream,
                                    )
                                    from pipeline.loader import build_vision_input

                                    _acct2 = _img_f.get("계정") or _ACCTS2[0]["label"]
                                    _svc2  = _bsvc2(_acct2)
                                    _fam2  = _vp_family(_img_model)
                                    _prompt2 = st.session_state.get(
                                        "vp_editor_claude" if _fam2 == "claude" else "vp_editor_gemini"
                                    ) or _vp_load_prompt(_img_model)

                                    with st.spinner("이미지 다운로드 중…"):
                                        _b2, _m2 = _dlf2(_svc2, _fid)

                                    with st.container(border=True):
                                        st.caption(f"🟢 **{_img_model}** 분석 중 — 응답 실시간 수신")
                                        _live2 = st.empty()
                                    _acc2 = ""
                                    _last_len2 = 0
                                    try:
                                        if _fam2 == "claude":
                                            _gen2 = generate_vision_claude_stream(
                                                _prompt2, [(_b2, _m2)], build_vision_input(row),
                                                model=_img_model,
                                            )
                                        else:
                                            _gen2 = generate_vision_gemini_stream(
                                                _prompt2, [(_b2, _m2)], build_vision_input(row),
                                                model=_img_model,
                                            )
                                        for _ck in _gen2:
                                            _acc2 += _ck
                                            if (len(_acc2) - _last_len2) >= 30 or _ck.endswith("\n"):
                                                _live2.markdown(f"```\n{_acc2}\n```")
                                                _last_len2 = len(_acc2)
                                        _live2.markdown(f"```\n{_acc2}\n```")
                                        _res2 = _acc2
                                    except Exception as _se2:
                                        _res2 = f"[ERROR] {type(_se2).__name__}: {_se2}"

                                    # DB 이력에 영구 저장
                                    insert_비전패스_이력(
                                        상품_id=product_id, 파일_id=_fid,
                                        모델명=_img_model, 프롬프트=_prompt2,
                                        결과=_res2, 실행_모드="single",
                                    )
                                    st.success(f"완료 ({_img_model}) — 아래 이력에 추가됨")
                                    st.rerun()
                                except Exception as _img_err:
                                    st.error(f"실패: {_img_err}")
                        with _ic3:
                            if _img_history:
                                st.markdown(f"**📜 실행 이력 ({len(_img_history)}건)**")
                                # Streamlit은 expander 중첩 불가 → 펼침/접힘을 세션 상태로 제어
                                for _idx, _h in enumerate(_img_history):
                                    _hid = _h["id"]
                                    _show_key = f"vp_hist_show_{_hid}"
                                    # 최근 1건은 기본 펼침, 나머지는 접힘
                                    if _show_key not in st.session_state:
                                        st.session_state[_show_key] = (_idx == 0)
                                    _is_open = st.session_state[_show_key]
                                    _arrow = "▼" if _is_open else "▶"
                                    _hdr_label = f"{_arrow} {_h['모델명']} · {_fmt_dt(_h.get('생성일'))}"
                                    with st.container(border=True):
                                        if st.button(
                                            _hdr_label,
                                            key=f"vp_hist_toggle_{_hid}",
                                            use_container_width=True,
                                        ):
                                            st.session_state[_show_key] = not _is_open
                                            st.rerun()
                                        if _is_open:
                                            st.text_area(
                                                "결과",
                                                value=_h.get("결과", ""),
                                                height=180,
                                                key=f"vp_hist_view_{_hid}",
                                                disabled=True,
                                                label_visibility="collapsed",
                                            )
                                            _bc1, _bc2 = st.columns([3, 1])
                                            with _bc1:
                                                if st.button(
                                                    "📥 시각설명에 반영",
                                                    key=f"vp_hist_apply_{_hid}",
                                                    use_container_width=True,
                                                ):
                                                    st.session_state["vp_pending"] = {
                                                        "items": [(_h["모델명"], _h.get("결과", ""))],
                                                        "mode": "partial",
                                                    }
                                                    st.rerun()
                                            with _bc2:
                                                if st.button(
                                                    "🗑",
                                                    key=f"vp_hist_del_{_hid}",
                                                    help="이 이력 삭제",
                                                ):
                                                    try:
                                                        delete_비전패스_이력(_hid)
                                                        st.rerun()
                                                    except Exception as _de:
                                                        st.error(f"삭제 실패: {_de}")
                            else:
                                st.caption("▶ 실행 후 결과가 이곳에 이력으로 저장됩니다.")

            # ──────────────────────────────────────────────
            # 저장된 시각설명 + 충돌 해소 UI (두 모드 공통)
            # ──────────────────────────────────────────────
            _saved_desc = row.get("시각설명") or ""
            _pending    = st.session_state.get("vp_pending")  # {"items": [(라벨, 텍스트), ...]}

            st.divider()
            st.markdown("### 📝 최종 시각설명")

            if _pending:
                # ── 충돌 해소 UI ──
                _items = _pending["items"]
                _items_label = " + ".join(lbl for lbl, _ in _items)

                if not _saved_desc:
                    # 케이스 1: 기존이 없음 → 신규를 그대로 표시 (편집 가능)
                    st.info(f"기존 시각설명 없음. 신규 결과({_items_label})를 편집 후 저장하세요.")
                    if len(_items) == 1:
                        _initial = _items[0][1]
                    else:
                        _initial = "\n\n".join(f"[{lbl}]\n{txt}" for lbl, txt in _items)
                    _val = st.text_area(
                        "신규 시각설명 (편집 가능)",
                        value=_initial, height=240, key="vp_pending_new_only",
                    )
                    _bc1, _bc2 = st.columns([3, 1])
                    with _bc1:
                        if st.button("💾 시각설명으로 저장", type="primary",
                                     use_container_width=True, key="btn_pending_save_new"):
                            try:
                                update_시각설명(product_id, _val)
                                with st.spinner("🤖 스펙·기타 특징 자동 추출 중…"):
                                    _spec_n, _bul_n = _auto_apply_after_vision(product_id, _val)
                                _msg = f"저장 완료! 자동 반영: 스펙 {_spec_n}개 / bullet {_bul_n}개"
                                st.success(_msg)
                                st.session_state.pop("vp_pending", None)
                                st.session_state.pop("vp_results", None)
                                st.rerun()
                            except Exception as _e:
                                st.error(f"저장 실패: {_e}")
                    with _bc2:
                        if st.button("❌ 취소", use_container_width=True,
                                     key="btn_pending_cancel_new"):
                            st.session_state.pop("vp_pending", None)
                            st.rerun()
                else:
                    # 케이스 2: 기존 시각설명 있음 → mode에 따라 분기
                    #   - "partial" (이미지별 결과·동영상 결과 등 보완성 패스): 누적 append
                    #   - "bulk"    (일괄 재실행 결과): 시각설명 덮어쓰기 + 스펙 필드 항목별 diff
                    _pmode = _pending.get("mode", "partial")  # 기본은 안전한 partial

                    if _pmode == "partial":
                        # ── partial: append 정책 ──
                        st.info(f"📎 신규 결과({_items_label})를 기존 시각설명 뒤에 누적 추가합니다.")
                        st.caption(
                            "부분 비전패스 결과는 기존 시각설명을 덮어쓰지 않고 라벨과 함께 아래에 추가됩니다. "
                            "필요하면 텍스트를 직접 수정한 뒤 저장하세요. "
                            "스펙 필드는 누적된 전체 텍스트에서 **빈 칸만** 자동 채워집니다 (기존 값 보호)."
                        )

                        _now_label = datetime.now().strftime("%m-%d %H:%M")
                        _appended_parts = [_saved_desc.rstrip()]
                        for _lbl, _txt in _items:
                            _appended_parts.append(
                                f"\n──── [부분 보충 · {_lbl} · {_now_label}]\n{(_txt or '').strip()}"
                            )
                        _initial_appended = "\n".join(_appended_parts)

                        _val = st.text_area(
                            "누적된 시각설명 (편집 가능)",
                            value=_initial_appended, height=360, key="vp_pending_appended",
                        )

                        _bc1, _bc2 = st.columns([3, 1])
                        with _bc1:
                            if st.button(
                                "💾 시각설명으로 저장",
                                type="primary", use_container_width=True,
                                key="btn_pending_save_appended",
                            ):
                                try:
                                    update_시각설명(product_id, _val)
                                    with st.spinner("🤖 스펙·기타 특징 자동 추출 중…"):
                                        _spec_n, _bul_n = _auto_apply_after_vision(product_id, _val)
                                    st.success(f"저장 완료! 자동 반영: 스펙 {_spec_n}개 / bullet {_bul_n}개")
                                    st.session_state.pop("vp_pending", None)
                                    st.session_state.pop("vp_results", None)
                                    st.rerun()
                                except Exception as _e:
                                    st.error(f"저장 실패: {_e}")
                        with _bc2:
                            if st.button(
                                "❌ 취소", use_container_width=True,
                                key="btn_pending_cancel_appended",
                            ):
                                st.session_state.pop("vp_pending", None)
                                st.rerun()
                    else:
                        # ── bulk: 시각설명 덮어쓰기 + 스펙 필드 항목별 diff ──
                        st.info(
                            f"🔄 일괄 재실행 결과({_items_label})로 **시각설명 덮어쓰기** + "
                            "스펙 필드 변경분 항목별 검토"
                        )
                        st.caption(
                            "기존 시각설명을 신규로 교체합니다. 스펙 필드는 신규 결과로부터 추출해 "
                            "**기존과 다른 항목만** 표시 — 항목별로 [기존 / 신규 / 직접 입력]을 선택하세요."
                        )

                        # 신규 시각설명 (단일 또는 다중 결과)
                        if len(_items) == 1:
                            _new_desc_default = _items[0][1] or ""
                        else:
                            _new_desc_default = "\n\n".join(
                                f"[{lbl}]\n{(txt or '').strip()}" for lbl, txt in _items
                            )

                        _new_desc_val = st.text_area(
                            "신규 시각설명 (편집 가능 — 저장 시 기존 시각설명을 이 내용으로 덮어씁니다)",
                            value=_new_desc_default, height=240,
                            key="vp_pending_bulk_desc",
                        )

                        # 스펙 필드 추출 (첫 진입 시 자동 1회 호출. 사용자가 텍스트 수정 후 재추출은 버튼)
                        _ext = st.session_state.get("_spec_extracted_bulk")
                        _ec1, _ec2 = st.columns([3, 1])
                        with _ec2:
                            if st.button("🔄 다시 추출", key="btn_bulk_re_extract",
                                         use_container_width=True,
                                         help="시각설명 텍스트를 수정한 뒤 누르면 스펙 필드를 다시 추출합니다."):
                                st.session_state.pop("_spec_extracted_bulk", None)
                                _ext = None

                        if _ext is None:
                            from pipeline.settings import load as _ls_bulk
                            from pipeline.vision_merge import extract_스펙
                            _cfg_bulk = _ls_bulk()
                            _ext_model = _cfg_bulk.get("primary_model_00") or "claude-sonnet-4-6"
                            with st.spinner(f"🤖 {_ext_model} 으로 신규 시각설명에서 스펙 필드 추출 중…"):
                                try:
                                    _ext = extract_스펙(_new_desc_val, model=_ext_model)
                                except Exception as _ee:
                                    _ext = {"_error": f"{type(_ee).__name__}: {_ee}"}
                            st.session_state["_spec_extracted_bulk"] = _ext

                        if _ext.get("_error"):
                            st.error(f"스펙 추출 실패: {_ext.get('_error')}")
                            if _ext.get("_raw"):
                                with st.expander("LLM 원본 응답"):
                                    st.code(_ext.get("_raw"), language=None)
                        else:
                            # 정규화 후 diff 계산
                            def _norm_val(v) -> str:
                                if v is None:
                                    return ""
                                if isinstance(v, (int, float)) and v == 0:
                                    return ""
                                return str(v).strip()

                            _diff_rows = []
                            for _f in SPEC_FIELDS:
                                _name = _f["name"]
                                _new_v = _ext.get(_name)
                                _cur_v = row.get(_name)
                                if _norm_val(_cur_v) != _norm_val(_new_v):
                                    _diff_rows.append({
                                        "f": _f, "name": _name, "label": _f["label"],
                                        "cur": _cur_v, "new": _new_v,
                                    })

                            st.markdown(f"#### 🔍 스펙 필드 변경분 ({len(_diff_rows)}건)")

                            _resolved_fields: dict[str, object] = {}
                            if not _diff_rows:
                                st.success("기존과 동일한 값들입니다. 변경할 필드 없음.")
                            else:
                                for _di, _d in enumerate(_diff_rows):
                                    with st.container(border=True):
                                        st.markdown(f"**{_d['label']}**")
                                        _cur_disp = "(없음)" if _d["cur"] in (None, "", 0) else str(_d["cur"])
                                        _new_disp = "(없음)" if _d["new"] in (None, "", 0) else str(_d["new"])
                                        _opts = [
                                            f"기존 유지: {_cur_disp}",
                                            f"신규 적용: {_new_disp}",
                                            "직접 입력",
                                        ]
                                        _ch = st.radio(
                                            "선택", _opts,
                                            key=f"vp_diff_radio_{_di}",
                                            label_visibility="collapsed",
                                            index=1,  # 기본 = 신규 적용
                                        )
                                        if _ch.startswith("기존"):
                                            _resolved_fields[_d["name"]] = _d["cur"]
                                        elif _ch.startswith("신규"):
                                            _resolved_fields[_d["name"]] = _d["new"]
                                        else:
                                            _seed = _new_disp if _new_disp != "(없음)" else (
                                                _cur_disp if _cur_disp != "(없음)" else ""
                                            )
                                            _custom_v = st.text_input(
                                                f"{_d['label']} 직접 입력",
                                                value=_seed,
                                                key=f"vp_diff_custom_{_di}",
                                                label_visibility="collapsed",
                                            )
                                            if _d["f"]["type"] == "number":
                                                try:
                                                    if _custom_v == "":
                                                        _resolved_fields[_d["name"]] = None
                                                    elif "." in _custom_v:
                                                        _resolved_fields[_d["name"]] = float(_custom_v)
                                                    else:
                                                        _resolved_fields[_d["name"]] = int(_custom_v)
                                                except Exception:
                                                    _resolved_fields[_d["name"]] = None
                                            else:
                                                _resolved_fields[_d["name"]] = _custom_v or None

                            # 신규 bullet 미리보기
                            _new_bullets = _ext.get("_특징_bullet") or []
                            _cur_bullets_raw = row.get("제품특징_bullet") or []
                            if isinstance(_cur_bullets_raw, str):
                                try:
                                    _cur_bullets_raw = json.loads(_cur_bullets_raw)
                                except Exception:
                                    _cur_bullets_raw = []
                            if not isinstance(_cur_bullets_raw, list):
                                _cur_bullets_raw = []
                            _cur_bullet_set = set(_cur_bullets_raw)
                            _new_bullets_only = [b for b in _new_bullets if b not in _cur_bullet_set]
                            if _new_bullets_only:
                                st.markdown(f"#### ➕ 신규 추가 가능한 bullet ({len(_new_bullets_only)}건)")
                                for _nb in _new_bullets_only:
                                    st.markdown(f"- {_nb}")

                            # 저장
                            _bc1, _bc2 = st.columns([3, 1])
                            with _bc1:
                                if st.button(
                                    "✅ 시각설명 덮어쓰기 + 변경 적용 & 저장",
                                    type="primary", use_container_width=True,
                                    key="btn_pending_save_bulk",
                                ):
                                    try:
                                        update_시각설명(product_id, _new_desc_val)
                                        _payload: dict = {}
                                        for _name, _val_resolved in _resolved_fields.items():
                                            _cur_v = row.get(_name)
                                            if _norm_val(_cur_v) != _norm_val(_val_resolved):
                                                _payload[_name] = _val_resolved
                                        # 인증번호 텍스트가 신규 채워지면 짝 boolean도 동반
                                        for _num_k, _bool_k in (
                                            ("kc인증번호", "kc인증"),
                                            ("전파인증번호", "전파인증"),
                                        ):
                                            if _payload.get(_num_k) and not row.get(_bool_k):
                                                _payload[_bool_k] = True
                                        # bullet 머지 (기존 + 신규 추가분)
                                        _bul_added_n = 0
                                        if _new_bullets_only:
                                            _payload["제품특징_bullet"] = list(_cur_bullets_raw) + _new_bullets_only
                                            _bul_added_n = len(_new_bullets_only)
                                        _lock_ok = True
                                        if _payload:
                                            _lock_ok = update_상품(
                                                product_id,
                                                _payload,
                                                original_수정일=row.get("수정일"),
                                            )
                                        if not _lock_ok:
                                            st.warning(
                                                "⚠️ 다른 사용자가 먼저 저장했습니다. "
                                                "시각설명은 저장되었지만 스펙 필드 반영은 취소되었습니다. "
                                                "새로고침 후 재시도하세요."
                                            )
                                        else:
                                            st.success(
                                                f"저장 완료! 시각설명 덮어씀 · "
                                                f"필드 변경 {len(_payload) - (1 if _bul_added_n else 0)}개 · "
                                                f"신규 bullet {_bul_added_n}개"
                                            )
                                            st.session_state.pop("vp_pending", None)
                                            st.session_state.pop("_spec_extracted_bulk", None)
                                            st.session_state.pop("vp_results", None)
                                            st.rerun()
                                    except Exception as _e:
                                        st.error(f"저장 실패: {_e}")
                            with _bc2:
                                if st.button(
                                    "❌ 취소", use_container_width=True,
                                    key="btn_pending_cancel_bulk",
                                ):
                                    st.session_state.pop("vp_pending", None)
                                    st.session_state.pop("_spec_extracted_bulk", None)
                                    st.rerun()
            else:
                # 평소: 저장된 시각설명을 직접 편집/저장만 가능
                if _saved_desc:
                    _시각설명_val = st.text_area(
                        "DB 저장본 (직접 편집 가능)",
                        value=_saved_desc,
                        height=200,
                        key="vp_final_text",
                    )
                    if st.button("💾 시각설명 저장", key="btn_save_vision"):
                        try:
                            update_시각설명(product_id, _시각설명_val)
                            with st.spinner("🤖 스펙·기타 특징 자동 추출 중…"):
                                _spec_n, _bul_n = _auto_apply_after_vision(product_id, _시각설명_val)
                            st.success(f"저장 완료! 자동 반영: 스펙 {_spec_n}개 / bullet {_bul_n}개")
                            st.rerun()
                        except Exception as _e:
                            st.error(f"저장 실패: {_e}")
                else:
                    st.caption("아직 저장된 시각설명이 없습니다. 위에서 Vision Pass를 실행하고 '📥 반영' 버튼을 누르세요.")

    # ── 동영상 Vision Pass (Gemini 전용) ─────────────────────
    _vp_videos = [
        f for f in get_files(product_id)
        if f.get("파일_유형") == "video" and f.get("드라이브_파일_id")
    ]

    st.divider()

    _vp_video_label = (
        f"🎬 동영상 Vision Pass — {len(_vp_videos)}개 분석 가능"
        if _vp_videos else "🎬 동영상 Vision Pass (동영상 없음)"
    )
    with st.expander(_vp_video_label, expanded=bool(_vp_videos) and is_owner()):
        if not is_owner():
            st.info("🔒 동영상 Vision Pass 실행은 owner 전용입니다.")
        elif not _vp_videos:
            st.caption("동영상(mp4/mov/webm)을 업로드하면 Gemini로 분석할 수 있습니다.")
            st.caption("⚠️ Claude는 동영상 미지원 — Gemini 전용 기능입니다.")
        else:
            st.caption(
                "⚠️ Claude는 동영상 미지원 — Gemini로만 실행됩니다. "
                "Gemini Files API로 업로드 후 분석하며, 영상 길이에 비례해 토큰 비용이 발생합니다."
            )
            st.caption(
                "📌 **동영상 전용 프롬프트** — 이미지 비전패스와 분리되어 있습니다. "
                "사운드·동작·시간 변화 등 영상 고유 정보를 자유 관찰 방식으로 캐치하도록 설계됨. "
                "(현재는 제품 시연 영상 특화)"
            )

            # 모델 선택 (Gemini만)
            _vid_model = st.selectbox(
                "Gemini 모델",
                GEMINI_VP_MODELS,
                index=0,
                key="vp_video_model",
                help="동영상은 Gemini 모델만 가능합니다.",
            )

            # 프롬프트 편집 (동영상 전용 — 이미지 VP와 분리)
            if st.checkbox("📄 동영상 전용 프롬프트 편집", value=False, key="vp_video_show_prompt"):
                st.caption(
                    "💡 동영상 전용 프롬프트(`agents/00_vision_pass/core_gemini_video.md`)를 편집합니다. "
                    "이미지 VP 프롬프트와 분리되어 독립적으로 저장됩니다."
                )
                _video_prompt_key = "vp_editor_gemini_video"  # 동영상 전용 (이미지 VP와 분리)
                if _video_prompt_key not in st.session_state:
                    st.session_state[_video_prompt_key] = _vp_load_video_prompt()
                _vp_load_prompt_video = st.text_area(
                    "동영상 전용 프롬프트 (제품시연 특화)",
                    value=st.session_state[_video_prompt_key],
                    height=180,
                    key="vp_video_editor",
                )
                if st.button("💾 동영상 프롬프트 저장", key="vp_video_btn_save_prompt"):
                    _vp_video_prompt_path().write_text(_vp_load_prompt_video, encoding="utf-8")
                    st.session_state[_video_prompt_key] = _vp_load_prompt_video
                    st.success("저장 완료! (core_gemini_video.md)")

            st.divider()

            # 이력 일괄 조회 (파일_id별 그룹화)
            _all_video_hist = list_비전패스_이력(product_id)
            _vid_hist_by_fid: dict[str, list[dict]] = {}
            for _h in _all_video_hist:
                _fid_h = _h.get("파일_id")
                if _fid_h:
                    _vid_hist_by_fid.setdefault(_fid_h, []).append(_h)

            # 각 동영상별 카드
            for _vi, _v in enumerate(_vp_videos):
                _drive_fid = _v["드라이브_파일_id"]
                _vname = _v.get("파일명") or f"video_{_vi}"
                _vurl = _v.get("드라이브_url") or f"https://drive.google.com/file/d/{_drive_fid}/view"
                _v_hists = _vid_hist_by_fid.get(_drive_fid, [])

                with st.container(border=True):
                    _vc1, _vc2 = st.columns([4, 1])
                    with _vc1:
                        st.markdown(f"**🎬 {_vname}**  ·  [Drive에서 보기]({_vurl})")
                        if _v_hists:
                            st.caption(f"이력 {len(_v_hists)}건")
                    with _vc2:
                        _do_run_vid = st.button(
                            "▶ 실행", type="primary",
                            key=f"btn_video_run_{_drive_fid}",
                            use_container_width=True,
                        )

                    # 실행
                    if _do_run_vid:
                        try:
                            from pipeline.drive_client import (
                                build_service as _bsvc_v,
                                download_file as _dlf_v,
                                _guess_mime as _gmv,
                            )
                            from pipeline.llm import generate_vision_gemini_video
                            from pipeline.loader import build_vision_input

                            _acc_v = _v.get("계정") or sel_account
                            with st.spinner(f"{_vname} — Drive에서 다운로드…"):
                                _svc_v = _bsvc_v(_acc_v)
                                _vbytes, _vmime = _dlf_v(_svc_v, _drive_fid)

                            # MIME 보정 (Drive가 octet-stream 반환 시 확장자로 추정)
                            if not _vmime.startswith("video/"):
                                _vmime = _gmv(_vname)

                            _v_prompt = (
                                st.session_state.get("vp_editor_gemini_video")
                                or _vp_load_video_prompt()
                            )

                            with st.spinner(f"{_vname} — Gemini Files 업로드 + 분석…"):
                                _v_result = generate_vision_gemini_video(
                                    system_prompt=_v_prompt,
                                    video_bytes=_vbytes,
                                    mime_type=_vmime,
                                    user_text=build_vision_input(row),
                                    display_name=_vname,
                                    model=_vid_model,
                                )

                            insert_비전패스_이력(
                                상품_id=product_id,
                                파일_id=_drive_fid,
                                모델명=_vid_model,
                                프롬프트=_v_prompt,
                                결과=_v_result,
                                실행_모드="single",
                            )
                            st.success(f"✅ {_vname} 분석 완료!")
                            st.rerun()
                        except Exception as _ve:
                            st.error(f"실행 실패: {type(_ve).__name__}: {_ve}")

                    # 이력 목록 (토글)
                    if _v_hists:
                        _vh_show_key = f"vp_video_hist_show_{_drive_fid}"
                        _vh_show = st.session_state.get(_vh_show_key, False)
                        if st.button(
                            ("▼ 이력 닫기" if _vh_show else "▶ 이력 보기"),
                            key=f"btn_video_hist_toggle_{_drive_fid}",
                        ):
                            st.session_state[_vh_show_key] = not _vh_show
                            st.rerun()

                        if _vh_show:
                            for _h in _v_hists:
                                with st.container(border=True):
                                    st.caption(
                                        f"`{_fmt_dt(_h.get('생성일'))}` · {_h.get('모델명')}"
                                    )
                                    st.text_area(
                                        "결과",
                                        value=_h.get("결과", ""),
                                        height=140,
                                        key=f"vp_video_hist_text_{_h['id']}",
                                        label_visibility="collapsed",
                                    )
                                    _bh1, _bh2, _bh3 = st.columns([1, 1, 5])
                                    with _bh1:
                                        if st.button(
                                            "📥 반영", key=f"btn_video_apply_{_h['id']}",
                                            help="시각설명에 반영 (충돌 해소 패널 활성화)",
                                        ):
                                            st.session_state["vp_pending"] = {
                                                "items": [(f"동영상 {_vname}", _h.get("결과", ""))],
                                                "applied_at": datetime.now().isoformat(),
                                                "mode": "partial",
                                            }
                                            st.rerun()
                                    with _bh2:
                                        if st.button(
                                            "🗑️ 삭제", key=f"btn_video_del_{_h['id']}",
                                        ):
                                            delete_비전패스_이력(_h["id"])
                                            st.rerun()

# ─────────────────────────────────────────────────────────
# 탭 2 — 스펙
# ─────────────────────────────────────────────────────────
with tab_스펙:
    # VP 결과 참고 배너
    _vp_ref = st.session_state.get("vp_results", {})
    if _vp_ref:
        with st.expander("💡 Vision Pass 결과 참고 (이미지 탭 실행 결과)", expanded=True):
            _ref_text = _vp_ref.get("main", "") or _vp_ref.get("sub", "")
            st.text_area("참고", value=_ref_text, height=180, key="vp_ref_in_spec",
                         disabled=True, label_visibility="collapsed")
            st.caption("이 결과를 참고해 아래 필드를 채우세요.")
    elif row.get("시각설명"):
        with st.expander("💡 저장된 시각설명 참고", expanded=False):
            st.text_area("저장본", value=row.get("시각설명"), height=180, key="vp_saved_ref",
                         disabled=True, label_visibility="collapsed")

    # ── 스펙 자동 추출 (4-C) ──────────────────────────────
    _saved_desc_for_extract = row.get("시각설명") or ""
    if _saved_desc_for_extract and is_owner():
        with st.expander("🤖 시각설명 → 스펙 필드 자동 추출 (수동 재실행)", expanded=False):
            st.caption(
                "시각설명 저장 시 자동으로 1회 실행됩니다. "
                "이 버튼은 시각설명 수정 후 재실행하거나 '전체 덮어쓰기'로 다시 채울 때 사용."
            )
            _ec1, _ec2 = st.columns([3, 1])
            with _ec1:
                _extract_model = st.selectbox(
                    "추출 모델",
                    _ALL_VP_MODELS,
                    index=_ALL_VP_MODELS.index(DEFAULT_EXTRACT_MODEL)
                          if DEFAULT_EXTRACT_MODEL in _ALL_VP_MODELS else 0,
                    key="vp_extract_model",
                )
            with _ec2:
                _do_extract = st.button(
                    "🤖 추출 실행",
                    type="primary", use_container_width=True,
                    key="btn_extract_spec",
                )

            if _do_extract:
                try:
                    from pipeline.vision_merge import extract_스펙
                    with st.spinner(f"{_extract_model} 추출 중…"):
                        _extracted = extract_스펙(_saved_desc_for_extract, model=_extract_model)
                    st.session_state["_spec_extracted"] = _extracted
                except Exception as _ee:
                    st.error(f"추출 실패: {_ee}")

            _extracted = st.session_state.get("_spec_extracted")
            if _extracted:
                if _extracted.get("_error"):
                    st.error(f"파싱 실패: {_extracted.get('_error')}")
                    st.markdown("**LLM 원본 응답**")
                    st.code(_extracted.get("_raw", ""), language=None)
                else:
                    # 미리보기 + 적용 모드 선택
                    st.markdown("**추출 결과 미리보기**")
                    _preview_rows = []
                    for _f in SPEC_FIELDS:
                        _new = _extracted.get(_f["name"])
                        _cur = row.get(_f["name"])
                        if _new is None and _cur in (None, "", 0):
                            continue  # 둘 다 비어있으면 스킵
                        _preview_rows.append({
                            "필드": _f["label"],
                            "현재값": "" if _cur in (None, 0) else str(_cur),
                            "추출값": "" if _new is None else str(_new),
                        })
                    if _preview_rows:
                        st.dataframe(_preview_rows, use_container_width=True, hide_index=True)
                    else:
                        st.info("추출된 값이 없거나 모두 빈 값입니다.")

                    # 기타 제품 특징 (bullet) 미리보기
                    _extracted_bullets = _extracted.get("_특징_bullet") or []
                    if _extracted_bullets:
                        st.markdown("**기타 제품 특징 후보 (bullet)**")
                        for _b in _extracted_bullets:
                            st.markdown(f"- {_b}")

                    _mode = st.radio(
                        "적용 방식",
                        ["빈 필드만 채우기", "전체 덮어쓰기"],
                        key="spec_apply_mode",
                        horizontal=True,
                    )
                    _ac1, _ac2 = st.columns([3, 1])
                    with _ac1:
                        if st.button(
                            "✅ 폼에 적용 (저장은 별도)",
                            type="primary", use_container_width=True,
                            key="btn_apply_extracted",
                        ):
                            _override = {}
                            for _k, _v in _extracted.items():
                                if _k.startswith("_") or _v is None:
                                    continue
                                _cur_v = row.get(_k)
                                if _mode == "전체 덮어쓰기" or _cur_v in (None, "", 0):
                                    _override[_k] = _v
                            # 인증번호 텍스트가 채워지면 짝 boolean 플래그도 True로 동반 적용
                            # (번호가 있다 = 인증 받았다는 의미이므로 사용자가 다시 체크할 필요 없음)
                            for _num_key, _bool_key in (
                                ("kc인증번호", "kc인증"),
                                ("전파인증번호", "전파인증"),
                            ):
                                if _override.get(_num_key):
                                    _cur_bool = row.get(_bool_key)
                                    if _mode == "전체 덮어쓰기" or not _cur_bool:
                                        _override[_bool_key] = True
                            st.session_state["_spec_override"] = _override

                            # 기타 제품 특징 (bullet) 머지
                            _bullets_new = _extracted.get("_특징_bullet") or []
                            _bullet_msg = ""
                            if _bullets_new:
                                _bullets_cur = row.get("제품특징_bullet") or []
                                if isinstance(_bullets_cur, str):
                                    try:
                                        _bullets_cur = json.loads(_bullets_cur)
                                    except Exception:
                                        _bullets_cur = []
                                if not isinstance(_bullets_cur, list):
                                    _bullets_cur = []
                                if _mode == "전체 덮어쓰기":
                                    _merged = list(_bullets_new)
                                else:
                                    _existing_set = set(_bullets_cur)
                                    _merged = list(_bullets_cur) + [
                                        b for b in _bullets_new if b not in _existing_set
                                    ]
                                st.session_state["ta_제품특징_bullet"] = "\n".join(_merged)
                                _bullet_msg = f", 기타 특징 bullet {len(_bullets_new)}개 반영"

                            st.session_state.pop("_spec_extracted", None)
                            st.success(f"{len(_override)}개 필드 적용{_bullet_msg}. 아래에서 검토 후 '💾 저장'을 누르세요.")
                            st.rerun()
                    with _ac2:
                        if st.button("❌ 취소", use_container_width=True, key="btn_extract_cancel"):
                            st.session_state.pop("_spec_extracted", None)
                            st.rerun()

    # ── 추출값 row에 머지 (위젯 렌더 전) ──────────────────
    # 저장 시까지 유지. 저장 핸들러에서 clear.
    _spec_override = st.session_state.get("_spec_override")
    if _spec_override:
        for _k, _v in _spec_override.items():
            row[_k] = _v
        _ic1, _ic2 = st.columns([5, 1])
        with _ic1:
            st.info(f"🤖 자동 추출값 {len(_spec_override)}개가 아래 폼에 반영되었습니다. 검토 후 '💾 저장'을 누르세요.")
        with _ic2:
            if st.button("↩️ 추출값 되돌리기", key="btn_revert_extract"):
                st.session_state.pop("_spec_override", None)
                st.rerun()

    st.subheader("📋 기본 정보")
    c1, c2 = st.columns(2)
    제품명 = c1.text_input(
        "제품명 (내부명) *",
        value=row.get("제품명") or "",
        help="판매자가 사내에서 부르는 이름. 외부에 노출되는 상품명과 별개입니다.",
    )
    모델명 = c2.text_input("모델명",   value=row.get("모델명") or "",
                          help="패키지/본체에 표기된 모델 번호 (비전패스가 자동 추출)")
    c3, c4, c5, c6 = st.columns(4)
    카테고리     = c3.text_input("카테고리",     value=row.get("카테고리") or "")
    서브카테고리 = c4.text_input("서브카테고리", value=row.get("서브카테고리") or "")
    원산지       = c5.text_input("원산지",       value=row.get("원산지") or "중국")
    제조사       = c6.text_input("제조사",       value=row.get("제조사") or "")
    c7, c8 = st.columns(2)
    수입자       = c7.text_input("수입자",       value=row.get("수입자") or "",
                                help="수입업체명. 패키지 뒷면에 명시된 경우 입력")
    사용연령     = c8.text_input("사용연령",     value=row.get("사용연령") or "",
                                placeholder="예: 3세 이상, 만 6세부터")

    st.divider()
    st.subheader("📦 재고")
    s1, s2, s3 = st.columns(3)
    실시간재고 = s1.number_input("실시간재고", min_value=0, value=int(row.get("실시간재고") or 0))
    처리후재고 = s2.number_input("처리후재고", min_value=0, value=int(row.get("처리후재고") or 0))
    재고수량   = s3.number_input("재고수량",   min_value=0, value=int(row.get("재고수량")   or 0))
    f1, f2, f3 = st.columns(3)
    재입고예정    = f1.checkbox("재입고 예정", value=bool(row.get("재입고예정")))
    단종여부      = f2.checkbox("단종",        value=bool(row.get("단종여부")))
    온라인판매가능 = f3.checkbox(
        "온라인 판매 가능",
        value=row.get("온라인판매가능") if row.get("온라인판매가능") is not None else True,
    )

    st.divider()
    with st.container(border=True):
        st.markdown("#### 💸 온라인 판매 가격 (현재 판매가)")
        st.caption("00~05 단계가 가격 언급 시 우선 참조하는 필드입니다.")
        온라인판매가격 = st.number_input(
            "온라인 판매 가격",
            min_value=0,
            value=int(row.get("온라인판매가격") or 0),
            step=100,
            label_visibility="collapsed",
            key="num_online_price",
        )

    st.subheader("💰 가격")
    p1, p2, p3, p4 = st.columns(4)
    소매가         = p1.number_input("소매가",         min_value=0, value=int(row.get("소매가")       or 0), step=100)
    도매가         = p2.number_input("도매가",         min_value=0, value=int(row.get("도매가")       or 0), step=100)
    실제받는가격   = p3.number_input("실제 받는 가격", min_value=0, value=int(row.get("실제받는가격") or 0), step=100)
    평균입고가     = p4.number_input("평균 입고가",    min_value=0, value=int(row.get("평균입고가")   or 0), step=100)

    st.divider()
    st.subheader("📐 치수 / 무게")
    st.markdown("**제품 본체**")
    d1, d2, d3, d4 = st.columns(4)
    가로 = d1.number_input("가로 (cm)", min_value=0.0, value=float(row.get("가로_cm") or 0), format="%.1f")
    세로 = d2.number_input("세로 (cm)", min_value=0.0, value=float(row.get("세로_cm") or 0), format="%.1f")
    높이 = d3.number_input("높이 (cm)", min_value=0.0, value=float(row.get("높이_cm") or 0), format="%.1f")
    무게 = d4.number_input("무게 (g)",  min_value=0.0, value=float(row.get("무게_g")  or 0), format="%.0f")
    st.markdown("**패키지(박스)**")
    b1, b2, b3, b4 = st.columns(4)
    박스_가로 = b1.number_input("박스 가로 (cm)", min_value=0.0,
                                value=float(row.get("박스_가로_cm") or 0), format="%.1f",
                                key="num_box_w")
    박스_세로 = b2.number_input("박스 세로 (cm)", min_value=0.0,
                                value=float(row.get("박스_세로_cm") or 0), format="%.1f",
                                key="num_box_d")
    박스_높이 = b3.number_input("박스 높이 (cm)", min_value=0.0,
                                value=float(row.get("박스_높이_cm") or 0), format="%.1f",
                                key="num_box_h")
    박스_무게 = b4.number_input("박스 무게 (g)",  min_value=0.0,
                                value=float(row.get("박스_무게_g")  or 0), format="%.0f",
                                key="num_box_wt")

    st.divider()
    st.subheader("🎨 소재 / 색상")
    st.markdown("**제품 본체**")
    m1, m2, m3 = st.columns(3)
    재질   = m1.text_input("재질",   value=row.get("재질") or "")
    색상   = m2.text_input("색상",   value=row.get("색상") or "")
    구성품 = m3.text_input("구성품", value=row.get("구성품") or "")
    st.markdown("**패키지(박스)**")
    bm1, bm2 = st.columns(2)
    박스_재질 = bm1.text_input("박스 재질", value=row.get("박스_재질") or "",
                              placeholder="예: 종이박스, PE백, 블리스터팩",
                              key="txt_box_material")
    박스_색상 = bm2.text_input("박스 색상", value=row.get("박스_색상") or "",
                              key="txt_box_color")

    st.divider()
    st.subheader("✅ 인증")
    kc1, kc2 = st.columns([1, 3])
    kc인증     = kc1.checkbox("KC 인증",   value=bool(row.get("kc인증")))
    kc인증번호 = kc2.text_input("KC 인증번호", value=row.get("kc인증번호") or "", disabled=not kc인증)
    ep1, ep2 = st.columns([1, 3])
    전파인증     = ep1.checkbox("전파인증",   value=bool(row.get("전파인증")))
    전파인증번호 = ep2.text_input("전파인증번호", value=row.get("전파인증번호") or "", disabled=not 전파인증)
    기타인증 = st.text_input("기타 인증", value=row.get("기타인증") or "")

    st.divider()
    st.subheader("🔍 검수")
    ins1, ins2 = st.columns([1, 3])
    검수필요 = ins1.checkbox("검수 필요", value=bool(row.get("검수완료")))
    검수메모 = ins2.text_input("검수 메모", value=row.get("검수메모") or "")

    st.divider()
    st.subheader("🏷️ 기타 제품 특징")
    st.caption("한 줄에 하나씩. **01~05 단계가 참고합니다.** 시각설명 자동 추출 시 함께 채워집니다.")

    _bullets_initial = row.get("제품특징_bullet") or []
    if isinstance(_bullets_initial, str):
        try:
            _bullets_initial = json.loads(_bullets_initial)
        except Exception:
            _bullets_initial = []
    if not isinstance(_bullets_initial, list):
        _bullets_initial = []

    _bullets_text_default = "\n".join(str(b) for b in _bullets_initial)
    bullets_text = st.text_area(
        "제품 특징 (bullet)",
        value=_bullets_text_default,
        height=140,
        placeholder="예:\n실리콘 흡착판으로 평면 부착\n충전 1회로 5시간 작동\n방수 등급 IPX5",
        key="ta_제품특징_bullet",
    )
    제품특징_bullet = [line.strip() for line in bullets_text.split("\n") if line.strip()]

    st.text_area(
        "제품 특징 추가",
        value=row.get("제품특징_추가") or "",
        height=80,
        placeholder="비전패스가 못 잡거나 제조사 정보 외에 판매에 도움될 내용 (bullet 보충용, 01~05 참조)",
        key="ta_제품특징_추가",
    )

    st.divider()

    def _coerce_selected(raw) -> set:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = []
        if not isinstance(raw, list):
            raw = []
        return set(raw)

    _활용_전체 = load_판매자특성_활용()
    _메모_전체 = load_판매자특성_메모()
    _활용_선택_set = _coerce_selected(row.get("판매자특성_선택"))
    _메모_선택_set = _coerce_selected(row.get("판매자특성_메모_선택"))

    _좌, _우 = st.columns(2)

    with _좌:
        st.subheader("🏪 판매자 특성 (파이프라인 활용형)")
        st.caption("⚙️ 설정에서 등록한 항목 중 이 제품에 해당하는 것을 체크. **01~05가 흐름상 필요하면 활용**합니다.")
        _판매자특성_체크 = []
        if _활용_전체:
            for _특성 in _활용_전체:
                if st.checkbox(_특성, value=(_특성 in _활용_선택_set), key=f"chk_활용_{_특성}"):
                    _판매자특성_체크.append(_특성)
        else:
            st.caption("⚙️ [설정 페이지](0_settings)에서 먼저 등록하세요.")

    with _우:
        st.subheader("📝 판매자 특성 (개인 메모용)")
        st.caption("판매자만 참고. **파이프라인 미참조** — 카피·이미지 생성에 영향 없음.")
        _메모특성_체크 = []
        if _메모_전체:
            for _특성 in _메모_전체:
                if st.checkbox(_특성, value=(_특성 in _메모_선택_set), key=f"chk_메모_{_특성}"):
                    _메모특성_체크.append(_특성)
        else:
            st.caption("⚙️ [설정 페이지](0_settings)에서 먼저 등록하세요.")

        판매자메모 = st.text_area(
            "자유 메모 (1회성 노트)",
            value=row.get("판매자메모") or "",
            height=120,
            placeholder=(
                "판매자만 참고하는 메모 (시스템 미참조)\n"
                "예) 박스 코너 약간 찌그러짐이 많은 상품\n"
                "예) 9월 3일 입고분"
            ),
            key="ta_판매자메모",
        )

    # ── 저장 payload 빌더 — 상단 placeholder + 하단 버튼 둘 다 동일 payload 사용 ──
    def _build_save_payload() -> dict:
        _ss = st.session_state
        return {
            "제품명":         제품명.strip(),
            "모델명":         모델명        or None,
            "카테고리":       카테고리      or None,
            "서브카테고리":   서브카테고리  or None,
            "원산지":         원산지        or None,
            "제조사":         제조사        or None,
            "수입자":         수입자        or None,
            "사용연령":       사용연령      or None,
            "가로_cm":        가로          or None,
            "세로_cm":        세로          or None,
            "높이_cm":        높이          or None,
            "무게_g":         무게          or None,
            "박스_가로_cm":   박스_가로     or None,
            "박스_세로_cm":   박스_세로     or None,
            "박스_높이_cm":   박스_높이     or None,
            "박스_무게_g":    박스_무게     or None,
            "재질":           재질          or None,
            "색상":           색상          or None,
            "구성품":         구성품        or None,
            "박스_재질":      박스_재질     or None,
            "박스_색상":      박스_색상     or None,
            "kc인증":         kc인증,
            "kc인증번호":     kc인증번호    or None,
            "전파인증":       전파인증,
            "전파인증번호":   전파인증번호  or None,
            "기타인증":       기타인증      or None,
            "소매가":         소매가         or None,
            "도매가":         도매가         or None,
            "실제받는가격":   실제받는가격   or None,
            "평균입고가":     평균입고가     or None,
            "온라인판매가격": 온라인판매가격 or None,
            "제품특징_bullet":  제품특징_bullet,
            "제품특징_추가":    _ss.get("ta_제품특징_추가", row.get("제품특징_추가")) or None,
            "판매자특성_선택":       _판매자특성_체크,
            "판매자특성_메모_선택":  _메모특성_체크,
            "판매자메모":     판매자메모    or None,
            "검수완료":       검수필요,
            "검수메모":       검수메모      or None,
            "실시간재고":     실시간재고,
            "처리후재고":     처리후재고,
            "재고수량":       재고수량,
            "재입고예정":     재입고예정,
            "단종여부":       단종여부,
            "온라인판매가능": 온라인판매가능,
        }

    # ── 헤더 placeholder 채우기 (워크플로 토글 줄 바로 아래 영역) ──
    # _save_top_placeholder는 _is_temp 아닐 때만 정의되어 있음 — 같은 조건으로 보호.
    if not _is_temp and product_id:
        with _save_top_placeholder.container():
            _th_l, _th_r = st.columns([4, 1])
            if _th_l.button("💾 저장", type="primary", use_container_width=True,
                            key="btn_save_top",
                            help="스펙·판매자정보 탭의 모든 입력을 한 번에 저장합니다."):
                _save(_build_save_payload())
            if _th_r.button("취소", use_container_width=True, key="btn_cancel_top",
                            help="편집 중인 값을 버리고 원래 값으로 되돌립니다."):
                _cancel()

    st.divider()
    _t2_l, _t2_r = st.columns([4, 1])
    if _t2_l.button("💾 저장", type="primary", use_container_width=True, key="btn_save_tab2"):
        _save(_build_save_payload())
    if _t2_r.button("취소", use_container_width=True, key="btn_cancel_tab2"):
        _cancel()

    # ── JSON 원본 (디버깅·엠군 파이프라인 입력 형식 확인용) ──
    with st.expander("🔧 JSON으로 보기 (DB 원본 / 엠군 입력 스펙)", expanded=False):
        st.caption("저장된 DB 레코드 raw 데이터 및 엠군 01/02 파이프라인이 받는 입력 형식.")
        st.markdown("**DB 원본 (상품 테이블 row)**")
        st.json(row)
        try:
            _spec_view = get_product_spec(product_id)
        except Exception:
            _spec_view = None
        if _spec_view:
            st.markdown("**엠군 입력용 스펙 (get_product_spec 결과)**")
            st.json(_spec_view)

# ─────────────────────────────────────────────────────────
# 탭 — 엠군 상태 (파이프라인 실행 이력)
# ─────────────────────────────────────────────────────────
with tab_엠군:
    st.subheader("🧪 엠군 파이프라인 실행 이력")

    if _is_temp:
        st.info("제품을 먼저 저장한 뒤 파이프라인을 실행할 수 있습니다.")
    else:
        try:
            _emgun_storage = get_storage()
            _runs = _emgun_storage.list_runs_by_product(product_id)
        except Exception as e:
            st.error(f"실행 목록 조회 실패: {type(e).__name__}: {e}")
            _runs = []
            _emgun_storage = None

        col_a, col_b = st.columns([1, 3])
        with col_a:
            if st.button("🚀 새 실행 시작",
                         type="primary",
                         use_container_width=True,
                         key="btn_new_pipeline_run"):
                spec_for_pipeline = get_product_spec(product_id) or row
                st.session_state["pipeline_product_spec"] = spec_for_pipeline
                for _k in (
                    "current_run_id", "_run_loaded", "targets_01",
                    "parsed_with_ids", "positioning_02",
                    "saved_run_id", "selected_target_db_id",
                ):
                    st.session_state.pop(_k, None)
                st.switch_page("pages/2_pipeline.py")
        with col_b:
            st.caption(f"이 제품의 누적 실행: **{len(_runs)}개**")

        if _emgun_storage is not None and not _runs:
            st.info("아직 실행된 파이프라인이 없습니다.")

        for r in _runs:
            run_id = r["id"]
            try:
                summary = _emgun_storage.get_run_summary(run_id)
            except Exception as e:
                st.error(f"#{run_id} 요약 조회 실패: {type(e).__name__}: {e}")
                continue
            selected = summary["selected_target"]

            if summary["has_positioning"]:
                badge = "🟢 02 완료"
            elif summary["target_count"] > 0:
                badge = "🟡 01만"
            else:
                badge = "⚪ 비어있음"

            with st.container(border=True):
                head_l, head_r = st.columns([2, 3])
                with head_l:
                    _ts = (r.get("생성일") or "")[:19].replace("T", " ")
                    st.markdown(f"**#{run_id}** · {_ts}")
                    st.caption(f"{badge} · 타겟 후보 {summary['target_count']}개")
                with head_r:
                    if selected:
                        star = "⭐ " if selected.get("추천_여부") else ""
                        label = (
                            selected.get("라벨")
                            or selected.get("캐릭터")
                            or "(라벨 없음)"
                        )
                        st.markdown(
                            f"**선택 타겟**: {star}{label}  "
                            f"`{selected.get('모델', '')} #{selected.get('순위', '?')}`"
                        )
                    else:
                        st.caption("선택 타겟: 미선택")

                # 작업한 타겟 목록 (멀티 타겟 자동 모드 검수용)
                _STAGE_LABELS_FULL = {
                    "02": "02 포지셔닝",
                    "03": "03 네이밍",
                    "04": "04 상세페이지",
                    "05": "05 채널",
                }
                try:
                    _all_targets = _emgun_storage.get_targets(run_id)
                    _all_target_ids = [t["id"] for t in _all_targets]
                    _results_summary = _emgun_storage.get_result_summary_for_targets(
                        _all_target_ids
                    )
                except Exception:
                    _all_targets = []
                    _results_summary = {}

                _worked = [
                    t for t in _all_targets
                    if _results_summary.get(t["id"])
                ]
                if _worked:
                    with st.expander(
                        f"📋 작업한 타겟 {len(_worked)}개",
                        expanded=False,
                    ):
                        for t in _worked:
                            stages = _results_summary.get(t["id"]) or set()
                            ordered = [
                                _STAGE_LABELS_FULL[s]
                                for s in ("02", "03", "04", "05")
                                if s in stages
                            ]
                            star = "⭐ " if t.get("추천_여부") else ""
                            sel_mark = "🟢 " if t.get("선택됨") else ""
                            label = (
                                t.get("라벨")
                                or t.get("캐릭터")
                                or "(라벨 없음)"
                            )
                            st.markdown(
                                f"- {sel_mark}{star}**#{t.get('순위')}** · {label} "
                                f"`{t.get('모델', '')}` — {', '.join(ordered)}"
                            )

                btn_open, btn_del = st.columns(2)
                with btn_open:
                    if st.button(
                        "📂 이 run 열기",
                        key=f"open_run_{run_id}",
                        use_container_width=True,
                    ):
                        for _k in (
                            "pipeline_product_spec", "targets_01",
                            "parsed_with_ids", "positioning_02",
                            "saved_run_id", "selected_target_db_id",
                            "_run_loaded",
                        ):
                            st.session_state.pop(_k, None)
                        st.session_state["current_run_id"] = run_id
                        st.switch_page("pages/2_pipeline.py")
                with btn_del:
                    _del_key = f"del_run_{run_id}"
                    _confirm_key = f"del_confirm_{run_id}"
                    if st.session_state.get(_confirm_key):
                        if st.button(
                            "정말 삭제하시겠습니까? (한 번 더 클릭)",
                            key=f"{_del_key}_yes",
                            type="secondary",
                            use_container_width=True,
                        ):
                            try:
                                _emgun_storage.delete_run(run_id)
                                st.session_state.pop(_confirm_key, None)
                                st.success(f"#{run_id} 삭제 완료")
                                st.rerun()
                            except Exception as e:
                                st.error(f"삭제 실패: {type(e).__name__}: {e}")
                    else:
                        if st.button(
                            "🗑️ 삭제",
                            key=_del_key,
                            use_container_width=True,
                        ):
                            st.session_state[_confirm_key] = True
                            st.rerun()

# ── 삭제 ─────────────────────────────────────────────────
st.divider()


@st.dialog("제품 영구 삭제")
def _confirm_delete_dialog() -> None:
    st.warning(
        f"**#{product_id} {row.get('제품명', '')}** 을(를) 영구 삭제합니다.\n\n"
        "연결된 파일 기록도 함께 삭제되며 복구할 수 없습니다."
    )
    st.write("정말 삭제하시겠습니까?")
    c_cancel, c_delete = st.columns(2)
    if c_cancel.button("취소", use_container_width=True, key="dlg_cancel_delete"):
        st.rerun()
    if c_delete.button("🗑️ 삭제", type="primary", use_container_width=True, key="dlg_confirm_delete"):
        try:
            delete_상품(product_id)
            st.session_state.pop("_temp_product_id", None)
            st.session_state.pop("edit_product_id", None)
            st.session_state.pop("edit_mode", None)
            st.switch_page("pages/1_products.py")
        except Exception as e:
            st.error(f"삭제 실패: {e}")


with st.expander("⚠️ 위험 구역", expanded=False):
    st.warning(f"**#{product_id} {row.get('제품명', '')}** 을(를) 삭제합니다. 연결된 파일 기록도 함께 삭제됩니다.")
    if st.button("🗑️ 영구 삭제", type="secondary", key="btn_delete"):
        _confirm_delete_dialog()
