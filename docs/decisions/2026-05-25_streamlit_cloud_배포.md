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
| **GitHub repo** | **Public** (코드 노출 OK — 동료에게 보여줘도 무방, 민감 정보는 모두 .gitignore) ⚠️ 초기 Private 시도했으나 Streamlit Community Cloud 무료 플랜이 Private repo 미지원 → Public으로 확정 |
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
| **OAuth client** | ~~본인 Google 계정으로 신규 발급~~ → **동료 계정(voyager/donnamoo) ID/비번 인수, 기존 credentials/ 그대로 사용** (신규 발급 없음) |
| **Drive 데이터 계정** | ~~본인 계정 신규 추가~~ → **동료 계정 그대로 사용** (신규 계정 추가 없음) |
| **전환 전략** | 해당 없음 — 동료 계정 그대로 운영 |
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

### Phase 0 — 선검증 ✅ 완료 (2026-05-25)

- [x] GitHub Public repo 생성: `aboutkyom-stack/auto-sales`
- [x] 코드 push (master 브랜치)
- [x] share.streamlit.io 가입 (aboutkyom@gmail.com)
- [x] 앱 배포: `https://auto-sales-wktrade.streamlit.app`
- [x] Restricted access: aboutkyom / voyager / donnamoo 3개 이메일
- [x] Secrets 등록 (MY_SUPABASE_*, API 키, APP_ROLE=partner)
- [x] 앱 정상 동작 확인 (DB·이미지·파이프라인)
- [x] 동료 접속 확인 (sign in 후 접근 가능)

### Phase 1 — DB 스키마 & 백엔드 ✅ 완료 (2026-05-26, commit `30655bc`)

- [x] **1-1. `편집_세션` 테이블** — `db/add_편집_세션.sql` + `db/run_add_편집_세션.py` (멱등 IF NOT EXISTS)
- [x] **1-2. `drive_auth` 테이블** — **옵션 b 채택** (우리 DB에 `drive_accounts` 없음). `db/add_drive_auth.sql` + 실행기
- [x] **1-3. Drive 토큰 함수** — `get_drive_token`, `upsert_drive_token` 추가
- [x] **1-4. 편집 세션 함수** — `upsert_편집_세션`, `get_active_편집_세션(ttl_min=5)` 추가
- [x] **1-5. 낙관적 락 지원** — `update_상품(original_수정일=None)` 시그니처 확장, 충돌 시 `False` 반환
- [x] **(부록) `상품_수정일_갱신` 트리거 추가** — §2-6 A의 "추가 마이그레이션 불필요" 가정이 실제와 달랐음 (수정일은 DEFAULT NOW만 있고 UPDATE 트리거 부재). BEFORE UPDATE 트리거로 보강 → 낙관적 락 동작 보장. `db/add_상품_수정일_트리거.sql` + 실행기

### Phase 2 — 코드 분기 로직 ✅ 완료 (2026-05-26, commit `6a3c693`)

- [x] **2-1. `drive_client.py` DB fallback** — pickle 우선 + `drive_auth` DB fallback. refresh 시 양쪽 동기화. 환경 감지는 `pipeline.runtime.is_streamlit_cloud`.
- [x] **2-2. `refresh_oauth_token.py` DB 자동 update** — 발급 후 `upsert_drive_token` 자동 호출
- [x] **2-3. `pages/2_product_edit.py` 동시편집 통합** — 진입 시 편집 세션 upsert(30초 debounce, 임시 레코드 제외) + 다른 사용자 편집 알림 배지 + `_save` / `_auto_apply_after_vision` / 충돌 해소 통합 저장에 낙관적 락 적용

### Phase 3 — Drive 계정 대시보드 ✅ 완료 (2026-05-27, commit `ea64391`)

- [x] **3-1. `get_account_quota(name)`** — `about(storageQuota,user)` 기반 정확 quota·email
- [x] **3-2. `pages/5_drive_dashboard.py` 신규** — 카드(역할·이메일·상태·잔여용량 progress·파일수·토큰동기화시각) + 추천 다음 업로드 계정 헤더 + `@st.cache_data(ttl=60)`
- [x] **3-3. 계정 역할 라벨 — 코드 단일 소스 채택** — `drive_client.ACCOUNTS` 항목에 `"역할"` 필드 추가 (voyager=메인 운영, donnamoo=보조 운영)
- [x] **(신규) OAuth 재인증 1차 — 가이드 expander** — 각 카드에 로컬 `refresh_oauth_token.py` 실행 절차 안내. 대시보드 내 진짜 OAuth callback 통합은 Backlog (redirect URI 추가 등록 필요)

