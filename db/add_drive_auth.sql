-- ============================================================
-- drive_auth 테이블 추가
-- 목적: Google Drive OAuth refresh_token을 Supabase에 동기화 → Streamlit Cloud(partner)도 토큰 사용 가능
-- 결정 로그: docs/decisions/2026-05-25_streamlit_cloud_배포.md §2-5
-- 실행: db/run_add_drive_auth.py 또는 Supabase SQL Editor에서 직접
-- ============================================================

CREATE TABLE IF NOT EXISTS drive_auth (
    id              BIGSERIAL PRIMARY KEY,
    account_name    TEXT NOT NULL UNIQUE,    -- voyager / donnamoo / kyom 등
    refresh_token   TEXT NOT NULL,
    client_id       TEXT NOT NULL,
    client_secret   TEXT NOT NULL,
    token_uri       TEXT NOT NULL DEFAULT 'https://oauth2.googleapis.com/token',
    scopes          TEXT[] NOT NULL DEFAULT ARRAY['https://www.googleapis.com/auth/drive'],
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
