"""실행 환경 감지 헬퍼.

로컬(개발자 PC) vs Streamlit Cloud(공유 호스팅) 구분.
role.py는 사용자 권한(owner/partner)을, 본 모듈은 실행 환경을 담당 — 별개 차원.
"""
from __future__ import annotations

import os


def is_streamlit_cloud() -> bool:
    """Streamlit Community Cloud에서 실행 중인지 판별.

    감지 신호 (하나라도 true이면 Cloud로 간주):
    - HOSTNAME이 "streamlit"으로 시작 (Cloud 컨테이너 호스트명 패턴)
    - STREAMLIT_SHARING_MODE 환경변수 존재
    - STREAMLIT_RUNTIME 환경변수 존재
    """
    hostname = (os.getenv("HOSTNAME") or "").lower()
    if hostname.startswith("streamlit"):
        return True
    if os.getenv("STREAMLIT_SHARING_MODE"):
        return True
    if os.getenv("STREAMLIT_RUNTIME"):
        return True
    return False
