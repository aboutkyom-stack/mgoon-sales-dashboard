"""페이지 2 — 엠군 파이프라인 실행.

흐름
- 01 실행: 새 실행(엠군_실행) 생성 → JSON 블록 파싱 → 모델별 모든 타겟 후보를
  엠군_타겟에 저장 (claude/gemini 각 N개).
- 사용자: 카드에서 타겟 1개 선택.
- 02 실행: 같은 실행을 재사용 — 선택 타겟에 `선택됨=true` + 02 결과 모델별 저장.
- 홈 → run 클릭 진입: 저장된 spec/targets/positioning을 화면에 그대로 복원.
"""
from __future__ import annotations

import json
import re

import streamlit as st

from pipeline.role import is_owner
from pipeline.auto_pipeline import (
    _extract_engine_plan,
    _extract_positioning_json,
    _extract_review_blocks,
    _extract_sections_json,
    run_stage_01 as auto_run_01,
    run_stage_02 as auto_run_02,
    run_stage_04 as auto_run_04,
    run_stage_04_1 as auto_run_04_1,
    run_stage_04_b as auto_run_04_b,
    run_stage_05 as auto_run_05,
)
from pipeline.lint import cross_lint_both, parse_lint_status
from pipeline.llm import generate_both
from pipeline.models_config import family_of
from pipeline.sections import regenerate_section, replace_section, split_sections
from pipeline.loader import (
    build_user_input_01,
    build_user_input_02,
    build_user_input_04,
    build_user_input_04_1,
    build_user_input_04_b,
    build_user_input_05,
    build_user_input_listing_name,
    load_agent_prompt,
    load_listing_name_prompt,
)
from pipeline.settings import (
    caption_for_stage,
    lint_enabled_for_stage,
    lint_models_for_stage,
    load as load_settings,
    model_for_family,
    models_for_stage,
)
from pipeline.storage import get_storage


# ──────────────────────── 헬퍼 함수 ─────────────────────────

def _extract_targets_json(text: str) -> dict | None:
    """01 결과 텍스트에서 `---TARGETS_JSON---` 블록을 파싱."""
    if not text:
        return None
    m = re.search(
        r"---TARGETS_JSON---\s*(.*?)\s*---END_TARGETS_JSON---",
        text,
        re.DOTALL,
    )
    if not m:
        return None
    raw = m.group(1).strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except Exception:
        return None


def _split_json_block(text: str) -> tuple[str, str]:
    """01 결과를 마크다운/JSON 블록으로 분리."""
    if not text:
        return "", ""
    m = re.search(r"---TARGETS_JSON---", text)
    if not m:
        return text, ""
    md = text[:m.start()].rstrip()
    json_block = text[m.start():].strip()
    return md, json_block


def _build_target_description(t: dict) -> str:
    """타겟 dict → 02에 넘길 사람이 읽기 쉬운 멀티라인 텍스트."""
    parts = []
    if t.get("character"):
        parts.append(f"직업/나이/상황: {t['character']}")
    if t.get("deficit"):
        parts.append(f"핵심 결핍: {t['deficit']}")
    if t.get("deficit_source"):
        parts.append(f"결핍 원천: {t['deficit_source']}")
    if t.get("benefit_type"):
        parts.append(f"구매편익 유형: {t['benefit_type']}")
    if t.get("involvement") not in (None, ""):
        parts.append(f"관여도: {t['involvement']}")
    if t.get("channel"):
        parts.append(f"주요 채널: {t['channel']}")
    if t.get("buyer_user_split"):
        parts.append(f"구매자/이용자 분리: {t['buyer_user_split']}")
    if t.get("wants_3tier"):
        parts.append(f"욕구깡패: {t['wants_3tier']}")
    if t.get("note"):
        parts.append(f"비고: {t['note']}")
    return "\n".join(parts)


def _db_row_to_target_dict(row: dict) -> dict:
    """엠군_타겟 DB 행 → UI/저장 공통 형식 dict."""
    return {
        "db_id": row["id"],
        "rank": row.get("순위"),
        "label": row.get("라벨") or "",
        "character": row.get("캐릭터") or "",
        "deficit": row.get("핵심_결핍") or "",
        "deficit_source": row.get("결핍_원천") or "",
        "benefit_type": row.get("구매편익") or "",
        "involvement": row.get("관여도"),
        "channel": row.get("주요_채널") or "",
        "buyer_user_split": row.get("구매자_이용자_분리") or "",
        "wants_3tier": row.get("욕구깡패") or "",
        "note": row.get("비고") or "",
        "is_recommended": bool(row.get("추천_여부")),
        "is_selected": bool(row.get("선택됨")),
    }


def _model_header(
    emoji_label: str,
    model_id: str,
    lint_status: tuple[str, int] | None = None,
    lint_enabled: bool = True,
) -> str:
    """결과 박스 헤더 한 줄. 모델명 + 검증 상태 표기.

    lint_enabled=False → "외부 린터 OFF (설정에서 켜기)" — 의도적으로 꺼둔 상태
    lint_enabled=True인데 lint_status 없음 → "외부 린터 ✗ 미실행" — 비정상
    lint_status (PASS, _) → "외부 린터 ✓ 통과"
    lint_status (WARN, N) → "외부 린터 ⚠️ N건 주의"
    lint_status (FAIL, N) → "외부 린터 ❌ N건 위반"
    lint_status (ERROR/UNKNOWN, _) → "외부 린터 ⚙️ 오류"
    """
    if not lint_enabled:
        lint_part = "외부 린터 OFF (⚙️ 설정에서 켜기)"
    elif lint_status is None:
        lint_part = "외부 린터 ✗ 미실행"
    else:
        status, count = lint_status
        if status == "PASS":
            lint_part = "외부 린터 ✓ 통과"
        elif status == "WARN":
            lint_part = f"외부 린터 ⚠️ {count}건 주의"
        elif status == "FAIL":
            lint_part = f"외부 린터 ❌ {count}건 위반"
        else:
            lint_part = "외부 린터 ⚙️ 오류"
    return f"### {emoji_label} `{model_id}` · 작성+자가검수 · {lint_part}"


def _lint_reviewer_label(builder: str) -> str:
    """builder 모델 → 검수한 reviewer 모델 이름. expander 제목용."""
    return "Claude" if builder == "gemini" else "Gemini"


def _result_layout(claude_model: str | None, gemini_model: str | None):
    """결과 표시 컨테이너 (claude_container, gemini_container) 반환.

    - 두 모델 모두 있으면 2-컬럼.
    - 한쪽만 있으면 단일 컨테이너(전체 너비) + 비활성 쪽 None.
    - 둘 다 None이면 (None, None).
    """
    if claude_model and gemini_model:
        c1, c2 = st.columns(2)
        return c1, c2
    if claude_model:
        return st.container(), None
    if gemini_model:
        return None, st.container()
    return None, None


def _compare_off_caption(claude_model: str | None, gemini_model: str | None) -> None:
    """비교 모델 off일 때 단일 family 안내문."""
    if not (claude_model and gemini_model):
        st.caption("ℹ️ 비교 모델 off — 주 사용 모델 결과만 표시합니다.")


_STAGE_FULL_NAMES: dict[str, str] = {
    "01": "01 결핍·타겟",
    "02": "02 포지셔닝",
    "04": "04 상세페이지",
    "04_1": "04-1 이미지 디렉션",
    "05": "05 채널",
}

_FAMILY_DISPLAY: dict[str, str] = {"claude": "Claude", "gemini": "Gemini"}


def _stage_models_display(stage: str, cfg: dict) -> str:
    """단계별 '주 작업 Claude, 검수 Gemini' 또는 'Claude' 형식 반환.

    - 비교 모델 켜져 있고 family 다르면 두 모델 모두 표기 (주 + 검수).
    - 비교 off거나 같은 family면 주 모델만 표기.
    """
    primary = cfg.get(f"primary_model_{stage}")
    compare = cfg.get(f"compare_model_{stage}")
    enabled = bool(cfg.get(f"compare_enabled_{stage}", True))

    if not primary:
        return ""

    pf = family_of(primary)
    primary_disp = _FAMILY_DISPLAY.get(pf, primary)

    if enabled and compare:
        cf = family_of(compare)
        if cf != pf:
            compare_disp = _FAMILY_DISPLAY.get(cf, compare)
            return f"주 작업 {primary_disp}, 검수 {compare_disp}"

    return primary_disp


def _stage_action_label(stage: str, cfg: dict) -> str:
    """버튼 라벨: '🚀 02 포지셔닝 실행 (주 작업 Claude, 검수 Gemini)'."""
    name = _STAGE_FULL_NAMES.get(stage, stage)
    models = _stage_models_display(stage, cfg)
    return f"🚀 {name} 실행 ({models})" if models else f"🚀 {name} 실행"


def _stage_spinner_label(stage: str, cfg: dict) -> str:
    """스피너 텍스트: '02 포지셔닝 생성 중… (주 작업 Claude, 검수 Gemini)'."""
    name = _STAGE_FULL_NAMES.get(stage, stage)
    models = _stage_models_display(stage, cfg)
    return f"{name} 생성 중… ({models})" if models else f"{name} 생성 중…"


def _section_edit_ui(
    builder: str,
    model_label: str,
    full_text: str,
    ss_payload_key: str,
    marker_style: str = "auto",
) -> None:
    """섹션 단위 수정 expander. 버튼 클릭 시 ss에 페이로드 저장 후 rerun.

    호출자가 다음 사이클에서 ss[ss_payload_key]를 pop해 처리 — 처리 로직은
    각 단계 결과 표시 영역 직전에 위치 (positioning_02_ver 증가, DB 저장 등).

    marker_style: "auto"(기본)·"dot"(02)·"bracket"(04·05). split_sections에 전달.
    """
    sections = split_sections(full_text, marker_style)
    real = [(i, h) for i, (h, _) in enumerate(sections)
            if h not in ("(전체)", "(인트로)")]
    if not real:
        return
    with st.expander(f"✏️ {model_label} 결과 섹션 단위 수정", expanded=False):
        sel_idx = st.selectbox(
            "수정할 섹션",
            options=[i for i, _ in real],
            format_func=lambda i: dict(real).get(i, f"#{i}"),
            key=f"sec_sel_{ss_payload_key}_{builder}",
        )
        feedback = st.text_area(
            "수정 피드백 — 무엇을 어떻게 바꾸고 싶은지 자연어로",
            placeholder=(
                "예: 두 까기가 둘 다 같은 결함 카테고리야. "
                "하나는 가격 부담, 하나는 흥미 지속성으로 다른 각도로 바꿔줘."
            ),
            key=f"sec_fb_{ss_payload_key}_{builder}",
            height=100,
        )
        if st.button(
            "🔄 이 섹션만 재생성",
            key=f"sec_regen_btn_{ss_payload_key}_{builder}",
            disabled=not feedback.strip(),
            use_container_width=True,
        ):
            st.session_state[ss_payload_key] = {
                "builder": builder,
                "section_index": sel_idx,
                "section_header": dict(real)[sel_idx],
                "feedback": feedback.strip(),
            }
            st.rerun()


# ──────────────────────── 페이지 시작 ────────────────────────

st.title("🧪 엠군 파이프라인")
st.caption("🗄️ DB — 상품 (읽기) | 엠군_실행, 엠군_타겟, 엠군_포지셔닝 (저장)")

ss = st.session_state
cfg = load_settings()
claude_model_01, gemini_model_01 = models_for_stage("01", cfg)
claude_model_02, gemini_model_02 = models_for_stage("02", cfg)
claude_model_04, gemini_model_04 = models_for_stage("04", cfg)
claude_model_04_1, gemini_model_04_1 = models_for_stage("04_1", cfg)
claude_model_05, gemini_model_05 = models_for_stage("05", cfg)


def _lint_pair(stage: str) -> tuple[str | None, str | None]:
    """단계별 린터용 (claude_model, gemini_model). 린터 off면 (None, None)."""
    if not lint_enabled_for_stage(stage, cfg):
        return (None, None)
    return lint_models_for_stage(stage, cfg)


lint_c_01, lint_g_01 = _lint_pair("01")
lint_c_02, lint_g_02 = _lint_pair("02")
lint_c_04, lint_g_04 = _lint_pair("04")
lint_c_04_1, lint_g_04_1 = _lint_pair("04_1")
lint_c_05, lint_g_05 = _lint_pair("05")

storage = get_storage()


def _ts_kst(ts: str) -> str:
    """UTC ISO 타임스탬프 → KST(+9h) 표시 문자열."""
    if not ts:
        return ""
    from datetime import datetime, timezone, timedelta
    _KST = timezone(timedelta(hours=9))
    try:
        raw = ts.strip()
        # psycopg2/supabase 반환 형식 정규화
        raw = raw.replace(" ", "T")
        if not raw.endswith(("Z", "+00:00")) and "+" not in raw[10:] and raw[-6] != "+":
            raw += "+00:00"
        raw = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw[:26] + "+00:00" if len(raw) < 20 else raw)
        return dt.astimezone(_KST).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts[:19].replace("T", " ")


def _version_history_ui(
    stage: str,
    builder: str,
    target_db_id: int | None,
) -> None:
    """단계별 버전 이력 expander.

    버전이 2개 이상일 때만 표시. 각 행에 [📥 표시] [🗑 삭제] 버튼.
    - 표시: 그 버전 원본을 ss[stage_key][builder]로 끌어와 화면 본문에 띄움
            (이후 후속 단계 실행 시 그 버전이 입력으로 사용됨)
    - 삭제: 확인 후 DB 행 제거. 현재 표시 중이던 버전이면 다음 최신으로 자동 전환.

    stage: "02" | "04" | "05"
    builder: "claude" | "gemini"
    """
    if not target_db_id:
        return

    if stage == "02":
        get_versions = storage.get_positioning_versions
        delete_one = storage.delete_positioning
        ss_key = "positioning_02"
    elif stage == "04":
        get_versions = storage.get_상세페이지_versions
        delete_one = storage.delete_상세페이지
        ss_key = "detail_04"
    elif stage == "04_1":
        get_versions = storage.get_이미지디렉션_versions
        delete_one = storage.delete_이미지디렉션
        ss_key = "image_direction_04_1"
    elif stage == "05":
        get_versions = storage.get_채널_versions
        delete_one = storage.delete_채널
        ss_key = "channel_05"
    else:
        return

    try:
        versions = get_versions(target_db_id, builder)
    except Exception as e:
        st.caption(f"버전 이력 조회 실패: {type(e).__name__}: {e}")
        return

    if len(versions) <= 1:
        return  # 버전이 1개 이하면 expander 자체 숨김

    with st.expander(f"📜 버전 히스토리 ({len(versions)}개)", expanded=False):
        st.caption(
            "표시 = 그 버전을 본문에 띄우고 후속 단계의 입력으로 사용. "
            "삭제 = DB에서 영구 제거 (되돌릴 수 없음)."
        )
        for i, v in enumerate(versions):
            ts = _ts_kst(v.get("생성일") or "")
            ver_label = "최신" if i == 0 else f"v{len(versions) - i}"
            row_l, row_btn1, row_btn2 = st.columns([4, 1, 1])
            with row_l:
                st.markdown(f"**{ver_label}** · {ts}")
            with row_btn1:
                if st.button(
                    "📥 표시",
                    key=f"vh_show_{stage}_{builder}_{v['id']}",
                    use_container_width=True,
                ):
                    cur = dict(ss.get(ss_key) or {})
                    cur[builder] = v.get("원본_출력") or ""
                    ss[ss_key] = cur
                    ss.pop(f"lint_{stage}", None)  # 린터 캐시 무효화
                    st.rerun()
            with row_btn2:
                confirm_key = f"vh_del_confirm_{stage}_{builder}_{v['id']}"
                if ss.get(confirm_key):
                    if st.button(
                        "확인?",
                        key=f"vh_del_yes_{stage}_{builder}_{v['id']}",
                        use_container_width=True,
                    ):
                        try:
                            delete_one(v["id"])
                            ss.pop(confirm_key, None)
                            # 현재 화면에 떠 있는 버전을 지운 거라면 다음 최신으로 갱신
                            cur = dict(ss.get(ss_key) or {})
                            if cur.get(builder, "") == (v.get("원본_출력") or ""):
                                remaining = [vv for vv in versions if vv["id"] != v["id"]]
                                cur[builder] = remaining[0].get("원본_출력") if remaining else ""
                                ss[ss_key] = cur
                            ss.pop(f"lint_{stage}", None)
                            st.rerun()
                        except Exception as e:
                            st.error(f"삭제 실패: {type(e).__name__}: {e}")
                else:
                    if st.button(
                        "🗑 삭제",
                        key=f"vh_del_{stage}_{builder}_{v['id']}",
                        use_container_width=True,
                    ):
                        ss[confirm_key] = True
                        st.rerun()


