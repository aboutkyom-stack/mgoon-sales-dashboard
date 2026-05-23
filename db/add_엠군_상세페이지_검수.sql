-- ============================================================
-- 엠군_상세페이지_검수 테이블 추가
-- 목적: 04_b 검수 결과 저장 (04_a 콘티에 대한 검수 보고서 + 다듬은 콘티)
-- 구조: 04_a 결과(엠군_상세페이지)와 1:N 관계 (모델별 행)
-- 옵션 3 (토글) 채택 — 사용자가 명시적으로 04_b 호출 시에만 행 생성.
-- 향후 옵션 1 전환 시에도 동일 테이블 재사용 (스키마 변경 없음).
-- 실행: db/run_add_엠군_상세페이지_검수.py
-- ============================================================

CREATE TABLE IF NOT EXISTS 엠군_상세페이지_검수 (
    id              BIGSERIAL PRIMARY KEY,
    상세페이지_id   BIGINT NOT NULL REFERENCES 엠군_상세페이지(id) ON DELETE CASCADE,
    모델            TEXT NOT NULL,
    원본_출력       TEXT,
    검수_보고서     TEXT,    -- ---REVIEW_REPORT--- 블록 파싱 결과
    다듬은_콘티     TEXT,    -- ---REFINED_DRAFT--- 블록 파싱 결과
    생성일          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_상세페이지검수_상세페이지 ON 엠군_상세페이지_검수(상세페이지_id);
