-- 엠군 파이프라인 결과 테이블 재구축
-- 영문 mgoon_* 테이블 폐기 후 한글 테이블로 신규 생성
-- (다른 한글 테이블 — 상품 / 상품_파일 / 비전패스_이력 — 과 명명 일관성)

-- 기존 영문 테이블 폐기 (CASCADE로 FK도 함께 정리)
DROP TABLE IF EXISTS mgoon_positioning CASCADE;
DROP TABLE IF EXISTS mgoon_targets CASCADE;
DROP TABLE IF EXISTS mgoon_runs CASCADE;

-- 엠군_실행: 한 제품에 대한 1회 파이프라인 실행 단위
CREATE TABLE IF NOT EXISTS 엠군_실행 (
    id              BIGSERIAL PRIMARY KEY,
    상품_id         BIGINT REFERENCES 상품(id) ON DELETE SET NULL,
    제품명          TEXT NOT NULL,
    제품_스냅샷     TEXT NOT NULL,
    생성일          TIMESTAMPTZ DEFAULT NOW()
);

-- 엠군_타겟: 01 결핍·타겟 결과의 모든 타겟 후보를 모델별로 저장
-- (1 실행 × 2 모델 × 타겟 N개 = 보통 6~8개 행)
CREATE TABLE IF NOT EXISTS 엠군_타겟 (
    id                  BIGSERIAL PRIMARY KEY,
    실행_id             BIGINT NOT NULL REFERENCES 엠군_실행(id) ON DELETE CASCADE,
    모델                TEXT NOT NULL,            -- claude / gemini
    순위                INTEGER,
    라벨                TEXT,                     -- 한 줄 요약 (UI용)
    캐릭터              TEXT,                     -- 직업+나이+상황
    핵심_결핍           TEXT,
    결핍_원천           TEXT,                     -- 부족|불편|불안|욕망
    구매편익            TEXT,                     -- 기능|경험|상징
    관여도              INTEGER,
    주요_채널           TEXT,
    구매자_이용자_분리  TEXT,
    욕구깡패            TEXT,
    비고                TEXT,
    추천_여부           BOOLEAN DEFAULT FALSE,    -- LLM의 recommended_rank 표시
    선택됨              BOOLEAN DEFAULT FALSE,    -- 사용자가 02로 진행한 타겟
    원본_출력           TEXT,                     -- LLM 마크다운 전체 (실행 내 같은 모델끼리 동일)
    생성일              TIMESTAMPTZ DEFAULT NOW()
);

-- 엠군_포지셔닝: 02 포지셔닝 결과 (선택된 타겟에 대해 모델별 1행씩)
CREATE TABLE IF NOT EXISTS 엠군_포지셔닝 (
    id          BIGSERIAL PRIMARY KEY,
    타겟_id     BIGINT NOT NULL REFERENCES 엠군_타겟(id) ON DELETE CASCADE,
    모델        TEXT NOT NULL,                    -- claude / gemini
    원본_출력   TEXT,
    생성일      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_엠군_타겟_실행id    ON 엠군_타겟(실행_id);
CREATE INDEX IF NOT EXISTS idx_엠군_타겟_선택됨   ON 엠군_타겟(실행_id, 선택됨);
CREATE INDEX IF NOT EXISTS idx_엠군_포지셔닝_타겟id ON 엠군_포지셔닝(타겟_id);
