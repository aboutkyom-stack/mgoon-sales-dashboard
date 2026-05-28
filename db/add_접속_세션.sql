-- ============================================================
-- 접속_세션 테이블 추가/마이그레이션
-- 목적: 현재 클라우드/로컬에서 누가 접속 중인지 owner에게만 표시 (사이드바 배지)
-- 동시편집 보호(편집_세션)와는 별도, 사용자 단위가 아닌 *세션 단위* presence.
--
-- v1 (초기): 사용자명 PK — 동일 username 여러 세션 시 1 row만 잡혀 카운트 부정확
-- v2 (현재): 세션_id PK + 사용자명 일반 컬럼 — 세션 단위 카운트 정확
-- 실행: db/run_add_접속_세션.py (멱등 — 재실행 안전)
-- ============================================================

-- v1 스키마(세션_id 컬럼 없음)가 존재하면 drop하고 v2로 재생성.
-- TTL 2분 row뿐이라 데이터 손실 영향 미미.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables WHERE table_name = '접속_세션'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = '접속_세션' AND column_name = '세션_id'
    ) THEN
        DROP TABLE 접속_세션;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS 접속_세션 (
    세션_id          TEXT PRIMARY KEY,        -- 클라이언트 생성 UUID (브라우저 세션 단위)
    사용자명         TEXT,                    -- SSO 미사용 시 'owner(나)'/'partner(동료)' 다수 가능
    현재페이지       TEXT,                    -- 옵션
    마지막_활동시각  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_접속세션_활동시각 ON 접속_세션(마지막_활동시각);
CREATE INDEX IF NOT EXISTS idx_접속세션_사용자명 ON 접속_세션(사용자명);