def _restore_from_run(run_id: int) -> bool:
    """저장된 run을 화면 상태로 복원. 성공 시 True."""
    run = storage.get_run(run_id)
    if not run:
        return False
    spec = run.get("제품_스냅샷")
    if isinstance(spec, dict):
        ss["pipeline_product_spec"] = spec

    target_rows = storage.get_targets(run_id)
    grouped: dict[str, list[dict]] = {"claude": [], "gemini": []}
    raw_per_model: dict[str, str] = {"claude": "", "gemini": ""}
    selected_db_id: int | None = None
    for row in target_rows:
        model = row.get("모델")
        if model in grouped:
            grouped[model].append(_db_row_to_target_dict(row))
            if not raw_per_model[model] and row.get("원본_출력"):
                raw_per_model[model] = row["원본_출력"]
        if row.get("선택됨"):
            selected_db_id = row["id"]

    if any(raw_per_model.values()):
        ss["targets_01"] = raw_per_model
        ss["parsed_with_ids"] = grouped

    if selected_db_id:
        pos_rows = storage.get_positioning(selected_db_id)
        positioning_02: dict[str, str] = {"claude": "", "gemini": ""}
        # 같은 모델로 여러 번 저장됐을 수 있음 → 마지막(최신)이 마지막에 덮어씀
        for prow in pos_rows:
            m = prow.get("모델")
            if m in positioning_02:
                positioning_02[m] = prow.get("원본_출력") or ""
        if any(positioning_02.values()):
            ss["positioning_02"] = positioning_02

        # 04 상세페이지 복원
        detail_rows = storage.get_상세페이지(selected_db_id)
        detail_04: dict[str, str] = {"claude": "", "gemini": ""}
        for d in detail_rows:
            m = d.get("모델")
            if m in detail_04:
                detail_04[m] = d.get("원본_출력") or ""
        if any(detail_04.values()):
            ss["detail_04"] = detail_04

        # 04-1 이미지 디렉션 복원
        direction_rows = storage.get_이미지디렉션(selected_db_id)
        image_direction_raw: dict[str, str] = {"claude": "", "gemini": ""}
        image_direction_parsed: dict[str, dict | None] = {"claude": None, "gemini": None}
        for d in direction_rows:
            m = d.get("모델")
            if m in image_direction_raw:
                image_direction_raw[m] = d.get("원본_출력") or ""
                # 섹션들/디자인시스템은 JSONB로 직렬화돼 올 수 있음
                sections = d.get("섹션들")
                ds = d.get("디자인시스템")
                if isinstance(sections, str):
                    try:
                        sections = json.loads(sections)
                    except Exception:
                        sections = None
                if isinstance(ds, str):
                    try:
                        ds = json.loads(ds)
                    except Exception:
                        ds = None
                if sections or ds or d.get("선택_방식"):
                    image_direction_parsed[m] = {
                        "sections": sections or [],
                        "design_system": ds or {},
                        "selection_method": d.get("선택_방식") or "",
                    }
        if any(image_direction_raw.values()):
            ss["image_direction_04_1"] = image_direction_raw
            ss["image_direction_04_1_parsed"] = image_direction_parsed

        # 05 채널 복원
        channel_rows = storage.get_채널(selected_db_id)
        channel_05: dict[str, str] = {"claude": "", "gemini": ""}
        for c in channel_rows:
            m = c.get("모델")
            if m in channel_05:
                channel_05[m] = c.get("원본_출력") or ""
        if any(channel_05.values()):
            ss["channel_05"] = channel_05

        ss["saved_run_id"] = run_id
        ss["selected_target_db_id"] = selected_db_id

    return True


def _find_selected_target_dict(selected_db_id: int) -> dict | None:
    """selected_target_db_id에 해당하는 타겟 dict를 ss["parsed_with_ids"]에서 검색."""
    parsed_with_ids = ss.get("parsed_with_ids") or {}
    for model_targets in parsed_with_ids.values():
        for t in (model_targets or []):
            if t.get("db_id") == selected_db_id:
                return t
    return None


# ── 04-1 이미지 디렉션 (대화형 적재) — GPT(ChatGPT) 복붙 카드 빌더 ──────────
# 동료가 ChatGPT 대화창에 그대로 복붙하는 자연어 블록을 만든다.
# 데이터는 core.md 스키마(엠군_이미지디렉션.섹션들 JSONB): section_no /
# section_name / canvas(문자열) / image_type / composition /
# main_subject{what,details,props} / background / lighting / color_palette[] /
# text_elements[{label,text,position,style}] / negative_avoided /
# production_method / notes / (직접촬영 컷만) shooting_guide
_CANVAS_PX = {
    "1:1": "1024x1024", "4:5": "≈1024x1280", "3:4": "≈1024x1536",
    "2:3": "1024x1536", "9:16": "2160x3840", "16:9": "2048x1152",
}

_GLOBAL_FIXED_NOTE = (
    "📎 제품 사진을 함께 첨부하고 '이미지1 = 제품 형태·색상·비율 기준'으로 지정하세요.\n"
    "   참고 이미지에 없는 부품·글자·로고·버튼은 새로 만들지 마세요.\n"
    "🚫 워터마크·가짜 QR·없는 로고·미확인 인증·실물과 다른 구성품은 생성하지 마세요."
)

# text_elements.label → GPT에 전달할 위계 힌트 (크기·강조 우선순위를 명시).
# 데이터의 style(폰트·색)은 그대로 두고, 라벨이 함축하는 위계를 풀어준다.
# GPT Image는 긴 한글을 작게/흐리게 그리는 경향이 있어, '크게·또렷이'를 명시한다.
_TEXT_HIER = {
    "HEADLINE": "매우 크게(이미지 가로폭 70~90%)·굵게, 배경과 강한 대비로 또렷이",
    "TITLE": "매우 크게(이미지 가로폭 70~90%)·굵게, 배경과 강한 대비로 또렷이",
    "SUB": "크고 또렷하게(헤드라인 다음 크기)",
    "SUBHEAD": "크고 또렷하게(헤드라인 다음 크기)",
    "BODY": "또렷이 읽히는 큰 본문 크기(작게·흐리게 금지)",
    "CAPTION": "또렷이 읽히는 크기(과하게 작지 않게)",
    "BADGE": "굵고 또렷한 강조 뱃지",
    "CTA": "크고 굵은 버튼형 강조 · 행동 유도",
}


def _canvas_with_px(canvas: str) -> str:
    """캔버스 비율 문자열에 GPT Image 권장 픽셀 사이즈를 병기."""
    c = (canvas or "").strip()
    px = _CANVAS_PX.get(c)
    return f"{c} ({px})" if px else c


def _production_badge(pm: str) -> tuple[str, str]:
    """production_method → (배지 라벨, 종류키). 종류키: ai|shoot|existing|mix|unknown."""
    s = pm or ""
    has_ai = ("AI" in s) or ("생성" in s)
    has_shoot = ("직접" in s) or ("촬영" in s)
    has_exist = "기존" in s
    if has_exist and has_shoot:
        return ("🔀 제안: 기존/직접 택1", "mix")
    if has_shoot and not has_exist and not has_ai:
        return ("📸 제안: 직접 촬영/동영상", "shoot")
    if has_exist:
        return ("🖼️ 제안: 기존 이미지", "existing")
    if has_ai:
        return ("🟢 제안: GPT 생성", "ai")
    return ("❓ 미지정", "unknown")


def _build_global_block(ds: dict | None) -> str:
    """디자인시스템(전역 규칙) → GPT 세션당 1회 복붙용 블록."""
    lines = ["[전역 — GPT 세션 시작 시 제품 사진과 함께 1회만 입력]"]
    if isinstance(ds, dict):
        cd = ds.get("canvas_default")
        if cd:
            lines.append(f"- 기본 캔버스: {_canvas_with_px(cd)}")
        cg = ds.get("color_palette_global") or ds.get("color_palette") or []
        if cg:
            lines.append(f"- 공통 색상: {' / '.join(str(c) for c in cg)}")
        pc = ds.get("people_consistency")
        if pc:
            lines.append(f"- 인물 일관성: {pc}")
        fb = ds.get("forbidden") or []
        if fb:
            lines.append(f"- 전역 금지: {' / '.join(str(f) for f in fb)}")
    lines.append(_GLOBAL_FIXED_NOTE)
    return "\n".join(lines)


def _build_cut_block(sec: dict, global_cp: list | None = None) -> str:
    """섹션 1개 → GPT 복붙용 자연어 블록. 색상은 전역과 다를 때(예외)만 표기."""
    L: list[str] = []
    canvas = _canvas_with_px(sec.get("canvas") or "")
    if canvas:
        L.append(f"- 캔버스: {canvas}")
    if sec.get("background"):
        L.append(f"- 배경/장면: {sec['background']}")
    ms = sec.get("main_subject")
    if isinstance(ms, dict):
        head = " — ".join(p for p in [ms.get("what"), ms.get("details")] if p)
        if head:
            L.append(f"- 주 피사체: {head}")
        if ms.get("props"):
            L.append(f"- 소품: {ms['props']}")
    elif ms:
        L.append(f"- 주 피사체: {ms}")
    if sec.get("composition"):
        L.append(f"- 구도: {sec['composition']}")
    if sec.get("lighting"):
        L.append(f"- 조명·스타일: {sec['lighting']}")
    cp = sec.get("color_palette") or []
    if cp and list(cp) != list(global_cp or []):
        L.append(f"- 색상(이 컷 예외): {' / '.join(str(c) for c in cp)}")
    te = sec.get("text_elements") or []
    if te:
        L.append("- 이미지 속 텍스트 (모든 글자는 크고 또렷하게·배경과 강한 대비 / 아래 문구만 정확히 표기 / 다른 글자·오타 생성 금지 / 줄바꿈 유지):")
        for t in te:
            if not isinstance(t, dict):
                continue
            label = (t.get("label") or "").strip()
            text = " ".join((t.get("text") or "").split())
            pos = t.get("position") or ""
            style = t.get("style") or ""
            hier = _TEXT_HIER.get(label.upper(), "")
            tag = (f"{label}·{hier}" if hier else label) if label else ""
            L.append(f'  · [{tag}] "{text}"' if tag else f'  · "{text}"')
            sub = " / ".join(
                x for x in [f"위치 {pos}" if pos else "", f"글자 스타일 {style}" if style else ""] if x
            )
            if sub:
                L.append(f"      {sub}")
    na = sec.get("negative_avoided")
    if na:
        L.append(f"- 생성 금지: {na}")
    return "\n".join(L)


def _strip_json_fences(text: str) -> str:
    """raw 출력에서 ```json ...``` / SECTIONS_JSON 블록 제거 (구조화 실패 시 폴백용)."""
    out = re.sub(r"```json.*?```", "", text or "", flags=re.DOTALL)
    out = re.sub(r"---SECTIONS_JSON---.*?(?:---END_SECTIONS_JSON---|$)", "", out, flags=re.DOTALL)
    return out.strip()


def _extract_img_direction(dir_rows: list[dict]) -> dict | None:
    """엠군_이미지디렉션 행 목록 → {sections, design_system, raw}. 구조화 우선."""
    for d in (dir_rows or []):
        sec = d.get("섹션들")
        if isinstance(sec, str):
            try:
                sec = json.loads(sec)
            except Exception:
                sec = None
        ds = d.get("디자인시스템")
        if isinstance(ds, str):
            try:
                ds = json.loads(ds)
            except Exception:
                ds = None
        if sec or ds:
            return {"sections": sec or [], "design_system": ds or {},
                    "raw": d.get("원본_출력") or ""}
    for d in (dir_rows or []):
        if d.get("원본_출력"):
            return {"sections": [], "design_system": {}, "raw": d["원본_출력"]}
    return None


def _render_image_direction_cards(img: dict) -> None:
    """대화형 적재 04-1을 GPT 복붙 카드로 렌더."""
    sections = img.get("sections") or []
    ds = img.get("design_system") or {}
    if not sections:
        body = _strip_json_fences(img.get("raw") or "")
        st.markdown(body or "_(이미지 디렉션 내용 없음)_")
        return

    st.warning(
        "**🔤 폰트·글자 안내 (꼭 읽어주세요)**\n\n"
        "GPT Image는 폰트 파일을 쓰지 않고 '굵은 산세리프 느낌'처럼 글자를 **그림으로 그립니다.** "
        "그래서 아래 디렉션의 폰트명(예: G마켓산스)은 **분위기 힌트일 뿐**, 실제 그 폰트로 찍히는 게 아닙니다.\n\n"
        "- 진짜 폰트 **라이선스는 후편집**(디자인 툴에서 실제 폰트를 얹을 때)에서만 문제됩니다. GPT 생성 단계에선 신경 안 써도 됩니다.\n"
        "- **요청 시 도입 가능:** 상업적 무료 폰트만 쓰도록 '안전 폰트 목록'을 시스템에 넣을 수 있어요. "
        "후보 — 프리텐다드(가장 안전·OFL)·G마켓산스·노토산스KR·나눔스퀘어 등. "
        "(폰트별 세부 조건(임베딩·수정·BI 사용)은 도입 시 개별 확인)\n\n"
        "→ **안전 폰트 목록 도입을 원하면 관리자에게 요청하세요. (현재 미적용)**"
    )

    gcp = (ds.get("color_palette_global") or ds.get("color_palette") or []) if isinstance(ds, dict) else []

    st.markdown("**📋 전역 디자인 — 세션당 1회 복붙**")
    st.code(_build_global_block(ds), language="text")
    st.caption("👆 새 GPT 세션 시작 시 제품 사진과 함께 1회만 입력. 아래 각 컷은 따로 복붙하세요.")
    st.divider()

    for sec in sections:
        if not isinstance(sec, dict):
            continue
        no = sec.get("section_no")
        name = sec.get("section_name") or "(이름 없음)"
        itype = sec.get("image_type") or ""
        badge, _ = _production_badge(sec.get("production_method") or "")
        canvas = _canvas_with_px(sec.get("canvas") or "")
        with st.container(border=True):
            st.markdown(f"#### ■ #{no} · {name}")
            meta = "　·　".join(x for x in [badge, itype, f"📐 {canvas}" if canvas else ""] if x)
            if meta:
                st.caption(meta)
            # production_method는 엠군의 '제안'일 뿐 — 동료가 어떤 컷이든 AI로 만들 수 있게
            # 모든 컷 복붙 카드를 항상 펼친다.
            st.code(_build_cut_block(sec, gcp), language="text")
            sg = sec.get("shooting_guide")
            if isinstance(sg, dict) and sg:
                with st.expander("🎬 촬영 가이드 (직접 촬영/동영상 시 참고)", expanded=False):
                    st.json(sg)
            notes = sec.get("notes")
            if notes:
                with st.expander("▾ 내부 메모 (GPT에 넣지 마세요)", expanded=False):
                    st.caption(notes)


