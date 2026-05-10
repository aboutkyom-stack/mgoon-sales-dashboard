"""Claude + Gemini 호출 추상화.

- Claude: anthropic SDK, system prompt + user message
- Gemini: google-genai SDK, system_instruction + contents
- generate_both: 두 모델 병렬 호출해 교차검증용

Claude는 system 블록에 cache_control을 붙여 prompt caching으로 비용 절감
(시스템 프롬프트는 MD 세트 전체라 대용량·재사용이 잦음).
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _log_claude_cache(label: str, resp) -> None:
    """Claude 응답의 prompt caching 통계를 stderr로 출력.

    cache_read=0, cache_creation>0 → 첫 호출 (캐시 생성, 90% 할인 미적용)
    cache_read>0                   → 캐시 hit (system prompt 90% 할인 적용)
    cache_read=0, cache_creation=0 → cache_control 미설정 또는 캐시 미적용
    """
    try:
        u = resp.usage
        cache_read = getattr(u, "cache_read_input_tokens", 0) or 0
        cache_created = getattr(u, "cache_creation_input_tokens", 0) or 0
        inp = getattr(u, "input_tokens", 0) or 0
        out = getattr(u, "output_tokens", 0) or 0
        print(
            f"[claude cache:{label}] read={cache_read} created={cache_created} "
            f"input={inp} output={out}",
            file=sys.stderr,
        )
    except Exception:
        pass


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
    _log_claude_cache("text", resp)
    return "".join(
        block.text for block in resp.content if getattr(block, "type", None) == "text"
    )


def generate_gemini(
    system_prompt: str,
    user_input: str,
    model: str | None = None,
    max_output_tokens: int | None = None,
) -> str:
    from google.genai import types
    client = _gemini_client()
    config_kwargs: dict = {"system_instruction": system_prompt}
    if max_output_tokens is not None:
        config_kwargs["max_output_tokens"] = max_output_tokens
    resp = client.models.generate_content(
        model=model or _gemini_model(),
        contents=[user_input],
        config=types.GenerateContentConfig(**config_kwargs),
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


def generate_vision_claude_stream(
    system_prompt: str,
    images: list[tuple[bytes, str]],
    user_text: str = "",
    max_tokens: int = 4096,
    model: str | None = None,
):
    """Claude Vision 스트리밍. 텍스트 청크를 yield하는 generator.

    호출부는 누적 변수에 chunk를 더해가며 UI를 실시간 갱신할 수 있다.
    호출 종료 시 누적 결과 == 비스트리밍 generate_vision_claude의 반환값과 동일.
    """
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
    with client.messages.stream(
        model=model or _claude_model(),
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system_prompt,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": content}],
    ) as stream:
        for text in stream.text_stream:
            yield text


def generate_vision_gemini_stream(
    system_prompt: str,
    images: list[tuple[bytes, str]],
    user_text: str = "",
    model: str | None = None,
):
    """Gemini Vision 스트리밍. 텍스트 청크를 yield하는 generator."""
    from google.genai import types
    client = _gemini_client()
    parts = []
    for img_bytes, mime in images:
        parts.append(types.Part.from_bytes(data=img_bytes, mime_type=mime))
    if user_text:
        parts.append(types.Part.from_text(text=user_text))
    for chunk in client.models.generate_content_stream(
        model=model or _gemini_model(),
        contents=types.Content(role="user", parts=parts),
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    ):
        if chunk.text:
            yield chunk.text


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
    """Claude + Gemini Vision 병렬 호출. 모델이 None이면 해당 family는 호출 생략."""
    results: dict[str, str] = {"claude": "", "gemini": ""}
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_c = ex.submit(generate_vision_claude, system_prompt, images, user_text, 4096, claude_model) if claude_model else None
        fut_g = ex.submit(generate_vision_gemini, system_prompt, images, user_text, gemini_model) if gemini_model else None
        if fut_c is not None:
            try:
                results["claude"] = fut_c.result()
            except Exception as e:
                results["claude"] = f"[ERROR] {type(e).__name__}: {e}"
        if fut_g is not None:
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
    max_tokens: int = 8192,
) -> dict[str, str]:
    """Claude/Gemini 병렬 호출. 모델이 None이면 해당 family는 호출 생략 (빈 문자열).

    max_tokens: Claude의 max_tokens 및 Gemini의 max_output_tokens에 동일하게 적용.
                기본 8192. 출력 길이가 매우 긴 단계(예: 04-1 이미지 디렉션 7섹션+JSON)는
                호출자가 더 큰 값(16384, 32000 등)을 명시한다.
    """
    results: dict[str, str] = {"claude": "", "gemini": ""}
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_c = ex.submit(generate_claude, system_prompt, user_input, max_tokens, claude_model) if claude_model else None
        fut_g = ex.submit(generate_gemini, system_prompt, user_input, gemini_model, max_tokens) if gemini_model else None
        if fut_c is not None:
            try:
                results["claude"] = fut_c.result()
            except Exception as e:
                results["claude"] = f"[ERROR] {type(e).__name__}: {e}"
        if fut_g is not None:
            try:
                results["gemini"] = fut_g.result()
            except Exception as e:
                results["gemini"] = f"[ERROR] {type(e).__name__}: {e}"
    return results