### Phase 4 — 배포 준비 ✅ 완료 (2026-05-27, commit `ea64391`)

- [x] **4-1. 환경 감지 헬퍼** — `pipeline/runtime.py:is_streamlit_cloud()` (HOSTNAME / STREAMLIT_SHARING_MODE / STREAMLIT_RUNTIME)
- [x] **4-2. `secrets.toml` 템플릿** — `.streamlit/secrets.toml.example` 신규
- [x] **4-3. `os.getenv` 호출 통일 점검** — 모든 키 top-level (APP_ROLE / ANTHROPIC_API_KEY / GEMINI_API_KEY / MY_SUPABASE_* / 모델 override). Streamlit secrets.toml top-level 자동 환경변수 매핑과 호환 → **코드 변경 불필요**

### Phase 5 — GitHub & Streamlit Cloud 셋업 ✅ 완료/취소 (Phase 0에서 처리)

- [x] **5-1. GitHub Public repo 생성** — Phase 0에서 완료 (`aboutkyom-stack/auto-sales`)
- [x] **5-2. 첫 push 인증** — Phase 0에서 완료
- ~~5-3. 본인 OAuth client 발급~~ — **취소** (§2-4 결정 변경: 동료 credentials 그대로 인수)
- ~~5-4. 본인 Drive 계정 ACCOUNTS 추가~~ — **취소** (§2-4 결정 변경: 동료 계정 그대로 사용)
- [x] **5-5. share.streamlit.io 가입 + 앱 생성** — Phase 0에서 완료
- [x] **5-6. Streamlit Cloud secrets 등록** — Phase 0에서 완료
- [x] **5-7. Restricted access 설정** — Phase 0에서 완료
- [x] **5-8. 동료 첫 접속 테스트** — Phase 0에서 완료

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
- **(2026-05-27 추가) Drive 대시보드 안 OAuth callback 통합 — 동료 측 + owner 측 양쪽**
  - **동료 측**: Drive 대시보드 안 "🔄 재인증" 버튼 → Streamlit Cloud에서 Google OAuth flow → `drive_auth` DB 자동 업데이트. 동료가 자기 손으로 자기 계정 토큰 갱신.
  - **owner 측**: 같은 페이지에 "🔄 내 계정 재인증" 버튼 → 로컬 브라우저로 OAuth flow → DB 갱신. 현재 `scripts/refresh_oauth_token.py` 단독 실행 방식을 페이지 버튼 클릭으로 대체. (사용자 요청: "py 파일 직접 실행은 너무 번거롭다")
  - 구현: Streamlit Cloud redirect URI 등록 + `flow.fetch_token` 통합 + 환경 분기(`is_streamlit_cloud()`)로 redirect URL 결정. 현재 1차는 가이드 expander만.
- **(2026-05-27 추가) Drive 토큰 만료 임박 표시** — `drive_auth.updated_at` 기준 N일 경과 시 ⚠️ 배지. OAuth 7일 만료 가정 + 활성 사용 시 연장 케이스 처리.
- **(2026-05-27 추가) 편집_세션 만료 row 정리** — 현재 ttl 5분 필터로 무시만 함, row 누적. 페이지 진입 시 또는 cron으로 정기 청소.

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

- [x] 기존 `drive_accounts` 테이블 스키마 확인 → 우리 DB에 없음 → 신규 `drive_auth` 테이블로 결정 (옵션 b)
- [x] git remote 상태 확인 → `https://github.com/aboutkyom-stack/auto-sales.git` 연결됨
- [x] OAuth client → 동료 credentials 그대로 인수 (신규 발급 없음)
- [x] Streamlit Cloud 가입 → 완료, 앱 배포 및 동료 접속 확인

---

## 7. 본 세션 git 이력 (참고)

```
351a514 feat: partner 모드 + 엠군작업대상 필드 추가
5d27ec2 chore: 테스트 이미지 파일 git 추적 제거 (.gitignore에 테스트/ 추가)
a21a0dc feat: agents 통합 구조 + 2단계 파이프라인 + 04_b 검수 자동화 통합
```
