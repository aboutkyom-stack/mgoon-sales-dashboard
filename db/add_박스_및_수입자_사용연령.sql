-- 박스(패키지) 치수/소재/색상 + 수입자 + 사용연령 컬럼 추가
-- 변경 사항:
--   (신규) 수입자        TEXT     ← 패키지 표기, 향후 필터로 활용
--   (신규) 사용연령      TEXT     ← 패키지 표기 (예: '3세 이상', '만 6세부터')
--   (신규) 박스_가로_cm  NUMERIC
--   (신규) 박스_세로_cm  NUMERIC
--   (신규) 박스_높이_cm  NUMERIC
--   (신규) 박스_무게_g   NUMERIC
--   (신규) 박스_재질     TEXT     ← 포장재 (예: '종이박스', 'PE백', '블리스터팩')
--   (신규) 박스_색상     TEXT     ← 패키지 주조색
-- 기존 가로_cm/세로_cm/높이_cm/무게_g/재질/색상 = 제품 치수·재질·색상으로 간주.
-- 기존 데이터는 모두 제품용으로 처리 (마이그레이션 시점 사용자 결정).

ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 수입자       TEXT;
ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 사용연령     TEXT;
ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 박스_가로_cm NUMERIC;
ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 박스_세로_cm NUMERIC;
ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 박스_높이_cm NUMERIC;
ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 박스_무게_g  NUMERIC;
ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 박스_재질    TEXT;
ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 박스_색상    TEXT;