def _load_interactive_run(run_id: int) -> dict | None:
    """적재(대화형) run이면 읽기 전용 표시용 데이터 묶음을 반환. 아니면 None.

    엠군_실행.모드 == 'interactive' (ingest_to_supabase.py가 적재한 run)만 해당한다.
    이 모드의 단계 결과는 모두 모델='interactive'로 저장돼, claude/gemini 2열 전제인
    `_restore_from_run`/단계 렌더가 전부 걸러낸다 → 화면에 아무것도 안 보임.
    그래서 적재 run은 이 함수로 직접 읽어 단일 열 읽기 전용 뷰로 표시한다.
    (owner/partner 무관 — 적재 run 자체의 표시 경로 문제)
    """
    run = storage.get_run(run_id)
    if not run or run.get("모드") != "interactive":
        return None

    targets = storage.get_targets(run_id)
    selected = next((t for t in targets if t.get("선택됨")), None)

    def _first_raw(rows: list[dict]) -> str:
        for r in (rows or []):
            if r.get("원본_출력"):
                return r["원본_출력"]
        return ""

    steps: dict[str, str] = {}
    img_direction: dict | None = None
    if selected:
        tid = selected["id"]
        # 01 원본 전체(타겟 행의 원본_출력 = 01_deficit_target.md 본문)
        steps["01"] = selected.get("원본_출력") or ""
        steps["02"] = _first_raw(storage.get_positioning(tid))
        steps["03"] = _first_raw(storage.get_네이밍(tid))
        detail_rows = storage.get_상세페이지(tid)
        detail_row = next(
            (r for r in detail_rows if r.get("원본_출력")),
            detail_rows[0] if detail_rows else None,
        )
        steps["04_a"] = (detail_row or {}).get("원본_출력") or ""
        if detail_row:
            steps["04_b"] = _first_raw(storage.get_상세페이지_검수(detail_row["id"]))
        dir_rows = storage.get_이미지디렉션(tid)
        steps["04_1"] = _first_raw(dir_rows)
        img_direction = _extract_img_direction(dir_rows)
        steps["05"] = _first_raw(storage.get_채널(tid))

    return {"run": run, "targets": targets, "selected": selected,
            "steps": steps, "img_direction": img_direction}


def _render_interactive_run(data: dict) -> None:
    """적재(대화형) run을 읽기 전용으로 표시. 동료가 주로 보는 04-1을 최상단에 둔다."""
    run = data["run"]
    targets = data["targets"]
    selected = data["selected"]
    steps = data["steps"]
    img_direction = data.get("img_direction")

    st.info(
        "📂 **대화형(엠군 수동) 적재 결과 — 읽기 전용**\n\n"
        "GPT Image(ChatGPT) 복붙용으로 정리한 화면입니다. 각 컷 코드블록 오른쪽 위 "
        "복사 아이콘으로 그대로 복사해 ChatGPT에 붙여넣으세요."
    )

    # run 메타 (시도 / 선택 타겟 / 가설)
    with st.container(border=True):
        if run.get("시도_라벨"):
            st.markdown(f"**시도**: {run['시도_라벨']}")
        if selected:
            _sel = _db_row_to_target_dict(selected)
            st.caption(f"🎯 선택 타겟 #{_sel.get('rank')} · {_sel.get('label') or ''}")
        if run.get("타겟_가설"):
            st.caption(f"🎯 타겟 가설: {run['타겟_가설']}")
        if run.get("결핍_가설"):
            st.caption(f"💢 결핍 가설: {run['결핍_가설']}")
        if run.get("대화형_폴더명"):
            st.caption(f"📁 원본 폴더: `{run['대화형_폴더명']}`")

    # ── 04-1 이미지 디렉션 — 최상단 (동료 메인 작업물) ──
    st.subheader("🎨 04-1 이미지 디렉션 — GPT 복붙용")
    if img_direction and (img_direction.get("sections") or img_direction.get("raw")):
        _render_image_direction_cards(img_direction)
    else:
        st.caption("04-1 이미지 디렉션이 아직 적재되지 않았습니다.")

    # ── 그 외 단계 (필요할 때 펼치기) ──
    st.divider()
    st.subheader("📂 그 외 단계 결과 (필요할 때 펼치기)")
    if not targets:
        st.caption("이 실행에는 타겟이 없습니다 (00·상품 단계만 적재됨).")
        return

    for t in sorted(targets, key=lambda x: (x.get("순위") or 99)):
        td = _db_row_to_target_dict(t)
        is_sel = bool(t.get("선택됨"))
        star = "⭐ " if td.get("is_recommended") else ""
        mark = "🟢 선택됨 · " if is_sel else ""
        head = f"{mark}{star}#{td.get('rank')} · {td.get('label') or '(라벨 없음)'}"
        with st.expander(f"🎯 타겟 — {head}", expanded=False):
            desc = _build_target_description(td)
            st.markdown(desc.replace("\n", "  \n") if desc else "_(상세 없음)_")

    if not selected:
        st.caption("선택된 타겟이 없어 02~05 결과를 표시할 수 없습니다.")
        return

    _STEP_VIEW = [
        ("01", "01 결핍·타겟 (원본 전체)"),
        ("02", "02 포지셔닝"),
        ("03", "03 네이밍"),
        ("04_a", "04 상세페이지 콘티"),
        ("04_b", "04 검수 · 다듬은 콘티"),
        ("05", "05 채널"),
    ]
    for key, label in _STEP_VIEW:
        raw = (steps.get(key) or "").strip()
        if not raw:
            continue
        with st.expander(f"▸ {label}", expanded=False):
            st.markdown(raw)


# 홈에서 기존 run 클릭으로 진입한 경우 1회 복원
if ss.get("current_run_id") and ss.get("_run_loaded") != ss["current_run_id"]:
    if _restore_from_run(ss["current_run_id"]):
        ss["_run_loaded"] = ss["current_run_id"]

spec = ss.get("pipeline_product_spec")

if not spec:
    st.warning("먼저 '제품 조회' 페이지에서 제품을 선택하세요.")
    st.page_link("pages/1_products.py", label="📦 제품 조회로 이동", icon="➡️")
    st.stop()

# ── Step A: 제품 요약 ───────────────────────────────────
with st.container(border=True):
    st.subheader(f"제품: #{spec.get('id')} · {spec.get('제품명')}")
    _재고 = (spec.get("재고") or {}).get("실시간재고", "-")
    _채널 = (spec.get("판매조건") or {}).get("판매채널", "-")
    _가격 = (spec.get("가격") or {})
    st.caption(
        f"채널: {_채널}  ·  재고: {_재고}  ·  "
        f"💸 온라인 판매 가격: **{_가격.get('온라인판매가격')}**  ·  "
        f"소매가: {_가격.get('소매가')}  ·  도매가: {_가격.get('도매가')}"
    )
    if ss.get("current_run_id"):
        st.caption(f"💾 저장된 실행: **#{ss['current_run_id']}**")
    with st.expander("스펙 원본 보기", expanded=False):
        st.json(spec)

st.divider()

# ── 적재(대화형) run은 읽기 전용 단일 열 뷰로 표시하고 종료 ──
# 자동화형 뷰어는 claude/gemini 2열 전제라 모드='interactive' 적재 run을 못 읽는다.
# (owner/partner 무관 — 동료 조회를 위해 전용 읽기 뷰로 분기)
if ss.get("current_run_id"):
    _interactive_data = _load_interactive_run(ss["current_run_id"])
    if _interactive_data is not None:
        _render_interactive_run(_interactive_data)
        st.stop()

# ── 🚀 자동 모드 ─────────────────────────────────────────
if not is_owner():
    st.info("🔒 파이프라인 실행은 owner 전용입니다. 저장된 결과는 아래에서 조회할 수 있습니다.")
with st.expander("🚀 자동 모드 (논스톱 실행)", expanded=False):
    st.caption(
        "01~05를 논스톱으로 돌립니다. 시간이 오래 걸리니 작업시켜놓고 다른 일을 하세요. "
        "03 제품명 (네이밍)은 분기·DB 구조가 달라 별도 페이지에서 수동 진행합니다."
    )

    auto_mode = st.radio(
        "타겟 모드",
        options=["추천 #1 자동", "멀티 타겟 자동"],
        horizontal=True,
        key="auto_mode",
        help=(
            "추천 #1 자동: 01부터 자동 실행 → 추천 타겟 #1 자동 선택 → 체크된 단계.\n"
            "멀티 타겟 자동: 01을 먼저 수동 실행 → 타겟 다중 체크 → 각 타겟별 체크된 단계."
        ),
    )

    st.markdown("**실행 단계**")
    cols_stage = st.columns(5)
    with cols_stage[0]:
        auto_do_02 = st.checkbox("02 포지셔닝", value=True, key="auto_do_02")
    with cols_stage[1]:
        auto_do_04 = st.checkbox("04 상세페이지", value=True, key="auto_do_04")
    with cols_stage[2]:
        auto_do_04_b = st.checkbox(
            "04_b 검수", value=False, key="auto_do_04_b",
            help="04_a 콘티에 대한 검수 + 다듬은 콘티 생성. 옵션 단계(선택적). 04가 함께 체크돼 있거나 기존 04 결과가 있어야 실행됩니다."
        )
    with cols_stage[3]:
        auto_do_04_1 = st.checkbox(
            "04-1 이미지 디렉션", value=False, key="auto_do_04_1",
            help="04 콘티가 있어야 실행됩니다. 04를 함께 체크하거나 기존 04 결과가 있어야 합니다."
        )
    with cols_stage[4]:
        auto_do_05 = st.checkbox("05 채널", value=True, key="auto_do_05")

    if auto_mode == "추천 #1 자동":
        st.caption("01 자동 실행 후 결과 JSON에서 `recommended_rank` 타겟을 자동 선택합니다.")
        if st.button(
            "🚀 추천 모드 자동 실행",
            type="primary",
            disabled=not is_owner(),
            use_container_width=True,
            key="auto_recommend_btn",
        ):
            ss["_auto_trigger"] = "recommend"
            ss["_auto_stages"] = {
                "02": auto_do_02, "04": auto_do_04,
                "04_b": auto_do_04_b,
                "04_1": auto_do_04_1, "05": auto_do_05,
            }
            st.rerun()
    else:
        # 멀티 타겟 모드 — 01이 이미 실행돼 있어야 함
        _existing_parsed = ss.get("parsed_with_ids") or {}
        _has_targets = bool(_existing_parsed.get("claude") or _existing_parsed.get("gemini"))
        if not _has_targets:
            st.warning("⚠️ 멀티 타겟 모드는 먼저 **아래에서 01을 수동 실행**해 타겟 목록을 확보하세요.")
        else:
            available_basis = [
                m for m in ("claude", "gemini")
                if (_existing_parsed.get(m) or [])
            ]
            if len(available_basis) >= 2:
                multi_basis = st.radio(
                    "타겟 출처 모델",
                    options=available_basis,
                    horizontal=True,
                    format_func=lambda x: {"claude": "🟠 Claude", "gemini": "🔵 Gemini"}[x],
                    key="auto_multi_basis",
                )
            else:
                multi_basis = available_basis[0]
                st.caption(f"타겟 출처: **{multi_basis}** (다른 모델 결과 없음)")

            target_options: list[dict] = _existing_parsed.get(multi_basis) or []
            if target_options:
                def _fmt_multi(t: dict) -> str:
                    star = "⭐ " if t.get("is_recommended") else ""
                    return f"{star}#{t.get('rank')} · {t.get('label', '(라벨 없음)')}"

                multi_selected = st.multiselect(
                    "처리할 타겟 (다중 선택)",
                    options=target_options,
                    format_func=_fmt_multi,
                    key="auto_multi_targets",
                )
                if st.button(
                    f"🚀 멀티 타겟 자동 실행 ({len(multi_selected)}개 타겟)",
                    type="primary",
                    use_container_width=True,
                    disabled=not is_owner() or not multi_selected,
                    key="auto_multi_btn",
                ):
                    ss["_auto_trigger"] = "multi"
                    ss["_auto_stages"] = {
                        "02": auto_do_02, "04": auto_do_04,
                        "04_b": auto_do_04_b,
                        "04_1": auto_do_04_1, "05": auto_do_05,
                    }
                    ss["_auto_multi_basis"] = multi_basis
                    ss["_auto_multi_targets"] = multi_selected
                    st.rerun()


# ── 자동 모드 실행 트리거 처리 ────────────────────────────
def _populate_ss_from_stage_01(result: dict) -> None:
    ss["targets_01"] = result["raw"]
    ss["lint_01"] = result["lint"]
    ss["parsed_with_ids"] = result["parsed_with_ids"]
    ss["current_run_id"] = result["run_id"]
    ss["_run_loaded"] = result["run_id"]
    for k in ("positioning_02", "saved_run_id", "selected_target_db_id",
              "detail_04", "image_direction_04_1",
              "image_direction_04_1_parsed", "channel_05",
              "lint_02", "lint_04", "lint_04_1", "lint_05",
              "positioning_02_ver",
              "detail_04_ver", "image_direction_04_1_ver", "channel_05_ver",
              "detail_04_based_on_ver",
              "image_direction_04_1_based_on_ver",
              "channel_05_based_on_ver",
              "_sec_regen_02", "_sec_regen_04", "_sec_regen_05"):
        ss.pop(k, None)


def _populate_ss_from_stage_02(result: dict, target_db_id: int, run_id: int) -> None:
    ss["positioning_02"] = result["raw"]
    ss["lint_02"] = result["lint"]
    ss["positioning_02_ver"] = ss.get("positioning_02_ver", 0) + 1
    ss["selected_target_db_id"] = target_db_id
    ss["saved_run_id"] = run_id


def _populate_ss_from_stage_04(result: dict) -> None:
    ss["detail_04"] = result["raw"]
    ss["lint_04"] = result["lint"]
    ss["detail_04_based_on_ver"] = ss.get("positioning_02_ver", 0)
    ss["detail_04_ver"] = ss.get("detail_04_ver", 0) + 1


