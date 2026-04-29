"""계정 표시 관련 UI 유틸리티.

계정명에 색상 dot을 자동 부여하고 짧은 이름을 추출.
계정 추가 시 코드 수정 없이 자동으로 색상이 매핑됨 (해시 기반).
"""
from __future__ import annotations

import hashlib

# 시각적으로 구분 잘 되는 emoji 색상 dot 풀 (⚫는 '미지정' 전용으로 제외)
# 해시 mod로 자동 분배 — 계정 8개까지 충돌 없음, 그 이상은 일부 충돌 허용
_DOT_POOL: list[str] = [
    "🔵", "🟢", "🟣", "🟠", "🔴", "🟡", "🟤", "⚪",
]


def account_color_dot(account_label: str | None) -> str:
    """계정 라벨의 해시값으로 일관된 색상 dot 반환.

    같은 계정명은 항상 같은 색상. 계정 추가 시 자동으로 색상 부여됨.
    """
    if not account_label:
        return "⚫"
    h = int(hashlib.md5(account_label.encode("utf-8")).hexdigest(), 16)
    return _DOT_POOL[h % len(_DOT_POOL)]


def account_short_name(account_label: str | None) -> str:
    """'account1_voyager' → 'voyager' 같이 짧은 이름 추출.

    'accountN_xxx' 패턴이면 'xxx'만, 아니면 그대로 반환.
    """
    if not account_label:
        return "?"
    if account_label.startswith("account") and "_" in account_label:
        return account_label.split("_", 1)[1]
    return account_label


def account_badge(
    account_label: str | None,
    *,
    with_dot: bool = True,
    with_short: bool = True,
    with_full: bool = False,
) -> str:
    """계정 배지 문자열.

    예시:
        account_badge('account1_voyager') -> '🔵 voyager'
        account_badge('account1_voyager', with_full=True) -> '🔵 voyager (account1_voyager)'
        account_badge(None) -> '⚫ 미지정'
    """
    if not account_label:
        return "⚫ 미지정"
    parts: list[str] = []
    if with_dot:
        parts.append(account_color_dot(account_label))
    if with_short:
        parts.append(account_short_name(account_label))
    text = " ".join(parts)
    if with_full and account_short_name(account_label) != account_label:
        text += f" ({account_label})"
    return text
