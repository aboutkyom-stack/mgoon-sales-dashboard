"""페이지 — 03 네이밍 (파이프라인 외부 도구).

흐름:
- 기존 엠군 실행(run) 선택 → 제품·선택 타겟·02·04·05 결과 자동 로드
- 02/04/05 각각 어느 모델 결과를 03 입력으로 쓸지 선택 (04/05는 생략 가능)
- 03 실행 (Claude + Gemini) → 엠군_네이밍 DB 저장
- 마지막 결과 자동 표시 + 이력 펼치기

설계 메모: 네이밍은 파이프라인의 한 단계가 아니라, 모든 단계 결과가 쌓인
후 종합적으로 호출되는 도구다. 따라서 별도 페이지로 분리.
"""
from __future__ import annotations

import json

import streamlit as st

from pipeline.llm import generate_both
from pipeline.loader import build_user_input_03, load_agent_prompt
from pipeline.settings import load as load_settings
from pipeline.storage import get_storage


# ──────────────────────── 헬퍼 함수 ─────────────────────────

def _build_target_description_kr(row: dict) -> str:
    """엠군_타겟 한글 컬럼 dict → 멀티라인 텍스트."""
    parts = []
    if row.get("캐릭터"):
        parts.append(f"직업/나이/상황: {row['캐릭터']}")
    if row.get("핵심_결핍"):
        parts.append(f"핵심 결핍: {row['핵심_결핍']}")
    if row.get("결핍_원천"):
        parts.append(f"결핍 원천: {row['결핍_원천']}")
    if row.get("구매편익"):
        parts.append(f"구매편익 유형: {row['구매편익']}")
    if row.get("관여도") not in (None, ""):
        parts.append(f"관여도: {row['관여도']}")
    if row.get("주요_채널"):
        parts.append(f"주요 채널: {row['주요_채널']}")
    if row.get("구매자_이용자_분리"):
        parts.append(f"구매자/이용자 분리: {row['구매자_이용자_분리']}")
    if row.get("욕구깡패"):
        parts.append(f"욕구깡패: {row['욕구깡패']}")
    if row.get("비고"):
        parts.append(f"비고: {row['비고']}")
    return "\n".join(parts)


def _to_dict_by_model(rows: list[dict]) -> dict[str, str]:
    """같은 모델이 여러 row면 마지막(최신)이 덮어씀."""
    d = {"claude": "", "gemini": ""}
    for r in rows:
        m = r.get("모델")
        if m in d:
            d[m] = r.get("원본_출력") or ""
    return d


def _fmt_dt(s) -> str:
    if not s:
        return ""
    return str(s).replace("T", " ").split(".")[0]


# ──────────────────────── 페이지 시작 ────────────────────────

st.title("🔤 03 네이밍")
st.caption("🗄️ DB — 엠군_실행/타겟/포지셔닝/상세페이지/채널 (읽기) | 엠군_네이밍 (저장)")

cfg = load_settings()
storage = get_storage()
ss = st.session_state

# ── Step 1: run 선택 ────────────────────────────────────────
runs = storage.list_runs(limit=200)
if not runs:
    st.warning("저장된 엠군 실행이 없습니다. 먼저 파이프라인 페이지에서 01·02를 실행하세요.")
    st.page_link("pages/2_pipeline.py", label="🧪 파이프라인으로 이동", icon="➡️")
    st.stop()

default_run_id = ss.get("current_run_id")
options = [r["id"] for r in runs]
default_idx = options.index(default_run_id) if default_run_id in options else 0


def _fmt_run(rid):
    r = next((x for x in runs if x["id"] == rid), None)
    if not r:
        return f"#{rid}"
    return f"#{rid} · {r.get('제품명') or '(이름 없음)'} ({_fmt_dt(r.get('생성일'))})"


selected_run_id = st.selectbox(
    "엠군 실행 선택",
    options=options,
    format_func=_fmt_run,
    index=default_idx,
)

