-- ============================================================
-- 엠군_실행: 대화형 '시도' 구분 컬럼 추가
-- ------------------------------------------------------------
-- 목적: 한 상품(상품_id 고정)에 대해 여러 대화형 시도(타겟·결핍 조합)를
--       엠군_실행 행으로 구분한다. 제품을 쪼개지 않고(= 상품 1 : 실행 N)
--       Drive 자료·가격·스펙 중복 없이 '그물 치기'를 표현하기 위함.
--       대화형 → Supabase 적재의 실행 식별 단위.
-- 멱등: ADD COLUMN IF NOT EXISTS / CREATE UNIQUE INDEX IF NOT EXISTS — 재실행 안전.
-- 매핑 문서: 대화형/agents/_shared/db_적재_매핑.md (5장)
-- 실행: db/run_add_엠군_실행_시도구분.py
-- ============================================================

ALTER TABLE 엠군_실행
  ADD COLUMN IF NOT EXISTS 시도_키        TEXT,         -- 한글 짧은 키 (예: '전원생활자-자유')
  ADD COLUMN IF NOT EXISTS 시도_라벨      TEXT,         -- 사람용 설명 라벨
  ADD COLUMN IF NOT EXISTS 타겟_가설      TEXT,         -- 이 시도의 타겟 가설
  ADD COLUMN IF NOT EXISTS 결핍_가설      TEXT,         -- 이 시도의 결핍 각도
  ADD COLUMN IF NOT EXISTS 모드          TEXT DEFAULT 'auto',  -- 'interactive' | 'auto'
  ADD COLUMN IF NOT EXISTS 대화형_폴더명  TEXT,         -- items/item_X/run_Y 역추적용
  ADD COLUMN IF NOT EXISTS 버전          INTEGER DEFAULT 1;    -- 같은 시도 재작업 버전

-- 멱등 재적재용 유니크: 같은 상품의 같은 (시도_키, 버전)은 1행.
-- 기존 auto 실행 행은 시도_키 NULL → Postgres에서 NULL은 유니크 충돌하지 않으므로
-- 여러 NULL 행이 공존 가능(기존 데이터 안전). 대화형 실행은 시도_키가 항상 채워져 충돌 감지됨.
CREATE UNIQUE INDEX IF NOT EXISTS uq_엠군_실행_시도
  ON 엠군_실행(상품_id, 시도_키, 버전);
