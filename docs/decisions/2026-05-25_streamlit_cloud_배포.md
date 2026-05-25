# Streamlit Cloud 배포 · 동시편집 보호 · Drive 토큰 DB 동기화 — 기획 결정

작성일: 2026-05-25
관련 파일: PROJECT_STATUS.md, OAUTH_SETUP.md, docs/BACKLOG.md

> 이 문서는 다음 세션에서 바로 코딩에 들어갈 수 있도록 모든 결정사항·작업 항목·구현 명세를 한 곳에 정리한 것이다.
> 새 채팅방 시작 시 PROJECT_STATUS.md "다음 채팅방 시작 시 안내 (2026-05-25 시점)" → 본 문서 정독 순으로 컨텍스트를 회복한다.

---

## 1. 배경

### 1-1. 원래 목표
- 동료와 DB·Drive 공유로 온라인 판매량 증대
- 동료는 운영 담당, 사용자(나)는 개발·기획 담당

### 1-2. 이번 세션에서 확정된 운영 방향
**핵심 전환**: "Streamlit 서버에 동료가 직접 접속해서 파이프라인 돌림" → "사용자 Claude Code로 파이프라인 돌리고 동료는 결과 조회·기본정보 입력만"

이유:
- 동료가 Streamlit으로 파이프라인 돌리면 Claude/Gemini API 비용 발생
- 사용자가 Claude Code로 돌리면 별도 API 비용 없음 (Claude Code 구독료에 포함)
- 동료는 Drive 이미지 업로드 + 스펙 입력 + 결과 조회만 하면 됨
- 사용자가 '엠군 작업대상' 표시된 제품을 한가할 때(예약 작업 가능) 일괄 처리

### 1-3. 이미 완료된 작업 (본 세션 전반부)
- `pipeline/role.py` — `APP_ROLE` 환경변수로 owner/partner 분기
- DB `상품.엠군작업대상 BOOLEAN` 컬럼 + 인덱스 추가 (마이그레이션 실행 완료)
- `set_엠군작업대상()` 함수 추가
- `1_products.py` — 🎯작업대상 컬럼 표시 + 필터
- `2_product_edit.py` — 엠군작업대상 토글 버튼 + partner 모드에서 VP·자동추출 숨김
- `2_pipeline.py` — partner 모드에서 실행 버튼 disabled (조회는 유지)

---

## 2. 확정된 결정사항

### 2-1. 배포 방식

| 항목 | 결정 |
|---|---|
| **호스팅** | Streamlit Cloud (Streamlit Inc. 제공) |
| **요금** | 무료 플랜 |
| **GitHub repo** | **Public** (코드 노출 OK — 동료에게 보여줘도 무방, 민감 정보는 모두 .gitignore) |
| **앱 접근 제한** | **Restricted access** — 사용자 + 동료 Google 이메일만 허용 |
| **자동 배포** | `git push` 시 Streamlit Cloud가 자동 pull → 빌드 → 재배포 |

### 2-2. 동료에게 줄 것

**아무것도 없음.** 동료는 Streamlit Cloud 앱 URL만 받음.
- 동료 PC에 코드/Python/.env/credentials 어떤 것도 설치 X
- 브라우저만 있으면 됨
- 코드 업데이트 시 동료는 새로고침만 하면 됨

### 2-3. `_공통 두뇌` 처리

- repo 루트(`자동화형/`) **밖**에 있어 git이 추적조차 안 함
- Streamlit Cloud에 자연스럽게 안 올라감 (.gitignore 등록 불필요)
- partner 모드에서는 `_공통 두뇌` 로드 함수 자체가 호출 안 되므로 폴더 없어도 에러 없음 (loader.py 확인 완료)

### 2-4. Google Drive OAuth 전환

| 항목 | 결정 |
|---|---|
| **OAuth client** | **본인 Google 계정으로 신규 발급** (현재 동료 계정 발급 OAuth client 사용 중) |
| **Drive 데이터 계정** | 본인 계정 신규 추가 + 동료 계정(donnamoo, voyager) **점진적 전환** |
| **전환 전략** | 본인 계정 추가 → 안정화 → 동료 계정 코드에서 제거 |
| **OAuth client 유형** | **데스크톱 앱** 유지 (방식 B: 로컬 스크립트 갱신 — 본인 계정이라 사용자가 직접 갱신) |
| **모드** | Testing 그대로 (Production 전환은 verification 부담 큼) |
| **만료 주기** | 공식 7일 (활성 사용 시 더 가는 경우도 있음) |
| **갱신 방식** | 만료 시 `python scripts/refresh_oauth_token.py {이름}` 실행 → 스크립트가 Supabase DB 자동 update |

