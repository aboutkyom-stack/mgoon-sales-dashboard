"""Vision Pass URL 테스트 페이지.

Drive 없이 이미지 URL로 Vision Pass를 직접 테스트.
- 메인 엔진 (기본: Claude Sonnet) + 서브 엔진 (기본: Gemini Flash, on/off 가능)
- 엔진별 프롬프트 독립 편집·저장
- DB 저장 없음 (테스트 전용)
"""
from __future__ import annotations

import urllib.request
import mimetypes
from pathlib import Path
import streamlit as st

AGENTS_DIR = Path(__file__).parent.parent / "agents" / "00_vision_pass"

CLAUDE_MODELS = ["claude-sonnet-4-6", "claude-opus-4-7", "claude-haiku-4-5-20251001"]
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.5-pro"]
ALL_MODELS    = CLAUDE_MODELS + GEMINI_MODELS

def _engine_family(model: str) -> str:
    return "gemini" if model.startswith("gemini") else "claude"

def _prompt_path(model: str) -> Path:
    fam = _engine_family(model)
    p = AGENTS_DIR / f"core_{fam}.md"
    return p if p.exists() else AGENTS_DIR / "core.md"

def _load_prompt(model: str) -> str:
    return _prompt_path(model).read_text(encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
st.title("🔍 Vision Pass — URL 테스트")
st.caption("Drive 없이 이미지 URL을 직접 입력해 Vision Pass를 실행합니다. DB 저장 없음.")

# ── 비용 참고표 ───────────────────────────────────────────────────────────────
with st.expander("💰 엔진별 비용 참고 (이미지 1장·출력 600토큰 기준)", expanded=False):
    st.markdown("""
| 모델 | Input | Output | **호출 1회** | **1,142개 전체** |
|---|---|---|---|---|
| Claude Sonnet 4.6 | $3/MTok | $15/MTok | ~$0.014 | ~$16 |
| Claude Haiku 4.5 | $1/MTok | $5/MTok | ~$0.005 | ~$5.7 |
| Gemini 2.5 Flash | $0.30/MTok | $2.50/MTok | ~$0.002 | ~$2.3 |
""")
    st.caption("이미지 장수 비례 증가. 캐싱은 시스템 프롬프트에만 적용(이미지 토큰은 항상 풀 비용).")

st.divider()

# ── 엔진 설정 ─────────────────────────────────────────────────────────────────
st.subheader("⚙️ 엔진 설정")
ec1, ec2 = st.columns(2)

with ec1:
    st.markdown("**메인 엔진**")
    main_model = st.selectbox(
        "메인 모델",
        ALL_MODELS,
        index=0,
        key="main_model",
        label_visibility="collapsed",
    )

with ec2:
    st.markdown("**서브 엔진**")
    sub_cols = st.columns([3, 1])
    with sub_cols[0]:
        sub_model = st.selectbox(
            "서브 모델",
            ALL_MODELS,
            index=len(CLAUDE_MODELS),  # gemini-2.5-flash 기본
            key="sub_model",
            label_visibility="collapsed",
        )
    with sub_cols[1]:
        sub_on = st.toggle("ON", value=True, key="sub_on")

st.caption("서브 엔진은 메인 결과의 교차검증용. 텍스트 많거나 정교한 이미지 → 메인, 나머지 → 서브 방향 검토 중.")

st.divider()

# ── 프롬프트 편집 ─────────────────────────────────────────────────────────────
st.subheader("📄 프롬프트 편집")
pt1, pt2 = st.columns(2)

with pt1:
    fam_main = _engine_family(main_model)
    st.markdown(f"**메인 프롬프트** (`core_{fam_main}.md`)")
    if f"prompt_main_{fam_main}" not in st.session_state:
        st.session_state[f"prompt_main_{fam_main}"] = _load_prompt(main_model)
    main_prompt_val = st.text_area(
        "메인 프롬프트",
        value=st.session_state[f"prompt_main_{fam_main}"],
        height=320,
        key=f"editor_main_{fam_main}",
        label_visibility="collapsed",
    )
    if st.button("💾 메인 프롬프트 저장", key="btn_save_main"):
        _prompt_path(main_model).write_text(main_prompt_val, encoding="utf-8")
        st.session_state[f"prompt_main_{fam_main}"] = main_prompt_val
        st.success("저장 완료!")

with pt2:
    fam_sub = _engine_family(sub_model)
    st.markdown(f"**서브 프롬프트** (`core_{fam_sub}.md`)" + ("" if sub_on else " *(서브 OFF)*"))
    if f"prompt_sub_{fam_sub}" not in st.session_state:
        st.session_state[f"prompt_sub_{fam_sub}"] = _load_prompt(sub_model)
    sub_prompt_val = st.text_area(
        "서브 프롬프트",
        value=st.session_state[f"prompt_sub_{fam_sub}"],
        height=320,
        key=f"editor_sub_{fam_sub}",
        label_visibility="collapsed",
        disabled=not sub_on,
    )
    if sub_on and st.button("💾 서브 프롬프트 저장", key="btn_save_sub"):
        _prompt_path(sub_model).write_text(sub_prompt_val, encoding="utf-8")
        st.session_state[f"prompt_sub_{fam_sub}"] = sub_prompt_val
        st.success("저장 완료!")

st.divider()

# ── 이미지 URL 입력 ───────────────────────────────────────────────────────────
st.subheader("🖼️ 이미지 URL")
st.caption("URL 여러 개 = 한 제품의 여러 이미지로 처리. AI당 호출 1번.")
url_text = st.text_area(
    "URL 목록 (한 줄에 하나, 최대 10개)",
    placeholder="https://example.com/image1.jpg\nhttps://example.com/image2.png",
    height=120,
    key="url_input",
)

# ── 제품 정보 (선택) ──────────────────────────────────────────────────────────
with st.expander("제품 정보 입력 (선택 — 입력하면 AI 분석에 참고됩니다)"):
    col1, col2 = st.columns(2)
    with col1:
        product_name = st.text_input("제품명", key="prod_name")
        category     = st.text_input("카테고리", key="prod_cat")
        material     = st.text_input("재질", key="prod_mat")
    with col2:
        model_no = st.text_input("모델명", key="prod_model")
        color    = st.text_input("색상", key="prod_color")
        keywords = st.text_input("키워드", key="prod_kw")
    features = st.text_area("특징", key="prod_feat", height=70)

st.divider()

# ── 실행 ──────────────────────────────────────────────────────────────────────
run_label = f"🚀 Vision Pass 실행 ({main_model}" + (f" + {sub_model}" if sub_on else "") + ")"
if st.button(run_label, type="primary", key="btn_run"):
    urls = [u.strip() for u in url_text.strip().splitlines() if u.strip()]
    if not urls:
        st.warning("이미지 URL을 하나 이상 입력하세요.")
        st.stop()
    urls = urls[:10]

    # 이미지 다운로드 (메모리에만, 로컬 파일 저장 없음)
    image_data: list[tuple[bytes, str]] = []
    prog = st.progress(0, text="이미지 다운로드 중…")
    for i, url in enumerate(urls):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
                ct = resp.headers.get_content_type() or ""
                if not ct or ct == "application/octet-stream":
                    ext = url.rsplit(".", 1)[-1].lower()
                    ct = mimetypes.types_map.get(f".{ext}", "image/jpeg")
                image_data.append((raw, ct))
        except Exception as e:
            st.warning(f"URL {i+1} 다운로드 실패: {e}")
        prog.progress((i + 1) / len(urls), text=f"다운로드 {i+1}/{len(urls)}")
    prog.empty()

    if not image_data:
        st.error("다운로드 가능한 이미지가 없습니다.")
        st.stop()

    st.info(f"{len(image_data)}장 다운로드 완료.")

    product = {k: v for k, v in {
        "제품명": product_name, "카테고리": category, "모델명": model_no,
        "재질": material, "색상": color, "키워드": keywords, "특징": features,
    }.items() if v}

    from pipeline.loader import build_vision_input
    user_text = build_vision_input(product) if product else "이미지를 분석하여 시각설명을 작성하라."

    # 편집기에서 수정 중인 프롬프트 우선 사용 (저장 안 했어도 반영)
    cur_main_prompt = st.session_state.get(f"editor_main_{fam_main}") or main_prompt_val
    cur_sub_prompt  = st.session_state.get(f"editor_sub_{fam_sub}")  or sub_prompt_val

    if sub_on:
        from pipeline.llm import generate_vision_claude, generate_vision_gemini
        from concurrent.futures import ThreadPoolExecutor

        results: dict[str, str] = {}
        with st.spinner(f"{main_model} + {sub_model} 병렬 분석 중…"):
            def _run_main():
                if _engine_family(main_model) == "claude":
                    return generate_vision_claude(cur_main_prompt, image_data, user_text, model=main_model)
                else:
                    return generate_vision_gemini(cur_main_prompt, image_data, user_text, model=main_model)

            def _run_sub():
                if _engine_family(sub_model) == "claude":
                    return generate_vision_claude(cur_sub_prompt, image_data, user_text, model=sub_model)
                else:
                    return generate_vision_gemini(cur_sub_prompt, image_data, user_text, model=sub_model)

            with ThreadPoolExecutor(max_workers=2) as ex:
                f_main = ex.submit(_run_main)
                f_sub  = ex.submit(_run_sub)
                try:
                    results["main"] = f_main.result()
                except Exception as e:
                    results["main"] = f"[ERROR] {e}"
                try:
                    results["sub"] = f_sub.result()
                except Exception as e:
                    results["sub"] = f"[ERROR] {e}"
    else:
        with st.spinner(f"{main_model} 분석 중…"):
            try:
                if _engine_family(main_model) == "claude":
                    from pipeline.llm import generate_vision_claude
                    results = {"main": generate_vision_claude(cur_main_prompt, image_data, user_text, model=main_model)}
                else:
                    from pipeline.llm import generate_vision_gemini
                    results = {"main": generate_vision_gemini(cur_main_prompt, image_data, user_text, model=main_model)}
            except Exception as e:
                st.error(f"Vision Pass 실패: {e}")
                st.stop()

    st.session_state["vt_results"]    = results
    st.session_state["vt_main_label"] = main_model
    st.session_state["vt_sub_label"]  = sub_model if sub_on else None
    st.session_state["vt_done"]       = True

# ── 결과 표시 ──────────────────────────────────────────────────────────────────
if st.session_state.get("vt_done"):
    results    = st.session_state["vt_results"]
    main_label = st.session_state["vt_main_label"]
    sub_label  = st.session_state["vt_sub_label"]

    st.success("분석 완료!")

    if sub_label:
        r1, r2 = st.columns(2)
        with r1:
            st.markdown(f"### 메인 — {main_label}")
            st.text_area("", value=results.get("main", ""), height=450, key="view_main", disabled=True)
        with r2:
            st.markdown(f"### 서브 — {sub_label}")
            st.text_area("", value=results.get("sub", ""), height=450, key="view_sub", disabled=True)
    else:
        st.markdown(f"### {main_label}")
        st.text_area("", value=results.get("main", ""), height=450, key="view_main_only", disabled=True)

    st.caption("결과 확인 후 제품 수정 페이지에서 시각설명으로 저장하세요.")
