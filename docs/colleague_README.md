# 📦 ProductHub v2 — 사용 설명서

> 이커머스 제품 등록 자동화 파이프라인
> 작성일: 2026년 4월 22일
> 최종 업데이트: 2026년 4월 22일 (v2 초기 구축 완료)

---

## 🎯 이 프로그램의 목적

온라인 쇼핑몰(쿠팡, 스마트스토어, 11번가 등)에 제품을 등록할 때 필요한 **모든 작업을 체계적으로 관리**하기 위한 시스템입니다.

### 핵심 철학
- **데이터는 한 곳에서 관리** — 제품 정보를 한 번만 입력하면 모든 플랫폼에 활용
- **AI가 할 수 있는 건 AI에게** — 이미지 분석, 문구 생성, 상세페이지 기획을 Gemini AI가 자동 처리
- **사람이 검수** — AI 결과물을 사람이 확인하고 최종 승인하는 구조
- **데이터 무결성 우선** — 스펙 데이터와 AI 생성물을 명확히 분리하여 관리

### 현재 개발 단계
```
현재 목표: 제품 데이터 입력 및 관리 시스템 구축
           (AI 분석/상세페이지 생성은 코드 구현 완료, 실제 운영은 추후)
```

### 전체 흐름
```
제품 목록(엑셀) → 카탈로그 DB → 등록 시작 → 스펙/판매자 정보 입력
→ 이미지 업로드(Drive) → [AI 분석] → [플랫폼별 문구 생성] → [상세페이지 이미지 생성]
```

---

## 📁 파일 구조

```
product_hub_v2/
├── app.py                   ← Streamlit 메인 실행 파일
├── requirements.txt         ← 패키지 목록
├── .env                     ← API 키 (공유 금지)
├── README.md                ← 이 파일
├── ProductHub_흐름도.html   ← 작업 흐름 시각화
├── ProductHub_Demo.html     ← 데모 페이지 (브라우저에서 바로 실행)
├── pages/
│   ├── 1_catalog.py         ← 제품 카탈로그
│   ├── 2_product.py         ← 제품 정보 입력
│   ├── 3_pipeline.py        ← AI 분석 실행
│   ├── 4_detail_page.py     ← 상세페이지 생성
│   └── 5_database.py        ← DB 브라우저
└── utils/
    ├── __init__.py
    ├── supabase_client.py   ← Supabase 연결/쿼리
    └── drive_client.py      ← Google Drive 연결
```

---

## ⚙️ 환경 설정 (.env)

```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=xxxx
GEMINI_API_KEY=xxxx
TOKEN_PATH=D:\Claude\product_hub\credentials\token.pickle
DRIVE_ROOT_FOLDER_ID=xxxx
```

---

## 🚀 실행 방법

```bash
# 패키지 설치 (최초 1회)
pip install -r requirements.txt

# 실행
streamlit run app.py

# 접속
http://localhost:8501
```

---

## 🗄️ DB 구조

Supabase(PostgreSQL) 사용 · 총 3개 테이블

---

### 1. product_catalog — 전체 제품 카탈로그

역할: 취급하는 모든 제품의 마스터 목록. 엑셀 주문업무 파일 기반.
특징: 온라인 등록 여부와 관계없이 전체 재고 제품 보관 (현재 1,142개)

| 필드명 | 타입 | 설명 |
|--------|------|------|
| id | 숫자 | 고유 식별자 (자동 생성) |
| name | 텍스트 | 제품명 |
| stock_realtime | 숫자 | 실시간 재고 수량 |
| stock_afterprocess | 숫자 | 후처리 재고 수량 |
| price_retail | 숫자 | 소매가 (원) |
| price_wholesale | 숫자 | 도매가 (원) |
| price_actual | 숫자 | 실거래가 (원) |
| price_avg_wholesale | 숫자 | 최종 평균도매가 (원) |

---

### 2. products_v2 — 온라인 등록 진행 제품

역할: product_catalog에서 실제 온라인 판매를 진행하기로 결정한 제품만 관리.
특징: catalog_id로 product_catalog와 연결. 등록에 필요한 모든 상세 정보 보관.

기본 정보
| 필드명 | 타입 | 설명 |
|--------|------|------|
| id | 숫자 | 고유 식별자 |
| catalog_id | 숫자 | product_catalog 연결 키 (FK) |
| name | 텍스트 | 제품명 |
| status | 텍스트 | draft / review / done |
| drive_folder_id | 텍스트 | Google Drive 폴더 ID |

제품 스펙 (직접 입력)
| 필드명 | 설명 |
|--------|------|
| spec_width_cm / spec_depth_cm / spec_height_cm | 가로/세로/높이 (cm) |
| spec_weight_g | 무게 (g) |
| spec_material / spec_color | 소재 / 색상 |
| spec_components | 구성품 |
| spec_origin / spec_manufacturer / spec_model | 제조국 / 브랜드 / 모델명 |

인증 정보 (직접 입력)
| 필드명 | 설명 |
|--------|------|
| cert_kc_yn | KC 인증 여부 |
| cert_kc_number | KC 인증 번호 |
| cert_other | 기타 인증 정보 |