### 2-5. Drive 토큰 DB 동기화 메커니즘

```
[기존]
credentials/token{n}_{name}.pickle (로컬 파일만)
   ↓ Streamlit Cloud에 직접 못 보냄 (파일은 secrets에 못 들어감)

[신규]
Supabase 테이블 `drive_auth` (또는 기존 drive_accounts 확장)
   ├ account_name  : voyager / donnamoo / kyom_main / kyom_sub
   ├ refresh_token : "1//0abc..." (영구 또는 7일)
   ├ client_id, client_secret
   ├ token_uri
   ├ scopes
   └ updated_at

[앱 동작]
- 로컬 owner 모드: credentials/{name}.pickle 우선, 없으면 DB fallback
- Streamlit Cloud partner 모드: DB read만 (pickle 없음)
- 만료 시: 로컬에서 refresh_oauth_token.py 실행 → 자동 DB update → Cloud에 다음 페이지 로드부터 반영

[Streamlit Cloud secrets]
- SUPABASE 키만 두면 됨 (Drive 관련 키는 DB에 있으니까)
- 자주 변경 안 됨 → 수동 등록 1회로 충분
```

### 2-6. 동시편집 보호 — 옵션 A + B 조합

**A. 낙관적 락 (Optimistic Lock)**

- 기존 `상품.수정일` 컬럼 활용 (이미 있음, 추가 마이그레이션 불필요)
- 저장 시 `.eq("수정일", original_수정일)` 조건 추가
- 충돌 감지 (저장이 빈 결과를 반환) 시 토스트:
  - `"⚠️ 다른 사용자가 먼저 수정했습니다. 새로고침 후 다시 시도하세요."`
- 자동 새로고침은 안 함 — 사용자가 입력한 내용 보호 위해 직접 확인 후 진행

**B. 편집 세션 테이블 (사회적 조정)**

신규 테이블 `편집_세션`:
```sql
CREATE TABLE 편집_세션 (
    id              BIGSERIAL PRIMARY KEY,
    상품_id         BIGINT NOT NULL REFERENCES 상품(id) ON DELETE CASCADE,
    사용자명        TEXT NOT NULL,         -- "owner(나)" / "partner(동료)"
    마지막_활동시각 TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (상품_id, 사용자명)
);
CREATE INDEX idx_편집세션_상품 ON 편집_세션(상품_id);
```

**동작**:
- `pages/2_product_edit.py` 진입 시 → 본인 row UPSERT (마지막_활동시각 = NOW())
- 페이지 상단에 같은 상품_id의 다른 row 있으면 배지: `"⚠️ 지금 {사용자명}이 편집 중입니다 ({마지막 활동}부터)"`
- 페이지에서 사용자 활동(텍스트 입력, 저장 등) 시 본인 `마지막_활동시각` 업데이트 (debounce: 30초)
- 5분 무활동 row는 만료된 것으로 간주 (배지 표시 안 함)
- 강제 차단 없음 — 경고만, 둘이 무릅쓰고 같이 편집 가능

**사용자명 결정**:
- `APP_ROLE=owner` → `"owner(나)"`
- `APP_ROLE=partner` → `"partner(동료)"`
- 추후 다인 운영 시 별도 식별자 추가 (지금은 2인 운영이라 충분)

### 2-7. push 자동화

| 옵션 | 채택 여부 |
|---|---|
| 명시적 요청 (사용자가 "push해줘") | ✅ 채택 |
| 슬래시 명령 단축 (`/push`) | 검토 (필요 시 추가) |
| 파일 변경 자동 push | ❌ Streamlit Cloud는 push 즉시 재배포 → 깨진 코드가 동료에게 즉시 전파될 위험 |
| 주기적 자동 push (cron) | ❌ 위와 동일 |

**push 직전 안전망**: GitHub Actions로 `python -m py_compile` 같은 간단한 syntax 체크 (선택사항, 나중에 추가 가능)

### 2-8. 기타 운영 결정

| 항목 | 결정 |
|---|---|
| git 브랜치 전략 | **master 직접 작업** (별도 폴더 복사 불필요, 환경 분기로 owner 동작 보호됨) |
| 큰 변경 전 | 사용자 사전 승인 후 진행 (CLAUDE.md 철칙) |
| 단계 커밋 | 각 작업 단위마다 커밋 (되돌리기 용이) |

