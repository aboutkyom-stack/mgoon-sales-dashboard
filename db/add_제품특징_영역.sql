-- 제품특징 영역 재구성
-- 변경 사항:
--   (신규) 제품특징_bullet JSONB DEFAULT '[]'  ← 스펙 탭, 비전패스 자동 추출 + 판매자 수정, 01~05 시스템 참고 ✅
--   (신규) 제품특징_추가   TEXT                ← 판매자 정보 탭, 판매자 수동 입력, 01~05 시스템 참고 ✅
--   (재정의) 판매자메모    TEXT                ← 판매자 정보 탭, 판매자 개인 메모, 시스템 미참조 (D항 excluded_fields)
-- 데이터 이관:
--   기존 '특징' 컬럼 텍스트를 줄바꿈 단위로 split → 빈 줄 제거 → 제품특징_bullet에 JSON 배열로 저장
-- 기존 '특징' 컬럼은 안전을 위해 일정 기간 유지 후 별도 마이그레이션으로 제거.
-- 적용 전: 백업 권장. 한글 컬럼은 따옴표 필수.

ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 제품특징_bullet JSONB DEFAULT '[]'::jsonb;
ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 제품특징_추가 TEXT;

-- 기존 '특징' 텍스트 → JSON 배열로 이관 (제품특징_bullet이 비어있는 row만)
UPDATE 상품
SET 제품특징_bullet = COALESCE((
    SELECT jsonb_agg(trim(line))
    FROM unnest(string_to_array(특징, E'\n')) AS line
    WHERE trim(line) <> ''
), '[]'::jsonb)
WHERE 특징 IS NOT NULL
  AND trim(특징) <> ''
  AND (제품특징_bullet IS NULL OR 제품특징_bullet = '[]'::jsonb);
