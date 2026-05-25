-- ============================================================
-- 편집_세션 테이블 추가
-- 목적: 동시편집 보호 — 같은 상품을 누가 편집 중인지 사회적 조정 (옵션 B)
-- 결정 로그: docs/decisions/2026-05-25_streamlit_cloud_배포.md §2-6
-- 실행: db/run_add_편집_세션.py 또는 Supabase SQL Editor에서 직접
-- ============================================================

CREATE TABLE IF NOT EXISTS 편집_세션 (
    id              BIGSERIAL PRIMARY KEY,
    상품_id         BIGINT NOT NULL REFERENCES 상품(id) ON DELETE CASCADE,
    사용자명        TEXT NOT NULL,         -- "owner(나)" / "partner(동료)"
    마지막_활동시각 TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (상품_id, 사용자명)
);

CREATE INDEX IF NOT EXISTS idx_편집세션_상품 ON 편집_세션(상품_id);
