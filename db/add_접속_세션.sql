-- ============================================================
-- 접속_세션 테이블 추가
-- 목적: 현재 클라우드/로컬에서 누가 접속 중인지 owner에게만 표시 (사이드바 배지)
-- 동시편집 보호(편집_세션)와는 별도로, 페이지 단위가 아닌 사용자 단위 presence.
-- 실행: db/run_add_접속_세션.py
-- ============================================================

CREATE TABLE IF NOT EXISTS 접속_세션 (
    사용자명         TEXT PRIMARY KEY,        -- SSO 이메일 앞부분 또는 'owner(나)'/'partner(동료)'
    현재페이지       TEXT,                    -- 옵션: 'pages/2_product_edit.py' 등
    마지막_활동시각  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_접속세션_활동시각 ON 접속_세션(마지막_활동시각);
