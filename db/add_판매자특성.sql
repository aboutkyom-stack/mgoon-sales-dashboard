-- 상품 테이블에 판매자특성_선택 컬럼 추가 (멱등)
-- 전역 판매자 특성(settings.json) 중 이 제품에 해당하는 항목의 텍스트 배열
ALTER TABLE 상품
    ADD COLUMN IF NOT EXISTS "판매자특성_선택" TEXT[] DEFAULT '{}';
