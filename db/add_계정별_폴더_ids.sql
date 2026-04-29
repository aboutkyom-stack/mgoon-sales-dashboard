-- ============================================================
-- 상품.계정별_폴더_ids JSONB 컬럼 추가
-- 목적: 한 상품이 여러 Google Drive 계정에 분산된 폴더를 가질 수 있게.
--        예: {"account1_voyager": "folder_xxx", "account2_donnamoo": "folder_yyy"}
-- 기존 단일 컬럼 드라이브_폴더_id는 호환성을 위해 유지 (deprecated).
-- 실행: db/run_add_계정별_폴더_ids.py 또는 Supabase SQL Editor에서 직접
-- 멱등(IF NOT EXISTS) — 재실행 안전.
-- ============================================================

-- 1) 컬럼 추가 (기본값 빈 JSON 객체)
ALTER TABLE 상품
    ADD COLUMN IF NOT EXISTS 계정별_폴더_ids JSONB NOT NULL DEFAULT '{}'::jsonb;

-- 2) 기존 드라이브_폴더_id 데이터 마이그레이션
--    상품_파일.계정 정보로 어느 계정 폴더인지 추정 (가장 많은 파일을 가진 계정)
WITH 상품_주_계정 AS (
    SELECT 상품_id, 계정
    FROM (
        SELECT 상품_id,
               계정,
               ROW_NUMBER() OVER (
                   PARTITION BY 상품_id
                   ORDER BY COUNT(*) DESC
               ) AS rn
        FROM 상품_파일
        WHERE 계정 IS NOT NULL
        GROUP BY 상품_id, 계정
    ) t
    WHERE rn = 1
)
UPDATE 상품 s
SET 계정별_폴더_ids = jsonb_build_object(spa.계정, s.드라이브_폴더_id)
FROM 상품_주_계정 spa
WHERE s.id = spa.상품_id
  AND s.드라이브_폴더_id IS NOT NULL
  AND s.드라이브_폴더_id != ''
  AND (s.계정별_폴더_ids = '{}'::jsonb);

-- 3) 인덱스 (계정별 검색용 GIN 인덱스, 선택)
CREATE INDEX IF NOT EXISTS idx_상품_계정별_폴더_ids ON 상품 USING GIN (계정별_폴더_ids);
