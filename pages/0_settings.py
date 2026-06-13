"""페이지 0 — 모델 설정.

단계 00~05 각각에 주 사용 모델 + 비교 모델(on/off)을 설정해
settings.json에 저장한다.
"""
from __future__ import annotations

import streamlit as st

from pipeline.settings import (
    DEFAULT_EXCLUDED_FIELDS,
    DEFAULT_SNAPSHOT_FIELDS,
    MODELS_ORDERED,
    SNAPSHOT_FIELD_CANDIDATES,
    STAGES,
    WORKFLOW_STAGES,
    load,
    save,
    load_판매자특성_활용,
    load_판매자특성_메모,
)
from pipeline.loader import load_instruction, save_instruction

# LLM 프롬프트에서 제외 선택 가능한 제품 필드 목록 (id·제품명은 항상 포함)
_EXCLUDABLE_FIELDS: list[str] = [
    "카테고리", "서브카테고리", "엠군상태",
    "시각설명",
    "스펙", "인증", "가격", "재고", "판매조건",
    "제품특징_bullet", "제품특징_추가", "판매자특성_선택",
    "판매자메모", "주의사항",
    "검수완료", "검수메모",
]

STAGE_LABELS: dict[str, str] = {
    "00": "00 단계 · Vision Pass (이미지 분석)",
    "01": "01 단계 · 결핍·타겟",
    "02": "02 단계 · 포지셔닝",
    "03": "03 단계 · 네이밍",
    "04": "04 단계 · 상세페이지",
    "04_1": "04-1 단계 · 이미지 디렉션",
    "05": "05 단계 · 채널",
}


st.title("⚙️ 모델 설정")
st.caption("단계별 주 사용 모델 + 비교 모델(on/off)을 설정합니다. 저장하면 모든 작업자(로컬·클라우드)에게 공유됩니다.")
st.caption("🗄️ DB — app_settings (Supabase) · 로컬·클라우드 공유")

cfg = load()

# 폼 입력값을 모아둘 dict
new_values: dict = {}

for stage in STAGES:
    st.subheader(STAGE_LABELS[stage])
    with st.container(border=True):
        primary_key  = f"primary_model_{stage}"
        compare_key  = f"compare_model_{stage}"
        enabled_key  = f"compare_enabled_{stage}"
        lint_key     = f"lint_enabled_{stage}"

        primary_default = cfg.get(primary_key, MODELS_ORDERED[0])
        compare_default = cfg.get(compare_key, MODELS_ORDERED[0])
        enabled_default = bool(cfg.get(enabled_key, True))
        lint_default = bool(cfg.get(lint_key, False))

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**주 사용 모델**")
            primary = st.selectbox(
                "primary",
                MODELS_ORDERED,
                index=MODELS_ORDERED.index(primary_default)
                if primary_default in MODELS_ORDERED
                else 0,
                key=f"sel_primary_{stage}",
                label_visibility="collapsed",
            )
        with c2:
            st.markdown("**비교 모델** — 아래 두 옵션 중 선택")
            compare = st.selectbox(
                "compare",
                MODELS_ORDERED,
                index=MODELS_ORDERED.index(compare_default)
                if compare_default in MODELS_ORDERED
                else 0,
                key=f"sel_compare_{stage}",
                label_visibility="collapsed",
            )
            enabled = st.checkbox(
                "비교 모델로 **결과 나란히 생성** (양쪽 호출 — 품질 비교용)",
                value=enabled_default,
                key=f"chk_compare_{stage}",
                help=(
                    "ON: 주 모델·비교 모델 둘 다 호출해 결과를 두 컬럼으로 표시. "
                    "OFF: 주 모델 결과만 표시 (비용 절감)."
                ),
            )
            lint_enabled = st.checkbox(
                "비교 모델이 **주 모델 결과를 검수** (외부 린터 — 비용 발생)",
                value=lint_default,
                key=f"chk_lint_{stage}",
                help=(
                    "ON: 비교 모델이 주 모델의 출력을 qa_checklist 기준으로 검수해 "
                    "PASS/WARN/FAIL을 알려줌. 결과 비교 옵션과 독립적."
                ),
            )

        if enabled and primary == compare:
            st.warning("주 모델과 비교 모델이 동일합니다. 비교 효과가 없습니다.")

        # 린터는 다른 family가 있어야 동작 — 같은 family면 안내
        if lint_enabled:
            from pipeline.models_config import family_of as _fam_of
            if _fam_of(primary) == _fam_of(compare):
                st.warning(
                    "외부 린터가 ON이지만 주/비교 모델이 같은 family입니다. "
                    "교차 검수가 자동 무력화됩니다 (자가 편향 회피)."
                )

        new_values[primary_key] = primary
        new_values[compare_key] = compare
        new_values[enabled_key] = enabled
        new_values[lint_key] = lint_enabled