---

## 3. 다음 세션 작업 체크리스트

> 새 채팅방 시작 시 이 섹션을 그대로 작업 목록으로 사용한다.

### Phase 1 — DB 스키마 & 백엔드 (작은 단위)

- [ ] **1-1. Supabase 마이그레이션 — `편집_세션` 테이블**
  - `db/add_편집_세션.sql` + `db/run_add_편집_세션.py` 신규
  - 멱등 (IF NOT EXISTS)

- [ ] **1-2. Supabase 마이그레이션 — `drive_auth` 컬럼/테이블**
  - 옵션 a: 기존 `drive_accounts` 테이블에 `refresh_token`, `client_id`, `client_secret`, `token_uri`, `scopes` 컬럼 추가
  - 옵션 b: 신규 `drive_auth` 테이블 별도 생성
  - **결정 필요**: 새 채팅방에서 기존 `drive_accounts` 스키마 확인 후 결정

- [ ] **1-3. `pipeline/supabase_read.py` — Drive 토큰 함수 추가**
  - `get_drive_token(name) → dict`
  - `upsert_drive_token(name, token_data)`

- [ ] **1-4. `pipeline/supabase_read.py` — 편집 세션 함수 추가**
  - `upsert_편집_세션(상품_id, 사용자명)`
  - `get_active_편집_세션(상품_id, exclude_사용자명, ttl_min=5) → list`

- [ ] **1-5. `pipeline/supabase_read.py` — 낙관적 락 지원**
  - `update_상품()` 함수 시그니처 확장: `original_수정일` optional 인자 추가
  - 매칭 실패 시 None 반환 (또는 별도 sentinel)

### Phase 2 — 코드 분기 로직

- [ ] **2-1. `pipeline/drive_client.py` — DB fallback 추가**
  - 환경 감지 (`_running_on_streamlit_cloud()` 헬퍼)
  - 로컬 owner: pickle 우선
  - Cloud 또는 pickle 없을 때: DB에서 토큰 read → `Credentials` 객체 빌드

- [ ] **2-2. `scripts/refresh_oauth_token.py` — DB 자동 update 추가**
  - 발급 후 pickle 저장 + DB upsert 자동 실행
  - 본인 계정 신규 발급 흐름 가이드 (OAUTH_SETUP.md 갱신)

- [ ] **2-3. `pages/2_product_edit.py` — 동시편집 통합**
  - 진입 시 `upsert_편집_세션()` 호출
  - 상단 배지: 다른 사용자 편집 중 알림
  - 저장 시 낙관적 락 (`update_상품(... , original_수정일)`) → 충돌 시 토스트

### Phase 3 — Drive 계정 대시보드 (사용자 요청)

- [ ] **3-1. `pipeline/drive_client.py` — quota 조회 함수**
  - `get_account_quota(name) → dict(total, used, free, percent)`
  - Drive API `about().get(fields="storageQuota,user")` 사용
  - 본인 OAuth 계정에서 정확한 값 조회 가능 (서비스 계정과 달리)

- [ ] **3-2. `pages/?_drive_dashboard.py` 신규 페이지**
  - 모든 연동 계정 카드 표시:
    - 계정명(label) + 이메일 + 역할 라벨 (예: "메인 운영", "백업", "테스트")
    - 총 용량 / 사용량 / 잔여 (progress bar)
    - DB의 `상품_파일` 행 수 (이 계정에 업로드된 파일 개수)
    - 마지막 사용 시각
    - 상태 (✅ 정상 / ⚠️ 토큰 만료 임박 / ❌ 토큰 무효)
  - 헤더에 "추천 다음 업로드 계정: {잔여 가장 많은 계정}"
  - 사이드바 메뉴에 등록 ("☁️ Drive 계정")

- [ ] **3-3. 계정 역할 라벨 DB 컬럼**
  - `drive_accounts.역할 TEXT` 같은 컬럼 추가 (옵션)
  - 또는 `drive_client.ACCOUNTS` 리스트에 역할 필드 추가
  - **결정 필요**: 새 채팅방에서 정함

### Phase 4 — 배포 준비 (코드 측면)

