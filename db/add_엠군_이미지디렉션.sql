-- ============================================================
-- 엠군_이미지디렉션 테이블 추가
-- 목적: 04-1 이미지 디렉션(상세페이지 콘티 → 이미지 1장 단위 확정 스펙) 결과 저장
-- 구조: 04 엠군_상세페이지와 동일 패턴 (타겟_id + 모델 + 원본_출력) + 섹션 JSONB
-- 실행: db/run_add_엠군_이미지디렉션.py (멱등 — 재실행 안전)
-- ============================================================

CREATE TABLE IF NOT EXISTS 엠군_이미지디렉션 (
    id          BIGSERIAL PRIMARY KEY,
    타겟_id     BIGINT NOT NULL REFERENCES 엠군_타겟(id) ON DELETE CASCADE,
    모델        TEXT NOT NULL,
    원본_출력   TEXT,
    섹션들      JSONB,
    디자인시스템 JSONB,
    선택_방식   TEXT,
    생성일      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_이미지디렉션_타겟 ON 엠군_이미지디렉션(타겟_id);
