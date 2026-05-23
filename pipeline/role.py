"""앱 역할(owner / partner) 판별 헬퍼.

.env 또는 Streamlit Cloud secrets의 APP_ROLE 값을 읽는다.
  - owner : AI API 기능 전체 사용 가능 (기본값)
  - partner : AI API 기능 비활성화, 스펙/이미지/결과 조회만 가능
"""
from __future__ import annotations

import os


def is_owner() -> bool:
    """APP_ROLE이 'owner'이거나 미설정이면 True."""
    return os.getenv("APP_ROLE", "owner").strip().lower() != "partner"
