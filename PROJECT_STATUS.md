# 자동화 판매 — 프로젝트 현황 및 설계 결정사항

> 이 문서는 채팅방이 바뀌어도 이어서 작업할 수 있도록  
> 지금까지의 결정사항, 설계, 남은 작업을 전부 기록한다.  
> 작업할 때마다 이 파일을 먼저 읽고, 완료된 항목은 체크한다.

---

## 1. 프로젝트 개요

### 목적
- 온라인 판매 상품에 대해 **부분엠군(마케팅 전략 AI)** 을 적용해 결핍·타겟 분석 → 포지셔닝 플랜을 자동 생성
- 장기적으로는 **이미지만 줘도** 분석 초안까지 자동화

### 파일 위치
```
C:\Users\kyum\Desktop\자동화 공장\자동화 판매\
```

### 실행
```
run.bat 더블클릭  (내부적으로 streamlit run app.py)
```

---

## 2. 현재 시스템 구조

```
자동화 판매/
├── app.py                      홈 (최근 실행 목록)
├── pages/
│   ├── 0_settings.py           모델 설정 (단계별 Claude/Gemini 모델 선택)
│   ├── 1_products.py           제품 조회 (Supabase read, 전체 필드 표시, 신규/수정 버튼)
│   ├── 2_product_edit.py       제품 등록·수정 (이미지 업로드, 스펙, Vision Pass, 충돌해소)
│   ├── 2_pipeline.py           01 결핍·타겟 → 타겟 선택 → 02 포지셔닝
│   ├── 3_gallery.py            전체 이미지 갤러리 + Drive 동기화
│   ├── 4_files.py              상품_파일 테이블 뷰어
│   └── 9_vision_test.py        Vision Pass 테스트 (URL 직접 입력, 비용 참고표)
├── pipeline/
│   ├── settings.py             모델 설정 load/save (settings.json)
│   ├── loader.py               agents/*.md 읽어 시스템 프롬프트 조립
│   ├── llm.py                  Claude + Gemini 호출 (비전 포함, 모델 오버라이드 지원)
│   ├── supabase_read.py        내 Supabase read/write 클라이언트 (상품·비전패스_이력 등)
│   ├── storage.py              엠군 결과 저장 (Supabase)
│   ├── drive_client.py         Google Drive OAuth2 (다중 계정, 업로드/다운로드)
│   ├── models_config.py        ★ AI 모델 목록 단일 소스 (.env override 지원)
│   ├── spec_schema.py          ★ 스펙 필드 정의 단일 소스
│   └── vision_merge.py         ★ 시각설명 비교(compare) + 스펙 추출(extract)
├── agents/
│   ├── 00_vision_pass/         core.md + core_claude.md + core_gemini.md
│   │                           + merge.md ★ + extract_spec.md ★
│   ├── 01_deficit_target/      core.md + examples.md + qa_checklist.md
│   ├── 02_positioning/         core.md + examples.md + qa_checklist.md
│   ├── 03_naming/              core.md + examples.md + expressions.md + qa_checklist.md
│   ├── 04_detail_page/         core.md + examples.md + expressions.md + qa_checklist.md
│   └── 05_channel/             core.md + examples.md + expressions.md + qa_checklist.md
├── db/
│   ├── schema.sql              로컬 SQLite 스키마
│   ├── mgoon.sqlite            엠군 실행 결과 저장소
│   ├── add_비전패스_이력.sql   ★ 비전패스_이력 테이블 DDL
│   └── run_add_비전패스_이력.py ★ psycopg2 마이그레이션 실행기 (멱등)
└── settings.json               단계별 모델 설정 (자동 생성)
```

> `★` 표시: 2026-04-27 새로 추가된 파일

### AI 모델 설정 (settings.json)
- 01 단계: Claude `claude-sonnet-4-6` / Gemini `gemini-2.5-flash` (기본값)
- 02 단계: Claude `claude-sonnet-4-6` / Gemini `gemini-2.5-flash` (기본값)
- 설정 페이지에서 단계별로 변경 가능 (Flash↔Pro 등)

### AI 인풋 구조 (현재)
- **시스템 프롬프트**: agents/ 하위 MD 3개 합친 것 (~10,000자)
- **유저 인풋**: DB 텍스트 필드를 JSON으로 변환한 것
- **이미지**: 현재 미포함 → Vision Pass 구현 후 포함 예정

---

## 3. 연결된 Supabase DB (동료 DB, 읽기 전용으로 참조)

### 접속 정보
```
URL: https://ivicvidbhbuvyocheaiv.supabase.co
KEY: .env 파일 참조 (SUPABASE_KEY)
```

### 현재 테이블 현황

| 테이블 | 행 수 | 상태 |
|---|---|---|
| `product_catalog` | 1,142개 | 가격·재고 마스터. **→ 새 DB로 마이그레이션 후 삭제 예정** |
| `products_v2` | 2개 | 상세 스펙 입력본. **→ 새 DB로 마이그레이션 후 삭제 예정** |
| `products` | 15개 | 구버전(v1). **→ 참고용으로 보관, 별도 조치 없음** |
| `drive_files` | 225개 | 파일 참조 (product_id FK). **→ 유지하되 FK 업데이트 예정** |
| `drive_accounts` | 2개 | Google Drive 계정 (credentials 포함). **→ 건드리지 않음** |

### product_catalog 컬럼 (10개)
`id, name, stock_realtime, stock_afterprocess, price_retail, price_wholesale, price_actual, price_avg_wholesale, created_at, updated_at`

### products_v2 컬럼 (39개)
`id, name, category, subcategory, price, status, created_at, updated_at, drive_folder_id, features, keywords, dimensions, target_audience*, selling_point*, competitor_weakness*, seller_notes, inspection_yn, inspection_note, stock_qty, restock_yn, discontinued_yn, box_reuse_yn, online_sale_yn, sale_channel, cautions, catalog_id, spec_width_cm, spec_depth_cm, spec_height_cm, spec_weight_g, spec_material, spec_color, spec_components, cert_kc_yn, cert_kc_number, cert_other, spec_origin, spec_manufacturer, spec_model`

> `*` 표시: 동료 AI 분석 필드 → 신규 DB에서 제외

### drive_files 컬럼 (11개)
`id, product_id, account_id, file_name, file_type, drive_file_id, drive_url, size_mb, uploaded_at, status, created_at`

> 이미지 표시: `drive_file_id`로 Google Drive 썸네일 URL 생성
> `https://drive.google.com/thumbnail?id={drive_file_id}&sz=w400`

---

## 4. 신규 DB 설계 결정사항

### 4-1. 기본 방침

| 결정 | 내용 |
|---|---|
| **테이블 통합** | `product_catalog` + `products_v2` → `상품` 단일 테이블 |
| **기존 테이블** | 안정화 전까지 백업용으로 유지, 이후 삭제 |
| **필드명** | 전부 한글 (PostgreSQL 큰따옴표 필요하나 Supabase Python SDK에서 정상 작동) |
| **동료 AI 필드** | 전량 제거 (target_audience, selling_point, competitor_weakness) |
| **promo/upload 필드** | 현재 범위 밖 → 필요시 그때 추가 |
| **has_image 류** | drive_files로 대체 가능 → 제거 |

### 4-2. 새 `상품` 테이블 스키마

```sql
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

    -- AI 작업 (Vision Pass + 엠군)
    시각설명            TEXT,       -- Vision Pass 결과
    엠군상태            TEXT DEFAULT '미시작',  -- 미시작 / 진행중 / 완료

    -- Google Drive
    드라이브_폴더_id    TEXT,

    -- 타임스탬프
    등록일              TIMESTAMPTZ DEFAULT NOW(),
    수정일              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_상품_엠군상태 ON 상품(엠군상태);
CREATE INDEX idx_상품_카테고리 ON 상품(카테고리);
CREATE INDEX idx_상품_제품명 ON 상품(제품명);
```

### 4-3. `상품_파일` 테이블 (drive_files 대체)

```sql
CREATE TABLE 상품_파일 (
    id              BIGSERIAL PRIMARY KEY,
    상품_id         BIGINT NOT NULL REFERENCES 상품(id) ON DELETE CASCADE,
    파일명          TEXT,
    파일_유형       TEXT,   -- image / video / detail_page / etc.
    드라이브_파일_id TEXT,   -- Google Drive file ID (썸네일 URL 생성용)
    드라이브_url    TEXT,
    상태            TEXT DEFAULT 'uploaded',
    업로드일        TIMESTAMPTZ,
    등록일          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_상품파일_상품id ON 상품_파일(상품_id);
```

### 4-4. 엠군 결과 저장 (로컬 SQLite — 변경 없음)

현재 `db/schema.sql`의 `mgoon_runs / mgoon_targets / mgoon_positioning` 유지.  
`mgoon_runs.source_product_id` → 새 `상품.id` 참조로 자연스럽게 전환됨.

---

## 5. Vision Pass 설계 (DB 재정비 완료 후 구현)