run = storage.get_run(selected_run_id)
if not run:
    st.error("실행 정보를 불러올 수 없습니다.")
    st.stop()

spec = run.get("제품_스냅샷")
if isinstance(spec, str):
    try:
        spec = json.loads(spec)
    except Exception:
        spec = {}
spec = spec or {}

# ── Step 2: 선택된 타겟 + 02/04/05 결과 자동 로드 ──────────
targets = storage.get_targets(selected_run_id)
selected_target_row = next((t for t in targets if t.get("선택됨")), None)

if not selected_target_row:
    st.warning(
        "이 실행에는 선택된 타겟이 없습니다 (02 포지셔닝까지 진행되지 않은 듯). "
        "파이프라인에서 02까지 실행 후 다시 시도하세요."
    )
    st.page_link("pages/2_pipeline.py", label="🧪 파이프라인으로 이동", icon="➡️")
    st.stop()

target_id = selected_target_row["id"]
pos_dict = _to_dict_by_model(storage.get_positioning(target_id))
detail_dict = _to_dict_by_model(storage.get_상세페이지(target_id))
channel_dict = _to_dict_by_model(storage.get_채널(target_id))

# ── Step 3: 컨텍스트 요약 ─────────────────────────────────
with st.container(border=True):
    st.subheader(f"제품: #{spec.get('id')} · {spec.get('제품명') or '(이름 없음)'}")
    st.caption(
        f"선택 타겟: #{selected_target_row.get('순위')} · "
        f"{selected_target_row.get('라벨') or '(라벨 없음)'}"
    )
    cols = st.columns(3)
    cols[0].metric("02 포지셔닝", "✅" if any(pos_dict.values()) else "—")
    cols[1].metric("04 상세페이지", "✅" if any(detail_dict.values()) else "—")
    cols[2].metric("05 채널",     "✅" if any(channel_dict.values()) else "—")

if not any(pos_dict.values()):
    st.error("02 포지셔닝 결과가 없습니다 — 네이밍은 02 결과가 필수입니다.")
    st.stop()

# ── Step 4-A: 네이밍 분류 선택 ────────────────────────────
st.divider()
naming_type = st.radio(
    "네이밍 분류",
    options=["제품명", "브랜드명"],
    horizontal=True,
    key="naming_type_radio",
    help=(
        "**제품명**: 이 제품 하나의 고유 이름 (상표권 등록 대상). "
        "키미테·하나로·탑블로 패턴.  \n"
        "**브랜드명**: 회사·라인의 우산 이름. 여러 제품을 묶는 상위 정체성. "
        "다이슨·무신사 패턴."
    ),
)

# ── Step 4-B: basis 선택 (02 / 04 / 05) ───────────────────
st.markdown("**입력 컨텍스트 선택** — 각 단계의 어떤 모델 결과를 03 네이밍 입력으로 쓸지")

c1, c2, c3 = st.columns(3)
with c1:
    pos_basis = st.radio(
        "02 포지셔닝 (필수)",
        options=["claude", "gemini"],
        format_func=lambda x: {"claude": "🟠 Claude", "gemini": "🔵 Gemini"}[x],
        key="naming_pos_basis",
        index=0 if pos_dict.get("claude") else 1,
    )
with c2:
    detail_options = ["claude", "gemini", "(생략)"]
    detail_default = 2  # 기본은 생략
    if detail_dict.get("claude"):
        detail_default = 0
    elif detail_dict.get("gemini"):
        detail_default = 1
    detail_basis = st.radio(
        "04 상세페이지",
        options=detail_options,
        format_func=lambda x: {"claude": "🟠 Claude", "gemini": "🔵 Gemini", "(생략)": "— 생략"}[x],
        key="naming_detail_basis",
        index=detail_default,
    )