def _populate_ss_from_stage_04_1(result: dict) -> None:
    ss["image_direction_04_1"] = result["raw"]
    ss["lint_04_1"] = result["lint"]
    ss["image_direction_04_1_parsed"] = result.get("parsed") or {"claude": None, "gemini": None}
    ss["image_direction_04_1_based_on_ver"] = ss.get("detail_04_ver", 0)
    ss["image_direction_04_1_ver"] = ss.get("image_direction_04_1_ver", 0) + 1


def _populate_ss_from_stage_05(result: dict) -> None:
    ss["channel_05"] = result["raw"]
    ss["lint_05"] = result["lint"]
    ss["channel_05_based_on_ver"] = ss.get("positioning_02_ver", 0)


_auto_trigger = ss.pop("_auto_trigger", None)
_auto_stages = ss.pop("_auto_stages", {"02": True, "04": True, "04_b": False, "04_1": False, "05": True})

if _auto_trigger == "recommend":
    with st.status("🚀 추천 모드 자동 실행 중…", expanded=True) as status:
        try:
            # 01
            st.write("▶ 01 결핍·타겟 실행 중…")
            r01 = auto_run_01(
                spec, storage, claude_model_01, gemini_model_01,
                lint_claude_model=lint_c_01, lint_gemini_model=lint_g_01,
            )
            _populate_ss_from_stage_01(r01)
            st.write(f"✅ 01 완료 (실행_id={r01['run_id']})")

            # 추천 타겟 추출 (claude 우선, 없으면 gemini)
            rec_target = None
            rec_basis = None
            for m in ("claude", "gemini"):
                for t in r01["parsed_with_ids"].get(m, []):
                    if t.get("is_recommended"):
                        rec_target = t
                        rec_basis = m
                        break
                if rec_target:
                    break

            if not rec_target:
                # 추천 표시가 없으면 첫 번째 타겟을 fallback으로 사용
                for m in ("claude", "gemini"):
                    if r01["parsed_with_ids"].get(m):
                        rec_target = r01["parsed_with_ids"][m][0]
                        rec_basis = m
                        st.write(f"⚠️ 추천 타겟이 표시되지 않아 #{rec_target.get('rank')} 타겟으로 진행합니다.")
                        break

            if not rec_target:
                status.update(label="❌ 자동 실행 실패 — 01에서 타겟 추출 불가", state="error")
                st.stop()

            target_db_id = rec_target["db_id"]
            target_label = rec_target.get("label") or ""
            st.write(f"⭐ 추천 타겟 자동 선택: #{rec_target.get('rank')} · {target_label}")

            # 02
            if _auto_stages.get("02"):
                st.write("▶ 02 포지셔닝 실행 중…")
                r02 = auto_run_02(
                    spec, rec_target, rec_basis, storage,
                    target_db_id, r01["run_id"],
                    claude_model_02, gemini_model_02,
                    lint_claude_model=lint_c_02, lint_gemini_model=lint_g_02,
                )
                _populate_ss_from_stage_02(r02, target_db_id, r01["run_id"])
                st.write("✅ 02 완료")

            # 04
            if _auto_stages.get("04"):
                pos_text = ""
                if ss.get("positioning_02"):
                    pos_text = ss["positioning_02"].get(rec_basis) or ""
                if not pos_text:
                    st.write("⚠️ 04 스킵 — 02 결과 없음 (02를 함께 체크하지 않은 경우)")
                else:
                    st.write("▶ 04 상세페이지 실행 중…")
                    ss["basis_04"] = rec_basis
                    r04 = auto_run_04(
                        spec, rec_target, pos_text, rec_basis, storage,
                        target_db_id, claude_model_04, gemini_model_04,
                        lint_claude_model=lint_c_04, lint_gemini_model=lint_g_04,
                    )
                    _populate_ss_from_stage_04(r04)
                    st.write("✅ 04 완료")

            # 04_b 검수 (옵션 — 토글)
            if _auto_stages.get("04_b"):
                pos_text = ""
                if ss.get("positioning_02"):
                    pos_text = ss["positioning_02"].get(rec_basis) or ""
                detail_text = ""
                if ss.get("detail_04"):
                    detail_text = ss["detail_04"].get(rec_basis) or ""
                if not detail_text:
                    st.write("⚠️ 04_b 스킵 — 04 결과 없음")
                elif not pos_text:
                    st.write("⚠️ 04_b 스킵 — 02 결과 없음")
                else:
                    st.write("▶ 04_b 검수 실행 중…")
                    r04_b = auto_run_04_b(
                        spec, rec_target, pos_text, rec_basis,
                        detail_text, rec_basis, storage,
                        target_db_id, claude_model_04, gemini_model_04,
                        lint_claude_model=lint_c_04, lint_gemini_model=lint_g_04,
                    )
                    ss["review_04_b"] = r04_b["raw"]
                    ss["review_04_b_basis"] = rec_basis
                    st.write("✅ 04_b 완료")

            # 04-1 이미지 디렉션
            if _auto_stages.get("04_1"):
                pos_text = ""
                if ss.get("positioning_02"):
                    pos_text = ss["positioning_02"].get(rec_basis) or ""
                detail_text = ""
                if ss.get("detail_04"):
                    detail_text = ss["detail_04"].get(rec_basis) or ""
                if not detail_text:
                    st.write("⚠️ 04-1 스킵 — 04 결과 없음 (04를 함께 체크하지 않았거나 04 결과가 비어있음)")
                elif not pos_text:
                    st.write("⚠️ 04-1 스킵 — 02 결과 없음")
                else:
                    st.write("▶ 04-1 이미지 디렉션 실행 중…")
                    ss["basis_04_1"] = rec_basis
                    r04_1 = auto_run_04_1(
                        spec, rec_target, pos_text, rec_basis,
                        detail_text, rec_basis, storage,
                        target_db_id, claude_model_04_1, gemini_model_04_1,
                        lint_claude_model=lint_c_04_1, lint_gemini_model=lint_g_04_1,
                    )
                    _populate_ss_from_stage_04_1(r04_1)
                    st.write("✅ 04-1 완료")

            # 05
            if _auto_stages.get("05"):
                pos_text = ""
                if ss.get("positioning_02"):
                    pos_text = ss["positioning_02"].get(rec_basis) or ""
                if not pos_text:
                    st.write("⚠️ 05 스킵 — 02 결과 없음 (02를 함께 체크하지 않은 경우)")
                else:
                    st.write("▶ 05 채널·물길 실행 중…")
                    ss["basis_05"] = rec_basis
                    r05 = auto_run_05(
                        spec, rec_target, pos_text, rec_basis, storage,
                        target_db_id, claude_model_05, gemini_model_05,
                        lint_claude_model=lint_c_05, lint_gemini_model=lint_g_05,
                    )
                    _populate_ss_from_stage_05(r05)
                    st.write("✅ 05 완료")

            status.update(label="🎉 추천 모드 자동 실행 완료", state="complete")
        except Exception as e:
            status.update(label=f"❌ 자동 실행 실패: {type(e).__name__}", state="error")
            st.error(f"{type(e).__name__}: {e}")

elif _auto_trigger == "multi":
    multi_targets: list[dict] = ss.pop("_auto_multi_targets", [])
    multi_basis: str = ss.pop("_auto_multi_basis", "claude")
    run_id = ss.get("current_run_id")

    if not run_id:
        st.error("❌ current_run_id가 없습니다. 01을 먼저 실행하세요.")
    elif not multi_targets:
        st.error("❌ 선택된 타겟이 없습니다.")
    else:
        with st.status(
            f"🚀 멀티 타겟 자동 실행 중… ({len(multi_targets)}개)",
            expanded=True,
        ) as status:
            last_target = None
            try:
                for idx, tgt in enumerate(multi_targets, 1):
                    target_db_id = tgt["db_id"]
                    target_label = tgt.get("label") or ""
                    st.write(f"━━ [{idx}/{len(multi_targets)}] #{tgt.get('rank')} · {target_label} ━━")

                    if _auto_stages.get("02"):
                        st.write("▶ 02 포지셔닝…")
                        r02 = auto_run_02(
                            spec, tgt, multi_basis, storage,
                            target_db_id, run_id,
                            claude_model_02, gemini_model_02,
                            lint_claude_model=lint_c_02, lint_gemini_model=lint_g_02,
                        )
                        _populate_ss_from_stage_02(r02, target_db_id, run_id)
                        last_pos = r02["raw"]
                        st.write("✅ 02 완료")
                    else:
                        last_pos = ss.get("positioning_02") or {}

                    last_detail: dict[str, str] = {}
                    if _auto_stages.get("04"):
                        pos_text = last_pos.get(multi_basis) or ""
                        if not pos_text:
                            st.write("⚠️ 04 스킵 — 02 결과 없음")
                        else:
                            st.write("▶ 04 상세페이지…")
                            ss["basis_04"] = multi_basis
                            r04 = auto_run_04(
                                spec, tgt, pos_text, multi_basis, storage,
                                target_db_id, claude_model_04, gemini_model_04,
                                lint_claude_model=lint_c_04, lint_gemini_model=lint_g_04,
                            )
                            _populate_ss_from_stage_04(r04)
                            last_detail = r04["raw"]
                            st.write("✅ 04 완료")
                    else:
                        last_detail = ss.get("detail_04") or {}

                    # 04_b 검수 (옵션 — 토글)
                    if _auto_stages.get("04_b"):
                        pos_text = last_pos.get(multi_basis) or ""
                        detail_text = last_detail.get(multi_basis) or ""
                        if not detail_text:
                            st.write("⚠️ 04_b 스킵 — 04 결과 없음")
                        elif not pos_text:
                            st.write("⚠️ 04_b 스킵 — 02 결과 없음")
                        else:
                            st.write("▶ 04_b 검수…")
                            r04_b = auto_run_04_b(
                                spec, tgt, pos_text, multi_basis,
                                detail_text, multi_basis, storage,
                                target_db_id, claude_model_04, gemini_model_04,
                                lint_claude_model=lint_c_04, lint_gemini_model=lint_g_04,
                            )
                            ss["review_04_b"] = r04_b["raw"]
                            ss["review_04_b_basis"] = multi_basis
                            st.write("✅ 04_b 완료")

                    if _auto_stages.get("04_1"):
                        pos_text = last_pos.get(multi_basis) or ""
                        detail_text = last_detail.get(multi_basis) or ""
                        if not detail_text:
                            st.write("⚠️ 04-1 스킵 — 04 결과 없음")
                        elif not pos_text:
                            st.write("⚠️ 04-1 스킵 — 02 결과 없음")
                        else:
                            st.write("▶ 04-1 이미지 디렉션…")
                            ss["basis_04_1"] = multi_basis
                            r04_1 = auto_run_04_1(
                                spec, tgt, pos_text, multi_basis,
                                detail_text, multi_basis, storage,
                                target_db_id, claude_model_04_1, gemini_model_04_1,
                                lint_claude_model=lint_c_04_1, lint_gemini_model=lint_g_04_1,
                            )
                            _populate_ss_from_stage_04_1(r04_1)
                            st.write("✅ 04-1 완료")

                    if _auto_stages.get("05"):
                        pos_text = last_pos.get(multi_basis) or ""
                        if not pos_text:
                            st.write("⚠️ 05 스킵 — 02 결과 없음")
                        else:
                            st.write("▶ 05 채널·물길…")
                            ss["basis_05"] = multi_basis
                            r05 = auto_run_05(
                                spec, tgt, pos_text, multi_basis, storage,
                                target_db_id, claude_model_05, gemini_model_05,
                                lint_claude_model=lint_c_05, lint_gemini_model=lint_g_05,
                            )
                            _populate_ss_from_stage_05(r05)
                            st.write("✅ 05 완료")

                    last_target = tgt

                status.update(
                    label=f"🎉 멀티 타겟 자동 실행 완료 ({len(multi_targets)}개)",
                    state="complete",
                )
                if last_target:
                    st.info(
                        f"마지막으로 처리한 타겟 **#{last_target.get('rank')} · "
                        f"{last_target.get('label', '')}**의 결과가 화면에 표시됩니다. "
                        f"다른 타겟의 결과는 아래 **타겟 선택 라디오에서 해당 타겟을 클릭**하면 "
                        f"DB에서 자동으로 로드됩니다."
                    )
            except Exception as e:
                status.update(label=f"❌ 자동 실행 실패: {type(e).__name__}", state="error")
                st.error(f"{type(e).__name__}: {e}")


# ── Step B: 01 실행 ─────────────────────────────────────
st.header("Step 1 · 01 결핍·타겟")

col_run, col_info = st.columns([1, 3])
with col_run:
    run_01 = st.button(
        _stage_action_label("01", cfg),
        type="primary",
        use_container_width=True,
        disabled=not is_owner(),
    )
with col_info:
    st.caption(caption_for_stage("01", cfg))

if run_01:
    try:
        system_prompt = load_agent_prompt("deficit_target")
        user_input = build_user_input_01(spec)
    except Exception as e:
        st.error(f"프롬프트 로드 실패: {type(e).__name__}: {e}")
        st.stop()

    with st.spinner(_stage_spinner_label("01", cfg)):
        targets_01 = generate_both(
            system_prompt, user_input,
            claude_model=claude_model_01,
            gemini_model=gemini_model_01,
        )
    ss["targets_01"] = targets_01

    if lint_c_01 or lint_g_01:
        with st.spinner("교차 린터 검수 중…"):
            ss["lint_01"] = cross_lint_both(
                "deficit_target",
                targets_01.get("claude", ""),
                targets_01.get("gemini", ""),
                claude_model=lint_c_01,
                gemini_model=lint_g_01,
            )
    else:
        ss["lint_01"] = {"claude": "", "gemini": ""}

    # 즉시 DB 저장: 새 실행 + 모든 타겟 후보 (모델별)
    try:
        run_id = storage.create_run(spec, source_product_id=spec.get("id"))
        parsed_with_ids: dict[str, list[dict]] = {"claude": [], "gemini": []}

        for model in ("claude", "gemini"):
            text = targets_01.get(model) or ""
            parsed = _extract_targets_json(text)
            if parsed and parsed.get("targets"):
                tlist = parsed["targets"]
                rec_rank = parsed.get("recommended_rank")
                ids = storage.save_targets(
                    run_id=run_id,
                    targets=tlist,
                    model=model,
                    raw_output=text,
                    recommended_rank=rec_rank,
                )
                enriched = []
                for t, db_id in zip(tlist, ids):
                    t = dict(t)
                    t["db_id"] = db_id
                    t["is_recommended"] = (
                        rec_rank is not None and t.get("rank") == rec_rank
                    )
                    enriched.append(t)
                parsed_with_ids[model] = enriched
            elif text:
                # JSON 파싱 실패해도 raw_output은 유실 안 되게 placeholder 1행 저장
                storage.save_targets(
                    run_id=run_id,
                    targets=[{
                        "rank": 1,
                        "label": f"(파싱 실패) {model}",
                        "note": "JSON 블록 누락 또는 파싱 실패 — 원본_출력 컬럼 참고",
                    }],
                    model=model,
                    raw_output=text,
                    recommended_rank=None,
                )
                parsed_with_ids[model] = []

        ss["parsed_with_ids"] = parsed_with_ids
        ss["current_run_id"] = run_id
        ss["_run_loaded"] = run_id
        for k in ("positioning_02", "saved_run_id", "selected_target_db_id",
                  "detail_04", "channel_05",
                  "lint_02", "lint_04", "lint_05",
                  "positioning_02_ver",
                  "detail_04_ver", "channel_05_ver",
                  "detail_04_based_on_ver", "channel_05_based_on_ver",
                  "_sec_regen_02", "_sec_regen_04", "_sec_regen_05"):
            ss.pop(k, None)
        st.success(f"01 저장 완료 (실행_id={run_id})")
    except Exception as e:
        st.error(f"01 DB 저장 실패: {type(e).__name__}: {e}")