### 개념
제품 이미지를 AI가 **1회만** 보고 텍스트로 기술 → `상품.시각설명` 저장  
이후 엠군 01/02 호출 시 `시각설명` 텍스트를 스펙에 포함 → **이미지 재전송 없음**

### 비용 효율
- 이미지 직접 전송 방식: 엠군 N회 실행 × 이미지 토큰 = 누적 고비용
- Vision Pass 방식: 이미지 1회 처리 후 텍스트 재활용 → 대폭 절감

### Vision Pass 프롬프트 방향 (초안)
```
두 가지 레이어로 기술하라:

[사실 레이어]
- 텍스트 스펙으로 못 잡는 시각 정보
  (크기감, 질감, 색 조합, 버튼 배치, 패키징 인상 등)

[해석 레이어]
- 이 외형이 어떤 연령/성별에게 시각적으로 어필하는가
- 고급스러운가 장난감 같은가 등 품질 인상
- 경쟁 제품 대비 외형 차별점
- 구매자가 처음 봤을 때 받을 첫인상
```

### 구현 위치
- `pages/1_products.py`: 제품 상세에 "Vision Pass 실행" 버튼 추가
- `pipeline/llm.py`: 이미지 URL 리스트를 받아 Claude/Gemini에 전달하는 함수 추가
- `pipeline/loader.py`: `load_vision_prompt()` 추가
- `agents/00_vision_pass/core.md` 신규 작성

---

## 6. 전체 자동화 로드맵

```
현재 단계
  이미지 → (사람이 수동 입력) → DB → 엠군 파이프라인

1단계 (다음 목표)
  DB 재정비 (새 상품 테이블) + Vision Pass 구현
  이미지 → Vision Pass → 시각설명 DB 저장
  DB(텍스트+시각설명) → 엠군 파이프라인

2단계
  이미지 → Vision Pass → DB 필드 자동 초안 채우기
  사람이 보정 → 엠군 파이프라인

3단계
  이미지 입력만으로 Vision Pass + 엠군 01/02 자동 실행
  결과 검토·승인 후 확정
```

---

## 7. 남은 작업 목록

