"""페이지 2 — 제품 등록 / 수정.

신규 등록 흐름:
  1. 1_products.py에서 session_state["edit_mode"] = "new" 설정 후 이 페이지 진입
  2. 이 페이지 진입 즉시 임시 레코드 자동 생성 → edit 모드로 전환
     (이전 세션에서 만든 임시 레코드가 남아 있으면 재사용, 새로 안 만듦)
  3. 이미지 탭에서 바로 업로드 + Vision Pass 실행 가능
  4. 스펙 탭에서 VP 결과 참고해 필드 채움 → 저장

수정: session_state["edit_mode"] = "edit"  +  session_state["edit_product_id"] = int
"""
from __future__ import annotations

import io
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
    delete_비전패스_이력,
    delete_파일,
    delete_상품,
    get_files,
    get_product,
    get_product_spec,
    get_thumbnail_url,
    insert_비전패스_이력,
    insert_상품,
    list_account_folders,
    list_비전패스_이력,
    set_account_folder,
    update_상품,
    update_시각설명,
    upsert_파일,
)
from pipeline.models_config import (
    ALL_VP_MODELS,
    CLAUDE_VP_MODELS,
    DEFAULT_EXTRACT_MODEL,
    DEFAULT_MERGE_MODEL,
    GEMINI_VP_MODELS,
    family_of as _vp_family_of,
)
from pipeline.spec_schema import SPEC_FIELDS

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

if _is_temp:
    st.title(f"🆕 신규 제품 등록 — #{product_id}")
    st.caption("🗄️ DB — 상품 테이블  ·  **임시 저장 상태** (스펙 탭에서 제품명 수정 후 저장하세요)")
else:
    st.title(f"✏️ 제품 수정 — #{product_id}")
    st.caption("🗄️ DB — 상품 테이블")

if st.button("← 목록으로", key="back_btn"):
    # 임시 레코드면 저장 없이 이탈하는 것이므로 즉시 삭제 (_cancel 로직과 동일)
    if _is_temp:
        try:
            delete_상품(product_id)
        except Exception:
            pass
        st.session_state.pop("_temp_product_id", None)
    st.session_state.pop("edit_product_id", None)
    st.session_state.pop("edit_mode", None)
    st.switch_page("pages/1_products.py")

st.divider()

# ── Vision Pass 공통 상수/유틸 ────────────────────────────
_AGENTS_DIR    = Path(__file__).parent.parent / "agents" / "00_vision_pass"
# 모델 목록은 pipeline.models_config 에서 import (단일 소스)
_CLAUDE_MODELS = CLAUDE_VP_MODELS
_GEMINI_MODELS = GEMINI_VP_MODELS
_ALL_VP_MODELS = ALL_VP_MODELS


def _vp_family(model: str) -> str:
    return _vp_family_of(model)


def _vp_prompt_path(model: str) -> Path:
    fam = _vp_family(model)
    p = _AGENTS_DIR / f"core_{fam}.md"
    return p if p.exists() else _AGENTS_DIR / "core.md"


def _vp_load_prompt(model: str) -> str:
    return _vp_prompt_path(model).read_text(encoding="utf-8")


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
    """스펙·판매자정보 payload를 DB에 저장."""
    if not payload.get("제품명", "").strip():
        st.error("제품명은 필수입니다.")
        return
    try:
        update_상품(product_id, payload)
        if not payload["제품명"].startswith("임시_"):
            st.session_state.pop("_temp_product_id", None)
        st.session_state.pop("_spec_override", None)
        st.success("저장 완료!")
        st.rerun()
    except Exception as _se:
        st.error(f"저장 실패: {type(_se).__name__}: {_se}")


def _cancel() -> None:
    """편집 취소 — 임시 레코드이면 삭제 후 목록으로."""
    if _is_temp:
        try:
            delete_상품(product_id)
        except Exception:
            pass
    st.session_state.pop("_temp_product_id", None)
    st.session_state.pop("edit_product_id", None)
    st.session_state.pop("edit_mode", None)
    st.switch_page("pages/1_products.py")


