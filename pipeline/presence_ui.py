"""사이드바 접속자 배지 — owner 전용.

is_owner() 체크 후 사이드바 상단에 활성 접속자 수/이름 배지 렌더.
heartbeat upsert도 함께 처리 (30초 debounce).

페이지마다 진입 직후 1회 호출:
    from pipeline.presence_ui import render_접속자_배지
    render_접속자_배지()
"""
from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta

import streamlit as st

from pipeline.role import current_username, is_owner
from pipeline.supabase_read import (
    get_active_접속_세션,
    upsert_접속_세션,
)

_HEARTBEAT_DEBOUNCE_SEC = 30
_TTL_MIN = 2
_KST = timezone(timedelta(hours=9))


def _format_kst_hhmm(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_KST).strftime("%H:%M")
    except Exception:
        return iso_str[11:16] if len(iso_str) >= 16 else iso_str


def render_접속자_배지() -> None:
    """사이드바 활성 접속자 표시 + heartbeat upsert.

    - heartbeat upsert는 **모든 사용자**가 수행해야 owner가 전체 접속자를 볼 수 있다.
    - 배지(사이드바 expander) **표시**만 owner 전용(동료에게는 노출 X).
    페이지 진입 직후 1회 호출.
    """
    me = current_username()

    # 1) heartbeat upsert (30초 debounce) — owner/partner 무관 모두 수행
    _now = time.time()
    if _now - st.session_state.get("_presence_last_upsert", 0) > _HEARTBEAT_DEBOUNCE_SEC:
        try:
            upsert_접속_세션(me)
            st.session_state["_presence_last_upsert"] = _now
        except Exception:
            pass

    # 2) 배지 표시는 owner에게만
    if not is_owner():
        return

    try:
        active = get_active_접속_세션(ttl_min=_TTL_MIN)
    except Exception:
        return

    if not active:
        return

    # 3) 사이드바 배지 (expander — 평소엔 숫자만, 클릭 시 이름 펼침)
    with st.sidebar:
        with st.expander(f"👥 접속 중 {len(active)}명", expanded=False):
            for row in active:
                name = row.get("사용자명") or "?"
                tag = " (나)" if name == me else ""
                hhmm = _format_kst_hhmm(row.get("마지막_활동시각", "") or "")
                st.caption(f"• {name}{tag} · {hhmm}")
