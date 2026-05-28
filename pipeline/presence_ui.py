"""사이드바 접속자 배지 — owner 전용 표시 + 모든 사용자 heartbeat.

페이지마다 진입 직후 1회 호출:
    from pipeline.presence_ui import render_접속자_배지
    render_접속자_배지()

스키마(접속_세션): 세션_id PK + 사용자명. 동일 username 다중 세션 카운트 가능.
"""
from __future__ import annotations

import time
import uuid
from collections import Counter
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


def _get_session_id() -> str:
    """이 브라우저 세션 고유 UUID. session_state에 1회 생성 후 재사용."""
    sid = st.session_state.get("_presence_session_id")
    if not sid:
        sid = uuid.uuid4().hex
        st.session_state["_presence_session_id"] = sid
    return sid


def render_접속자_배지() -> None:
    """사이드바 활성 접속자 표시 + heartbeat upsert.

    - heartbeat upsert는 **모든 사용자**가 수행 (owner가 전체 접속자를 볼 수 있게).
    - 배지(사이드바 expander) **표시**만 owner 전용.
    페이지 진입 직후 1회 호출.
    """
    me = current_username()
    sid = _get_session_id()

    # 1) heartbeat upsert (30초 debounce) — 모든 사용자
    _now = time.time()
    if _now - st.session_state.get("_presence_last_upsert", 0) > _HEARTBEAT_DEBOUNCE_SEC:
        try:
            upsert_접속_세션(sid, me)
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

    # 3) 사이드바 배지 — username별 그룹화 + 세션 카운트
    name_counts = Counter(row.get("사용자명") or "?" for row in active)
    # 그룹별 가장 최근 활동시각
    last_seen: dict[str, str] = {}
    for row in active:
        n = row.get("사용자명") or "?"
        ts = row.get("마지막_활동시각", "") or ""
        if n not in last_seen or ts > last_seen[n]:
            last_seen[n] = ts

    total_sessions = len(active)

    with st.sidebar:
        with st.expander(f"👥 접속 중 {total_sessions}명", expanded=False):
            for name, cnt in name_counts.most_common():
                tag = " (나)" if name == me else ""
                multi = f" ×{cnt}" if cnt > 1 else ""
                hhmm = _format_kst_hhmm(last_seen.get(name, ""))
                st.caption(f"• {name}{tag}{multi} · {hhmm}")