with c3:
    channel_options = ["claude", "gemini", "(생략)"]
    channel_default = 2
    if channel_dict.get("claude"):
        channel_default = 0
    elif channel_dict.get("gemini"):
        channel_default = 1
    channel_basis = st.radio(
        "05 채널",
        options=channel_options,
        format_func=lambda x: {"claude": "🟠 Claude", "gemini": "🔵 Gemini", "(생략)": "— 생략"}[x],
        key="naming_channel_basis",
        index=channel_default,
    )

pos_text = pos_dict.get(pos_basis, "")
detail_text = detail_dict.get(detail_basis, "") if detail_basis != "(생략)" else ""
channel_text = channel_dict.get(channel_basis, "") if channel_basis != "(생략)" else ""

# ── Step 5: 실행 ─────────────────────────────────────────
st.caption(
    f"Claude: `{cfg['claude_model_02']}` · Gemini: `{cfg['gemini_model_02']}`  "
    "(02 모델 재사용 — [⚙️ 설정](0_settings)에서 변경)"
)

if st.button(f"🚀 {naming_type} 네이밍 실행 (Claude + Gemini)", type="primary",
             use_container_width=True, disabled=not pos_text.strip()):
    target_dict = {
        "label": selected_target_row.get("라벨") or "",
        "description": _build_target_description_kr(selected_target_row),
    }
    try:
        system_prompt = load_agent_prompt("naming")
        user_input = build_user_input_03(
            spec, target_dict,
            pos_text, pos_basis,
            detail_text, detail_basis if detail_basis != "(생략)" else "",
            channel_text, channel_basis if channel_basis != "(생략)" else "",
            naming_type=naming_type,
        )
    except Exception as e:
        st.error(f"프롬프트 로드 실패: {type(e).__name__}: {e}")
        st.stop()

    with st.spinner("Claude + Gemini 호출 중…"):
        naming_03 = generate_both(
            system_prompt, user_input,
            claude_model=cfg["claude_model_02"],
            gemini_model=cfg["gemini_model_02"],
        )

    try:
        for m in ("claude", "gemini"):
            storage.save_네이밍(
                target_id=target_id, model=m,
                raw_output=naming_03.get(m, ""),
                분류=naming_type,
            )
        st.success(f"03 {naming_type} 네이밍 저장 완료 (타겟_id={target_id})")
        st.rerun()
    except Exception as e:
        st.error(f"03 DB 저장 실패: {type(e).__name__}: {e}")

# ── Step 6: 결과 표시 (DB에서 매번 최신 로드, 현재 분류로 필터링) ──
naming_rows = storage.get_네이밍(target_id)

# 현재 라디오에서 선택한 분류만 메인 화면에 표시
filtered_rows = [r for r in naming_rows if r.get("분류") == naming_type]
latest = _to_dict_by_model(filtered_rows)

if any(latest.values()):
    st.divider()
    st.markdown(f"**03 {naming_type} 네이밍 결과 (최신)**")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### 🟠 Claude")
        st.markdown(latest.get("claude") or "_(empty)_")
    with c2:
        st.markdown("### 🔵 Gemini")
        st.markdown(latest.get("gemini") or "_(empty)_")

# 전체 이력 (모든 분류 포함, 분류 미기록 옛 row도 포함)
if naming_rows:
    other_count = len(naming_rows) - len(filtered_rows)
    label = (
        f"📜 전체 이력 ({len(naming_rows)}건"
        + (f" — 다른 분류·이전 시도 {other_count}건 포함" if other_count else "")
        + ")"
    )
    with st.expander(label, expanded=False):
        for r in sorted(naming_rows, key=lambda x: x.get("id", 0), reverse=True):
            cls = r.get("분류") or "(분류 미기록)"
            st.caption(
                f"#{r.get('id')} · [{cls}] · {r.get('모델')} · {_fmt_dt(r.get('생성일'))}"
            )
            st.markdown(r.get("원본_출력") or "_(empty)_")
            st.divider()
