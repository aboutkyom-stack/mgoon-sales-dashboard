-- 상품 테이블에 엠군작업대상 컬럼 추가 (멱등)
-- 동료가 작업 요청 표시 → owner가 Claude Code로 파이프라인 실행하는 워크플로우용

ALTER TABLE 상품
    ADD COLUMN IF NOT EXISTS "엠군작업대상" BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_상품_엠군작업대상 ON 상품("엠군작업대상");
