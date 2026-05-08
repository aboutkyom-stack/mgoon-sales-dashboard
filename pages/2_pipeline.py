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

from pipeline.lint import cross_lint_both, parse_lint_status
from pipeline.llm import generate_both
from pipeline.sections import regenerate_section, replace_section, split_sections
from pipeline.loader import (
    build_user_input_01,
    build_user_input_02,
    build_user_input_04,
    build_user_input_05,
    load_agent_prompt,
)
from pipeline.settings import (
    caption_for_stage,
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
) -> str:
    """결과 박스 헤더 한 줄. 모델명 + 검증 상태 표기.

    lint_status 없음 → "외부 린터 ✗" (미실행)
    lint_status (PASS, _) → "외부 린터 ✓ 통과"
    lint_status (WARN, N) → "외부 린터 ⚠️ N건 주의"
    lint_status (FAIL, N) → "외부 린터 ❌ N건 위반"
    lint_status (ERROR/UNKNOWN, _) → "외부 린터 ⚙️ 오류"
    """
    if lint_status is None:
        lint_part = "외부 린터 ✗"
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
claude_model_05, gemini_model_05 = models_for_stage("05", cfg)
storage = get_storage()


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

# ── Step B: 01 실행 ─────────────────────────────────────
st.header("Step 1 · 01 결핍·타겟")

col_run, col_info = st.columns([1, 3])
with col_run:
    run_01 = st.button(
        "🚀 01 실행 (Claude + Gemini)",
        type="primary",
        use_container_width=True,
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

    with st.spinner("Claude + Gemini 호출 중…"):
        targets_01 = generate_both(
            system_prompt, user_input,
            claude_model=claude_model_01,
            gemini_model=gemini_model_01,
        )
    ss["targets_01"] = targets_01

    with st.spinner("교차 린터 검수 중…"):
        ss["lint_01"] = cross_lint_both(
            "deficit_target",
            targets_01.get("claude", ""),
            targets_01.get("gemini", ""),
            claude_model=claude_model_01,
            gemini_model=gemini_model_01,
        )

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
            st.markdown(_model_header("🟠 Claude", claude_model_01, lint_c))
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
            st.markdown(_model_header("🔵 Gemini", gemini_model_01, lint_g))
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

        def _fmt(rank):
            t = next((x for x in targets_list if x.get("rank") == rank), None)
            if not t:
                return f"#{rank}"
            star = "⭐ " if t.get("is_recommended") else ""
            return f"{star}#{rank} · {t.get('label', '(라벨 없음)')}"

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
        "🚀 02 실행 (Claude + Gemini)",
        type="primary",
        use_container_width=True,
        disabled=not (target_label.strip() and target_text.strip()),
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

        with st.spinner("Claude + Gemini 호출 중…"):
            positioning_02 = generate_both(
                system_prompt, user_input,
                claude_model=claude_model_02,
                gemini_model=gemini_model_02,
            )
        ss["positioning_02"] = positioning_02
        # 02 갱신: 이전 04/05는 보존하되 버전 카운터로 stale 표시.
        # 04/05 결과 영역에서 based_on_ver 비교로 ⚠️ 배지 + 재생성 안내.
        ss["positioning_02_ver"] = ss.get("positioning_02_ver", 0) + 1

        with st.spinner("교차 린터 검수 중…"):
            ss["lint_02"] = cross_lint_both(
                "positioning",
                positioning_02.get("claude", ""),
                positioning_02.get("gemini", ""),
                claude_model=claude_model_02,
                gemini_model=gemini_model_02,
            )

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
                storage.save_positioning(
                    target_id=selected_db_id,
                    model=m,
                    raw_output=positioning_02.get(m, ""),
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
                        storage.save_positioning(
                            target_id=tid,
                            model=sec_payload["builder"],
                            raw_output=merged,
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
            st.markdown(_model_header("🟠 Claude", claude_model_02, lint_c2))
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
    if gc2 is not None:
        with gc2:
            st.markdown(_model_header("🔵 Gemini", gemini_model_02, lint_g2))
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
        "🚀 04 실행 (Claude + Gemini)",
        type="primary",
        use_container_width=True,
        disabled=not pos_text_for_04.strip(),
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

        with st.spinner("Claude + Gemini 호출 중…"):
            detail_04 = generate_both(
                system_prompt, user_input,
                claude_model=claude_model_04,
                gemini_model=gemini_model_04,
            )
        ss["detail_04"] = detail_04
        ss["detail_04_based_on_ver"] = ss.get("positioning_02_ver", 0)

        with st.spinner("교차 린터 검수 중…"):
            ss["lint_04"] = cross_lint_both(
                "detail_page",
                detail_04.get("claude", ""),
                detail_04.get("gemini", ""),
                claude_model=claude_model_04,
                gemini_model=gemini_model_04,
            )

        try:
            tid = ss["selected_target_db_id"]
            for m in ("claude", "gemini"):
                storage.save_상세페이지(
                    target_id=tid, model=m,
                    raw_output=detail_04.get(m, ""),
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
                        storage.save_상세페이지(
                            target_id=tid,
                            model=sec_payload_04["builder"],
                            raw_output=merged,
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
            st.markdown(_model_header("🟠 Claude", claude_model_04, lint_c4))
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
    if gc4 is not None:
        with gc4:
            st.markdown(_model_header("🔵 Gemini", gemini_model_04, lint_g4))
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
        "🚀 05 실행 (Claude + Gemini)",
        type="primary",
        use_container_width=True,
        disabled=not pos_text_for_05.strip(),
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

        with st.spinner("Claude + Gemini 호출 중…"):
            channel_05 = generate_both(
                system_prompt, user_input,
                claude_model=claude_model_05,
                gemini_model=gemini_model_05,
            )
        ss["channel_05"] = channel_05
        ss["channel_05_based_on_ver"] = ss.get("positioning_02_ver", 0)

        with st.spinner("교차 린터 검수 중…"):
            ss["lint_05"] = cross_lint_both(
                "channel",
                channel_05.get("claude", ""),
                channel_05.get("gemini", ""),
                claude_model=claude_model_05,
                gemini_model=gemini_model_05,
            )

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
            st.markdown(_model_header("🟠 Claude", claude_model_05, lint_c5))
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
    if gc5 is not None:
        with gc5:
            st.markdown(_model_header("🔵 Gemini", gemini_model_05, lint_g5))
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
