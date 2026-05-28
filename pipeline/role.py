"""앱 역할(owner / partner) 판별 + 사용자 식별 헬퍼.

.env 또는 Streamlit Cloud secrets의 APP_ROLE 값을 읽는다.
  - owner : AI API 기능 전체 사용 가능 (기본값)
  - partner : AI API 기능 비활성화, 스펙/이미지/결과 조회만 가능

사용자명(편집/접속 세션 식별)은 Streamlit Cloud Restricted access의
Google SSO 이메일을 우선 사용. 로컬·SSO 미인증 시 APP_ROLE 기반으로 fallback.
"""
from __future__ import annotations

import os

import streamlit as st


def is_owner() -> bool:
    """APP_ROLE이 'owner'이거나 미설정이면 True."""
    return os.getenv("APP_ROLE", "owner").strip().lower() != "partner"


def _sso_email() -> str:
    """Streamlit Cloud Restricted access에서 로그인한 Google 이메일.

    로컬·SSO 미인증 시 빈 문자열. streamlit 1.42+의 `st.user`와
    이전 버전의 `st.experimental_user` 양쪽 시도, 각각 attribute/dict 접근 모두 fallback.
    """
    for attr in ("user", "experimental_user"):
        try:
            user_obj = getattr(st, attr, None)
            if user_obj is None:
                continue
            # 1) attribute access (st.user.email)
            email = getattr(user_obj, "email", None)
            # 2) dict-style access (st.experimental_user["email"])
            if not email:
                try:
                    email = user_obj["email"]
                except Exception:
                    email = None
            # 3) to_dict() fallback
            if not email:
                try:
                    d = user_obj.to_dict()
                    if isinstance(d, dict):
                        email = d.get("email")
                except Exception:
                    pass
            if email:
                return str(email).strip()
        except Exception:
            continue
    return ""


def current_username() -> str:
    """편집/접속 세션 식별자.

    1순위: Streamlit Cloud SSO 이메일 앞부분 (예: aboutkyom@gmail.com → 'aboutkyom')
    2순위: APP_ROLE 기반 ('owner(나)' / 'partner(동료)') — 로컬·SSO 미인증 fallback
    """
    email = _sso_email()
    if email:
        return email.split("@", 1)[0] if "@" in email else email
    return "owner(나)" if is_owner() else "partner(동료)"
