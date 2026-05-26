"""Drive 계정 대시보드.

연동된 Google Drive OAuth 계정별 quota / 파일 수 / 토큰 상태를 한눈에 본다.
- 등록된 계정(`drive_client.ACCOUNTS`) 카드 표시
- 추천 다음 업로드 계정 (잔여 용량 가장 많은 정상 계정)
- OAuth 재인증 가이드 (만료 시 로컬에서 refresh_oauth_token.py 실행 안내)
"""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from pipeline.drive_client import ACCOUNTS, get_account_quota
from pipeline.supabase_read import count_파일_by_계정, get_drive_token

st.title("☁️ Drive 계정 대시보드")
st.caption("연동된 Google Drive OAuth 계정의 사용량 · 파일수 · 토큰 상태")


@st.cache_data(ttl=60, show_spinner=False)
def _gather() -> list[dict]:
    """모든 계정의 quota + 파일수 + drive_auth 동기화 시각을 한 번에 모은다.

    60초 캐시 — Drive API quota 호출 부담 완화.
    """
    counts = count_파일_by_계정()
    results: list[dict] = []
    for acc in ACCOUNTS:
        q = get_account_quota(acc["name"])
        token = get_drive_token(acc["name"])
        q["파일수"] = counts.get(acc["name"], 0)
        q["token_synced_at"] = token.get("updated_at") if token else None
        results.append(q)
    return results


def _fmt_size(b: int) -> str:
    if b is None or b <= 0:
        return "0 GB"
    return f"{b / 1024 ** 3:.2f} GB"


def _fmt_dt(s: str | None) -> str:
    if not s:
        return "—"
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return s[:16]


with st.spinner("계정 정보 조회 중…"):
    rows = _gather()

# 추천 다음 업로드 계정 — 정상 계정 중 free 최대
healthy = [r for r in rows if not r.get("error") and r.get("total", 0) > 0]
top_c1, top_c2 = st.columns([4, 1])
with top_c1:
    if healthy:
        rec = max(healthy, key=lambda r: r["free"])
        st.success(
            f"💡 추천 다음 업로드 계정: **{rec['name']}** "
            f"({rec['역할'] or '—'}) · 잔여 **{_fmt_size(rec['free'])}**"
        )
    else:
        st.warning("⚠️ 사용 가능한 정상 계정이 없습니다 — 카드별 재인증 가이드 참고")
with top_c2:
    if st.button("🔄 새로고침", help="quota·파일수 캐시 무효화 후 다시 조회"):
        _gather.clear()
        st.rerun()

st.divider()

# 카드 — 계정별
for r in rows:
    with st.container(border=True):
        head_c1, head_c2 = st.columns([3, 2])
        with head_c1:
            st.markdown(f"### {r['name']}  ·  _{r.get('역할') or '—'}_")
            st.caption(r.get("email") or "—")
            if r.get("error"):
                st.error(f"❌ 토큰 무효 · {r['error']}")
            elif r.get("total", 0) == 0:
                st.warning("⚠️ quota 조회 실패 (응답 비어 있음)")
            else:
                st.success("✅ 정상")
        with head_c2:
            st.metric(
                label="잔여 용량",
                value=_fmt_size(r.get("free", 0)),
                delta=f"-{_fmt_size(r.get('used', 0))} 사용",
                delta_color="off",
            )

        pct = max(min(r.get("pct", 0.0), 1.0), 0.0)
        st.progress(
            pct,
            text=(
                f"{_fmt_size(r.get('used', 0))} / {_fmt_size(r.get('total', 0))} · "
                f"{pct * 100:.1f}%"
            ),
        )

        meta_c1, meta_c2, meta_c3 = st.columns(3)
        with meta_c1:
            st.caption(f"📁 업로드 파일 **{r.get('파일수', 0):,}건**")
        with meta_c2:
            st.caption(f"🔑 토큰 동기화 **{_fmt_dt(r.get('token_synced_at'))}**")
        with meta_c3:
            st.caption(f"🏷️ label **{r.get('label', '—')}**")

        # OAuth 재인증 가이드 (1차 구현 — Cloud 내장 callback은 Backlog)
        acc_def = next((a for a in ACCOUNTS if a["name"] == r["name"]), None)
        n = acc_def["n"] if acc_def else "?"
        with st.expander("🔁 OAuth 재인증 가이드"):
            st.markdown(
                "**토큰 만료(`invalid_grant`) 또는 새 권한 필요 시 절차:**\n\n"
                f"1. **로컬 PC**에서 자동화형 폴더 진입\n"
                f"2. `python scripts/refresh_oauth_token.py {r['name']}` 실행\n"
                f"3. 브라우저가 열림 → Google 로그인 → 권한 동의\n"
                f"4. 완료 시 `credentials/token{n}_{r['name']}.pickle` 갱신 + DB `drive_auth` 자동 동기화\n"
                f"5. (Streamlit Cloud 운영 중이면 추가 push 불필요 — Cloud는 DB에서 직접 토큰 read)\n"
            )
            st.info(
                "⚙️ 향후: 대시보드 안에서 동료가 직접 재인증할 수 있게 OAuth callback 통합 예정 "
                "(redirect URI 추가 등록 필요 — Backlog)."
            )
