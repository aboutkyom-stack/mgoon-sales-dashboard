-- ============================================================
-- app_settings 테이블 추가
-- 목적: 전역 앱 설정(기존 settings.json)을 Supabase에 동기화
--       → 로컬 작업자(owner)와 Streamlit Cloud(partner)가 같은 설정 공유
-- 구조: 단일 행(id=1)에 전체 설정을 JSONB로 보관
--       (통째 교체 / last-write-wins — 항목별 행 분리 안 함)
-- 결정 로그: docs/decisions/2026-06-12_settings_supabase_이전.md
-- 실행: db/run_add_app_settings.py (psycopg2 직접) 또는 Supabase SQL Editor
-- ============================================================

CREATE TABLE IF NOT EXISTS app_settings (
    id          INT PRIMARY KEY DEFAULT 1,
    data        JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    -- 단일 행만 허용 (전역 설정 1벌)
    CONSTRAINT app_settings_singleton CHECK (id = 1)
);
