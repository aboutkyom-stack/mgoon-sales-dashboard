-- ============================================================
-- 비전패스_이력 테이블 추가
-- 목적: 이미지별/일괄 Vision Pass 실행 결과를 영구 보존
-- 실행: db/run_add_비전패스_이력.py 또는 Supabase SQL Editor에서 직접
-- ============================================================

CREATE TABLE IF NOT EXISTS 비전패스_이력 (
    id          BIGSERIAL PRIMARY KEY,
    상품_id     BIGINT NOT NULL REFERENCES 상품(id) ON DELETE CASCADE,
    파일_id     TEXT,           -- 드라이브 파일 ID. NULL이면 일괄실행 결과
    모델명      TEXT NOT NULL,
    프롬프트    TEXT,           -- 실행 시점 프롬프트 스냅샷 (재현/디버깅용)
    결과        TEXT NOT NULL,
    실행_모드   TEXT,           -- 'single' (이미지별) | 'bulk' (일괄)
    생성일      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_비전패스_상품_파일 ON 비전패스_이력(상품_id, 파일_id);
CREATE INDEX IF NOT EXISTS idx_비전패스_상품_생성일 ON 비전패스_이력(상품_id, 생성일 DESC);