st.divider()
st.subheader("🔍 참고 필드 관리")
st.caption(
    "LLM에 제품 정보를 넘길 때 각 단계에서 **제외할 필드**를 선택합니다. "
    "선택된 필드는 해당 단계의 프롬프트에서 빠집니다."
)

for stage in STAGES:
    excl_key = f"excluded_fields_{stage}"
    current_excl: list[str] = cfg.get(excl_key, list(DEFAULT_EXCLUDED_FIELDS))
    # 저장된 값 중 현재 목록에 없는 항목 제거 (구버전 호환)
    current_excl = [f for f in current_excl if f in _EXCLUDABLE_FIELDS]
    excluded = st.multiselect(
        STAGE_LABELS[stage],
        options=_EXCLUDABLE_FIELDS,
        default=current_excl,
        key=f"excl_{stage}",
    )
    new_values[excl_key] = excluded

st.divider()
st.subheader("📸 변경 감지 필드 관리")
st.caption(
    "워크플로 단계 토글(기초입력/엠군/상세페이지) ON 시점에 박제할 **핵심 필드**를 선택합니다. "
    "후속 작업자가 페이지 진입 시 박제된 값 vs 현재 값을 비교해 🔄 변동 알림을 표시합니다.\n\n"
    "- 비교 로직은 강건: 체크 해제한 필드는 비교 대상에서 제외되므로 false positive 없음.\n"
    "- 그룹 필드 (예: `가격`, `치수 / 무게`)는 내부 컬럼들을 묶어 한 번에 비교.\n"
    "- `파일_image` / `파일_video` / `파일_etc`는 각각 해당 파일_유형의 추가·삭제·이름 변경을 모두 감지.\n"
    "- `엠군_*` 단계는 엠군 파이프라인 결과 (실행/타겟/단계별 출력) 변동을 감지."
)
st.caption(
    "📂 후보 목록의 단일 소스는 `pipeline/snapshot_schema.py`입니다. "
    "수정 페이지의 그룹명이나 엠군 단계가 바뀌면 그 모듈을 같이 갱신하세요."
)

# 엠군 단계는 키 자체가 길어(예: `엠군_02_포지셔닝`) 사용자에게는 사람이 읽는 라벨로 보이게 한다.
from pipeline.snapshot_schema import 엠군_stage_label

_WS_LABELS: dict[str, str] = {
    "기초입력":   "🟠 기초입력 단계 (후속자=엠군 돌리는 사람)",
    "엠군":       "🔵 엠군 단계 (후속자=상세페이지 만드는 동료)",
    "상세페이지": "✅ 상세페이지 단계 (현재 후속자 없음 — 향후 채널 단계용)",
}

for ws in WORKFLOW_STAGES:
    snap_key = f"snapshot_fields_{ws}"
    current_snap: list[str] = cfg.get(snap_key, list(DEFAULT_SNAPSHOT_FIELDS.get(ws, [])))
    candidates = SNAPSHOT_FIELD_CANDIDATES.get(ws, [])
    # 후보에 없는 저장값은 제거 (구버전 호환)
    current_snap = [f for f in current_snap if f in candidates]
    if not candidates:
        # 상세페이지는 현재 후보 없음 → 안내만 표시하고 빈 리스트 저장
        st.caption(f"{_WS_LABELS[ws]} — 현재 후보 필드 없음 (빈 `{{}}`로 박제)")
        new_values[snap_key] = []
        continue

    # 엠군 단계는 키 → 라벨 표시. 기초입력 단계는 키 그대로(그룹명이 사람이 읽는 형태).
    if ws == "엠군":
        _format_func = 엠군_stage_label
    else:
        _format_func = lambda x: x  # noqa: E731

    selected = st.multiselect(
        _WS_LABELS[ws],
        options=candidates,
        default=current_snap,
        format_func=_format_func,
        key=f"snap_{ws}",
    )
    new_values[snap_key] = selected

st.divider()
st.subheader("🏪 판매자 특성 (파이프라인 활용형)")
st.caption(
    "이 셀러만의 운영 방식·강점을 **한 줄에 하나씩** 적어두면, "
    "개별 제품 스펙 탭에서 체크박스로 선택해 **01~05 단계에 전달**됩니다.\n\n"
    "예:\n"
    "- 친환경 포장 (주변 상권에서 수거한 박스 재활용)\n"
    "- 직접 포장·발송 — 소량도 꼼꼼하게\n"
    "- 국내 A/S 가능\n"
    "- 100% 환불 보장 상품\n"
    "- 무료 배송"
)

