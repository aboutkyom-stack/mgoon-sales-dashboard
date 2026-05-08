-- 가격 컬럼 정정 + 온라인판매가격 신설
-- 변경 사항:
--   실제가     → 실제받는가격
--   평균도매가 → 평균입고가
--   (신규)     온라인판매가격 INTEGER  ← 00~05 단계가 우선 참조하는 현재 판매가
-- 적용 전: 백업 권장. 한글 컬럼은 따옴표 필수.
-- 주의: BOOLEAN '온라인판매가능'과 헷갈리지 않도록 컬럼명을 '온라인판매가격'으로 명확히 구분.

ALTER TABLE 상품 RENAME COLUMN 실제가 TO 실제받는가격;
ALTER TABLE 상품 RENAME COLUMN 평균도매가 TO 평균입고가;
ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 온라인판매가격 INTEGER;