targets_01 = ss.get("targets_01")
lint_01 = ss.get("lint_01") or {}
if targets_01:
    st.markdown("**01 결과 비교**")
    md_c, json_c = _split_json_block(targets_01.get("claude") or "")
    md_g, json_g = _split_json_block(targets_01.get("gemini") or "")
    lint_text_c = lint_01.get("claude") or ""
    lint_text_g = lint_01.get("gemini") or ""
    lint_c = parse_lint_status(lint_text_c) if lint_text_c else None
    lint_g = parse_lint_status(lint_text_g) if lint_text_g else None
    _compare_off_caption(claude_model_01, gemini_model_01)
    cc, gc = _result_layout(claude_model_01, gemini_model_01)
    if cc is not None:
        with cc:
            st.markdown(_model_header(
                "🟠 Claude", claude_model_01, lint_c,
                lint_enabled=lint_enabled_for_stage("01", cfg),
            ))
            st.markdown(md_c or "_(empty)_")
            if lint_text_c:
                with st.expander(
                    f"🔍 {_lint_reviewer_label('claude')} 린터 검수",
                    expanded=lint_c[0] in ("FAIL", "WARN") if lint_c else False,
                ):
                    st.markdown(lint_text_c)
            if json_c:
                with st.expander("🔧 JSON 블록 (디버그)", expanded=False):
                    st.code(json_c, language="json")
    if gc is not None:
        with gc:
            st.markdown(_model_header(
                "🔵 Gemini", gemini_model_01, lint_g,
                lint_enabled=lint_enabled_for_stage("01", cfg),
            ))
            st.markdown(md_g or "_(empty)_")
            if lint_text_g:
                with st.expander(
                    f"🔍 {_lint_reviewer_label('gemini')} 린터 검수",
                    expanded=lint_g[0] in ("FAIL", "WARN") if lint_g else False,
                ):
                    st.markdown(lint_text_g)
            if json_g:
                with st.expander("🔧 JSON 블록 (디버그)", expanded=False):
                    st.code(json_g, language="json")

# ── Step C: 타겟 선택 + Step D: 02 실행 ─────────────────
if targets_01:
    st.divider()
    st.header("Step 2 · 타겟 확정 + 02 포지셔닝")

    available_bases_01 = [
        m for m in ("claude", "gemini")
        if (targets_01.get(m) or "").strip()
    ]
    if len(available_bases_01) >= 2:
        basis = st.radio(
            "02의 기준이 될 01 결과",
            options=available_bases_01,
            horizontal=True,
            format_func=lambda x: {"claude": "🟠 Claude", "gemini": "🔵 Gemini"}[x],
        )
    elif available_bases_01:
        basis = available_bases_01[0]
    else:
        basis = "claude"

    parsed_with_ids = ss.get("parsed_with_ids") or {}
    targets_list: list[dict] = parsed_with_ids.get(basis) or []

    target_label = ""
    target_text = ""
    target_rank = 1
    selected_db_id: int | None = None

    if targets_list:
        rec_rank = next(
            (t.get("rank") for t in targets_list if t.get("is_recommended")),
            None,
        )
        if rec_rank:
            st.info(f"⭐ **추천 타겟 #{rec_rank}**")

        ranks = [t.get("rank") for t in targets_list if t.get("rank") is not None]

        # 기본 선택: 이전에 선택했던 타겟 → 추천 타겟 → 첫 번째
        default_idx = 0
        prev_id = ss.get("selected_target_db_id")
        if prev_id:
            for i, t in enumerate(targets_list):
                if t.get("db_id") == prev_id:
                    default_idx = i
                    break
        elif rec_rank in ranks:
            default_idx = ranks.index(rec_rank)

        # 타겟별 작업 이력 bulk 조회 (라디오 라벨에 "완료: 02 포지셔닝, ..." 표시용)
        _STAGE_LABELS_FULL = {
            "02": "02 포지셔닝",
            "03": "03 제품명 (네이밍)",
            "04": "04 상세페이지",
            "05": "05 채널",
        }
        _all_target_ids = [
            t["db_id"] for t in targets_list
            if t.get("db_id") is not None
        ]
        try:
            _results_summary = storage.get_result_summary_for_targets(_all_target_ids)
        except Exception:
            _results_summary = {}

        def _fmt(rank):
            t = next((x for x in targets_list if x.get("rank") == rank), None)
            if not t:
                return f"#{rank}"
            star = "⭐ " if t.get("is_recommended") else ""
            base = f"{star}#{rank} · {t.get('label', '(라벨 없음)')}"
            stages = _results_summary.get(t.get("db_id")) or set()
            if stages:
                ordered = [
                    _STAGE_LABELS_FULL[s]
                    for s in ("02", "03", "04", "05")
                    if s in stages
                ]
                if ordered:
                    return f"{base}    ✅ {', '.join(ordered)}"
            return base

        selected_rank = st.radio(
            "타겟 선택",
            options=ranks,
            format_func=_fmt,
            index=default_idx,
            horizontal=False,
        )
        selected = next(
            (x for x in targets_list if x.get("rank") == selected_rank),
            None,
        )

        if selected:
            with st.container(border=True):
                st.markdown(
                    f"**선택된 타겟 #{selected.get('rank')}** · "
                    f"{selected.get('label', '')}"
                )
                if selected.get("character"):
                    st.caption(f"📋 {selected['character']}")
                cols = st.columns(2)
                with cols[0]:
                    if selected.get("deficit"):
                        st.markdown(f"- **핵심 결핍**: {selected['deficit']}")
                    if selected.get("deficit_source"):
                        st.markdown(f"- **결핍 원천**: {selected['deficit_source']}")
                    if selected.get("benefit_type"):
                        st.markdown(f"- **구매편익**: {selected['benefit_type']}")
                    if selected.get("involvement") not in (None, ""):
                        st.markdown(f"- **관여도**: {selected['involvement']}")
                with cols[1]:
                    if selected.get("channel"):
                        st.markdown(f"- **주요 채널**: {selected['channel']}")
                    if selected.get("buyer_user_split"):
                        st.markdown(f"- **구매자≠이용자**: {selected['buyer_user_split']}")
                    if selected.get("wants_3tier"):
                        st.markdown(f"- **욕구깡패**: {selected['wants_3tier']}")
                if selected.get("note"):
                    st.caption(f"💡 {selected['note']}")

            target_label = (selected.get("label") or "").strip()
            target_text = _build_target_description(selected)
            target_rank = selected.get("rank") or 1
            selected_db_id = selected.get("db_id")

            # 타겟 변경 감지 → 그 타겟의 기존 02/04/05 결과를 DB에서 자동 로드.
            # 멀티 타겟 자동 모드 후 다른 타겟의 결과를 보려면 이 경로가 필요.
            if (
                selected_db_id
                and ss.get("selected_target_db_id") != selected_db_id
            ):
                pos_rows = storage.get_positioning(selected_db_id)
                pos_loaded: dict[str, str] = {"claude": "", "gemini": ""}
                for prow in pos_rows:
                    m = prow.get("모델")
                    if m in pos_loaded:
                        pos_loaded[m] = prow.get("원본_출력") or ""

                detail_rows = storage.get_상세페이지(selected_db_id)
                detail_loaded: dict[str, str] = {"claude": "", "gemini": ""}
                for d in detail_rows:
                    m = d.get("모델")
                    if m in detail_loaded:
                        detail_loaded[m] = d.get("원본_출력") or ""

                channel_rows = storage.get_채널(selected_db_id)
                channel_loaded: dict[str, str] = {"claude": "", "gemini": ""}
                for c in channel_rows:
                    m = c.get("모델")
                    if m in channel_loaded:
                        channel_loaded[m] = c.get("원본_출력") or ""

                if any(pos_loaded.values()):
                    ss["positioning_02"] = pos_loaded
                    ss["positioning_02_ver"] = ss.get("positioning_02_ver", 0) + 1
                else:
                    ss.pop("positioning_02", None)

                if any(detail_loaded.values()):
                    ss["detail_04"] = detail_loaded
                    ss["detail_04_based_on_ver"] = ss.get("positioning_02_ver", 0)
                else:
                    ss.pop("detail_04", None)

                if any(channel_loaded.values()):
                    ss["channel_05"] = channel_loaded
                    ss["channel_05_based_on_ver"] = ss.get("positioning_02_ver", 0)
                else:
                    ss.pop("channel_05", None)

                # 이전 타겟 린터 결과는 무효 — 헤더가 ✗로 표시되도록 비움
                for k in ("lint_02", "lint_04", "lint_05"):
                    ss.pop(k, None)

                ss["selected_target_db_id"] = selected_db_id
                ss["saved_run_id"] = ss.get("current_run_id")
                st.rerun()
    else:
        st.warning(
            "⚠️ 01 결과에 타겟 카드를 만들 수 없습니다 (JSON 블록 없음). 수동 입력으로 진행하세요."
        )
        with st.container(border=True):
            target_label = st.text_input(
                "타겟 라벨 (한 줄 요약)",
                placeholder="예: 32세 1인 자취 여성, 층간소음 스트레스",
            )
            target_text = st.text_area(
                "타겟 내용",
                height=200,
                placeholder="직업+나이+상황 / 핵심 결핍 / 결핍 원천 / 구매편익 / 관여도 / 채널 / 비고 / 욕구깡패 3차…",
            )

    st.caption(caption_for_stage("02", cfg))
    run_02 = st.button(
        _stage_action_label("02", cfg),
        type="primary",
        use_container_width=True,
        disabled=not is_owner() or not (target_label.strip() and target_text.strip()),
    )

    if run_02:
        try:
            system_prompt = load_agent_prompt("positioning")
            target_dict = {
                "source_model": basis,
                "label": target_label.strip(),
                "description": target_text.strip(),
            }
            user_input = build_user_input_02(spec, target_dict)
        except Exception as e:
            st.error(f"프롬프트 로드 실패: {type(e).__name__}: {e}")
            st.stop()

        with st.spinner(_stage_spinner_label("02", cfg)):
            positioning_02 = generate_both(
                system_prompt, user_input,
                claude_model=claude_model_02,
                gemini_model=gemini_model_02,
            )
        ss["positioning_02"] = positioning_02
        # 02 갱신: 이전 04/05는 보존하되 버전 카운터로 stale 표시.
        # 04/05 결과 영역에서 based_on_ver 비교로 ⚠️ 배지 + 재생성 안내.
        ss["positioning_02_ver"] = ss.get("positioning_02_ver", 0) + 1

        if lint_c_02 or lint_g_02:
            with st.spinner("교차 린터 검수 중…"):
                ss["lint_02"] = cross_lint_both(
                    "positioning",
                    positioning_02.get("claude", ""),
                    positioning_02.get("gemini", ""),
                    claude_model=lint_c_02,
                    gemini_model=lint_g_02,
                )
        else:
            ss["lint_02"] = {"claude": "", "gemini": ""}

        try:
            run_id = ss.get("current_run_id")
            if not run_id:
                # 01 거치지 않은 비정상 경로 — 새 run 생성
                run_id = storage.create_run(spec, source_product_id=spec.get("id"))
                ss["current_run_id"] = run_id

            # fallback (수동 입력) 또는 db_id 누락 → 새 target row 추가
            if selected_db_id is None:
                new_ids = storage.save_targets(
                    run_id=run_id,
                    targets=[{
                        "rank": target_rank,
                        "label": target_label.strip(),
                        "note": target_text.strip(),
                    }],
                    model=basis,
                    raw_output=targets_01.get(basis, ""),
                )
                selected_db_id = new_ids[0]

            storage.clear_selected_in_run(run_id)
            storage.mark_target_selected(selected_db_id, True)
            ss["selected_target_db_id"] = selected_db_id

            for m in ("claude", "gemini"):
                text_02 = positioning_02.get(m, "") or ""
                pos_parsed = _extract_positioning_json(text_02) or {}
                storage.save_positioning(
                    target_id=selected_db_id,
                    model=m,
                    raw_output=text_02,
                    category_objections=pos_parsed.get("category_objections"),
                    rule_engine_inputs=pos_parsed.get("rule_engine_inputs"),
                    rule_engine_flags=pos_parsed.get("rule_engine_flags"),
                    persuasion_method_candidates=pos_parsed.get("persuasion_method_candidates"),
                )
            ss["saved_run_id"] = run_id
            st.success(
                f"02 저장 완료 (실행_id={run_id}, 타겟_id={selected_db_id})"
            )
        except Exception as e:
            st.error(f"02 DB 저장 실패: {type(e).__name__}: {e}")