판매자 운영 정보 (직접 입력)
| 필드명 | 설명 |
|--------|------|
| seller_notes | 판매자 특이사항 (장단점 전부) |
| inspection_yn / inspection_note | 검수 여부 / 방법 |
| stock_qty / restock_yn / discontinued_yn | 재고 / 재입고 / 단종 |
| box_reuse_yn / online_sale_yn / sale_channel | 박스재사용 / 온라인판매 / 채널제한 |
| cautions | 기타 주의사항 |

AI 분석 결과 (pipeline 자동 입력)
| 필드명 | 설명 |
|--------|------|
| features / keywords | 핵심 특징 / 검색 키워드 |
| dimensions | AI 추출 치수 정보 (JSON) |
| target_audience / selling_point | 타겟 고객 / 핵심 소구점 |
| competitor_weakness | 경쟁사 약점 |

AI 생성 문구 (pipeline 자동 입력)
| 필드명 | 설명 |
|--------|------|
| detail_page_text | 상세페이지 공통 본문 |
| promo_coupang / promo_smartstore / promo_11st / promo_esm | 각 플랫폼별 문구 (JSON) |
| promo_band / promo_blog / promo_youtube | 밴드 / 블로그 / 유튜브 문구 |

---

### 3. drive_files — Google Drive 파일 목록

역할: 각 제품의 이미지/영상 파일을 Drive에 업로드한 후 DB에 기록.

| 필드명 | 설명 |
|--------|------|
| id | 고유 식별자 |
| product_id | products_v2 연결 키 (FK) |
| drive_file_id | Google Drive 파일 ID |
| file_name / file_type | 파일명 / 종류 (image/video/detail) |
| drive_url | Drive 접근 URL |

---

## 🔗 테이블 관계도

```
product_catalog (1,142개 전체 제품)
        │
        │ catalog_id (1:1)
        ▼
products_v2 (온라인 등록 진행 제품만)
        │
        │ product_id (1:N)
        ▼
drive_files (제품별 이미지/영상 파일)
```

---

## 🔄 제품 등록 작업 순서

```
1. 📋 제품 카탈로그
   → 등록할 제품 검색 (검색/필터 지원)
   → "등록 시작" 버튼 클릭
   → products_v2에 레코드 자동 생성 (status: draft)

2. ✏️ 제품 정보 입력
   [이미지 업로드 탭]
   → 이미지 업로드 → Google Drive 자동 저장 → drive_files DB 기록

   [제품 스펙 입력 탭]
   → 크기/무게/소재/색상/구성품 직접 입력
   → 제조국/브랜드/모델명, KC 인증 정보 입력

   [판매자 정보 입력 탭]
   → 특이사항, 재고, 검수 여부, 판매 채널 등 입력
   → 사소한 것도 전부 입력 (AI가 선별해서 사용)

3. 🤖 AI 분석 실행 (추후 운영 예정)
   → Gemini Vision 이미지 분석
   → 핵심 특징/키워드/타겟 자동 추출
   → 플랫폼별 판매 문구 자동 생성
   → status 자동으로 review로 변경

4. 🎨 상세페이지 생성 (추후 운영 예정)
   → 참조 이미지 선택
   → AI 기획안 생성 (섹션별 전략/메시지)
   → 상세페이지 이미지 자동 생성 → Drive 저장
```

---

## 📌 status 의미

| status | 의미 | 표시 |
|--------|------|------|
| draft | 작업 진행 중 (기본값) | 🔵 |
| review | AI 분석 완료, 검토 대기 | 🟡 |
| done | 최종 완료 | 🟢 |

---

## 🚧 개발 현황 (2026.04.22 기준)

### ✅ 완료
- product_catalog 구축 (1,142개 엑셀 데이터 업로드)
- products_v2 테이블 설계 및 생성 (스펙/인증/판매자/AI 필드 포함)
- drive_files 테이블 연동
- Streamlit 5개 페이지 구현 및 로컬 테스트 완료
- Google Drive 이미지 업로드/조회/삭제
- 제품 스펙 입력 화면 (크기/소재/인증 등)
- 판매자 정보 입력 화면
- DB 브라우저 (조회 + 수정)
- 카탈로그 검색/필터 (미등록/진행중/검토대기/완료)
- AI 분석 파이프라인 코드 구현 (Gemini Vision + 문구 생성)
- 상세페이지 생성 코드 구현
- 데모 HTML 페이지 제작 (ProductHub_Demo.html)
- 작업 흐름도 제작 (ProductHub_흐름도.html)

### 🔜 예정
- 실제 제품 데이터 입력 및 DB 축적
- AI 분석 파이프라인 테스트 및 퀄리티 개선
- AI 분석 / 상세페이지 생성 별도 앱 분리 검토
- GitHub 연동 및 협업 구조 구축
- Streamlit Cloud 배포 (URL 고정, 팀원 접근)
- 플랫폼 자동 업로드 (쿠팡, 스마트스토어 등) — 장기

### ⏸️ 보류
- AI 분석 실제 운영 (코드 완성, 퀄리티 개선 후 운영)
- 상세페이지 생성 실제 운영 (이미지 생성 모델 안정화 필요)
- GitHub 협업 구조 (데이터 충분히 쌓인 후 전환)
