"""페이지 2 — 엠군 파이프라인 실행.

Step A: 제품 확인 (page 1에서 선택한 제품)
Step B: 01 결핍·타겟 실행 (Claude + Gemini 병렬)
Step C: 사용할 타겟 1개 선택 + 붙여넣기 (01 결과에서)
Step D: 02 포지셔닝 실행 (Claude + Gemini 병렬) → 결과 SQLite 저장
"""
from __future__ import annotations

import streamlit as st

from pipeline.llm import generate_both
from pipeline.loader import (
    build_user_input_01,
    build_user_input_02,
    load_agent_prompt,
)
from pipeline.settings import load as load_settings
from pipeline.storage import get_storage

st.title("🧪 엠군 파이프라인")
st.caption("🗄️ DB — 상품 테이블 (읽기) | mgoon_runs, mgoon_targets, mgoon_positioning (저장)")

ss = st.session_state
cfg = load_settings()

# ── 제품 컨텍스트 확보 ──────────────────────────────────
spec = ss.get("pipeline_product_spec")

if not spec and ss.get("current_run_id"):
    # 홈에서 기존 run을 클릭해 들어온 경우: product_snapshot 복원
    run = get_storage().get_run(ss["current_run_id"])
    if run:
        spec = run["product_snapshot"]
        ss["pipeline_product_spec"] = spec

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
    st.caption(f"채널: {_채널}  ·  재고: {_재고}  ·  소매가: {_가격.get('소매가')}  ·  도매가: {_가격.get('도매가')}")
    with st.expander("스펙 원본 보기", expanded=False):
        st.json(spec)

st.divider()

# ── Step B: 01 실행 ─────────────────────────────────────
st.header("Step 1 · 01 결핍·타겟")

col_run, col_info = st.columns([1, 3])
with col_run:
    run_01 = st.button("🚀 01 실행 (Claude + Gemini)", type="primary", use_container_width=True)
with col_info:
    st.caption(
        f"Claude: `{cfg['claude_model_01']}` · Gemini: `{cfg['gemini_model_01']}`  "
        "([⚙️ 설정](0_settings)에서 변경)"
    )

if run_01:
    try:
        system_prompt = load_agent_prompt("deficit_target")
        user_input = build_user_input_01(spec)
    except Exception as e:
        st.error(f"프롬프트 로드 실패: {type(e).__name__}: {e}")
        st.stop()

    with st.spinner("Claude + Gemini 호출 중…"):
        ss["targets_01"] = generate_both(
            system_prompt, user_input,
            claude_model=cfg["claude_model_01"],
            gemini_model=cfg["gemini_model_01"],
        )
    # 02 상태 초기화
    for k in ("positioning_02", "saved_run_id"):
        ss.pop(k, None)

targets_01 = ss.get("targets_01")
if targets_01:
    st.markdown("**01 결과 비교**")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### 🟠 Claude")
        st.markdown(targets_01.get("claude") or "_(empty)_")
    with c2:
        st.markdown("### 🔵 Gemini")
        st.markdown(targets_01.get("gemini") or "_(empty)_")

# ── Step C: 타겟 선택 + Step D: 02 실행 ─────────────────
if targets_01:
    st.divider()
    st.header("Step 2 · 타겟 확정 + 02 포지셔닝")

    with st.container(border=True):
        basis = st.radio(
            "02의 기준이 될 01 결과",
            options=["claude", "gemini"],
            horizontal=True,
            format_func=lambda x: {"claude": "🟠 Claude", "gemini": "🔵 Gemini"}[x],
        )
        target_label = st.text_input(
            "타겟 라벨 (한 줄 요약)",
            placeholder="예: 32세 1인 자취 여성, 층간소음 스트레스",
        )
        target_text = st.text_area(
            "타겟 내용 (01 결과에서 한 명을 골라 해당 행/블록을 복사해 붙여넣기)",
            height=200,
            placeholder="직업+나이+상황 / 핵심 결핍 / 결핍 원천 / 구매편익 / 간호도 / 채널 / 비고 / 욕구깡패 3차…",
        )

        st.caption(
            f"Claude: `{cfg['claude_model_02']}` · Gemini: `{cfg['gemini_model_02']}`  "
            "([⚙️ 설정](0_settings)에서 변경)"
        )
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
                claude_model=cfg["claude_model_02"],
                gemini_model=cfg["gemini_model_02"],
            )
        ss["positioning_02"] = positioning_02

        # ── 저장 (run + target 1개 + positioning 2개) ────
        try:
            storage = get_storage()
            run_id = storage.create_run(spec, source_product_id=spec.get("id"))
            target_row = {
                "rank": 1,
                "character": target_label.strip(),
                "note": target_text.strip(),
            }
            target_ids = storage.save_targets(
                run_id=run_id,
                targets=[target_row],
                model=basis,
                raw_output=targets_01.get(basis, ""),
            )
            target_id = target_ids[0]
            storage.mark_target_selected(target_id, True)
            for m in ("claude", "gemini"):
                storage.save_positioning(
                    target_id=target_id,
                    result={},
                    model=m,
                    raw_output=positioning_02.get(m, ""),
                )
            ss["saved_run_id"] = run_id
            st.success(f"Supabase 저장 완료 (run_id={run_id}, target_id={target_id})")
        except Exception as e:
            st.error(f"DB 저장 실패: {type(e).__name__}: {e}")

positioning_02 = ss.get("positioning_02")
if positioning_02:
    st.markdown("**02 결과 비교**")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### 🟠 Claude")
        st.markdown(positioning_02.get("claude") or "_(empty)_")
    with c2:
        st.markdown("### 🔵 Gemini")
        st.markdown(positioning_02.get("gemini") or "_(empty)_")

    if ss.get("saved_run_id"):
        st.info(f"이 실행은 Supabase에 run_id=**{ss['saved_run_id']}** 로 저장되었습니다.")