### ✅ 완료 (2026-04-25)
- [x] 신규 Supabase 프로젝트 생성 (auto-selling, `eikuzgymjzyjauzeghfg`)
- [x] Supabase에 `상품` 테이블 생성 (4-2 스키마, SQL Editor 직접 실행)
- [x] Supabase에 `상품_파일` 테이블 생성 (4-3 스키마)
- [x] `product_catalog` 1,142개 → `상품` 마이그레이션 완료
- [x] `products_v2` 2개 → `상품` UPDATE 완료 (스페이스건 #999S-7, 다이노 공룡로봇)
- [x] `drive_files` → `상품_파일` 37개 마이그레이션 (188개는 v1 고아 파일, catalog_id 없어 연결 불가 — 정상)
- [x] `pipeline/supabase_read.py` 신규 테이블 기준 재작성
- [x] `pages/1_products.py` 신규 테이블 기준 재작성
- [x] `pages/2_pipeline.py` 새 상품.id 및 한글 spec 키 기준 수정

- [x] `credentials/` 폴더 생성, account1_voyager.json + account2_donnamoo.json 복사 완료
- [x] `.gitignore`에 `credentials/` 추가 (보안)
- [x] `docs/` 폴더에 동료 흐름도·데모·README 참고용 복사 완료

- [x] `pipeline/storage.py` SQLite → Supabase(SupabaseStorage)로 전환
- [x] `db/init_supabase.py` 신규 (한 번 실행으로 mgoon 테이블 + 상품_파일.계정 컬럼 생성)
- [x] `pipeline/supabase_read.py` 갤러리/이미지카운트/시각설명/upsert 함수 추가
- [x] `pages/3_gallery.py` 신규 (전체 이미지 갤러리 + 계정별 필터 + Drive 동기화 UI)
- [x] `pages/1_products.py` 이미지 수 배지 표시
- [x] `pipeline/drive_client.py` 신규 (OAuth 인증 + Drive 폴더 스캔)
- [x] `pipeline/settings.py` Vision Pass(00단계) 모델 설정 추가
- [x] `pages/0_settings.py` Vision Pass 모델 선택 UI 추가
- [x] `requirements.txt` psycopg2-binary + google-auth 패키지 추가

### ✅ 완료 (2026-04-25, 소스 확인)
- [x] `.env` 모든 필수 환경변수 설정 완료 (`MY_SUPABASE_DB_URL` 포함)
- [x] `db/init_supabase.py` 실행 완료 (mgoon 테이블 생성됨)
- [x] `pip install -r requirements.txt` 완료 (11개 패키지)
- [x] `agents/03_naming/` — core.md + examples.md + expressions.md + qa_checklist.md 완성
- [x] `agents/04_detail_page/` — core.md + examples.md + expressions.md + qa_checklist.md 완성
- [x] `agents/05_channel/` — core.md + examples.md + expressions.md + qa_checklist.md 완성
- [x] `pages/4_files.py` 신규 (상품_파일 테이블 뷰어)

### ✅ 완료 (2026-04-25 Phase A·B·C)

**Phase A — 제품 CRUD UI**
- [x] `pipeline/supabase_read.py` — `insert_상품()`, `update_상품()`, `delete_상품()` 추가
- [x] `pages/2_product_edit.py` 신규 (4탭: 이미지/스펙/판매자정보/Vision Pass)
- [x] `pages/1_products.py` — "➕ 신규 등록" 버튼 + 행 선택 후 "✏️ 수정" 버튼 추가
- [x] `app.py` — 사이드바에 "✏️ 제품 등록/수정" 페이지 등록

**Phase B — Drive 멀티계정 이미지 업로드**
- [x] `pipeline/drive_client.py` — SCOPES `drive.readonly` → `drive` 전체
- [x] `pipeline/drive_client.py` — `create_folder()`, `get_or_create_folder()`, `upload_file()`, `parse_folder_id()`, `_guess_mime()`, `_guess_type()` 추가
- [x] `pages/2_product_edit.py` Tab 1 — 계정 자동 감지 + 폴더 자동 생성 + 다중 업로드 + 진행바

**Phase C — Vision Pass**
- [x] `agents/00_vision_pass/core.md` 작성 (사실 레이어 + 해석 레이어)
- [x] `pipeline/drive_client.py` — `download_file()` 추가
- [x] `pipeline/llm.py` — `generate_vision_claude()`, `generate_vision_gemini()`, `generate_vision_both()` 추가
- [x] `pipeline/loader.py` — `load_vision_prompt()`, `build_vision_input()` 추가
- [x] `pages/2_product_edit.py` Tab 4 — 실행 버튼 + Claude/Gemini 결과 비교 + 수동 편집·저장

### ✅ 완료 (2026-04-25, Vision Pass 엔진 이원화 + 프롬프트 설계 확정)

**구현**
- [x] `agents/00_vision_pass/core_claude.md` 신규 — Claude 전용 프롬프트
- [x] `agents/00_vision_pass/core_gemini.md` 신규 — Gemini 전용 프롬프트 (텍스트 레이어 항목별 구조화)
- [x] `pipeline/loader.py` — `load_vision_prompt(engine=)` 파라미터 추가, engine별 `core_{engine}.md` 우선 로드, 없으면 `core.md` fallback
- [x] `pages/9_vision_test.py` 전면 개편
  - 비용 참고표 (모델별 호출 단가·1,142개 전체 비용 추정)
  - 메인 엔진 selectbox (기본: claude-sonnet-4-6)
  - 서브 엔진 selectbox + ON/OFF 토글 (기본: gemini-2.5-flash, ON)
  - 엔진별 독립 프롬프트 편집기 + 저장 버튼 (`core_{family}.md`에 저장)
  - 편집 중인 프롬프트 저장 없이 즉시 반영

**엔진 전략 결정사항**
| 구분 | 기본값 | 역할 |
|---|---|---|
| 메인 엔진 | Claude Sonnet 4.6 | 주 분석, 깊이 있는 해석 레이어 |
| 서브 엔진 | Gemini 2.5 Flash | 교차검증 및 비용 절감 대안 |

- 서브 ON/OFF 토글, 메인·서브 모두 selectbox로 언제든 교체 가능
- **비용**: Gemini Flash ≈ $0.002/호출, Claude Sonnet ≈ $0.014/호출 (이미지 1장 기준)
- **비용 전략**: 1,142개 bulk는 Gemini, 엠군 연계 우선 제품은 Claude
- **미래**: 이미지 복잡도 기반 자동 라우팅 검토 (텍스트 밀도 높은 이미지 → 메인, 단순 누끼 → 서브)

**프롬프트 설계 철학 결정**
- **B방식 채택**: 3레이어 틀(텍스트/사실/해석)만 고정, 내용은 AI 재량. 하드코딩 지양.
- 텍스트 레이어 구조는 모든 제품에 범용 적용 가능 (라벨·스펙·인증·주의사항 패턴 동일)
- 사실·해석 레이어는 항목 목록만 제시, "해당 없으면 생략" 허용 → 제품 유형 무관하게 작동
- Few-shot 예시 하드코딩 **하지 않기로 결정** — 예시 고정 시 특정 카테고리로 bias 발생 위험
- 카테고리별 전용 프롬프트 분리는 실전 테스트 후 실제로 문제 생기면 그때 검토
- `core_gemini.md` "반드시 모두 포함하라" → "해당 없는 항목은 생략" 수정 완료

**테스트 결과 (해파리 완구, 이미지 1장)**
- Gemini Flash (개선 프롬프트): 텍스트 레이어 구조화 지시 잘 따름, OCR 오탈자 1건 (Plusitory→Plustory), 해석 레이어 가격 추정 부정확
- Claude Sonnet: OCR 정확, 해석 깊이·가격 추정·배경 추천 모두 우수
- 결론: 텍스트 레이어는 Gemini도 충분, 해석 레이어는 Claude 우위 → 전략 방향 확인됨

### ✅ 완료 (2026-04-25, Drive 업로드 정상화)
- [x] Drive 업로드 403 오류 근본 원인 파악 — `credentials/*.json`이 서비스 계정(Service Account) 키. 서비스 계정은 개인 Drive 저장 용량 없어 파일 업로드 불가 (폴더 생성은 용량 불필요라 성공했던 것)
- [x] `pipeline/drive_client.py` `_get_credentials()` — 서비스 계정 → OAuth2 pickle 방식으로 전환. pickle 로드 → 만료 시 refresh_token 자동 갱신 → pickle 저장
- [x] 동료에게 `token.pickle` 수령 → `credentials/token1_voyager.pickle`로 배치
- [x] Supabase `상품_파일` 테이블 — `드라이브_파일_id` UNIQUE 제약 추가 (upsert ON CONFLICT 42P10 오류 해결)
- [x] `pipeline/drive_client.py` `upload_file()` — 업로드 후 자동으로 `anyone/reader` 권한 부여 (썸네일 URL 표시용)
- [x] 기존 업로드된 파일 3개(#2143) 수동 권한 부여 완료
- [x] `token2_donnamoo.pickle` 수령 완료 (2026-04-27) — `credentials/token2_donnamoo.pickle` 배치 완료

### 나중에 — Drive 동기화 (2026-04-27 논의, 보류)

**배경**: 기존 1,142개 상품에 Drive 이미지 연결 → Vision Pass 실행 위해 필요.

**donnamoo 계정 Drive 폴더 정보**:
- 폴더 URL: `https://drive.google.com/drive/folders/1mcqX1Z8Ab06JqxlOHgzLrxZ_sk1k_J52`
- 폴더 ID: `1mcqX1Z8Ab06JqxlOHgzLrxZ_sk1k_J52`
- token2_donnamoo.pickle 있으니 인증 가능

**현재**: 갤러리 페이지에 단건 동기화 UI 있음 (폴더 URL + 제품 선택 → 스캔 → DB 저장).  
**미구현**: Bulk 자동 동기화 (Drive 폴더명 ↔ 제품 자동 매핑).

### ✅ 완료 (2026-04-27, 2_product_edit.py 4가지 버그 수정)

- [x] **Q1 — 임시 레코드 중복 방지**: `session_state["_temp_product_id"]`에 임시 ID 기억. 신규 등록 재진입 시 기존 임시 레코드 재사용. 저장/취소/삭제 시 세션 참조 제거.
- [x] **Q2 — 중복 업로드 방지 + 위젯 초기화**: `upload_key` 카운터로 업로드 성공 후 `file_uploader` 자동 초기화. 기존 `파일명` 목록과 대조해 중복 파일 건너뜀 + 경고.
- [x] **Q3 — 이미지별 삭제 버튼**: 각 이미지 카드에 🗑️ 버튼 추가. `delete_파일(id)` 호출 후 rerun. `supabase_read.py`에 `delete_파일()` 함수 추가.
- [x] **Q4 — 이미지별 Vision Pass 모드**: 실행 모드 라디오 추가 ("일괄 실행" / "이미지별 실행"). 이미지별 모드에서 각 이미지마다 모델 selectbox + ▶ 실행 + 결과 textarea + 💾 저장 독립 제공.

### ✅ 완료 (2026-04-27, Vision Pass 영구화·합성·스펙 추출 전체 구현)

**신규 파일 생성**
- [x] `pipeline/models_config.py` — AI 모델 목록 단일 소스 (`CLAUDE_VP_MODELS`, `GEMINI_VP_MODELS`, `ALL_VP_MODELS`, `DEFAULT_MERGE_MODEL`, `DEFAULT_EXTRACT_MODEL`, `family_of()`). `.env` override 지원.
- [x] `pipeline/spec_schema.py` — 스펙 필드 12개 (`SPEC_FIELDS`) 정의. `build_extraction_schema_text()`로 LLM 프롬프트 가이드 자동 생성.
- [x] `pipeline/vision_merge.py` — `compare_시각설명()` (기존↔신규 비교, 3-way 지원) + `extract_스펙()` (시각설명→스펙 JSON). 강건한 JSON 파싱(_parse_json).
- [x] `agents/00_vision_pass/merge.md` — 비교 분석 프롬프트 (일치/충돌 분리 규칙 엄격 정의)
- [x] `agents/00_vision_pass/extract_spec.md` — 스펙 추출 프롬프트 (`{SPEC_FIELDS_GUIDE}` 플레이스홀더, 런타임에 spec_schema가 채움)
- [x] `db/add_비전패스_이력.sql` — `비전패스_이력` 테이블 DDL (인덱스 포함, IF NOT EXISTS 멱등)
- [x] `db/run_add_비전패스_이력.py` — psycopg2 + `MY_SUPABASE_POOLER_URL`로 마이그레이션 직접 실행 (실행 완료, 테이블 생성 확인됨)

**기존 파일 수정**
- [x] `pipeline/supabase_read.py` — `insert_비전패스_이력()`, `list_비전패스_이력()`, `delete_비전패스_이력()` 추가
- [x] `pages/2_product_edit.py` 대규모 개선:
  - 하드코딩 모델 목록 → `models_config.ALL_VP_MODELS` 교체
  - 일괄 실행: 결과 `비전패스_이력` DB 저장 (실행_모드='bulk')
  - 일괄 실행: 💾 저장 버튼 → 📥 반영 버튼 (충돌 해소 패널 투입)
  - 3-way 버튼: "📥📥 메인+서브 동시 반영"
  - 이미지별 모드(4-A): 페이지 로드 시 전체 이력 DB에서 읽어 표시 (세션 상태 X)
  - 이미지별 모드(4-A): ▶ 실행 후 DB 저장 + `st.rerun()` (이력 즉시 반영)
  - 이미지별 모드(4-A): ▶/▼ 토글 버튼으로 이력 열기/닫기 (`st.expander` 중첩 제거)
  - 충돌 해소 패널(4-B): `vp_pending` session_state 활성화 시 페이지 하단 표시
    - 기존 시각설명 없음 → text_area 직접 편집 후 저장
    - 기존 있음 → LLM 비교 → 일치 텍스트(편집가능) + 충돌 항목 라디오(기존/신규/직접입력) → "✅ 최종 적용 & 저장"
  - 스펙 자동 추출(4-C): 스펙 탭에 `🤖 시각설명 → 스펙 필드 자동 추출` expander
    - 모델 selectbox + 추출 실행 → 미리보기 테이블
    - "빈 필드만 채우기" / "전체 덮어쓰기" 선택 → "✅ 폼에 적용"
    - "↩️ 추출값 되돌리기" 취소 지원
  - `_fmt_dt()` 헬퍼 추가 (타임스탬프 → 한국 시간 포맷)
  - 빈 레이블 `st.text_area("", ...)` 5곳 → `label_visibility="collapsed"` 추가 (Streamlit 경고 제거)

**DB 마이그레이션 (완료)**
- [x] `.env`에 `MY_SUPABASE_POOLER_URL` 추가 (Tokyo 리전 Pooler, IPv4)
  - 직접 연결(`db.eikuzgymjzyjauzeghfg.supabase.co`)은 이 네트워크에서 DNS 미해결(IPv6 전용)
  - Pooler 주소: `aws-1-ap-northeast-1.pooler.supabase.com:6543` 사용
- [x] `run_add_비전패스_이력.py` 실행 → `비전패스_이력` 테이블 + 인덱스 생성 완료

**Streamlit 중첩 expander 오류 완전 해소**
- [x] 근본 원인: `st.expander` 내부에 다른 `st.expander` 중첩 → Streamlit 런타임 오류
- [x] 해결 방식: 중첩 expander 4곳 모두 대체
  1. 이미지별 이력 목록 → 세션 상태 토글 버튼 + `st.container(border=True)`
  2. 충돌 해소 결과 미리보기 → `st.container()` + `st.text_area()`
  3. 비교 분석 LLM 원본 응답 (디버그) → `st.code()`
  4. 스펙 추출 LLM 원본 응답 (디버그) → `st.code()`
- ⚠️ **주의**: 파일 수정 후 Streamlit이 즉시 재로드하지 않는 경우 있음 (Windows 파일 잠금으로 bytecode 캐시 잔존). 오류가 지속되면 `Ctrl+C` 후 `run.bat` 재실행 필요.

### 진행 중 / 다음 작업 (2026-04-27 현재)

**현재 작업 흐름**:
```
[완료] 제품 등록·수정 UI (2_product_edit.py) — 이미지 업로드 + VP 정상화
[완료] Vision Pass 영구화 (비전패스_이력 DB) + 충돌 해소 UI + 스펙 자동 추출
    ↓
[검증 필요] Streamlit 재시작 후 신규 기능 동작 확인 (expander 중첩 오류 해소 여부)
    ↓
[다음 ①] 기존 1,142개 상품에 Drive 이미지 연결 (donnamoo 폴더 bulk 동기화)
    ↓
[다음 ②] 이미지 연결된 상품들 Vision Pass 실행 → 시각설명 DB 저장
    ↓
[다음 ③] 시각설명이 채워진 상품으로 엠군 01/02 파이프라인 실행 테스트
```

**⚠️ 검증 필요 — Streamlit 재시작 후 확인 사항**
- `run.bat` 으로 재시작 후 `2_product_edit.py` 진입 시 오류 없이 로드되는지 확인
- Vision Pass 섹션 진입 후 이미지별 이력 토글(▶/▼) 정상 작동 확인
- 📥 반영 버튼 → 충돌 해소 패널 활성화 확인
- 스펙 탭 `🤖 시각설명 → 스펙 필드 자동 추출` expander 작동 확인

**다음 ① — Drive bulk 동기화** (현재 블로킹 아님, 언제든 시작 가능)
- donnamoo 폴더 ID: `1mcqX1Z8Ab06JqxlOHgzLrxZ_sk1k_J52`
- Drive 폴더명 ↔ 상품명 자동 매핑 스크립트 필요 (아직 미구현)
- 지금은 갤러리 페이지에서 단건 수동 동기화만 가능

**다음 ② — Vision Pass 대량 실행**
- `1_products.py` 하단에 "Vision Pass 실행" 버튼 추가
- 이미지가 있는 상품만 대상, 결과를 `상품.시각설명`에 저장

**다음 ③ — 엠군 파이프라인 실전 테스트**
- 현재 `2_pipeline.py` UI는 있으나 실전 테스트 미실시
- `시각설명`이 채워진 상품 1~2개로 01 결핍·타겟 → 02 포지셔닝 흐름 검증 필요

### 나중에
- [ ] **오픈마켓 상품명(리스팅 제목) 별도 모듈** (2026-05-02 결정 — 03 네이밍에서 제외) — 03 네이밍은 제품명·브랜드명에 집중. 오픈마켓 상품명은 SEO 키워드 조합이라 검색량 데이터 없이 AI가 짓는 건 추측에 불과. **지금은 옵션 Z**(만들지 않음). 추후 결정:
  - **옵션 X**: 네이버 검색광고 API 연동 → 키워드 검색량·경쟁도 자동 수집 → AI가 데이터 기반 상품명 조립
  - **옵션 Y**: 사용자가 키워드 도구(블랙키위·키워드마스터 등)에서 키워드 목록 복사 → 페이지에 붙여넣음 → AI가 그 키워드로 제목 조립
  - 트리거: 03에서 제품명·브랜드명 확정 → 사용자가 수동 작성하면서 진짜 필요성 체감 → 그때 X/Y 결정
- [ ] **01 결핍·타겟 품질 개선** — 실전 테스트 결과, 결핍 각도가 아직 얕고 타겟 후보 다양성이 부족. `agents/01_deficit_target/core.md` + `examples.md` 보완 필요 (2026-04-30 실전 테스트에서 확인)
- [ ] 엠군 03 네이밍 / 04 상세페이지 / 05 채널 연동
- [ ] Vision Pass → DB 필드 자동 채우기 (초안 자동화)
- [ ] **엠군 01/02 캐싱 워크플로우 최적화** — 엠군 시스템 프롬프트는 MD 3개 합산 ~10,000자로 대용량. 동일 프롬프트로 여러 제품을 연속 처리할 때 Anthropic cache_control(ephemeral, 5분 TTL)이 적용되어 시스템 프롬프트 비용 ~90% 절감 가능. 구현 방향: 제품 목록에서 여러 상품을 선택 → 배치로 엠군 01 순차 실행 → 5분 내 처리 시 캐시 히트. 단, 이미지 토큰(Vision Pass)은 캐싱 안 됨 — Vision Pass는 이미 1회만 실행 후 텍스트 저장하는 구조라 별도 캐싱 불필요.
- [ ] ~~동료 DB에 결과 덮어쓰기/추가~~ → 불필요 (동료 DB 연결 끊음)
- [ ] Streamlit Cloud 배포 (공용화)
- [ ] Drive 자동 할당 로직 (아래 참고)
- [ ] Drive 사용량 정확도 보강 — OAuth2 전환 완료로 개인 계정 quota 조회 가능해짐. `get_all_quota_info()`에서 `about().get(fields="storageQuota")` 방식으로 전환 검토 필요 (현재는 파일 크기 합산 방식)

---

## 7-A. 리팩토링 계획 (product_hub_v2 계승) — ✅ 전체 완료

> 동료가 개발에서 손을 떼고 우리가 인수. 입력 UI를 우리 앱에 통합.
> product_hub_v2 UX는 계승하되, AI/Drive/DB는 우리 방식으로 교체.

### 페이지 구조 변경 — ✅ 완료

```
현재                        →  변경 후
─────────────────────────────────────────────
home.py                        home.py (유지)
pages/0_settings.py            pages/0_settings.py (유지)
pages/1_products.py            pages/1_products.py (CRUD 버튼 추가) ✅
                               pages/2_product_edit.py  ← 신규 ✅
pages/2_pipeline.py            pages/2_pipeline.py (번호 유지)
pages/3_gallery.py             pages/3_gallery.py (유지)
pages/9_vision_test.py         pages/9_vision_test.py ← 신규 ✅
```

### Phase A — 제품 CRUD UI ✅ 완료

- [x] `pages/2_product_edit.py` 신규
  - 탭1 📁 이미지 & Vision Pass (이미지 표시 + 업로드 + VP 통합)
  - 탭2 📐 스펙 입력 (치수/소재/인증)
  - 탭3 📝 판매자 정보 (재고/채널/검수)
- [x] `pages/1_products.py` — "➕ 신규 등록" 버튼 + 행 선택 후 "✏️ 수정" 버튼 추가
- [x] `pipeline/supabase_read.py` — `insert_상품()`, `update_상품()`, `delete_상품()`, `delete_파일()` 추가

### Phase B — 이미지 업로드 (Drive 멀티계정) ✅ 완료

- [x] `pipeline/drive_client.py` — `upload_file()`, `create_folder()`, `get_or_create_folder()`, `parse_folder_id()`, `download_file()` 추가
- [x] `pages/2_product_edit.py` 탭1 이미지 섹션
  - 계정 자동 감지 + 드롭다운 선택
  - file_uploader → Drive 업로드 → `상품_파일` 저장 + 진행바
  - 중복 파일명 건너뜀 + 업로드 후 위젯 자동 초기화 (upload_key 카운터)
  - 업로드된 이미지 갤러리 표시 + 🗑️ 개별 삭제 버튼

### Phase C — Vision Pass ✅ 완료

- [x] `agents/00_vision_pass/core.md`, `core_claude.md`, `core_gemini.md` 작성
- [x] `pipeline/llm.py` — `generate_vision_claude()`, `generate_vision_gemini()` 추가
- [x] `pipeline/loader.py` — `load_vision_prompt()`, `build_vision_input()` 추가
- [x] `pages/2_product_edit.py` 탭1 Vision Pass 섹션 (expander)
  - 일괄 실행 모드: 메인+서브 엔진 selectbox + ON/OFF 토글 + 병렬 실행
  - 이미지별 실행 모드: 각 이미지마다 모델 선택 + ▶ 실행 + 결과 + 💾 저장
  - 프롬프트 편집 (체크박스 토글, Claude/Gemini 독립 편집·저장)
  - 결과 → `상품.시각설명` DB 저장 + 직접 편집 가능
- [x] `pages/9_vision_test.py` — URL 직접 입력 테스트 페이지 (비용 참고표 포함)

### Phase D — 정리 (일부 완료, 일부 보류)

- [x] 동료 Supabase 데이터 이관 완료 → 연결은 남아있으나 실질적으로 미사용
- [ ] `pipeline/supabase_read.py` colleague 클라이언트 코드 제거 (나중에)
- [ ] `pages/4_files.py` 제거 (gallery로 흡수) (나중에)

### Drive 자동 할당 로직 (미래 구현용 설계)

**목표**: 계정 10개 × 15GB = 150GB처럼 사용, 수동 지정 없이 자동 분배

**구현 방식**:
```python
# 업로드 시 자동으로 가용 용량 가장 큰 계정 선택
def pick_best_account(drive_clients: dict) -> str:
    quotas = {}
    for name, service in drive_clients.items():
        about = service.about().get(fields="storageQuota").execute()
        used = int(about["storageQuota"]["usage"])
        limit = int(about["storageQuota"]["limit"])
        quotas[name] = limit - used  # 남은 용량
    return max(quotas, key=quotas.get)
```

**적용 위치**: `pipeline/drive_client.py`에 `auto_pick_account()` 함수로 추가.
제품 등록 시 계정 선택 드롭다운 대신 자동 호출.

**전제 조건**: credentials JSON이 개인 OAuth 계정 기반이어야 `storageQuota` 조회 가능.
서비스 계정(service account)은 quota 개념 다름 — 계정 유형 확인 후 구현.

---

## 8. 주요 결정사항 로그

| 날짜 | 결정 | 이유 |
|---|---|---|
| 2026-04-24 | 엠군 전용 앱 별도 신규 구축 | 기존 통합 DB app.py가 엉망, 엠군 특화 UI 필요 |
| 2026-04-24 | 동료 DB는 read-only로 스펙만 가져옴 | 동료 DB 구조가 맘에 안 들어, 결과물은 별도 저장 |
| 2026-04-24 | 엠군 결과는 로컬 SQLite에 저장 | 빠른 시작, 인터페이스 추상화로 추후 교체 가능 |
| 2026-04-24 | Claude + Gemini 교차검증 | 같은 제품·같은 MD로 두 모델 비교해서 인사이트 보강 |
| 2026-04-24 | Gemini 기본값 Flash (Pro 아님) | 01/02 작업에서 Flash로 충분, 비용 절감. 중요 제품만 Pro |
| 2026-04-24 | Vision Pass 분리 구조 채택 | 이미지 1회 처리 후 텍스트로 재활용 → 비용 효율 + 재실행 유연성 |
| 2026-04-24 | product_catalog + products_v2 통합 | JOIN 불필요, 관리 포인트 단순화, 필터로 충분 |
| 2026-04-24 | DB 필드명 한글화 | 의미 중복 방지, 팀 내부 가독성 향상 |
| 2026-04-24 | 동료 AI 분석 필드 전량 제거 | 동료 구현 없음, 우리가 직접 구현할 것들만 남김 |
| 2026-04-24 | DB 재정비 → Vision Pass 순서 | Vision Pass 저장 위치 확정 후 구현해야 이중작업 없음 |
| 2026-04-24 | 신규 Supabase 프로젝트 분리 | 동료 service_role key 미제공, 독립 DB가 장기적으로도 맞음 |
| 2026-04-24 | drive_files 188개 고아 파일 제외 | products v1(15개) 전용 파일, catalog_id 없어 연결 불가 — 무시해도 무방 |
| 2026-04-25 | 동료 Supabase 연결 끊고 우리 DB만 운영 | 데이터 이관 완료, 이후 신규 입력은 우리 UI로 직접 등록 |
| 2026-04-25 | Drive 계정 할당 — 지금은 수동 드롭다운 | 자동 할당 로직은 설계만 해두고 나중에 구현 |
| 2026-04-25 | Vision Pass 결과 수동 편집 가능하게 | AI 결과 저장 후 text_area에서 보완·수정·저장 지원 |

---

## 9. 참고: 엠군 에이전트 구조

| 에이전트 | 폴더 | 역할 |
|---|---|---|
| 00 Vision Pass | `agents/00_vision_pass/` | 이미지 → 시각설명 텍스트 (신규 구현 예정) |
| 01 결핍·타겟 | `agents/01_deficit_target/` | 제품 스펙 → 타겟 후보 분석 (완료) |
| 02 포지셔닝 | `agents/02_positioning/` | 선택된 타겟 → 포지셔닝 플랜 (완료) |
| 03 네이밍 | `agents/03_naming/` | 미구현 |
| 04 상세페이지 | `agents/04_detail_page/` | 미구현 |
| 05 채널 | `agents/05_channel/` | 미구현 |

---

## 10. 환경 설정

### .env 필수 항목
```
# 동료 DB (read-only — 제품 스펙 읽기용)
COLLEAGUE_SUPABASE_URL=https://ivicvidbhbuvyocheaiv.supabase.co
COLLEAGUE_SUPABASE_KEY=<anon key>

# 내 DB (read-write — 상품·상품_파일·엠군 결과 저장)
MY_SUPABASE_URL=https://eikuzgymjzyjauzeghfg.supabase.co
MY_SUPABASE_ANON_KEY=<anon key>
MY_SUPABASE_SERVICE_KEY=<service_role key>   ← DDL·쓰기용, 절대 외부 노출 금지

# DB 직접 연결 (init_supabase.py 실행용 — 한 번만 필요)
# Supabase 대시보드 → Project Settings → Database → Connection string → Direct → URI 복사
MY_SUPABASE_DB_URL=postgresql://postgres:[패스워드]@db.eikuzgymjzyjauzeghfg.supabase.co:5432/postgres

# DB Pooler 연결 (psycopg2 마이그레이션 스크립트용 — 이 네트워크에서 직접 연결 DNS 미해결 시 사용)
# Project Settings → Database → Connection string → Connection pooler → URI 복사
MY_SUPABASE_POOLER_URL=postgresql://postgres.[프로젝트ID]:[패스워드]@aws-1-ap-northeast-1.pooler.supabase.com:6543/postgres

ANTHROPIC_API_KEY=<Claude API key>
GEMINI_API_KEY=<Gemini API key>

# Vision Pass 모델 목록 override (선택, 미설정 시 models_config.py 기본값 사용)
# CLAUDE_VP_MODELS=claude-sonnet-4-6,claude-opus-4-7,claude-haiku-4-5-20251001
# GEMINI_VP_MODELS=gemini-2.5-flash,gemini-2.5-pro
# MERGE_MODEL=claude-sonnet-4-6
# EXTRACT_MODEL=claude-sonnet-4-6
```

### 주요 컬럼 이름 주의사항
- `KC인증`, `KC인증번호` → PostgreSQL unquoted 식별자 소문자 저장으로 실제 컬럼명은 `kc인증`, `kc인증번호`
- supabase_read.py에서 이미 소문자 키로 처리 중

### requirements.txt
```
streamlit
supabase
anthropic
google-genai
python-dotenv
pandas
```

### Google Drive Credentials 관리

```
credentials/
├── account1_voyager.json       ← voyager.dream0110@gmail.com (동료 계정 1)
├── account2_donnamoo.json      ← donnamoo6262@gmail.com (동료 계정 2)
├── token1_voyager.pickle       ← OAuth 토큰 (최초 인증 후 자동 생성)
├── token2_donnamoo.pickle      ← OAuth 토큰 (최초 인증 후 자동 생성)
└── accountN_XXX.json           ← 계정 추가 시 동일 패턴으로 확장
```

- **네이밍 규칙**: `accountN_식별명.json` / `tokenN_식별명.pickle`
- **N**: 순서 번호 (1부터), **식별명**: 이메일 로컬파트 앞부분
- 계정 추가 시 위 패턴으로 파일 추가 + `pipeline/drive_client.py`에 계정 목록 등록 (예정)
- `.gitignore`에 `credentials/` 전체 추가 필요 (API 키 보안)
- 각 계정이 접근하는 Drive 폴더: `product_XXX/image|video|detail` 구조

---

## ⭐ Vision Pass 결과 영구화·합성·스펙 추출 (2026-04-27 추가)

### 변경 요약
이미지별 Vision Pass 결과를 세션이 아닌 **DB에 영구 저장**하고, 기존 시각설명과의
**충돌을 사용자가 검토**해 통합하며, 시각설명에서 **스펙 필드를 자동 추출**하는
파이프라인 도입.

### 추가된 구성

| 파일 | 역할 |
|------|------|
| `db/add_비전패스_이력.sql` | `비전패스_이력` 테이블 정의 |
| `db/run_add_비전패스_이력.py` | psycopg2로 마이그레이션 직접 실행 (멱등) |
| `pipeline/models_config.py` | AI 모델 목록 단일 소스. `.env`로 override |
| `pipeline/spec_schema.py` | 스펙 필드 정의 단일 소스. 필드 변경 시 여기만 수정 |
| `pipeline/vision_merge.py` | `compare_시각설명`, `extract_스펙` |
| `agents/00_vision_pass/merge.md` | 비교 분석 프롬프트 |
| `agents/00_vision_pass/extract_spec.md` | 스펙 추출 프롬프트 |

### DB 스키마: `비전패스_이력`
```
id, 상품_id (FK), 파일_id (NULL=일괄), 모델명, 프롬프트, 결과, 실행_모드, 생성일
```

### UI 흐름
1. **이미지별 실행** — 결과를 DB `비전패스_이력`에 저장 → 페이지 재진입 시 ▶/▼ 토글 버튼으로 이력 표시
   - (Streamlit expander 중첩 제한 때문에 세션 상태 toggle + `st.container(border=True)` 방식 채택)
2. **📥 반영 버튼** — 신규 결과를 `vp_pending` session_state에 등록 → 페이지 하단 "충돌 해소 패널" 활성화
3. **충돌 해소 패널** — 기존 vs 신규를 LLM 비교 → 일치는 통합 텍스트(편집 가능), 충돌은 라디오 선택(기존/신규/직접입력)
4. **3-way 비교** — 일괄실행에서 "메인+서브 동시 반영" 시 기존+메인+서브 셋이 한 번에 비교됨
5. **스펙 자동 추출** — 스펙 탭에서 시각설명을 파싱해 폼 필드 자동 채우기 (빈 필드만/전체 덮어쓰기 선택)

### 메인/서브 엔진 협력 — 추후 논의용

현재는 사용자 안목 의존 구조:
- 메인+서브 병렬 실행 → 각각 결과 → 사용자가 충돌 해소 UI에서 직접 선택
- 사용자 의견: "당분간은 사용자 안목에 의존할 것이고, 그래서 서브는 평소 OFF일 것"
- 자동화는 차차 도입 예정

검토했던 대안 (보류 — 추후 자동화 단계 진입 시 재고려):
| 옵션 | 흐름 | 비용 | 정확도 | 비고 |
|------|------|------|--------|------|
| A. 직렬 보강 | 메인 → 서브가 메인 결과 보고 누락 보완 | ≈2배 | 중 | 사용자 안목 여전히 필요 |
| B. 병렬+합성 | 메인‖서브 → 3차 LLM이 합성 | ≈3배 | 상 | 가장 정확하나 비싸고 검증 필요 |
| C. 병렬 비교 (현재) | 메인‖서브 → 사용자가 충돌 해소 UI에서 결정 | 2배 | 사용자 의존 | 채택 |

향후 옵션 B 자동화 도입 시 검토 포인트:
- 합성 LLM이 두 결과를 합칠 때 "어느 쪽이 정확한가" 판단 기준 정립 필요
- 단순히 "더 구체적" = "정확함"이 아니므로, 이미지 재참조 또는 다중 모델 투표 등 검증 메커니즘 필요

### 모델명 변경 대응
- 모델 목록은 `pipeline/models_config.py` 한 곳에서 정의
- `.env`의 `CLAUDE_VP_MODELS`, `GEMINI_VP_MODELS` 로 재배포 없이 갱신 가능
- 예: 제미나이 2.0 → 2.5 전환 시 `.env`에 `GEMINI_VP_MODELS=gemini-2.5-flash,...` 만 수정

### 스펙 필드 변경 대응
- `pipeline/spec_schema.py` 의 `SPEC_FIELDS` 리스트만 수정
- `extract_스펙` 함수와 추출 프롬프트가 자동 반영 (수동 동기화 불필요)
- 단, 스펙 탭의 위젯(`pages/2_product_edit.py`)은 별도 수정 필요

---

## ⭐ 제품 조회/편집 UX 개선 + 임시 레코드 누수 정리 (2026-04-29 추가)

### 배경 — 사용자 피드백
1. **수정 동선이 불편** — 제품 조회 페이지에서 행 클릭 시 JSON(DB 원본 / 엠군 입력 스펙)이 강제로 표시되는데, 실제로는 거의 보지 않음. 주로 "수정" 버튼을 눌러 편집 페이지로 이동 후 또 "스펙" 탭을 클릭해야 함 — 3단계로 너무 길다.
2. **임시 레코드 누수** — 신규 제품 등록 페이지 진입 시 `임시_MMDD_HHMMSS` 형식의 임시 레코드가 자동 생성되는데, 사이드바로 다른 페이지로 이동하면 삭제되지 않고 DB에 누적됨. 다시 신규 등록 페이지에 가면 또 새 임시 레코드가 생성되어 계속 쌓임.

### 결정사항

#### 1. 제품 조회 → 편집 이동 1단계 단축
- **JSON 뷰 제거**: 제품 조회에서 강제 표시되던 `DB 원본` / `엠군 입력 스펙` expander 두 개 삭제
- **버튼 정리**: "✏️ 수정" → **"✏️ 스펙 수정"** (primary, 의도 명확화)
- **수정 페이지 진입 시 스펙 탭 자동 활성화**: Streamlit `st.tabs()`는 첫 번째 탭이 항상 활성화되는 특성 활용

#### 2. 편집 페이지 탭 순서 동적 변경 (`_is_temp` 기반)
- **신규 등록 모드 (`_is_temp=True`)**: `["📁 이미지 & Vision Pass", "📐 스펙", "📝 판매자 정보"]` — 이미지 업로드 → VP 추출 → 스펙 채우기 워크플로우 유지
- **수정 모드 (`_is_temp=False`)**: `["📐 스펙", "📁 이미지 & Vision Pass", "📝 판매자 정보"]` — 가장 잦은 작업인 스펙 편집을 첫 화면에 배치
- 별도 session_state 플래그 불필요 — 기존 `_is_temp` 변수만으로 판단

#### 3. JSON 뷰는 스펙 탭 하단 expander로 보존
- "🔧 JSON으로 보기 (DB 원본 / 엠군 입력 스펙)" — `expanded=False` 기본 접힘
- 디버깅·엠군 파이프라인 입력 형식 확인 시에만 펼쳐서 사용

#### 4. 임시 레코드 누수 정리 (2단 방어)
- **선제 정리 — `pages/1_products.py` 진입 시 자동 청소**: `delete_임시_products()` 호출하여 제품명이 `임시_`로 시작하는 모든 레코드 일괄 삭제. 사이드바 이탈로 인한 고아 레코드를 다음 제품조회 진입 시 자동 회수. 정리되면 `_temp_product_id` / `edit_product_id` / `edit_mode` session_state 키도 함께 pop.
- **명시적 정리 — `pages/2_product_edit.py`의 "← 목록으로" 버튼**: 임시 레코드면 즉시 `delete_상품(product_id)` 호출 후 이동. `_cancel()` 함수와 동일 로직을 인라인으로 적용.
- **확인 다이얼로그**: 보류 (현재 2단 방어로 충분, 필요 시 추후 추가)

### 신규 함수
- `pipeline/supabase_read.py` :
  ```python
  delete_임시_products(exclude_id: int | None = None) -> int
  ```
  - 제품명이 `임시_`로 시작하는 모든 레코드 삭제, 삭제 개수 반환
  - `exclude_id` 옵션으로 현재 편집 중인 임시 레코드는 보호 가능 (현재는 전체 정리 모드로 사용)
  - `ilike("임시%")` 로 1차 필터 후 Python에서 `startswith("임시_")` 로 안전 재검증

### 수정 파일
| 파일 | 변경 |
|------|------|
| `pipeline/supabase_read.py` | `delete_임시_products()` 함수 추가 |
| `pages/1_products.py` | 진입 시 임시 레코드 자동 정리 + 토스트 / 강제 JSON 두 개 제거 / "✏️ 스펙 수정" 버튼(primary) |
| `pages/2_product_edit.py` | `_is_temp` 기반 탭 순서 동적 변경 / 스펙 탭 하단 JSON expander / "← 목록으로" 버튼에 임시 삭제 로직 / `get_product_spec` import 추가 |

### 기대 동작
- **수정 시**: 제품 조회 → 행 클릭 → 이미지 + "스펙 수정" 버튼만 표시 → 클릭 → **스펙 탭이 첫 화면에 열림** (총 2클릭, 기존 4클릭에서 단축)
- **신규 등록 시**: 기존 워크플로우(이미지 → VP → 스펙) 그대로 유지
- **임시 레코드**: 어떤 경로로 이탈해도 다음 제품조회 진입 시 자동 회수, "← 목록으로" 클릭 시 즉시 삭제

### Streamlit 동작 메모
- `st.tabs(labels)`: 프로그래밍 방식 탭 전환 API 없음 → 첫 번째 탭이 항상 활성화되는 특성을 이용해 라벨 순서 자체를 바꿈
- `with tab_x:` 블록의 Python 실행 순서는 파일 내 정의 순서를 따름. 시각적 탭 순서와 무관 (탭3에서 탭2의 지역변수 참조하는 기존 코드 안전)

### 후속 과제 (별도 작업)
- ~~**Google Drive 폴더 브라우저**~~ → ✅ 2026-04-29 완료

---

## ⭐ 이미지 업로드 UX + Drive 폴더 브라우저 + 동영상 Vision Pass (2026-04-29 추가)

### 구현 내용

#### 1. 클립보드 붙여넣기 (스크린샷·복사 이미지 업로드)

- **라이브러리**: `streamlit-paste-button==0.1.2` 추가 (`requirements.txt`)
- **UX 흐름**: 📋 버튼 클릭 → Ctrl+V → PNG로 누적 → 미리보기 → 기존 파일선택과 합쳐 Drive 업로드
- **구현 방식**:
  - `_paste_key` 카운터로 붙여넣기 후 위젯 자동 초기화 (중복 방지)
  - 누적 이미지는 `st.session_state["pasted_images"]` 리스트에 저장
  - PIL Image → `io.BytesIO` → PNG bytes로 정규화 후 기존 업로드 루프에 합류
  - 업로드 성공 시 `pasted_images` 자동 비움
- **한계**: 영상 클립보드 캡처는 OS/브라우저 수준 미지원으로 이미지 전용

#### 2. Drive 폴더 브라우저

- **진입**: 상위 Drive 폴더 입력 옆 `📁 찾기` 버튼 토글
- **UI 구성**: breadcrumb(경로 표시) + 서브폴더 3열 그리드 + 액션 버튼(← 상위 / 🏠 루트 / ✓ 이 폴더 선택 / ✕ 닫기)
- **구현 방식**:
  - `f"folder_nav_{sel_account}"` 세션 키로 계정별 독립 네비게이션 스택 관리 → 계정 변경 시 자동 초기화
  - 선택 시 `st.session_state["_picked_folder_id"]` 에 저장, 다음 렌더링에서 `upload_root_folder` 위젯 키에 반영 (위젯 렌더 전 주입 패턴)
  - `list_subfolders(svc, "root")`로 Drive 최상위 폴더 조회 (Drive API `'root' in parents` 쿼리)
- **수정 파일**: `pipeline/drive_client.py` (`list_subfolders` import 추가), `pages/2_product_edit.py`

#### 3. GIF / 동영상 Vision Pass

**GIF**: 별도 처리 없이 기존 이미지 파이프라인 그대로 동작.
- file_uploader가 이미 `gif` 허용, drive_client가 `image/gif → "image"` 유형으로 분류
- Claude: GIF 첫 프레임 분석 / Gemini: 애니메이션 프레임 자동 인식

**동영상 (mp4/mov/webm)**: Gemini Files API 경유 전용 기능.

- **file_uploader 타입 추가**: `"mp4", "mov", "webm"` 추가 및 레이블 "이미지/영상 선택"으로 변경
- **drive_client.py**: `.webm → video/webm` MIME 매핑 및 `_MIME_TO_TYPE` 추가
- **`pipeline/llm.py`**: `generate_vision_gemini_video()` 신규 함수
  ```
  video_bytes → client.files.upload() → ACTIVE 폴링(최대 5분) → Part.from_uri()로 호출 → cleanup
  ```
  - 파일 객체 직접 전달 시 `video_metadata.videoDuration` extra 필드 Pydantic 오류 발생
  - `types.Part.from_uri(file_uri=..., mime_type=...)` 방식으로 URI만 참조하여 해결
  - `cleanup=True` 기본값: 호출 후 Files API 업로드 파일 자동 삭제
- **`pages/2_product_edit.py`**: `🎬 동영상 Vision Pass` 섹션 신규 추가 (이미지 VP expander 아래)
  - Gemini 모델 selectbox만 표시 (Claude 동영상 미지원)
  - Gemini 프롬프트 편집기 (이미지 VP와 공유)
  - 동영상별 카드: ▶ 실행 → 결과 DB 저장(`비전패스_이력`) → 이력 토글(▶/▼) → 📥 반영 / 🗑️ 삭제
  - 📥 반영은 기존 `vp_pending` 충돌 해소 패널과 그대로 연동

**동영상 비용 참고** (Gemini Files API 업로드 후 토큰화):
| | 산정 방식 |
|---|---|
| 영상 프레임 | ~258 토큰/프레임 × (영상 초 × 1fps 샘플) |
| 오디오 | ~32 토큰/초 |
| 1분 영상(Flash) | 약 17,400 토큰 → 약 $0.003 (≈0.4원) |

**사운드 인식**: Gemini는 음성 나레이션(텍스트 추출), 배경음악 분위기, 효과음, 환경음 모두 분석 가능. 제품 설명 나레이션이 있는 홍보 영상에서 특히 유용.

### 수정 파일 요약
| 파일 | 변경 내용 |
|------|-----------|
| `requirements.txt` | `streamlit-paste-button` 추가 |
| `pipeline/drive_client.py` | `.webm` MIME 매핑 추가 |
| `pipeline/llm.py` | `generate_vision_gemini_video()` 신규 |
| `pages/2_product_edit.py` | 클립보드 붙여넣기 UI / Drive 폴더 브라우저 / 동영상 file_uploader 타입 / 🎬 동영상 Vision Pass 섹션 |

---

## 비전패스 개선 — 기획 결정 (2026-04-29)

### 발견된 문제
- **동영상 비전패스가 이미지 프롬프트 공유 사용 중** ([pages/2_product_edit.py:1186](pages/2_product_edit.py)) → 사운드/동작/시간 변화 분석 누락
- **이미지 비전패스 프롬프트가 카테고리 기반**이라 시야가 좁아짐 — 사용자 의도("볼 수 있는 건 모두 보고 최대한 상세히 기록")와 충돌

### 결정사항 요약
1. **이미지 VP**: 단일 호출 2단계(자유관찰 → 구조화)로 개선. 자유관찰 원본도 함께 저장. 검증 단계엔 기존/신규 동시 비교.
2. **동영상 VP**: 전용 프롬프트 분리 (제품시연 특화로 시작). 미래 영상 타입 들어오면 분기 추가.
3. **하이브리드 이미지 첨부**: 평소 시각설명 텍스트 사용 + 필요 시 이미지 첨부 옵션 → 페르소나 LLM 호출 헬퍼 만들 때 표준 옵션으로 포함 (페르소나 01 시작 시점).
4. **Prompt Caching**: 인프라는 페르소나 01 시작 시점에 깔되 활성화는 5개 페르소나 완성 후.
5. **시각설명 1벌 vs N벌**: 페르소나 01 코딩 후 실제 비교로 결정.
6. **git 추적**: 자동화 판매 폴더에 로컬 git init (nested 구조). GitHub은 미래 `aboutkyom-stack/auto-selling`으로.

### 작업 진행 (Phase 1)
- [x] **Step 0**: git init + `.gitignore` + baseline commit (`154050c`)
- [x] **Step 1**: 결정 로그 md 작성 + PROJECT_STATUS.md 갱신 (`6c47906`)
  - 부수: `.gitignore` 보완 누락분 별도 commit (`b0ed03b`)
- [x] **Step 2**: 동영상 VP 프롬프트 분리 — 제품시연 특화 (`2b5e700`)
  - 신규: `agents/00_vision_pass/core_gemini_video.md` (자유관찰 우선 + 놓치기 쉬운 영역 리마인더)
  - 헬퍼: `_vp_video_prompt_path()`, `_vp_load_video_prompt()` 추가
  - 세션 키 분리: `vp_editor_gemini` (이미지) ↔ `vp_editor_gemini_video` (동영상)
- [x] **Step 2.5**: 자동화 판매 폴더 CLAUDE.md 신규 작성 (`b2c293b`)
- [ ] **Step 3**: ⭐ **사용자 검증 — 현재 단계** ⭐
  - 동영상 VP 실행 → 결과에 사운드/동작/시간변화/카메라워크가 잡히는지 확인
  - 동일 동영상의 이전 이력과 비교하면 차이가 명확
- [ ] **Step 4**: 검증 만족 시 → 이미지 VP C안(자유관찰→구조화) + A안(원본 동시 저장) 적용

### Phase 1 git 이력
```
b2c293b docs: CLAUDE.md (자동화 판매 폴더)
2b5e700 feat: 동영상 VP 프롬프트 분리 (제품시연 특화)
b0ed03b chore: .gitignore 보완 (부수자료 제외)
6c47906 docs: 비전패스 개선 기획 결정 로그 작성
154050c chore: 자동화 판매 프로젝트 git 초기화 (baseline)
```

### 상세 결정 사유 + 검토 대안 + 추후 메모
→ [docs/decisions/2026-04-29_vision_pass_planning.md](docs/decisions/2026-04-29_vision_pass_planning.md)

미래 채팅방에서 비전패스 관련 작업 시 이 문서를 먼저 읽으면 맥락·결정 사유·다음 작업 단계를 모두 파악 가능.

---

## 🔖 다음 채팅방 시작 시 안내 (2026-04-30 시점)

### 자동 로드되는 컨텍스트
- 글로벌 CLAUDE.md (`C:\Users\kyum\.claude\CLAUDE.md`) — 사용자 철칙
- 프로젝트 CLAUDE.md (자동화 판매 폴더) — 작업 안내, 폴더 구조
- 메모리 (MEMORY.md 및 연결 파일들)

### 새 채팅방 시작 시 가장 먼저
1. 이 `PROJECT_STATUS.md`를 읽기 (작업 진행 섹션 확인)
2. 비전패스 관련 작업이면 [docs/decisions/2026-04-29_vision_pass_planning.md](docs/decisions/2026-04-29_vision_pass_planning.md) 정독

### 현재 대기 중인 작업 — Step 3 검증

**사용자가 직접 동영상 VP를 실행해 결과 확인 중.**

검증 결과별 다음 행동:
- ✅ **만족** → Step 4 진행 (이미지 VP C+A안 적용)
- ⚠️ **일부 만족** → 동영상 VP 프롬프트 미세 조정 (`agents/00_vision_pass/core_gemini_video.md`)
- ❌ **부족** → 더 강한 자유관찰 지시로 재설계

### Step 4 작업 미리보기 (참고)

이미지 VP를 다음과 같이 개선:
1. **C안 (단일 호출 2단계)**: 자유관찰 → 구조화 정리
2. **A안 (원본 동시 저장)**: 자유관찰 원본도 함께 DB 저장 (사용자가 의심되면 직접 검토 가능)
3. **검증 단계엔 기존/신규 동시 비교 모드** (처음 5~10개 제품)

수정 대상 파일 (예상):
- `agents/00_vision_pass/core_claude.md`, `core_gemini.md` (또는 별도 파일 신규)
- `pages/2_product_edit.py` (이미지 VP 섹션 — 자유관찰 결과 별도 표시)
- DB 스키마 가능 (자유관찰 원본 컬럼 추가 필요할 수 있음)

### 추후 (Phase 2~) 메모

- **페르소나 01 LLM 호출 헬퍼 만들 때**: `images: list | None = None` 옵션 + `cache: bool = False` 옵션 표준 포함 (Q2 하이브리드, Q4 캐싱 인프라)
- **동영상 VP 영상 타입 분기**: 제품 시연 외 영상(광고/강의/일상 등) 들어오는 시점에 드롭다운 + 타입별 프롬프트 분기 추가
- **시각설명 1벌 vs N벌 품질 비교**: 페르소나 01 코딩 후 실제 비교 → N벌 도입 여부 결정
- **Prompt Caching 활성화**: 페르소나 5개 완성 후 자동화 파이프라인에서 토글
- **GitHub 이전**: 프로그램 완성 후 `aboutkyom-stack/auto-selling`으로 push, Streamlit Cloud 배포 검토

---

## 🔖 다음 채팅방 시작 시 안내 (2026-05-02 시점) — 최신

### 직전 세션에서 한 일 (2026-05-02 — 파이프라인 결과 품질 1차 패스)

#2143 테스트 결과 분석 → 4가지 문제 발견(가격 오인·두 까기 같은 결함·나비효과·자가 검수 편향) → 4가지 인프라 해결책 도입:

1. **`agents/_shared/data_contract.md`** — 데이터 권위 규약. `loader.py`가 모든 단계 system prompt 맨 앞에 자동 prepend.
2. **`pipeline/llm.py` cache 로그** — Claude prompt caching hit율 stderr 출력.
3. **`pipeline/lint.py`** — 교차 LLM 린터(Claude↔Gemini). 자가 검수 편향 해결.
4. **`pipeline/sections.py` + UI 통합** — 02 결과를 섹션 단위 부분 수정 가능. cascade는 자동 안 함, 04·05에 stale 배지 + 🔄 재생성 버튼 표시.

`pages/2_pipeline.py`에 헤더 표기(모델명+검증 상태) + 섹션 수정 UI + stale UI 통합. **02 단계만 적용 완료**, 04·05는 다음 방에서 확장.

검증 제품: #2143(가격 오인 해결 확인), #1703(정상 동작 + 린터가 R-01·R-07·R-06 위반 인용까지 정확히 지적).

### 자동 로드되는 컨텍스트
- 글로벌 CLAUDE.md (사용자 철칙)
- 프로젝트 CLAUDE.md (자동화 판매 폴더)
- 메모리 (MEMORY.md 및 연결 파일들)

### 새 채팅방 시작 시 가장 먼저
1. 이 `PROJECT_STATUS.md` (현재 섹션) 읽기
2. **[docs/decisions/2026-05-02_pipeline_quality_pass.md](docs/decisions/2026-05-02_pipeline_quality_pass.md)** 정독 — 결정 사유·변경 파일·다음 우선순위 전부 정리됨
3. (비전패스 작업으로 돌아갈 거면 위 2026-04-30 시점 안내 참고)

### 다음 우선순위 (2026-05-02 결정 로그 §4 참조)
1. **04·05 섹션 단위 수정 UI 확장** — 02 패턴 검증 완료. 단 04·05는 `■ N.` 마커가 아닌 표·`[키워드]:` 구조라 `split_sections()` 패턴 확장 필요.
2. **룰 기반 린터** (정규식·키워드 매칭, 비용 0)
3. **의도적 fail 케이스 테스트** — 린터 객관성 검증
4. **DB versioning 옵션 C** — `엠군_포지셔닝`에 `변경된_섹션 jsonb` 컬럼 추가
5. **캐시 로그 1번째 줄 추적** — 원인 불명 짧은 호출 출처

### 미해결 설계 의문 (결정 로그 §5)
- data_contract proactive 해결 (origin 메타태그) — 보류
- 린터 reviewer를 Opus로 격상 — 검토 가치 있음
- 섹션 부분 수정 시 린터 자동 재호출 여부 — 사용자 선호 미정

---

## 🔖 다음 채팅방 시작 시 안내 (2026-05-03 시점) — 최신

### 직전 세션에서 한 일 (2026-05-03)

세 개의 큰 작업이 한 커밋에 묶여 들어감:

#### 1. 03 네이밍 페이지 신설 — `pages/2_naming.py`
- 파이프라인 외부 도구로 분리. 03은 01~05 결과가 모두 쌓인 후 종합 호출되는 도구라, `2_pipeline.py`에 끼워 넣지 않고 별도 페이지로.
- 흐름: 기존 엠군 run 선택 → 02/04/05 각각 어느 모델 결과를 03 입력으로 쓸지 선택(04·05는 생략 가능) → Claude+Gemini 동시 호출 → `엠군_네이밍` 저장 → 마지막 결과 자동 표시 + 이력 펼치기.
- 헬퍼 추가: `pipeline/loader.py`의 `build_user_input_03()`.

#### 2. 엠군 DB 재구축
신규 테이블(운영 DB 적용 완료):
- `엠군_네이밍` (03 결과)
- `엠군_상세페이지` (04 결과)
- `엠군_채널` (05 결과)
- 부속: `엠군_네이밍_분류`, `엠군_단계출력`, `전파인증`

적용 방식: `db/add_엠군_*.sql` + 대응 `db/run_add_*.py`, 또는 통합본 `db/엠군_재구축.sql` + `db/run_엠군_재구축.py`. 모두 `IF NOT EXISTS` 멱등.

#### 3. 간호도 → 관여도 용어 통일 ⚠️
- **운영 DB 컬럼 rename 1회 실행 완료** (`db/run_rename_간호도_to_관여도.py` — `엠군_타겟.간호도` → `관여도` rename + 0값 1 보정). **재실행 금지** (이미 컬럼이 `관여도`라 rename 실패 + 0→1 보정이 의도와 다른 데이터를 덮을 위험).
- 코드/MD 일괄 치환: `agents/01_deficit_target/*.md`, `agents/02_positioning/qa_checklist.md`, `AGENTS_HANDOVER.md`, `pages/2_pipeline.py`, `pages/2_product_edit.py`, `pipeline/storage.py`, `pipeline/loader.py`, `pipeline/spec_schema.py`.

#### + 동봉된 2026-05-02분
같은 커밋에 묶여 들어간 이전 세션 미커밋분 — 본문 윗 섹션(2026-05-02 시점 안내)에 이미 상세 기록됨:
- `agents/_shared/data_contract.md`, `pipeline/lint.py`, `pipeline/sections.py`, 02 섹션 단위 수정 UI, stale 배지/🔄 버튼.

### 자동 로드되는 컨텍스트
- 글로벌 CLAUDE.md (사용자 철칙)
- 프로젝트 CLAUDE.md (자동화 판매 폴더)
- 메모리 (MEMORY.md 및 연결 파일들)

### 새 채팅방 시작 시 가장 먼저
1. 이 `PROJECT_STATUS.md` (현재 섹션) 읽기
2. **[docs/decisions/2026-05-02_pipeline_quality_pass.md](docs/decisions/2026-05-02_pipeline_quality_pass.md)** 정독 (린터·섹션 수정·data_contract 결정 사유)
3. 03 네이밍 작업이면 `pages/2_naming.py` + `pipeline/loader.py:build_user_input_03()` 직접 확인

### 다음 우선순위 (2026-05-03 갱신)

1. **03 네이밍 결과 품질 검증** — 제품 1~2개로 실측. 제품명·브랜드명 후보의 다양성·시장 정합성 확인.
2. **04·05 섹션 단위 수정 UI 확장** — 02 패턴 검증 완료. 04·05는 `■ N.` 마커가 아닌 표·`[키워드]:` 구조라 `split_sections()` 패턴 확장 필요.
3. **룰 기반 린터** (정규식·키워드 매칭, 비용 0)
4. **의도적 fail 케이스 테스트** — 린터 객관성 검증
5. **DB versioning 옵션 C** — `엠군_포지셔닝`에 `변경된_섹션 jsonb` 컬럼 추가
6. **캐시 로그 1번째 줄 추적** — 원인 불명 짧은 호출 출처

### 미해결 설계 의문 (이전 세션에서 이월)
- data_contract proactive 해결 (origin 메타태그) — 보류
- 린터 reviewer를 Opus로 격상 — 검토 가치 있음
- 섹션 부분 수정 시 린터 자동 재호출 여부 — 사용자 선호 미정
