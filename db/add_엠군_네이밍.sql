-- ============================================================
-- 엠군_네이밍 테이블 추가
-- 목적: 03 네이밍 결과 저장 (타겟별, 모델별)
-- 사용 시점: 02·04·05 끝낸 뒤 별도 페이지에서 종합 정보로 호출
-- 구조: 02 엠군_포지셔닝과 동일 패턴
-- 실행: db/run_add_엠군_단계출력.py
-- ============================================================

CREATE TABLE IF NOT EXISTS 엠군_네이밍 (
    id          BIGSERIAL PRIMARY KEY,
    타겟_id     BIGINT NOT NULL REFERENCES 엠군_타겟(id) ON DELETE CASCADE,
    모델        TEXT NOT NULL,
    원본_출력   TEXT,
    생성일      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_네이밍_타겟 ON 엠군_네이밍(타겟_id);
