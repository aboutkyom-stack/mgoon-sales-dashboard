-- ============================================================
-- is_test 컬럼 추가
-- 목적: 테스트 레코드와 운영 레코드 구분
-- 실행: db/run_add_is_test.py 또는 Supabase SQL Editor에서 직접
-- 멱등(IF NOT EXISTS 포함) — 재실행 안전
-- ============================================================

ALTER TABLE 상품
    ADD COLUMN IF NOT EXISTS is_test BOOLEAN NOT NULL DEFAULT false;