positioning_02 = ss.get("positioning_02")
lint_02 = ss.get("lint_02") or {}
if positioning_02:
    # ── 섹션 재생성 트리거 처리 (이전 사이클 _section_edit_ui 버튼) ──
    sec_payload = ss.pop("_sec_regen_02", None)
    if sec_payload:
        sel_target = _find_selected_target_dict(ss.get("selected_target_db_id"))
        if sel_target:
            target_dict = {
                "source_model": sec_payload["builder"],
                "label": sel_target.get("label") or "",
                "description": _build_target_description(sel_target),
            }
            base_input = build_user_input_02(spec, target_dict)
            full_old = positioning_02.get(sec_payload["builder"], "")
            with st.spinner(
                f"섹션 재생성 중… ({sec_payload['builder']} / "
                f"{sec_payload['section_header']})"
            ):
                try:
                    new_section = regenerate_section(
                        agent="positioning",
                        base_user_input=base_input,
                        full_text=full_old,
                        section_header=sec_payload["section_header"],
                        user_feedback=sec_payload["feedback"],
                        builder_model=sec_payload["builder"],
                        model_id=model_for_family(sec_payload["builder"], "02", cfg),
                    )
                    merged = replace_section(
                        full_old,
                        sec_payload["section_index"],
                        new_section,
                    )
                    new_pos = dict(positioning_02)
                    new_pos[sec_payload["builder"]] = merged
                    ss["positioning_02"] = new_pos
                    positioning_02 = new_pos  # 아래 표시 영역도 갱신본 사용
                    ss["positioning_02_ver"] = ss.get("positioning_02_ver", 0) + 1

                    tid = ss.get("selected_target_db_id")
                    if tid:
                        pos_parsed = _extract_positioning_json(merged) or {}
                        storage.save_positioning(
                            target_id=tid,
                            model=sec_payload["builder"],
                            raw_output=merged,
                            category_objections=pos_parsed.get("category_objections"),
                            rule_engine_inputs=pos_parsed.get("rule_engine_inputs"),
                            rule_engine_flags=pos_parsed.get("rule_engine_flags"),
                            persuasion_method_candidates=pos_parsed.get("persuasion_method_candidates"),
                        )
                    # 린터 캐시 무효화 — 헤더 ✗로 표시되어 재검수 필요 신호
                    ss.pop("lint_02", None)
                    lint_02 = {}
                    st.success(
                        f"✅ 섹션 재생성 완료: {sec_payload['section_header']} "
                        f"({sec_payload['builder']})"
                    )
                except Exception as e:
                    st.error(f"섹션 재생성 실패: {type(e).__name__}: {e}")
        else:
            st.error("선택된 타겟 정보를 찾을 수 없습니다. 02 통째 재실행이 필요합니다.")

    st.markdown("**02 결과 비교**")
    lint_text_c2 = lint_02.get("claude") or ""
    lint_text_g2 = lint_02.get("gemini") or ""
    lint_c2 = parse_lint_status(lint_text_c2) if lint_text_c2 else None
    lint_g2 = parse_lint_status(lint_text_g2) if lint_text_g2 else None
    _compare_off_caption(claude_model_02, gemini_model_02)
    cc2, gc2 = _result_layout(claude_model_02, gemini_model_02)
    if cc2 is not None:
        with cc2:
            st.markdown(_model_header(
                "🟠 Claude", claude_model_02, lint_c2,
                lint_enabled=lint_enabled_for_stage("02", cfg),
            ))
            st.markdown(positioning_02.get("claude") or "_(empty)_")
            if lint_text_c2:
                with st.expander(
                    f"🔍 {_lint_reviewer_label('claude')} 린터 검수",
                    expanded=lint_c2[0] in ("FAIL", "WARN") if lint_c2 else False,
                ):
                    st.markdown(lint_text_c2)
            _section_edit_ui(
                "claude", "Claude",
                positioning_02.get("claude") or "",
                "_sec_regen_02",
            )
            _version_history_ui("02", "claude", ss.get("selected_target_db_id"))
    if gc2 is not None:
        with gc2:
            st.markdown(_model_header(
                "🔵 Gemini", gemini_model_02, lint_g2,
                lint_enabled=lint_enabled_for_stage("02", cfg),
            ))
            st.markdown(positioning_02.get("gemini") or "_(empty)_")
            if lint_text_g2:
                with st.expander(
                    f"🔍 {_lint_reviewer_label('gemini')} 린터 검수",
                    expanded=lint_g2[0] in ("FAIL", "WARN") if lint_g2 else False,
                ):
                    st.markdown(lint_text_g2)
            _section_edit_ui(
                "gemini", "Gemini",
                positioning_02.get("gemini") or "",
                "_sec_regen_02",
            )
            _version_history_ui("02", "gemini", ss.get("selected_target_db_id"))

    if ss.get("saved_run_id"):
        st.info(
            f"이 실행은 Supabase에 실행_id=**{ss['saved_run_id']}** 로 저장되었습니다."
        )

# ── Step 3: 04 상세페이지 ───────────────────────────────────
if positioning_02 and ss.get("selected_target_db_id"):
    st.divider()
    st.header("Step 3 · 04 상세페이지")

    available_bases_02 = [
        m for m in ("claude", "gemini")
        if (positioning_02.get(m) or "").strip()
    ]
    if len(available_bases_02) >= 2:
        detail_basis = st.radio(
            "04 입력으로 쓸 02 결과",
            options=available_bases_02,
            horizontal=True,
            format_func=lambda x: {"claude": "🟠 Claude", "gemini": "🔵 Gemini"}[x],
            key="basis_04",
        )
    elif available_bases_02:
        detail_basis = available_bases_02[0]
    else:
        detail_basis = "claude"

    st.caption(caption_for_stage("04", cfg))
    pos_text_for_04 = positioning_02.get(detail_basis) or ""
    run_04 = st.button(
        _stage_action_label("04", cfg),
        type="primary",
        use_container_width=True,
        disabled=not is_owner() or not pos_text_for_04.strip(),
        key="run_04",
    )
    # 04 결과 영역의 "🔄 재생성" 버튼이 누른 트리거도 같이 받는다.
    if ss.pop("_restage_04", False):
        run_04 = True

    if run_04:
        sel_target = _find_selected_target_dict(ss["selected_target_db_id"])
        if not sel_target:
            st.error("선택된 타겟 정보를 찾을 수 없습니다. 02부터 다시 실행하세요.")
            st.stop()

        target_dict = {
            "label": sel_target.get("label") or "",
            "description": _build_target_description(sel_target),
        }
        try:
            system_prompt = load_agent_prompt("detail_page")
            user_input = build_user_input_04(
                spec, target_dict, pos_text_for_04, detail_basis,
            )
        except Exception as e:
            st.error(f"프롬프트 로드 실패: {type(e).__name__}: {e}")
            st.stop()

        with st.spinner(_stage_spinner_label("04", cfg)):
            detail_04 = generate_both(
                system_prompt, user_input,
                claude_model=claude_model_04,
                gemini_model=gemini_model_04,
            )
        ss["detail_04"] = detail_04
        ss["detail_04_based_on_ver"] = ss.get("positioning_02_ver", 0)

        if lint_c_04 or lint_g_04:
            with st.spinner("교차 린터 검수 중…"):
                ss["lint_04"] = cross_lint_both(
                    "detail_page",
                    detail_04.get("claude", ""),
                    detail_04.get("gemini", ""),
                    claude_model=lint_c_04,
                    gemini_model=lint_g_04,
                )
        else:
            ss["lint_04"] = {"claude": "", "gemini": ""}

        try:
            tid = ss["selected_target_db_id"]
            for m in ("claude", "gemini"):
                text_04 = detail_04.get(m, "") or ""
                plan_parsed = _extract_engine_plan(text_04) or {}
                storage.save_상세페이지(
                    target_id=tid, model=m,
                    raw_output=text_04,
                    engine_plan=plan_parsed or None,
                    한_축_사슬=plan_parsed.get("한_축_사슬"),
                    설득_방식_주=plan_parsed.get("설득_방식_주"),
                    설득_방식_보조=plan_parsed.get("설득_방식_보조"),
                )
            st.success(f"04 저장 완료 (타겟_id={tid})")
        except Exception as e:
            st.error(f"04 DB 저장 실패: {type(e).__name__}: {e}")

detail_04 = ss.get("detail_04")
lint_04 = ss.get("lint_04") or {}
if detail_04:
    # ── 섹션 재생성 트리거 처리 (이전 사이클 _section_edit_ui 버튼) ──
    sec_payload_04 = ss.pop("_sec_regen_04", None)
    if sec_payload_04:
        sel_target = _find_selected_target_dict(ss.get("selected_target_db_id"))
        if sel_target:
            target_dict = {
                "label": sel_target.get("label") or "",
                "description": _build_target_description(sel_target),
            }
            basis_for_04 = ss.get("basis_04") or "claude"
            pos_text_for_04 = positioning_02.get(basis_for_04) or ""
            base_input = build_user_input_04(
                spec, target_dict, pos_text_for_04, basis_for_04,
            )
            full_old = detail_04.get(sec_payload_04["builder"], "")
            with st.spinner(
                f"섹션 재생성 중… ({sec_payload_04['builder']} / "
                f"{sec_payload_04['section_header']})"
            ):
                try:
                    new_section = regenerate_section(
                        agent="detail_page",
                        base_user_input=base_input,
                        full_text=full_old,
                        section_header=sec_payload_04["section_header"],
                        user_feedback=sec_payload_04["feedback"],
                        builder_model=sec_payload_04["builder"],
                        model_id=model_for_family(sec_payload_04["builder"], "04", cfg),
                    )
                    merged = replace_section(
                        full_old,
                        sec_payload_04["section_index"],
                        new_section,
                    )
                    new_d = dict(detail_04)
                    new_d[sec_payload_04["builder"]] = merged
                    ss["detail_04"] = new_d
                    detail_04 = new_d
                    ss["detail_04_ver"] = ss.get("detail_04_ver", 0) + 1

                    tid = ss.get("selected_target_db_id")
                    if tid:
                        plan_parsed = _extract_engine_plan(merged) or {}
                        storage.save_상세페이지(
                            target_id=tid,
                            model=sec_payload_04["builder"],
                            raw_output=merged,
                            engine_plan=plan_parsed or None,
                            한_축_사슬=plan_parsed.get("한_축_사슬"),
                            설득_방식_주=plan_parsed.get("설득_방식_주"),
                            설득_방식_보조=plan_parsed.get("설득_방식_보조"),
                        )
                    ss.pop("lint_04", None)
                    lint_04 = {}
                    st.success(
                        f"✅ 섹션 재생성 완료: {sec_payload_04['section_header']} "
                        f"({sec_payload_04['builder']})"
                    )
                except Exception as e:
                    st.error(f"섹션 재생성 실패: {type(e).__name__}: {e}")
        else:
            st.error("선택된 타겟 정보를 찾을 수 없습니다. 04 통째 재실행이 필요합니다.")

    is_stale_04 = (
        ss.get("detail_04_based_on_ver", 0) != ss.get("positioning_02_ver", 0)
    )
    if is_stale_04:
        col_w, col_b = st.columns([4, 1])
        with col_w:
            st.warning("⚠️ 이 04 결과는 **이전 02 기반**입니다. 02가 갱신되었으니 재생성을 권장합니다.")
        with col_b:
            if st.button("🔄 04 재생성", key="restage_04", use_container_width=True):
                ss["_restage_04"] = True
                st.rerun()
    st.markdown("**04 결과 비교**")
    lint_text_c4 = lint_04.get("claude") or ""
    lint_text_g4 = lint_04.get("gemini") or ""
    lint_c4 = parse_lint_status(lint_text_c4) if lint_text_c4 else None
    lint_g4 = parse_lint_status(lint_text_g4) if lint_text_g4 else None
    _compare_off_caption(claude_model_04, gemini_model_04)
    cc4, gc4 = _result_layout(claude_model_04, gemini_model_04)
    if cc4 is not None:
        with cc4:
            st.markdown(_model_header(
                "🟠 Claude", claude_model_04, lint_c4,
                lint_enabled=lint_enabled_for_stage("04", cfg),
            ))
            st.markdown(detail_04.get("claude") or "_(empty)_")
            if lint_text_c4:
                with st.expander(
                    f"🔍 {_lint_reviewer_label('claude')} 린터 검수",
                    expanded=lint_c4[0] in ("FAIL", "WARN") if lint_c4 else False,
                ):
                    st.markdown(lint_text_c4)
            _section_edit_ui(
                "claude", "Claude",
                detail_04.get("claude") or "",
                "_sec_regen_04",
                marker_style="bracket",
            )
            _version_history_ui("04", "claude", ss.get("selected_target_db_id"))
    if gc4 is not None:
        with gc4:
            st.markdown(_model_header(
                "🔵 Gemini", gemini_model_04, lint_g4,
                lint_enabled=lint_enabled_for_stage("04", cfg),
            ))
            st.markdown(detail_04.get("gemini") or "_(empty)_")
            if lint_text_g4:
                with st.expander(
                    f"🔍 {_lint_reviewer_label('gemini')} 린터 검수",
                    expanded=lint_g4[0] in ("FAIL", "WARN") if lint_g4 else False,
                ):
                    st.markdown(lint_text_g4)
            _section_edit_ui(
                "gemini", "Gemini",
                detail_04.get("gemini") or "",
                "_sec_regen_04",
                marker_style="bracket",
            )
            _version_history_ui("04", "gemini", ss.get("selected_target_db_id"))

# ── Step 3-B: 04_b 검수 (옵션 3 — 선택적 토글) ─────────────
# 04_a 콘티를 풀세트·ENGINE_PLAN 기준으로 검수. 항상 거치지 않고 필요할 때만 호출.
# 옵션 1 (자동 단계화)로 전환하려면 04_a 직후 자동 호출하도록 변경하면 됨.
detail_04 = ss.get("detail_04")
if (
    positioning_02
    and ss.get("selected_target_db_id")
    and detail_04
    and any((detail_04.get(m) or "").strip() for m in ("claude", "gemini"))
):
    st.divider()
    st.header("Step 3-B · 04_b 검수 (선택)")
    st.caption(
        "04_a 콘티를 풀세트·ENGINE_PLAN 기준으로 검수합니다. "
        "결과는 검수 보고서 + 다듬은 콘티 두 블록으로 저장됩니다. "
        "선택적 단계 — 콘티 퀄리티가 걱정될 때만 실행하세요."
    )

    # 04_b는 04와 같은 모델·basis를 재사용 (옵션 3 단순화)
    available_bases_04b = [
        m for m in ("claude", "gemini")
        if (detail_04.get(m) or "").strip()
    ]
    if len(available_bases_04b) >= 2:
        review_basis = st.radio(
            "04_b 입력으로 쓸 04_a 콘티",
            options=available_bases_04b,
            horizontal=True,
            format_func=lambda x: {"claude": "🟠 Claude", "gemini": "🔵 Gemini"}[x],
            key="basis_04_b",
        )
    elif available_bases_04b:
        review_basis = available_bases_04b[0]
    else:
        review_basis = "claude"

    detail_text_for_04_b = detail_04.get(review_basis) or ""
    pos_text_for_04_b = (positioning_02 or {}).get(review_basis) or ""

    run_04_b = st.button(
        "🔍 04_b 검수 실행",
        type="primary",
        use_container_width=True,
        disabled=not is_owner() or not detail_text_for_04_b.strip(),
        key="run_04_b",
    )

    if run_04_b:
        sel_target = _find_selected_target_dict(ss["selected_target_db_id"])
        if not sel_target:
            st.error("선택된 타겟 정보를 찾을 수 없습니다. 02부터 다시 실행하세요.")
            st.stop()

        target_dict = {
            "label": sel_target.get("label") or "",
            "description": _build_target_description(sel_target),
        }
        try:
            system_prompt = load_agent_prompt("detail_review")
            user_input = build_user_input_04_b(
                spec, target_dict, pos_text_for_04_b, detail_text_for_04_b,
                positioning_basis=review_basis,
                detail_basis=review_basis,
            )
        except Exception as e:
            st.error(f"프롬프트 로드 실패: {type(e).__name__}: {e}")
            st.stop()

        with st.spinner("04_b 검수 중…"):
            review_04_b = generate_both(
                system_prompt, user_input,
                claude_model=claude_model_04,
                gemini_model=gemini_model_04,
                max_tokens=16384,
            )
        ss["review_04_b"] = review_04_b
        ss["review_04_b_basis"] = review_basis

        # DB 저장 (04_a 행 id를 FK로)
        try:
            tid = ss["selected_target_db_id"]
            detail_rows = storage.get_상세페이지(tid)
            detail_id_map: dict[str, int | None] = {"claude": None, "gemini": None}
            for row in detail_rows:
                m = row.get("모델")
                if m in detail_id_map and detail_id_map[m] is None:
                    detail_id_map[m] = row.get("id")

            saved_count = 0
            for m in ("claude", "gemini"):
                text = review_04_b.get(m, "") or ""
                if not text:
                    continue  # 호출 안 된 모델은 행 저장 X (옵션 3 정책)
                did = detail_id_map.get(m)
                if did is None:
                    st.warning(f"{m}: 04_a 결과가 DB에 없어 04_b 저장 건너뜀")
                    continue
                report, refined = _extract_review_blocks(text)
                storage.save_상세페이지_검수(
                    detail_id=did,
                    model=m,
                    raw_output=text,
                    검수_보고서=report,
                    다듬은_콘티=refined,
                )
                saved_count += 1
            if saved_count > 0:
                st.success(f"04_b 저장 완료 ({saved_count}개 모델)")
        except Exception as e:
            st.error(f"04_b DB 저장 실패: {type(e).__name__}: {e}")