- [ ] **4-1. Streamlit Cloud 환경 감지 헬퍼**
  - `pipeline/runtime.py` 신규 또는 `role.py` 확장
  - `is_streamlit_cloud() → bool` (`os.getenv("HOSTNAME")` 또는 `st.runtime` 활용)

- [ ] **4-2. `secrets.toml` 템플릿**
  - `.streamlit/secrets.toml.example` 신규 (실제 secrets.toml은 .gitignore 그대로)
  - Streamlit Cloud secrets 등록 UI에 그대로 붙여넣을 수 있는 형식

- [ ] **4-3. `os.getenv` 호출 통일**
  - 코드 전반에서 `os.getenv` 사용 중 — Streamlit Cloud는 secrets를 자동으로 환경변수에 매핑하므로 그대로 동작
  - 단 secrets.toml에 [section]을 쓰면 `os.getenv("section_KEY")` 형식이라 통일 확인 필요

### Phase 5 — GitHub & Streamlit Cloud 셋업 (사용자 직접 + Claude 보조)

- [ ] **5-1. GitHub Public repo 생성** (`gh repo create` 가능)
- [ ] **5-2. 첫 push 인증 (Personal Access Token 등록)**
- [ ] **5-3. 본인 OAuth client 발급 (Google Cloud Console — 사용자 직접)**
- [ ] **5-4. 본인 Drive 계정 ACCOUNTS 리스트에 추가 + pickle 발급 + DB upsert**
- [ ] **5-5. share.streamlit.io 가입 + 앱 생성 (사용자 직접)**
- [ ] **5-6. Streamlit Cloud secrets 등록 (사용자 직접, Claude가 toml 내용 안내)**
- [ ] **5-7. Restricted access 설정 + 동료 이메일 추가 (사용자 직접)**
- [ ] **5-8. 동료 첫 접속 테스트**

---

## 4. Backlog (당장 안 하지만 잊지 말 것)

- **Drive 계정 간 자료 이동/백업 기능**
  - A 계정 파일 → B 계정으로 복사+삭제 (외부 계정 간은 권한 이전 불가, 복사+원본삭제 방식)
  - 단일 파일 / 폴더 단위 일괄 처리
  - Phase 3 대시보드에서 액션 버튼으로
- **OAuth Production 전환 도전**
  - 7일 만료가 진짜 빈번하게 골치 아프면 시도
  - 개인정보 처리방침, 도메인 검증, 시연 영상 등 자료 준비
  - 수 주~수 개월 소요 가능
- **push 직전 GitHub Actions syntax check**
- **OAuth 갱신 방식 A (Streamlit Cloud 내장 OAuth 갱신 페이지)** — 방식 B(로컬 스크립트)가 너무 불편할 때
- **다인 운영 대비 사용자명 식별자 강화** (현재 owner/partner 2값)
- **Drive 자동 분배 로직** — 잔여 용량 가장 많은 계정 자동 선택 (PROJECT_STATUS.md 기존 backlog와 동일)

---

## 5. 새 채팅방에서의 시작 방법

새 채팅방에서 사용자가 "시작하자" 또는 "다음 작업 가자" 정도만 말하면:

1. 클로드코드가 `자동화형/CLAUDE.md` 자동 로드
2. CLAUDE.md 18번 줄 지시에 따라 `PROJECT_STATUS.md` 정독
3. PROJECT_STATUS.md "다음 채팅방 시작 시 안내 (2026-05-25 시점) — 최신" 섹션에서 본 결정 로그 가리킴
4. 본 결정 로그 정독 → §3 체크리스트를 작업 목록으로 옮김 (TaskCreate)
5. Phase 1부터 순차 진행

---

## 6. 핵심 사전 확인 사항 (다음 세션 시작 시)

- [ ] 기존 `drive_accounts` 테이블 스키마 확인 — 컬럼 추가 vs 신규 테이블 분리 결정
- [ ] 현재 git remote 상태 확인 — GitHub repo 아직 연결 안 됨
- [ ] OAuth client 본인 명의 발급 여부 확인 (사용자 직접 작업)
- [ ] Streamlit Cloud 가입 여부 확인 (사용자 직접 작업)

---

## 7. 본 세션 git 이력 (참고)

```
351a514 feat: partner 모드 + 엠군작업대상 필드 추가
5d27ec2 chore: 테스트 이미지 파일 git 추적 제거 (.gitignore에 테스트/ 추가)
a21a0dc feat: agents 통합 구조 + 2단계 파이프라인 + 04_b 검수 자동화 통합
```