# ── 탭 구성 ──────────────────────────────────────────────
# 신규 등록(임시) 모드: 이미지부터 → 스펙 → 판매자 (이미지 업로드 후 VP 추출 워크플로우)
# 수정 모드: 스펙부터 → 이미지 → 판매자 (스펙 편집이 가장 잦은 작업)
# 첫 번째 탭이 자동 활성화되는 Streamlit 특성 활용.
if _is_temp:
    tab_이미지, tab_스펙, tab_판매자 = st.tabs(
        ["📁 이미지 & Vision Pass", "📐 스펙", "📝 판매자 정보"]
    )
else:
    tab_스펙, tab_이미지, tab_판매자 = st.tabs(
        ["📐 스펙", "📁 이미지 & Vision Pass", "📝 판매자 정보"]
    )

# ─────────────────────────────────────────────────────────
# 탭 — 이미지 + Vision Pass
# ─────────────────────────────────────────────────────────
with tab_이미지:
    # ── 등록된 이미지 조회 ────────────────────────────────
    drive_files = get_files(product_id)
    images = [f for f in drive_files if f.get("파일_유형") == "image" and f.get("드라이브_파일_id")]

    if images:
        # 계정별 카운트 요약 (헤더에 표기)
        _img_acc_counts: dict[str, int] = {}
        for _imf in images:
            _img_acc_counts[_imf.get("계정") or ""] = _img_acc_counts.get(_imf.get("계정") or "", 0) + 1
        _acc_summary = " · ".join(
            f"{account_badge(acc) if acc else '⚫ 미지정'} {cnt}장"
            for acc, cnt in sorted(_img_acc_counts.items(), key=lambda x: -x[1])
        )
        st.markdown(f"**등록된 이미지 ({len(images)}장)** — {_acc_summary}")

        cols = st.columns(min(len(images), 4))
        for i, f in enumerate(images):
            fid = f["드라이브_파일_id"]
            _f_acc = f.get("계정")
            with cols[i % 4]:
                try:
                    st.image(get_thumbnail_url(fid, 400), use_container_width=True)
                    # 계정 배지 + 파일명
                    st.caption(f"{account_badge(_f_acc)} · {f.get('파일명', '')}")
                    _btn_del, _btn_orig = st.columns([1, 2])
                    with _btn_del:
                        # Q3: 개별 이미지 삭제 버튼
                        if st.button("🗑️", key=f"del_img_{f['id']}", help="이 이미지 삭제"):
                            delete_파일(f["id"])
                            st.rerun()
                    with _btn_orig:
                        st.markdown(f"[원본](https://drive.google.com/uc?export=view&id={fid})")
                except Exception:
                    st.caption(f"로드 실패: {fid}")
    else:
        st.info("등록된 이미지가 없습니다. 아래에서 업로드하세요.")

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
    with st.expander(_vp_exp_label, expanded=bool(_vp_images)):
        if not _vp_images:
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
                _ec1, _ec2 = st.columns(2)
                with _ec1:
                    st.markdown("**메인 엔진**")
                    _vp_main_model = st.selectbox(
                        "메인 모델", _ALL_VP_MODELS, index=0,
                        key="vp_main_model", label_visibility="collapsed",
                    )
                with _ec2:
                    st.markdown("**서브 엔진**")
                    _sub_c = st.columns([3, 1])
                    with _sub_c[0]:
                        _vp_sub_model = st.selectbox(
                            "서브 모델", _ALL_VP_MODELS, index=len(_CLAUDE_MODELS),
                            key="vp_sub_model", label_visibility="collapsed",
                        )
                    with _sub_c[1]:
                        _vp_sub_on = st.toggle("ON", value=True, key="vp_sub_on")

                _run_label = (
                    f"🔍 일괄 실행 ({_vp_main_model}"
                    + (f" + {_vp_sub_model}" if _vp_sub_on else "")
                    + f", {len(_vp_images)}장)"
                )
                if st.button(_run_label, type="primary", key="btn_vp_run_bulk"):
                    try:
                        from pipeline.drive_client import ACCOUNTS as _ACCTS, build_service as _bsvc, download_file as _dlf
                        from pipeline.llm import generate_vision_claude, generate_vision_gemini
                        from pipeline.loader import build_vision_input
                        from concurrent.futures import ThreadPoolExecutor

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

                        def _run_engine(model: str, prompt: str) -> str:
                            if _vp_family(model) == "claude":
                                return generate_vision_claude(prompt, _image_data, _user_text, model=model)
                            return generate_vision_gemini(prompt, _image_data, _user_text, model=model)

                        _vp_res: dict[str, str] = {}
                        if _vp_sub_on:
                            with st.spinner(f"{_vp_main_model} + {_vp_sub_model} 병렬 분석 중…"):
                                with ThreadPoolExecutor(max_workers=2) as _ex:
                                    _fm = _ex.submit(_run_engine, _vp_main_model, _cur_main)
                                    _fs = _ex.submit(_run_engine, _vp_sub_model,  _cur_sub)
                                    try:
                                        _vp_res["main"] = _fm.result()
                                    except Exception as _e:
                                        _vp_res["main"] = f"[ERROR] {_e}"
                                    try:
                                        _vp_res["sub"] = _fs.result()
                                    except Exception as _e:
                                        _vp_res["sub"] = f"[ERROR] {_e}"
                        else:
                            with st.spinner(f"{_vp_main_model} 분석 중…"):
                                try:
                                    _vp_res["main"] = _run_engine(_vp_main_model, _cur_main)
                                except Exception as _e:
                                    _vp_res["main"] = f"[ERROR] {_e}"

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
                        with st.spinner(f"{_para_model} — {len(_vp_images)}장 병렬 분석 중…"):
                            with ThreadPoolExecutor(max_workers=_max_workers) as _ex3:
                                _futs = {_ex3.submit(_run_single_img, f): f for f in _vp_images}
                                for _fut in as_completed(_futs):
                                    try:
                                        _para_results.append(_fut.result())
                                    except Exception as _fe:
                                        _para_errors.append(f"{_futs[_fut].get('파일명', '?')}: {_fe}")

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
                                st.image(get_thumbnail_url(_fid, 200), use_container_width=True)
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
                                    from pipeline.llm import generate_vision_claude, generate_vision_gemini
                                    from pipeline.loader import build_vision_input

                                    _acct2 = _img_f.get("계정") or _ACCTS2[0]["label"]
                                    _svc2  = _bsvc2(_acct2)
                                    _fam2  = _vp_family(_img_model)
                                    _prompt2 = st.session_state.get(
                                        "vp_editor_claude" if _fam2 == "claude" else "vp_editor_gemini"
                                    ) or _vp_load_prompt(_img_model)

                                    with st.spinner(f"{_img_model} 분석 중…"):
                                        _b2, _m2 = _dlf2(_svc2, _fid)
                                        if _fam2 == "claude":
                                            _res2 = generate_vision_claude(_prompt2, [(_b2, _m2)], build_vision_input(row), model=_img_model)
                                        else:
                                            _res2 = generate_vision_gemini(_prompt2, [(_b2, _m2)], build_vision_input(row), model=_img_model)

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
                                st.success("저장 완료!")
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
                    # 케이스 2: 기존 있음 → AI 비교 → 일치/충돌 분리 UI
                    st.info(f"🔀 기존 시각설명 vs 신규({_items_label}) 비교")

                    # 비교 프롬프트 편집
                    _merge_prompt_path = _AGENTS_DIR / "merge.md"
                    _sk_merge = "vp_merge_prompt"
                    if _sk_merge not in st.session_state:
                        st.session_state[_sk_merge] = _merge_prompt_path.read_text(encoding="utf-8")
                    if st.checkbox("📄 비교 프롬프트 편집 (merge.md)", value=False, key="vp_show_merge_prompt"):
                        _merge_prompt_val = st.text_area(
                            "merge.md",
                            value=st.session_state[_sk_merge],
                            height=320,
                            key="vp_editor_merge",
                            label_visibility="collapsed",
                        )
                        if st.button("💾 비교 프롬프트 저장", key="vp_btn_save_merge"):
                            _merge_prompt_path.write_text(_merge_prompt_val, encoding="utf-8")
                            st.session_state[_sk_merge] = _merge_prompt_val
                            st.success("저장!")

                    _mc1, _mc2 = st.columns([3, 1])
                    with _mc1:
                        _merge_model = st.selectbox(
                            "비교 분석 모델",
                            _ALL_VP_MODELS,
                            index=_ALL_VP_MODELS.index(DEFAULT_MERGE_MODEL)
                                  if DEFAULT_MERGE_MODEL in _ALL_VP_MODELS else 0,
                            key="vp_merge_model",
                        )
                    with _mc2:
                        _do_compare = st.button(
                            "🔍 비교 분석 실행",
                            type="primary", use_container_width=True,
                            key="btn_pending_compare",
                        )

                    if _do_compare:
                        try:
                            from pipeline.vision_merge import compare_시각설명
                            with st.spinner(f"{_merge_model} 비교 중…"):
                                _new_arg = (
                                    _items[0][1] if len(_items) == 1
                                    else _items  # 3-way 이상
                                )
                                _cmp = compare_시각설명(_saved_desc, _new_arg, model=_merge_model)
                            st.session_state["vp_compare_result"] = _cmp
                        except Exception as _ce:
                            st.error(f"비교 실패: {_ce}")

                    _cmp = st.session_state.get("vp_compare_result")
                    if _cmp:
                        if _cmp.get("_error"):
                            st.error(f"파싱 실패: {_cmp.get('_error')}")
                            st.markdown("**LLM 원본 응답 (디버깅용)**")
                            st.code(_cmp.get("_raw", ""), language=None)
                        else:
                            # 일치 항목 — 편집 가능 텍스트
                            st.markdown("#### ✅ 일치/통합 항목")
                            _agreed_val = st.text_area(
                                "일치 텍스트 (편집 가능)",
                                value=_cmp.get("일치", ""),
                                height=200,
                                key="vp_pending_agreed",
                            )

                            # 충돌 항목 — 라디오 선택
                            _conflicts = _cmp.get("충돌", [])
                            _resolved: dict[int, str] = {}
                            if _conflicts:
                                st.markdown(f"#### ⚠️ 충돌 항목 ({len(_conflicts)}건 — 각 항목 선택 필요)")
                                for _ci, _cf in enumerate(_conflicts):
                                    _항목 = _cf.get("항목", f"항목{_ci+1}")
                                    _기존 = _cf.get("기존", "") or ""
                                    _신규 = _cf.get("신규", "") or ""
                                    _메모 = _cf.get("메모", "") or ""
                                    with st.container(border=True):
                                        st.markdown(f"**{_항목}**")
                                        if _메모:
                                            st.caption(f"💡 {_메모}")
                                        _opts = [
                                            f"기존: {_기존}",
                                            f"신규: {_신규}",
                                            "직접 입력",
                                        ]
                                        _choice = st.radio(
                                            "선택",
                                            _opts,
                                            key=f"vp_conf_radio_{_ci}",
                                            label_visibility="collapsed",
                                            horizontal=False,
                                        )
                                        if _choice.startswith("기존"):
                                            _resolved[_ci] = f"{_항목}: {_기존}"
                                        elif _choice.startswith("신규"):
                                            _resolved[_ci] = f"{_항목}: {_신규}"
                                        else:
                                            _custom = st.text_input(
                                                f"{_항목} 직접 입력",
                                                key=f"vp_conf_custom_{_ci}",
                                                label_visibility="collapsed",
                                            )
                                            _resolved[_ci] = f"{_항목}: {_custom}" if _custom else ""
                            else:
                                st.success("충돌 항목 없음. 일치 텍스트를 그대로 저장하면 됩니다.")

                            # 최종 저장
                            _bc1, _bc2 = st.columns([3, 1])
                            with _bc1:
                                if st.button(
                                    "✅ 최종 적용 & 저장",
                                    type="primary", use_container_width=True,
                                    key="btn_pending_finalize",
                                ):
                                    _parts = [_agreed_val.strip()] if _agreed_val.strip() else []
                                    if _resolved:
                                        _parts.append("\n[충돌 해결]")
                                        for _ri in sorted(_resolved.keys()):
                                            _line = _resolved[_ri].strip()
                                            if _line:
                                                _parts.append(f"• {_line}")
                                    _final_text = "\n".join(_parts).strip()
                                    if not _final_text:
                                        st.error("저장할 내용이 비어있습니다.")
                                    else:
                                        try:
                                            update_시각설명(product_id, _final_text)
                                            st.success("저장 완료!")
                                            st.session_state.pop("vp_pending", None)
                                            st.session_state.pop("vp_compare_result", None)
                                            st.session_state.pop("vp_results", None)
                                            st.rerun()
                                        except Exception as _e:
                                            st.error(f"저장 실패: {_e}")
                            with _bc2:
                                if st.button(
                                    "❌ 취소",
                                    use_container_width=True,
                                    key="btn_pending_cancel",
                                ):
                                    st.session_state.pop("vp_pending", None)
                                    st.session_state.pop("vp_compare_result", None)
                                    st.rerun()

                    # 비교 분석 전: 신규 텍스트 미리보기
                    if not _cmp:
                        with st.container(border=True):
                            st.markdown("**기존 시각설명 미리보기**")
                            st.text_area(
                                "기존",
                                value=_saved_desc, height=140,
                                key="vp_preview_saved", disabled=True,
                                label_visibility="collapsed",
                            )
                        for _pi, (lbl, txt) in enumerate(_items):
                            with st.container(border=True):
                                st.markdown(f"**신규: {lbl}**")
                                st.text_area(
                                    "신규",
                                    value=txt, height=140,
                                    key=f"vp_preview_new_{_pi}", disabled=True,
                                    label_visibility="collapsed",
                                )
                        if st.button("❌ 반영 취소", key="btn_pending_cancel_pre"):
                            st.session_state.pop("vp_pending", None)
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
                            st.success("저장 완료!")
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
    with st.expander(_vp_video_label, expanded=bool(_vp_videos)):
        if not _vp_videos:
            st.caption("동영상(mp4/mov/webm)을 업로드하면 Gemini로 분석할 수 있습니다.")
            st.caption("⚠️ Claude는 동영상 미지원 — Gemini 전용 기능입니다.")
        else:
            st.caption(
                "⚠️ Claude는 동영상 미지원 — Gemini로만 실행됩니다. "
                "Gemini Files API로 업로드 후 분석하며, 영상 길이에 비례해 토큰 비용이 발생합니다."
            )

            # 모델 선택 (Gemini만)
            _vid_model = st.selectbox(
                "Gemini 모델",
                GEMINI_VP_MODELS,
                index=0,
                key="vp_video_model",
                help="동영상은 Gemini 모델만 가능합니다.",
            )

            # 프롬프트 편집 (Gemini 프롬프트 공유)
            if st.checkbox("📄 Gemini 프롬프트 편집", value=False, key="vp_video_show_prompt"):
                _video_prompt_key = "vp_editor_gemini"  # 이미지 VP와 공유
                if _video_prompt_key not in st.session_state:
                    st.session_state[_video_prompt_key] = _vp_load_prompt("gemini-2.5-flash")
                _vp_load_prompt_video = st.text_area(
                    "Gemini 프롬프트 (이미지 VP와 공유)",
                    value=st.session_state[_video_prompt_key],
                    height=180,
                    key="vp_video_editor",
                )
                if st.button("💾 Gemini 프롬프트 저장", key="vp_video_btn_save_prompt"):
                    _vp_prompt_path("gemini-2.5-flash").write_text(_vp_load_prompt_video, encoding="utf-8")
                    st.session_state[_video_prompt_key] = _vp_load_prompt_video
                    st.success("저장 완료!")

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
                                st.session_state.get("vp_editor_gemini")
                                or _vp_load_prompt("gemini-2.5-flash")
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
    if _saved_desc_for_extract:
        with st.expander("🤖 시각설명 → 스펙 필드 자동 추출", expanded=False):
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
                            st.session_state["_spec_override"] = _override
                            st.session_state.pop("_spec_extracted", None)
                            st.success(f"{len(_override)}개 필드 적용. 아래에서 검토 후 '💾 저장'을 누르세요.")
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

    st.subheader("기본 정보")
    c1, c2 = st.columns(2)
    제품명 = c1.text_input("제품명 *", value=row.get("제품명") or "")
    모델명 = c2.text_input("모델명",   value=row.get("모델명") or "")

    c3, c4, c5 = st.columns(3)
    카테고리     = c3.text_input("카테고리",     value=row.get("카테고리") or "")
    서브카테고리 = c4.text_input("서브카테고리", value=row.get("서브카테고리") or "")
    원산지       = c5.text_input("원산지",       value=row.get("원산지") or "중국")
    제조사 = st.text_input("제조사", value=row.get("제조사") or "")

    st.subheader("치수 / 무게")
    d1, d2, d3, d4 = st.columns(4)
    가로 = d1.number_input("가로 (cm)", min_value=0.0, value=float(row.get("가로_cm") or 0), format="%.1f")
    세로 = d2.number_input("세로 (cm)", min_value=0.0, value=float(row.get("세로_cm") or 0), format="%.1f")
    높이 = d3.number_input("높이 (cm)", min_value=0.0, value=float(row.get("높이_cm") or 0), format="%.1f")
    무게 = d4.number_input("무게 (g)",  min_value=0.0, value=float(row.get("무게_g")  or 0), format="%.0f")

    st.subheader("소재 / 색상")
    m1, m2 = st.columns(2)
    재질   = m1.text_input("재질", value=row.get("재질") or "")
    색상   = m2.text_input("색상", value=row.get("색상") or "")
    구성품 = st.text_input("구성품", value=row.get("구성품") or "")

    st.subheader("인증")
    kc1, kc2 = st.columns([1, 3])
    kc인증     = kc1.checkbox("KC 인증", value=bool(row.get("kc인증")))
    kc인증번호 = kc2.text_input("KC 인증번호", value=row.get("kc인증번호") or "", disabled=not kc인증)
    기타인증   = st.text_input("기타 인증", value=row.get("기타인증") or "")

    st.subheader("가격")
    p1, p2, p3, p4 = st.columns(4)
    소매가     = p1.number_input("소매가",     min_value=0, value=int(row.get("소매가")     or 0), step=100)
    도매가     = p2.number_input("도매가",     min_value=0, value=int(row.get("도매가")     or 0), step=100)
    실제가     = p3.number_input("실제가",     min_value=0, value=int(row.get("실제가")     or 0), step=100)
    평균도매가 = p4.number_input("평균도매가", min_value=0, value=int(row.get("평균도매가") or 0), step=100)

    st.subheader("텍스트 콘텐츠")
    특징     = st.text_area("특징",     value=row.get("특징")     or "", height=100)
    키워드   = st.text_area("키워드",   value=row.get("키워드")   or "", height=80)
    치수정보 = st.text_area("치수정보", value=row.get("치수정보") or "", height=80)

    st.divider()
    _t2_l, _t2_r = st.columns([4, 1])
    if _t2_l.button("💾 저장", type="primary", use_container_width=True, key="btn_save_tab2"):
        # tab_판매자 위젯은 아직 실행 전 → session_state 키로 읽고, 없으면 DB값 폴백
        _ss = st.session_state
        _save({
            "제품명":         제품명.strip(),
            "모델명":         모델명        or None,
            "카테고리":       카테고리      or None,
            "서브카테고리":   서브카테고리  or None,
            "원산지":         원산지        or None,
            "제조사":         제조사        or None,
            "가로_cm":        가로          or None,
            "세로_cm":        세로          or None,
            "높이_cm":        높이          or None,
            "무게_g":         무게          or None,
            "재질":           재질          or None,
            "색상":           색상          or None,
            "구성품":         구성품        or None,
            "kc인증":         kc인증,
            "kc인증번호":     kc인증번호    or None,
            "기타인증":       기타인증      or None,
            "소매가":         소매가        or None,
            "도매가":         도매가        or None,
            "실제가":         실제가        or None,
            "평균도매가":     평균도매가    or None,
            "특징":           특징          or None,
            "키워드":         키워드        or None,
            "치수정보":       치수정보      or None,
            "판매자메모":     _ss.get("sf_판매자메모",     row.get("판매자메모")    ) or None,
            "검수완료":       _ss.get("sf_검수완료",       bool(row.get("검수완료"))),
            "검수메모":       _ss.get("sf_검수메모",       row.get("검수메모") or "") or None,
            "실시간재고":     _ss.get("sf_실시간재고",     int(row.get("실시간재고") or 0)),
            "처리후재고":     _ss.get("sf_처리후재고",     int(row.get("처리후재고") or 0)),
            "재고수량":       _ss.get("sf_재고수량",       int(row.get("재고수량")   or 0)),
            "재입고예정":     _ss.get("sf_재입고예정",     bool(row.get("재입고예정"))),
            "단종여부":       _ss.get("sf_단종여부",       bool(row.get("단종여부"))),
            "온라인판매가능": _ss.get("sf_온라인판매가능", row.get("온라인판매가능") if row.get("온라인판매가능") is not None else True),
            "판매채널":       _ss.get("sf_판매채널",       row.get("판매채널") or "") or None,
            "박스재사용":     _ss.get("sf_박스재사용",     bool(row.get("박스재사용"))),
            "주의사항":       _ss.get("sf_주의사항",       row.get("주의사항") or "") or None,
            "엠군상태":       _ss.get("sf_엠군상태",       row.get("엠군상태") or "미시작"),
        })
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
# 탭 — 판매자 정보
# ─────────────────────────────────────────────────────────
with tab_판매자:
    판매자메모 = st.text_area("판매자 특이사항", value=row.get("판매자메모") or "", height=120,
                               key="sf_판매자메모")

    st.subheader("검수")
    ins1, ins2 = st.columns([1, 3])
    검수완료 = ins1.checkbox("검수 완료",  value=bool(row.get("검수완료")), key="sf_검수완료")
    검수메모 = ins2.text_input("검수 메모", value=row.get("검수메모") or "",  key="sf_검수메모")

    st.subheader("재고")
    s1, s2, s3 = st.columns(3)
    실시간재고 = s1.number_input("실시간재고", min_value=0, value=int(row.get("실시간재고") or 0), key="sf_실시간재고")
    처리후재고 = s2.number_input("처리후재고", min_value=0, value=int(row.get("처리후재고") or 0), key="sf_처리후재고")
    재고수량   = s3.number_input("재고수량",   min_value=0, value=int(row.get("재고수량")   or 0), key="sf_재고수량")

    f1, f2, f3 = st.columns(3)
    재입고예정    = f1.checkbox("재입고 예정", value=bool(row.get("재입고예정")), key="sf_재입고예정")
    단종여부      = f2.checkbox("단종",        value=bool(row.get("단종여부")),   key="sf_단종여부")
    온라인판매가능 = f3.checkbox(
        "온라인 판매 가능",
        value=row.get("온라인판매가능") if row.get("온라인판매가능") is not None else True,
        key="sf_온라인판매가능",
    )

    st.subheader("판매 조건")
    판매채널   = st.text_input("판매 채널 제한", value=row.get("판매채널") or "",
                                placeholder="예: 쿠팡, 스마트스토어", key="sf_판매채널")
    박스재사용 = st.checkbox("박스 재사용", value=bool(row.get("박스재사용")), key="sf_박스재사용")
    주의사항   = st.text_area("주의사항",   value=row.get("주의사항") or "", height=80,
                               key="sf_주의사항")

    st.subheader("엠군 상태")
    _mgoon_opts = ["미시작", "진행중", "완료"]
    엠군상태 = st.selectbox("엠군상태", _mgoon_opts,
                             index=_mgoon_opts.index(row.get("엠군상태") or "미시작"),
                             key="sf_엠군상태")

    st.divider()
    _t3_l, _t3_r = st.columns([4, 1])
    if _t3_l.button("💾 저장", type="primary", use_container_width=True, key="btn_save_tab3"):
        # tab_스펙 블록이 먼저 실행됐으므로 지역변수 그대로 사용 가능
        _save({
            "제품명":         제품명.strip(),
            "모델명":         모델명        or None,
            "카테고리":       카테고리      or None,
            "서브카테고리":   서브카테고리  or None,
            "원산지":         원산지        or None,
            "제조사":         제조사        or None,
            "가로_cm":        가로          or None,
            "세로_cm":        세로          or None,
            "높이_cm":        높이          or None,
            "무게_g":         무게          or None,
            "재질":           재질          or None,
            "색상":           색상          or None,
            "구성품":         구성품        or None,
            "kc인증":         kc인증,
            "kc인증번호":     kc인증번호    or None,
            "기타인증":       기타인증      or None,
            "소매가":         소매가        or None,
            "도매가":         도매가        or None,
            "실제가":         실제가        or None,
            "평균도매가":     평균도매가    or None,
            "특징":           특징          or None,
            "키워드":         키워드        or None,
            "치수정보":       치수정보      or None,
            "판매자메모":     판매자메모    or None,
            "검수완료":       검수완료,
            "검수메모":       검수메모      or None,
            "실시간재고":     실시간재고,
            "처리후재고":     처리후재고,
            "재고수량":       재고수량,
            "재입고예정":     재입고예정,
            "단종여부":       단종여부,
            "온라인판매가능": 온라인판매가능,
            "판매채널":       판매채널      or None,
            "박스재사용":     박스재사용,
            "주의사항":       주의사항      or None,
            "엠군상태":       엠군상태,
        })
    if _t3_r.button("취소", use_container_width=True, key="btn_cancel_tab3"):
        _cancel()

# ── 삭제 ─────────────────────────────────────────────────
st.divider()
with st.expander("⚠️ 위험 구역", expanded=False):
    st.warning(f"**#{product_id} {row.get('제품명', '')}** 을(를) 삭제합니다. 연결된 파일 기록도 함께 삭제됩니다.")
    confirm = st.text_input("삭제 확인: 제품명을 정확히 입력하세요",
                            placeholder=row.get("제품명", ""), key="delete_confirm_input")
    if st.button("🗑️ 영구 삭제", type="secondary", key="btn_delete"):
        if confirm == row.get("제품명", ""):
            try:
                delete_상품(product_id)
                st.success("삭제 완료.")
                st.session_state.pop("_temp_product_id", None)
                st.session_state.pop("edit_product_id", None)
                st.session_state.pop("edit_mode", None)
                st.switch_page("pages/1_products.py")
            except Exception as e:
                st.error(f"삭제 실패: {e}")
        else:
            st.error("제품명이 일치하지 않습니다.")