review_04_b = ss.get("review_04_b")
if review_04_b:
    st.markdown("**04_b 검수 결과**")
    cc4b, gc4b = _result_layout(claude_model_04, gemini_model_04)

    def _render_review_panel(text: str, model_label: str):
        if not text:
            st.caption(f"_({model_label} 호출 안 됨)_")
            return
        report, refined = _extract_review_blocks(text)
        if report:
            with st.expander("📋 검수 보고서", expanded=True):
                st.markdown(report)
        if refined:
            with st.expander("✨ 다듬은 콘티", expanded=False):
                st.markdown(refined)
        if not report and not refined:
            st.warning("⚠️ 블록 마커(`---REVIEW_REPORT---` / `---REFINED_DRAFT---`) 누락 — 원본 출력 그대로 표시")
            st.markdown(text)

    if cc4b is not None:
        with cc4b:
            st.markdown(_model_header(
                "🟠 Claude", claude_model_04, None,
                lint_enabled=False,
            ))
            _render_review_panel(review_04_b.get("claude") or "", "claude")
    if gc4b is not None:
        with gc4b:
            st.markdown(_model_header(
                "🔵 Gemini", gemini_model_04, None,
                lint_enabled=False,
            ))
            _render_review_panel(review_04_b.get("gemini") or "", "gemini")

# ── Step 3-1: 04-1 이미지 디렉션 ───────────────────────────
detail_04 = ss.get("detail_04")
if (
    positioning_02
    and ss.get("selected_target_db_id")
    and detail_04
    and any((detail_04.get(m) or "").strip() for m in ("claude", "gemini"))
):
    st.divider()
    st.header("Step 3-1 · 04-1 이미지 디렉션")
    st.caption(
        "콘티(04)의 각 섹션을 이미지 1장 단위 확정 디렉션으로 변환합니다. "
        "각 섹션마다 GPT Images 2.0에 바로 복붙할 수 있는 영문 프롬프트가 생성됩니다."
    )

    available_bases_04 = [
        m for m in ("claude", "gemini")
        if (detail_04.get(m) or "").strip()
    ]
    if len(available_bases_04) >= 2:
        direction_basis = st.radio(
            "04-1 입력으로 쓸 04 콘티",
            options=available_bases_04,
            horizontal=True,
            format_func=lambda x: {"claude": "🟠 Claude", "gemini": "🔵 Gemini"}[x],
            key="basis_04_1",
        )
    elif available_bases_04:
        direction_basis = available_bases_04[0]
    else:
        direction_basis = "claude"

    st.caption(caption_for_stage("04_1", cfg))
    detail_text_for_04_1 = detail_04.get(direction_basis) or ""
    pos_text_for_04_1 = (positioning_02 or {}).get(direction_basis) or ""

    run_04_1 = st.button(
        _stage_action_label("04_1", cfg),
        type="primary",
        use_container_width=True,
        disabled=not is_owner() or not detail_text_for_04_1.strip(),
        key="run_04_1",
    )
    if ss.pop("_restage_04_1", False):
        run_04_1 = True

    if run_04_1:
        sel_target = _find_selected_target_dict(ss["selected_target_db_id"])
        if not sel_target:
            st.error("선택된 타겟 정보를 찾을 수 없습니다. 02부터 다시 실행하세요.")
            st.stop()

        target_dict = {
            "label": sel_target.get("label") or "",
            "description": _build_target_description(sel_target),
        }
        try:
            system_prompt = load_agent_prompt("image_direction")
            user_input = build_user_input_04_1(
                spec, target_dict, pos_text_for_04_1, detail_text_for_04_1,
                positioning_basis=direction_basis,
                detail_basis=direction_basis,
            )
        except Exception as e:
            st.error(f"프롬프트 로드 실패: {type(e).__name__}: {e}")
            st.stop()

        with st.spinner(_stage_spinner_label("04_1", cfg)):
            image_direction_04_1 = generate_both(
                system_prompt, user_input,
                claude_model=claude_model_04_1,
                gemini_model=gemini_model_04_1,
                max_tokens=16384,
            )
        ss["image_direction_04_1"] = image_direction_04_1
        ss["image_direction_04_1_based_on_ver"] = ss.get("detail_04_ver", 0)
        ss["image_direction_04_1_ver"] = ss.get("image_direction_04_1_ver", 0) + 1

        # 파싱 + 저장
        parsed_per_model: dict[str, dict | None] = {"claude": None, "gemini": None}
        for m in ("claude", "gemini"):
            text = image_direction_04_1.get(m, "") or ""
            parsed = _extract_sections_json(text)
            parsed_per_model[m] = parsed
            sections = (parsed or {}).get("sections")
            ds = (parsed or {}).get("design_system")
            sm = (parsed or {}).get("selection_method")
            try:
                storage.save_이미지디렉션(
                    target_id=ss["selected_target_db_id"],
                    model=m,
                    raw_output=text,
                    sections=sections if isinstance(sections, list) else None,
                    design_system=ds if isinstance(ds, dict) else None,
                    selection_method=sm if isinstance(sm, str) else None,
                )
            except Exception as e:
                st.error(f"04-1 DB 저장 실패 ({m}): {type(e).__name__}: {e}")
        ss["image_direction_04_1_parsed"] = parsed_per_model

        if lint_c_04_1 or lint_g_04_1:
            with st.spinner("교차 린터 검수 중…"):
                ss["lint_04_1"] = cross_lint_both(
                    "image_direction",
                    image_direction_04_1.get("claude", ""),
                    image_direction_04_1.get("gemini", ""),
                    claude_model=lint_c_04_1,
                    gemini_model=lint_g_04_1,
                )
        else:
            ss["lint_04_1"] = {"claude": "", "gemini": ""}

        st.success(f"04-1 저장 완료 (타겟_id={ss['selected_target_db_id']})")

image_direction_04_1 = ss.get("image_direction_04_1")
lint_04_1 = ss.get("lint_04_1") or {}
image_direction_parsed = ss.get("image_direction_04_1_parsed") or {}

if image_direction_04_1 and any(image_direction_04_1.values()):
    is_stale_04_1 = (
        ss.get("image_direction_04_1_based_on_ver", 0)
        != ss.get("detail_04_ver", 0)
    )
    if is_stale_04_1 and ss.get("detail_04_ver", 0) > 0:
        col_w, col_b = st.columns([4, 1])
        with col_w:
            st.warning("⚠️ 이 04-1 결과는 **이전 04 콘티 기반**입니다. 04가 갱신되었으니 재생성을 권장합니다.")
        with col_b:
            if st.button("🔄 04-1 재생성", key="restage_04_1", use_container_width=True):
                ss["_restage_04_1"] = True
                st.rerun()

    st.markdown("**04-1 결과 비교**")
    lint_text_c41 = lint_04_1.get("claude") or ""
    lint_text_g41 = lint_04_1.get("gemini") or ""
    lint_c41 = parse_lint_status(lint_text_c41) if lint_text_c41 else None
    lint_g41 = parse_lint_status(lint_text_g41) if lint_text_g41 else None
    _compare_off_caption(claude_model_04_1, gemini_model_04_1)
    cc41, gc41 = _result_layout(claude_model_04_1, gemini_model_04_1)

    def _strip_json_block(text: str) -> str:
        """---SECTIONS_JSON---...---END_SECTIONS_JSON--- 블록을 제거해 렌더링용 텍스트 반환.
        닫는 마커가 없으면 시작 마커부터 끝까지 제거."""
        import re as _re
        # 1) 닫는 마커까지 블록 전체 제거
        out = _re.sub(
            r"---SECTIONS_JSON---.*?---END_SECTIONS_JSON---",
            "",
            text,
            flags=_re.DOTALL,
        )
        # 2) 닫는 마커 없이 시작 마커만 남은 경우 — 마커부터 끝까지 제거
        out = _re.sub(r"---SECTIONS_JSON---.*$", "", out, flags=_re.DOTALL)
        return out.strip()

    def _build_design_system_copy_block(ds: dict | None) -> str:
        """디자인 시스템(전역 규칙)만 따로 한국어 마크다운으로 조립.
        GPT Image 세션 시작 시 1회만 붙여넣는 용도."""
        if not isinstance(ds, dict) or not ds:
            return ""
        lines: list[str] = ["[디자인 시스템 (전역 규칙) — 세션당 1회만 입력]"]
        cp = ds.get("color_palette") or []
        if cp:
            lines.append(f"- 컬러 팔레트: {' / '.join(str(c) for c in cp)}")
        typo = ds.get("typography") or {}
        if isinstance(typo, dict):
            for k, v in typo.items():
                lines.append(f"- {k} 폰트: {v}")
        pc = ds.get("people_consistency")
        if pc:
            lines.append(f"- 인물 일관성: {pc}")
        forbidden = ds.get("forbidden") or []
        if forbidden:
            lines.append(f"- 전역 금지: {' / '.join(str(f) for f in forbidden)}")
        return "\n".join(lines)

    def _build_section_copy_block(sec: dict) -> str:
        """섹션 정보만 GPT Image 복붙용 한국어 마크다운으로 조립.
        디자인 시스템은 별도 블록(_build_design_system_copy_block)에서 1회만 입력.
        섹션 이름(예: '오프닝—결핍직격')은 마케팅 전략 레이블이라 GPT에 전달하면
        자율성을 떨어뜨리므로 복붙 영역에서는 제외하고 카드 헤더에만 노출한다."""
        lines: list[str] = []

        canvas = sec.get("canvas") or {}
        if canvas:
            wpx = canvas.get("width_px") or ""
            hpx = canvas.get("height_px") or ""
            ratio = canvas.get("ratio") or ""
            if wpx and hpx:
                lines.append(f"- 캔버스: {wpx}x{hpx}" + (f", {ratio}" if ratio else ""))
            elif wpx:
                lines.append(f"- 캔버스: {wpx}" + (f", {ratio}" if ratio else ""))

        if sec.get("background"):
            lines.append(f"- 배경/장면: {sec.get('background')}")
        if sec.get("composition"):
            lines.append(f"- 구도: {sec.get('composition')}")
        if sec.get("mood"):
            lines.append(f"- 무드: {sec.get('mood')}")

        text_elements = sec.get("text_elements") or []
        if text_elements:
            lines.append("- 카피:")
            for te in text_elements:
                if not isinstance(te, dict):
                    continue
                content = te.get("content") or ""
                role = te.get("role") or ""
                # 카피 내 줄바꿈은 공백으로 치환 — GPT Image가 문맥 보고 알아서 줄바꿈
                content_oneline = " ".join(content.split())
                role_suffix = f" [{role}]" if role else ""
                lines.append(f'  · "{content_oneline}"{role_suffix}')

        if sec.get("design_notes"):
            lines.append(f"- 디자인 노트: {sec.get('design_notes')}")

        return "\n".join(lines)

    def _render_image_direction_panel(
        builder: str, builder_label: str, model_id: str | None,
        lint_status, lint_text: str,
    ) -> None:
        st.markdown(_model_header(
            builder_label, model_id or "", lint_status,
            lint_enabled=lint_enabled_for_stage("04_1", cfg),
        ))
        raw_text = image_direction_04_1.get(builder) or ""
        parsed = image_direction_parsed.get(builder) or {}
        sections = parsed.get("sections") if isinstance(parsed, dict) else None
        ds = parsed.get("design_system") if isinstance(parsed, dict) else None
        sm = parsed.get("selection_method") if isinstance(parsed, dict) else None

        if sections:
            if sm:
                st.caption(f"**선택 방식**: {sm}")
            if isinstance(ds, dict) and ds:
                with st.expander("🎨 디자인 시스템 (전역 규칙)", expanded=False):
                    st.json(ds)
                ds_copy = _build_design_system_copy_block(ds)
                if ds_copy:
                    st.markdown("**📋 GPT Image 복붙용 — 디자인 시스템 (세션당 1회)**")
                    st.code(ds_copy, language="text")
                    st.caption("👆 GPT Image 새 세션 시작 시 제품 사진과 함께 1회만 입력하세요. 아래 섹션 블록에는 중복 포함되지 않습니다.")
            for sec in sections:
                if not isinstance(sec, dict):
                    continue
                order = sec.get("order")
                name = sec.get("name") or "(이름 없음)"
                with st.container(border=True):
                    st.markdown(f"### #{order} · {name}")
                    canvas = sec.get("canvas") or {}
                    if canvas:
                        ratio = canvas.get("ratio") or ""
                        wpx = canvas.get("width_px") or ""
                        hpx = canvas.get("height_px") or ""
                        size_str = f"{wpx}x{hpx}" if wpx and hpx else (wpx or "")
                        st.caption(f"📐 캔버스: {size_str} ({ratio})" if ratio or size_str else "")
                    if sec.get("composition"):
                        st.markdown(f"**구도**: {sec.get('composition')}")
                    if sec.get("background"):
                        st.markdown(f"**배경**: {sec.get('background')}")
                    if sec.get("mood"):
                        st.markdown(f"**무드**: {sec.get('mood')}")
                    text_elements = sec.get("text_elements") or []
                    if text_elements:
                        st.markdown("**확정 카피**")
                        for te in text_elements:
                            if not isinstance(te, dict):
                                continue
                            role = te.get("role") or ""
                            content = te.get("content") or ""
                            meta = f"_{role}_" if role else ""
                            st.markdown(f"- {meta}<br>**“{content}”**", unsafe_allow_html=True)
                    if sec.get("design_notes"):
                        st.markdown(f"**디자인 노트**: {sec.get('design_notes')}")
                    copy_text = _build_section_copy_block(sec)
                    if copy_text:
                        st.markdown("**📋 GPT Image 복붙용 — 섹션 브리프**")
                        st.code(copy_text, language="text")
        else:
            st.caption("⚠️ JSON 블록 파싱 실패 — 원본 출력만 표시합니다.")
            st.markdown(_strip_json_block(raw_text) or "_(empty)_")

        with st.expander("🧾 원본 출력 보기", expanded=False):
            st.markdown(_strip_json_block(raw_text) or "_(empty)_")

        if lint_text:
            with st.expander(
                f"🔍 {_lint_reviewer_label(builder)} 린터 검수",
                expanded=lint_status[0] in ("FAIL", "WARN") if lint_status else False,
            ):
                st.markdown(lint_text)
        _version_history_ui("04_1", builder, ss.get("selected_target_db_id"))

    if cc41 is not None:
        with cc41:
            _render_image_direction_panel(
                "claude", "🟠 Claude", claude_model_04_1, lint_c41, lint_text_c41,
            )
    if gc41 is not None:
        with gc41:
            _render_image_direction_panel(
                "gemini", "🔵 Gemini", gemini_model_04_1, lint_g41, lint_text_g41,
            )

