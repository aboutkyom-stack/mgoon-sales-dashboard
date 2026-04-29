-- ============================================================
-- Supabase 신규 테이블 생성 + 마이그레이션
-- 실행 순서: 1단계(테이블 생성) → 2단계(데이터 이전) → 3단계(검증)
-- Supabase SQL Editor에서 단계별로 실행할 것
-- ============================================================


-- ============================================================
-- 1단계: 신규 테이블 생성
-- ============================================================

-- 상품 테이블 (product_catalog + products_v2 통합)
CREATE TABLE 상품 (
    id                  BIGSERIAL PRIMARY KEY,

    -- 마이그레이션 참조용 (안정화 후 삭제 가능)
    구_카탈로그_id      INTEGER,
    구_v2_id            INTEGER,

    -- 기본 정보
    제품명              TEXT NOT NULL,
    카테고리            TEXT,
    서브카테고리        TEXT,
    모델명              TEXT,
    제조사              TEXT,
    원산지              TEXT DEFAULT '중국',

    -- 가격
    소매가              INTEGER,
    도매가              INTEGER,
    실제가              INTEGER,
    평균도매가          INTEGER,

    -- 재고
    실시간재고          INTEGER DEFAULT 0,
    처리후재고          INTEGER DEFAULT 0,
    재고수량            INTEGER DEFAULT 0,
    재입고예정          BOOLEAN DEFAULT FALSE,
    단종여부            BOOLEAN DEFAULT FALSE,

    -- 스펙
    가로_cm             NUMERIC,
    세로_cm             NUMERIC,
    높이_cm             NUMERIC,
    무게_g              NUMERIC,
    재질                TEXT,
    색상                TEXT,
    구성품              TEXT,

    -- 인증
    KC인증              BOOLEAN DEFAULT FALSE,
    KC인증번호          TEXT,
    기타인증            TEXT,

    -- 판매 조건
    온라인판매가능      BOOLEAN DEFAULT TRUE,
    판매채널            TEXT,
    박스재사용          BOOLEAN DEFAULT FALSE,

    -- 텍스트 콘텐츠
    특징                TEXT,
    키워드              TEXT,
    치수정보            TEXT,
    판매자메모          TEXT,
    주의사항            TEXT,

    -- 검수
    검수완료            BOOLEAN DEFAULT FALSE,
    검수메모            TEXT,

    -- AI 작업
    시각설명            TEXT,           -- Vision Pass 결과
    엠군상태            TEXT DEFAULT '미시작',  -- 미시작 / 진행중 / 완료

    -- Google Drive
    드라이브_폴더_id    TEXT,

    -- 타임스탬프
    등록일              TIMESTAMPTZ DEFAULT NOW(),
    수정일              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_상품_엠군상태 ON 상품(엠군상태);
CREATE INDEX idx_상품_카테고리 ON 상품(카테고리);
CREATE INDEX idx_상품_제품명   ON 상품(제품명);


-- 상품_파일 테이블 (drive_files 대체)
CREATE TABLE 상품_파일 (
    id              BIGSERIAL PRIMARY KEY,
    상품_id         BIGINT NOT NULL REFERENCES 상품(id) ON DELETE CASCADE,
    파일명          TEXT,
    파일_유형       TEXT,   -- image / video / detail_page 등
    드라이브_파일_id TEXT,   -- Google Drive file ID (썸네일 URL 생성용)
    드라이브_url    TEXT,
    상태            TEXT DEFAULT 'uploaded',
    업로드일        TIMESTAMPTZ,
    등록일          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_상품파일_상품id ON 상품_파일(상품_id);


-- ============================================================
-- 2단계: 데이터 마이그레이션
-- ============================================================

-- [2-1] product_catalog 전체 → 상품 INSERT (1,142개)
-- 카탈로그에는 가격·재고만 있으므로 기본 필드만 채움
INSERT INTO 상품 (
    구_카탈로그_id,
    제품명,
    소매가,
    도매가,
    실제가,
    평균도매가,
    실시간재고,
    처리후재고
)
SELECT
    id,
    name,
    price_retail,
    price_wholesale,
    price_actual,
    price_avg_wholesale,
    COALESCE(stock_realtime, 0),
    COALESCE(stock_afterprocess, 0)
FROM product_catalog;


-- [2-2] products_v2 → 상품 UPDATE (2개)
-- catalog_id 매칭으로 해당 상품 행에 상세 스펙 덮어쓰기
-- 제외 필드: target_audience, selling_point, competitor_weakness (동료 AI 분석)
--           detail_page_text, promo_* (AI 생성 문구)
UPDATE 상품 s
SET
    구_v2_id            = v.id,
    카테고리            = v.category,
    서브카테고리        = v.subcategory,
    모델명              = v.spec_model,
    제조사              = v.spec_manufacturer,
    원산지              = COALESCE(v.spec_origin, '중국'),
    재고수량            = COALESCE(v.stock_qty, 0),
    재입고예정          = COALESCE(v.restock_yn, FALSE),
    단종여부            = COALESCE(v.discontinued_yn, FALSE),
    가로_cm             = v.spec_width_cm,
    세로_cm             = v.spec_depth_cm,
    높이_cm             = v.spec_height_cm,
    무게_g              = v.spec_weight_g,
    재질                = v.spec_material,
    색상                = v.spec_color,
    구성품              = v.spec_components,
    KC인증              = COALESCE(v.cert_kc_yn, FALSE),
    KC인증번호          = v.cert_kc_number,
    기타인증            = v.cert_other,
    온라인판매가능      = COALESCE(v.online_sale_yn, TRUE),
    판매채널            = v.sale_channel,
    박스재사용          = COALESCE(v.box_reuse_yn, FALSE),
    특징                = v.features,
    키워드              = v.keywords,
    치수정보            = v.dimensions::TEXT,
    판매자메모          = v.seller_notes,
    주의사항            = v.cautions,
    검수완료            = COALESCE(v.inspection_yn, FALSE),
    검수메모            = v.inspection_note,
    드라이브_폴더_id    = v.drive_folder_id
FROM products_v2 v
WHERE s.구_카탈로그_id = v.catalog_id;


-- [2-3] drive_files → 상품_파일 INSERT (225개)
-- products_v2.catalog_id → 상품.구_카탈로그_id 경로로 상품_id 연결
INSERT INTO 상품_파일 (
    상품_id,
    파일명,
    파일_유형,
    드라이브_파일_id,
    드라이브_url,
    상태,
    업로드일,
    등록일
)
SELECT
    s.id,
    df.file_name,
    df.file_type,
    df.drive_file_id,
    df.drive_url,
    COALESCE(df.status, 'uploaded'),
    df.uploaded_at,
    COALESCE(df.created_at, NOW())
FROM drive_files df
JOIN products_v2 v  ON df.product_id = v.id
JOIN 상품 s         ON s.구_카탈로그_id = v.catalog_id;


-- ============================================================
-- 3단계: 검증 쿼리 (마이그레이션 후 순서대로 실행)
-- ============================================================

-- 행 수 확인 (기대값: 상품 1142, 상품_파일 225)
SELECT '상품'    AS 테이블, COUNT(*) AS 행수 FROM 상품
UNION ALL
SELECT '상품_파일', COUNT(*) FROM 상품_파일;

-- products_v2 매칭 확인 (구_v2_id IS NOT NULL 이어야 2개)
SELECT COUNT(*) AS v2_매칭수 FROM 상품 WHERE 구_v2_id IS NOT NULL;

-- 상품_파일 연결 확인 (상품별 파일 수)
SELECT s.제품명, COUNT(f.id) AS 파일수
FROM 상품 s
JOIN 상품_파일 f ON f.상품_id = s.id
GROUP BY s.id, s.제품명
ORDER BY 파일수 DESC;

-- 스펙 채워진 상품 확인 (products_v2 에서 옮겨진 것)
SELECT id, 제품명, 카테고리, 모델명, 가로_cm, 무게_g, KC인증
FROM 상품
WHERE 구_v2_id IS NOT NULL;
