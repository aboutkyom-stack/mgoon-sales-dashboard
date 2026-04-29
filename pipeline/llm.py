"""Claude + Gemini 호출 추상화.

- Claude: anthropic SDK, system prompt + user message
- Gemini: google-genai SDK, system_instruction + contents
- generate_both: 두 모델 병렬 호출해 교차검증용

Claude는 system 블록에 cache_control을 붙여 prompt caching으로 비용 절감
(시스템 프롬프트는 MD 세트 전체라 대용량·재사용이 잦음).
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@lru_cache(maxsize=1)
def _anthropic_client():
    from anthropic import Anthropic
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(".env에 ANTHROPIC_API_KEY를 설정하세요.")
    return Anthropic(api_key=key)


@lru_cache(maxsize=1)
def _gemini_client():
    from google import genai
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(".env에 GEMINI_API_KEY를 설정하세요.")
    return genai.Client(api_key=key)


def _claude_model() -> str:
    return os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")


def _gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def generate_claude(
    system_prompt: str,
    user_input: str,
    max_tokens: int = 8192,
    model: str | None = None,
) -> str:
    client = _anthropic_client()
    resp = client.messages.create(
        model=model or _claude_model(),
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system_prompt,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_input}],
    )
    return "".join(
        block.text for block in resp.content if getattr(block, "type", None) == "text"
    )


def generate_gemini(
    system_prompt: str,
    user_input: str,
    model: str | None = None,
) -> str:
    from google.genai import types
    client = _gemini_client()
    resp = client.models.generate_content(
        model=model or _gemini_model(),
        contents=[user_input],
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    )
    return resp.text or ""


def generate(system_prompt: str, user_input: str, model: str) -> str:
    if model == "claude":
        return generate_claude(system_prompt, user_input)
    if model == "gemini":
        return generate_gemini(system_prompt, user_input)
    raise ValueError(f"unknown model: {model}")


def generate_vision_claude(
    system_prompt: str,
    images: list[tuple[bytes, str]],  # [(bytes, mime_type), ...]
    user_text: str = "",
    max_tokens: int = 4096,
    model: str | None = None,
) -> str:
    """Claude Vision 호출. images = [(bytes, mime_type), ...]"""
    import base64
    client = _anthropic_client()
    content: list = []
    for img_bytes, mime in images:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime,
                "data": base64.standard_b64encode(img_bytes).decode(),
            },
        })
    if user_text:
        content.append({"type": "text", "text": user_text})
    resp = client.messages.create(
        model=model or _claude_model(),
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system_prompt,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": content}],
    )
    return "".join(
        block.text for block in resp.content if getattr(block, "type", None) == "text"
    )


def generate_vision_gemini(
    system_prompt: str,
    images: list[tuple[bytes, str]],
    user_text: str = "",
    model: str | None = None,
) -> str:
    """Gemini Vision 호출. images = [(bytes, mime_type), ...]"""
    from google.genai import types
    client = _gemini_client()
    parts = []
    for img_bytes, mime in images:
        parts.append(types.Part.from_bytes(data=img_bytes, mime_type=mime))
    if user_text:
        parts.append(types.Part.from_text(text=user_text))
    resp = client.models.generate_content(
        model=model or _gemini_model(),
        contents=types.Content(role="user", parts=parts),
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    )
    return resp.text or ""


def generate_vision_gemini_video(
    system_prompt: str,
    video_bytes: bytes,
    mime_type: str,
    user_text: str = "",
    model: str | None = None,
    display_name: str = "video",
    poll_interval_sec: float = 2.0,
    poll_timeout_sec: float = 300.0,
    cleanup: bool = True,
) -> str:
    """Gemini 동영상 분석.

    Files API에 업로드 → ACTIVE 대기 → generate_content 호출 → (옵션) 파일 삭제.
    Claude는 동영상 미지원이므로 이 함수는 Gemini 전용.

    Args:
        video_bytes: 동영상 raw bytes.
        mime_type: 'video/mp4', 'video/quicktime', 'video/webm' 등.
        cleanup: 호출 후 업로드된 파일을 Files API에서 삭제할지. 기본 True.
    """
    import io as _io
    import time

    from google.genai import types

    client = _gemini_client()

    # 1) 업로드
    upload_buf = _io.BytesIO(video_bytes)
    try:
        uploaded = client.files.upload(
            file=upload_buf,
            config=types.UploadFileConfig(
                mime_type=mime_type,
                display_name=display_name,
            ),
        )
    except Exception as e:
        raise RuntimeError(f"Gemini Files 업로드 실패: {type(e).__name__}: {e}")

    file_name = uploaded.name  # "files/xxxx" 형태

    # 2) 처리 완료 대기 (PROCESSING → ACTIVE)
    deadline = time.monotonic() + poll_timeout_sec
    while True:
        # 상태값이 enum인 경우와 문자열인 경우를 모두 처리
        state = getattr(uploaded, "state", None)
        state_str = state.name if hasattr(state, "name") else str(state)
        if state_str == "ACTIVE":
            break
        if state_str == "FAILED":
            raise RuntimeError(f"Gemini Files 처리 실패: {file_name}")
        if time.monotonic() > deadline:
            raise TimeoutError(f"Gemini Files 처리 타임아웃 ({poll_timeout_sec}s): {file_name}")
        time.sleep(poll_interval_sec)
        uploaded = client.files.get(name=file_name)

    # 3) 분석 호출
    try:
        # 파일 객체를 직접 넘기면 video_metadata 등 extra 필드로 Pydantic 오류 발생.
        # URI 참조 방식으로 Part를 명시 구성한다.
        file_part = types.Part.from_uri(
            file_uri=uploaded.uri,
            mime_type=mime_type,
        )
        parts: list = [file_part]
        if user_text:
            parts.append(types.Part.from_text(text=user_text))
        resp = client.models.generate_content(
            model=model or _gemini_model(),
            contents=types.Content(role="user", parts=parts),
            config=types.GenerateContentConfig(system_instruction=system_prompt),
        )
        return resp.text or ""
    finally:
        # 4) 정리 (실패해도 무시)
        if cleanup:
            try:
                client.files.delete(name=file_name)
            except Exception:
                pass


def generate_vision_both(
    system_prompt: str,
    images: list[tuple[bytes, str]],
    user_text: str = "",
    claude_model: str | None = None,
    gemini_model: str | None = None,
) -> dict[str, str]:
    """Claude + Gemini Vision 병렬 호출. 한쪽 실패해도 다른 쪽은 반환."""
    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_c = ex.submit(generate_vision_claude, system_prompt, images, user_text, 4096, claude_model)
        fut_g = ex.submit(generate_vision_gemini, system_prompt, images, user_text, gemini_model)
        try:
            results["claude"] = fut_c.result()
        except Exception as e:
            results["claude"] = f"[ERROR] {type(e).__name__}: {e}"
        try:
            results["gemini"] = fut_g.result()
        except Exception as e:
            results["gemini"] = f"[ERROR] {type(e).__name__}: {e}"
    return results


def generate_both(
    system_prompt: str,
    user_input: str,
    claude_model: str | None = None,
    gemini_model: str | None = None,
) -> dict[str, str]:
    """Claude와 Gemini를 병렬 호출. 한쪽 실패해도 다른 쪽 결과는 반환."""
    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_c = ex.submit(generate_claude, system_prompt, user_input, 8192, claude_model)
        fut_g = ex.submit(generate_gemini, system_prompt, user_input, gemini_model)
        try:
            results["claude"] = fut_c.result()
        except Exception as e:
            results["claude"] = f"[ERROR] {type(e).__name__}: {e}"
        try:
            results["gemini"] = fut_g.result()
        except Exception as e:
            results["gemini"] = f"[ERROR] {type(e).__name__}: {e}"
    return results