# ── Step 4: 05 채널·물길 ────────────────────────────────────
if positioning_02 and ss.get("selected_target_db_id"):
    st.divider()
    st.header("Step 4 · 05 채널·물길")

    available_bases_02_for_05 = [
        m for m in ("claude", "gemini")
        if (positioning_02.get(m) or "").strip()
    ]
    if len(available_bases_02_for_05) >= 2:
        channel_basis = st.radio(
            "05 입력으로 쓸 02 결과",
            options=available_bases_02_for_05,
            horizontal=True,
            format_func=lambda x: {"claude": "🟠 Claude", "gemini": "🔵 Gemini"}[x],
            key="basis_05",
        )
    elif available_bases_02_for_05:
        channel_basis = available_bases_02_for_05[0]
    else:
        channel_basis = "claude"

    st.caption(caption_for_stage("05", cfg))
    pos_text_for_05 = positioning_02.get(channel_basis) or ""
    run_05 = st.button(
        _stage_action_label("05", cfg),
        type="primary",
        use_container_width=True,
        disabled=not is_owner() or not pos_text_for_05.strip(),
        key="run_05",
    )
    if ss.pop("_restage_05", False):
        run_05 = True

    if run_05:
        sel_target = _find_selected_target_dict(ss["selected_target_db_id"])
        if not sel_target:
            st.error("선택된 타겟 정보를 찾을 수 없습니다. 02부터 다시 실행하세요.")
            st.stop()

        target_dict = {
            "label": sel_target.get("label") or "",
            "description": _build_target_description(sel_target),
        }
        try:
            system_prompt = load_agent_prompt("channel")
            user_input = build_user_input_05(
                spec, target_dict, pos_text_for_05, channel_basis,
            )
        except Exception as e:
            st.error(f"프롬프트 로드 실패: {type(e).__name__}: {e}")
            st.stop()

        with st.spinner(_stage_spinner_label("05", cfg)):
            channel_05 = generate_both(
                system_prompt, user_input,
                claude_model=claude_model_05,
                gemini_model=gemini_model_05,
            )
        ss["channel_05"] = channel_05
        ss["channel_05_based_on_ver"] = ss.get("positioning_02_ver", 0)

        if lint_c_05 or lint_g_05:
            with st.spinner("교차 린터 검수 중…"):
                ss["lint_05"] = cross_lint_both(
                    "channel",
                    channel_05.get("claude", ""),
                    channel_05.get("gemini", ""),
                    claude_model=lint_c_05,
                    gemini_model=lint_g_05,
                )
        else:
            ss["lint_05"] = {"claude": "", "gemini": ""}

        try:
            tid = ss["selected_target_db_id"]
            for m in ("claude", "gemini"):
                storage.save_채널(
                    target_id=tid, model=m,
                    raw_output=channel_05.get(m, ""),
                )
            st.success(f"05 저장 완료 (타겟_id={tid})")
        except Exception as e:
            st.error(f"05 DB 저장 실패: {type(e).__name__}: {e}")

channel_05 = ss.get("channel_05")
lint_05 = ss.get("lint_05") or {}
if channel_05:
    # ── 섹션 재생성 트리거 처리 (이전 사이클 _section_edit_ui 버튼) ──
    sec_payload_05 = ss.pop("_sec_regen_05", None)
    if sec_payload_05:
        sel_target = _find_selected_target_dict(ss.get("selected_target_db_id"))
        if sel_target:
            target_dict = {
                "label": sel_target.get("label") or "",
                "description": _build_target_description(sel_target),
            }
            basis_for_05 = ss.get("basis_05") or "claude"
            pos_text_for_05 = positioning_02.get(basis_for_05) or ""
            base_input = build_user_input_05(
                spec, target_dict, pos_text_for_05, basis_for_05,
            )
            full_old = channel_05.get(sec_payload_05["builder"], "")
            with st.spinner(
                f"섹션 재생성 중… ({sec_payload_05['builder']} / "
                f"{sec_payload_05['section_header']})"
            ):
                try:
                    new_section = regenerate_section(
                        agent="channel",
                        base_user_input=base_input,
                        full_text=full_old,
                        section_header=sec_payload_05["section_header"],
                        user_feedback=sec_payload_05["feedback"],
                        builder_model=sec_payload_05["builder"],
                        model_id=model_for_family(sec_payload_05["builder"], "05", cfg),
                    )
                    merged = replace_section(
                        full_old,
                        sec_payload_05["section_index"],
                        new_section,
                    )
                    new_c = dict(channel_05)
                    new_c[sec_payload_05["builder"]] = merged
                    ss["channel_05"] = new_c
                    channel_05 = new_c
                    ss["channel_05_ver"] = ss.get("channel_05_ver", 0) + 1

                    tid = ss.get("selected_target_db_id")
                    if tid:
                        storage.save_채널(
                            target_id=tid,
                            model=sec_payload_05["builder"],
                            raw_output=merged,
                        )
                    ss.pop("lint_05", None)
                    lint_05 = {}
                    st.success(
                        f"✅ 섹션 재생성 완료: {sec_payload_05['section_header']} "
                        f"({sec_payload_05['builder']})"
                    )
                except Exception as e:
                    st.error(f"섹션 재생성 실패: {type(e).__name__}: {e}")
        else:
            st.error("선택된 타겟 정보를 찾을 수 없습니다. 05 통째 재실행이 필요합니다.")

    is_stale_05 = (
        ss.get("channel_05_based_on_ver", 0) != ss.get("positioning_02_ver", 0)
    )
    if is_stale_05:
        col_w, col_b = st.columns([4, 1])
        with col_w:
            st.warning("⚠️ 이 05 결과는 **이전 02 기반**입니다. 02가 갱신되었으니 재생성을 권장합니다.")
        with col_b:
            if st.button("🔄 05 재생성", key="restage_05", use_container_width=True):
                ss["_restage_05"] = True
                st.rerun()
    st.markdown("**05 결과 비교**")
    lint_text_c5 = lint_05.get("claude") or ""
    lint_text_g5 = lint_05.get("gemini") or ""
    lint_c5 = parse_lint_status(lint_text_c5) if lint_text_c5 else None
    lint_g5 = parse_lint_status(lint_text_g5) if lint_text_g5 else None
    _compare_off_caption(claude_model_05, gemini_model_05)
    cc5, gc5 = _result_layout(claude_model_05, gemini_model_05)
    if cc5 is not None:
        with cc5:
            st.markdown(_model_header(
                "🟠 Claude", claude_model_05, lint_c5,
                lint_enabled=lint_enabled_for_stage("05", cfg),
            ))
            st.markdown(channel_05.get("claude") or "_(empty)_")
            if lint_text_c5:
                with st.expander(
                    f"🔍 {_lint_reviewer_label('claude')} 린터 검수",
                    expanded=lint_c5[0] in ("FAIL", "WARN") if lint_c5 else False,
                ):
                    st.markdown(lint_text_c5)
            _section_edit_ui(
                "claude", "Claude",
                channel_05.get("claude") or "",
                "_sec_regen_05",
                marker_style="bracket",
            )
            _version_history_ui("05", "claude", ss.get("selected_target_db_id"))
    if gc5 is not None:
        with gc5:
            st.markdown(_model_header(
                "🔵 Gemini", gemini_model_05, lint_g5,
                lint_enabled=lint_enabled_for_stage("05", cfg),
            ))
            st.markdown(channel_05.get("gemini") or "_(empty)_")
            if lint_text_g5:
                with st.expander(
                    f"🔍 {_lint_reviewer_label('gemini')} 린터 검수",
                    expanded=lint_g5[0] in ("FAIL", "WARN") if lint_g5 else False,
                ):
                    st.markdown(lint_text_g5)
            _section_edit_ui(
                "gemini", "Gemini",
                channel_05.get("gemini") or "",
                "_sec_regen_05",
                marker_style="bracket",
            )
            _version_history_ui("05", "gemini", ss.get("selected_target_db_id"))

    # ── 보조 작업: 리스팅 제목(상품명) / 브랜드명 — 별도 LLM 호출 ──
    # 05 본체(채널 분석)와 분리된 호출이므로 05 채널 결과 품질에 영향 없음.
    st.divider()
    st.subheader("📝 리스팅 제목(상품명) / 브랜드명")
    st.caption(
        "05 채널 결과를 바탕으로 채널별 리스팅 제목(상품명)을 생성합니다. "
        "**별도 LLM 호출**이라 위쪽 채널 분석 결과는 영향받지 않습니다. "
        "브랜드명은 선택(기본 OFF)."
    )

    _tid_05b = ss.get("selected_target_db_id")
    if _tid_05b:
        try:
            _naming_rows = storage.get_네이밍(_tid_05b)
        except Exception:
            _naming_rows = []
        _product_names: dict[str, str] = {"claude": "", "gemini": ""}
        for r in _naming_rows:
            if r.get("분류") == "제품명":
                m = r.get("모델")
                if m in _product_names:
                    _product_names[m] = r.get("원본_출력") or ""

        _has_product_name = any(v.strip() for v in _product_names.values())
        if not _has_product_name:
            st.info(
                "03 단계에서 제품명을 먼저 확정한 뒤 이 작업을 호출하면 더 정확합니다. "
                "[🔤 네이밍 페이지](/네이밍)에서 03을 실행하세요. "
                "(제품명 없이도 진행은 가능합니다)"
            )

        # 제품명 basis 선택 (둘 다 있을 때만 라디오)
        _pname_options = [m for m in ("claude", "gemini") if _product_names.get(m, "").strip()]
        if len(_pname_options) >= 2:
            _pname_basis = st.radio(
                "03 제품명 입력으로 쓸 모델 결과",
                options=_pname_options,
                horizontal=True,
                format_func=lambda x: {"claude": "🟠 Claude", "gemini": "🔵 Gemini"}[x],
                key="basis_listing_pname",
            )
        elif _pname_options:
            _pname_basis = _pname_options[0]
            st.caption(f"03 제품명: {_pname_basis} (단일)")
        else:
            _pname_basis = ""

        _chosen_pname = _product_names.get(_pname_basis, "") if _pname_basis else ""

        # 05 채널 basis 선택 (사용자가 어느 모델의 채널 결과를 입력으로 쓸지)
        _channel_options = [m for m in ("claude", "gemini") if (channel_05.get(m) or "").strip()]
        if len(_channel_options) >= 2:
            _channel_basis_for_listing = st.radio(
                "05 채널 입력으로 쓸 모델 결과",
                options=_channel_options,
                horizontal=True,
                format_func=lambda x: {"claude": "🟠 Claude", "gemini": "🔵 Gemini"}[x],
                key="basis_listing_channel",
            )
        elif _channel_options:
            _channel_basis_for_listing = _channel_options[0]
        else:
            _channel_basis_for_listing = "claude"

        _chosen_channel_text = channel_05.get(_channel_basis_for_listing, "") or ""

        # 02 포지셔닝 basis는 위쪽 05 본체에서 정한 값 재사용
        _basis_for_05 = ss.get("basis_05") or "claude"
        _pos_text_for_listing = (positioning_02.get(_basis_for_05) or "") if positioning_02 else ""

        # 옵션 UI
        _opt_c1, _opt_c2 = st.columns([3, 2])
        with _opt_c1:
            _channel_target = st.selectbox(
                "대상 채널",
                options=[
                    "전체 추천 채널",
                    "스마트스토어",
                    "쿠팡",
                    "11번가",
                    "카페24",
                    "기타 (직접 입력)",
                ],
                key="listing_channel_target",
                help="채널별 SEO 가이드가 다르므로 명시. '전체'면 05 결과 상위 1~2개 채널을 자동 선택.",
            )
            if _channel_target == "기타 (직접 입력)":
                _channel_target = st.text_input(
                    "채널명 직접 입력",
                    key="listing_channel_target_custom",
                    placeholder="예: 오늘의집, 자사몰 등",
                ) or "전체 추천 채널"
        with _opt_c2:
            _want_brand = st.checkbox(
                "🏷️ 브랜드명도 같이 생성",
                value=False,
                key="listing_want_brand",
                help="OFF면 상품명만 생성. 브랜드명은 회사·라인 우산 이름(다이슨·무신사 패턴).",
            )

        # 실행 버튼
        _run_listing = st.button(
            "🚀 리스팅 제목(상품명)" + (" + 브랜드명" if _want_brand else "") + " 생성 (Claude + Gemini)",
            type="primary",
            use_container_width=True,
            disabled=not is_owner() or not _pos_text_for_listing.strip(),
            key="run_listing_name",
        )

        if _run_listing:
            sel_target = _find_selected_target_dict(_tid_05b)
            if not sel_target:
                st.error("선택된 타겟 정보를 찾을 수 없습니다. 02부터 다시 실행하세요.")
                st.stop()
            target_dict = {
                "label": sel_target.get("label") or "",
                "description": _build_target_description(sel_target),
            }
            try:
                _sys_listing = load_listing_name_prompt()
                _user_listing = build_user_input_listing_name(
                    product=spec,
                    target=target_dict,
                    positioning_text=_pos_text_for_listing,
                    product_name=_chosen_pname,
                    channel_text=_chosen_channel_text,
                    channel_target=_channel_target,
                    want_brand=_want_brand,
                    cfg=cfg,
                )
            except Exception as e:
                st.error(f"리스팅 프롬프트 로드 실패: {type(e).__name__}: {e}")
                st.stop()

            with st.spinner("상품명·브랜드명 생성 중… (Claude + Gemini)"):
                listing_result = generate_both(
                    _sys_listing, _user_listing,
                    claude_model=claude_model_05,
                    gemini_model=gemini_model_05,
                )

            # DB 저장 — 분류="상품명", (옵션) "브랜드명"
            # 모델별 raw_output을 통째로 저장. 한 호출에 상품명·브랜드명 두 절이 함께 들어 있어도
            # 후속 조회 시 같은 row에서 같이 보임.
            _save_분류 = "상품명+브랜드명" if _want_brand else "상품명"
            try:
                for _m in ("claude", "gemini"):
                    storage.save_네이밍(
                        target_id=_tid_05b,
                        model=_m,
                        raw_output=listing_result.get(_m, ""),
                        분류=_save_분류,
                    )
                st.success(f"리스팅({_save_분류}) 저장 완료 (타겟_id={_tid_05b})")
                ss["listing_name_result"] = listing_result
            except Exception as e:
                st.error(f"DB 저장 실패: {type(e).__name__}: {e}")

        # 결과 표시 (DB에서 최신 로드)
        try:
            _all_naming = storage.get_네이밍(_tid_05b)
        except Exception:
            _all_naming = []
        _listing_rows = [
            r for r in _all_naming
            if r.get("분류") in ("상품명", "상품명+브랜드명")
        ]
        if _listing_rows:
            _latest_by_model: dict[str, dict] = {}
            for r in sorted(_listing_rows, key=lambda x: x.get("id", 0)):
                _latest_by_model[r.get("모델")] = r
            if _latest_by_model:
                st.markdown("**📝 리스팅 결과 (최신)**")
                _lc, _lg = st.columns(2)
                with _lc:
                    _r = _latest_by_model.get("claude")
                    st.markdown("### 🟠 Claude")
                    st.markdown((_r or {}).get("원본_출력") or "_(empty)_")
                with _lg:
                    _r = _latest_by_model.get("gemini")
                    st.markdown("### 🔵 Gemini")
                    st.markdown((_r or {}).get("원본_출력") or "_(empty)_")
