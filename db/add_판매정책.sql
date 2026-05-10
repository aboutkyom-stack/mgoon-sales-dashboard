-- 판매 정책 옵션 컬럼 추가
-- 변경 사항:
--   (신규) 환불보장  BOOLEAN DEFAULT FALSE  ← 100% 환불 보장 옵션 (활성 시 01~05 단계에서 필요시 활용)
--   (신규) 무료배송  BOOLEAN DEFAULT FALSE  ← 무료 배송 옵션 (활성 시 01~05 단계에서 필요시 활용)

ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 환불보장 BOOLEAN DEFAULT FALSE;
ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 무료배송 BOOLEAN DEFAULT FALSE;
