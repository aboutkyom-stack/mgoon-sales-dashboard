-- ============================================================
-- 상품.수정일 자동 갱신 트리거 추가
-- 목적: 모든 UPDATE 시 수정일 = NOW() 자동 적용 → 낙관적 락 동작 보장
-- 결정 로그: docs/decisions/2026-05-25_streamlit_cloud_배포.md §2-6 A (부록: 결정 로그 작성 시점에는 수정일이 자동 갱신된다고 가정했으나 실제로는 DEFAULT NOW()만 있었음 → 트리거 추가로 보강)
-- 실행: db/run_add_상품_수정일_트리거.py 또는 Supabase SQL Editor에서 직접
-- 멱등: CREATE OR REPLACE FUNCTION + DROP TRIGGER IF EXISTS + CREATE TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION trg_상품_수정일_갱신()
RETURNS TRIGGER AS $$
BEGIN
    NEW."수정일" = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS 상품_수정일_갱신 ON 상품;

CREATE TRIGGER 상품_수정일_갱신
    BEFORE UPDATE ON 상품
    FOR EACH ROW
    EXECUTE FUNCTION trg_상품_수정일_갱신();
