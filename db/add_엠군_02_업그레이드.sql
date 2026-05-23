-- ============================================================
-- 엠군_포지셔닝 테이블 업그레이드 (통합본 신규 필드 반영)
-- 목적: 대화형2 진화로 추가된 02 신규 필드를 컬럼으로 보존
-- 추가 컬럼:
--   - category_objections        JSONB   [{objection, counter, source}, ...]
--   - rule_engine_inputs         JSONB   {구매편익, 관여도, 경쟁강도, 타겟지능, 결핍유형, R복잡도}
--   - rule_engine_flags          JSONB   {재구매_제품, 호환성_불안_있음, 차별점_명확, 구매핵심가치_이동_필요, 구매핵심가치_이동_근거}
--   - persuasion_method_candidates JSONB [{method, reason}, ...]
-- 멱등 (IF NOT EXISTS) — 재실행 안전
-- 실행: db/run_add_엠군_업그레이드.py
-- ============================================================

ALTER TABLE 엠군_포지셔닝
  ADD COLUMN IF NOT EXISTS category_objections JSONB,
  ADD COLUMN IF NOT EXISTS rule_engine_inputs JSONB,
  ADD COLUMN IF NOT EXISTS rule_engine_flags JSONB,
  ADD COLUMN IF NOT EXISTS persuasion_method_candidates JSONB;

-- 검색용 인덱스 (필요 시. 운영하면서 쿼리 패턴 보고 결정)
-- CREATE INDEX IF NOT EXISTS idx_포지셔닝_결핍유형
--   ON 엠군_포지셔닝 ((rule_engine_inputs->>'결핍유형'));
-- CREATE INDEX IF NOT EXISTS idx_포지셔닝_관여도
--   ON 엠군_포지셔닝 (((rule_engine_inputs->>'관여도')::int));

COMMENT ON COLUMN 엠군_포지셔닝.category_objections IS
  '카테고리 의심 반론. 04_a 핵심 반론 선제 처리 블록(풀세트 3.5단계) 직접 입력. 형식: [{objection, counter, source}, ...]';

COMMENT ON COLUMN 엠군_포지셔닝.rule_engine_inputs IS
  'Rule Engine 6변수. 04_a ENGINE_PLAN 생성 입력. 형식: {구매편익, 관여도, 경쟁강도, 타겟지능, 결핍유형, R복잡도}';

COMMENT ON COLUMN 엠군_포지셔닝.rule_engine_flags IS
  'Rule Engine 4플래그. 04_a ENGINE_PLAN 생성 입력. 형식: {재구매_제품, 호환성_불안_있음, 차별점_명확, 구매핵심가치_이동_필요, 구매핵심가치_이동_근거}';

COMMENT ON COLUMN 엠군_포지셔닝.persuasion_method_candidates IS
  '02에서 도출한 설득 방식 후보. 04_a 설득 방식 선택 근거. 형식: [{method, reason}, ...]';