_활용_current = load_판매자특성_활용()
_활용_text = st.text_area(
    "판매자 특성 (파이프라인 활용형)",
    value="\n".join(_활용_current),
    height=180,
    placeholder="한 줄에 하나씩 입력하세요.\n저장 후 제품 스펙 탭에서 체크박스로 나타납니다.",
    key="ta_판매자특성_활용",
    label_visibility="collapsed",
)
new_values["판매자특성_활용"] = [
    line.strip() for line in _활용_text.splitlines() if line.strip()
]

st.divider()
st.subheader("📝 판매자 특성 (개인 메모용)")
st.caption(
    "판매자만 참고하는 운영 라벨. **파이프라인(01~05) 미참조** — 카피·이미지 생성에 영향 없음.\n\n"
    "예:\n"
    "- 합포장 가능\n"
    "- 수기 검수 필요\n"
    "- 9월 입고분만 핸들링 주의"
)

_메모_current = load_판매자특성_메모()
_메모_text = st.text_area(
    "판매자 특성 (개인 메모용)",
    value="\n".join(_메모_current),
    height=140,
    placeholder="한 줄에 하나씩 입력하세요.\n저장 후 제품 스펙 탭에서 체크박스로 나타납니다.",
    key="ta_판매자특성_메모",
    label_visibility="collapsed",
)
new_values["판매자특성_메모"] = [
    line.strip() for line in _메모_text.splitlines() if line.strip()
]

st.divider()
if st.button("💾 저장", type="primary", use_container_width=True):
    try:
        save(new_values)
        st.success("저장 완료! — DB에 동기화되어 로컬·클라우드 양쪽에 반영됩니다.")
    except Exception as e:
        st.error(
            "⚠️ DB 저장 실패 — 로컬에는 저장됐지만 DB 동기화에 실패했습니다. "
            f"인터넷/Supabase 연결을 확인하고 다시 저장하세요.\n\n`{e}`"
        )

st.divider()
st.subheader("📝 입력 프롬프트 편집 (instruction.md)")
st.caption(
    "각 단계에서 AI에게 보내는 **유저 프롬프트(지시문)**입니다. "
    "core.md(강의 핵심본)는 건드리지 않고, 이 지시문만 편집해 호출 품질을 조정합니다.\n\n"
    "⚠️ 중괄호 placeholder(`{product}`, `{target}`, `{positioning}`, `{positioning_basis_label}`, "
    "`{detail_section}`, `{channel_section}`)는 그대로 두세요. 실행 시 실제 데이터로 치환됩니다."
)

INSTRUCTION_TARGETS: list[tuple[str, str, str | None]] = [
    ("01 결핍·타겟",        "deficit_target",  None),
    ("02 포지셔닝",         "positioning",     None),
    ("03 네이밍 (제품명)",  "naming",          "제품명"),
    ("03 네이밍 (브랜드명)", "naming",          "브랜드명"),
    ("04 상세페이지",       "detail_page",     None),
    ("04-1 이미지 디렉션",  "image_direction", None),
    ("05 채널",             "channel",         None),
]

for label, agent, variant in INSTRUCTION_TARGETS:
    suffix = f"_{variant}" if variant else ""
    sk_loaded = f"instr_loaded_{agent}{suffix}"
    sk_value  = f"instr_value_{agent}{suffix}"
    if sk_loaded not in st.session_state:
        try:
            st.session_state[sk_value] = load_instruction(agent, variant)
        except FileNotFoundError:
            st.session_state[sk_value] = ""
        st.session_state[sk_loaded] = True

    with st.expander(f"📄 {label}", expanded=False):
        edited = st.text_area(
            label,
            value=st.session_state[sk_value],
            height=320,
            key=f"editor_{agent}{suffix}",
            label_visibility="collapsed",
        )
        if st.button(f"💾 {label} 저장", key=f"btn_save_instr_{agent}{suffix}"):
            save_instruction(agent, edited, variant)
            st.session_state[sk_value] = edited
            st.success(f"{label} 저장 완료!")

st.divider()
st.subheader("현재 설정")
st.json(load())

st.caption(
    "**모델 비용 참고**\n"
    "- claude-sonnet-4-6: 비용/성능 균형 (기본값)\n"
    "- claude-opus-4-7: 가장 고비용, 중요 제품 최종 확인용\n"
    "- claude-haiku-4-5-20251001: 가장 저비용, 단순 작업용\n"
    "- gemini-2.5-flash: 저비용, 비전·요약 무난\n"
    "- gemini-2.5-pro: 고비용, 창의적 표현이 중요한 단계용"
)
