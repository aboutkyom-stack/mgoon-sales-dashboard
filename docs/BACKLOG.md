# 자동화형 BACKLOG — 추후 할일 모음

> 짬 날 때 처리할 작업 목록. 우선순위·상세 가이드 문서·관련 파일을 한 곳에.
> 작업 완료 시 항목 옆에 ✅ + 완료일 + 결과 파일 위치 기록.
> 새 추후 할일 발견 시 우선순위 표시하고 여기에 append.

**범례**: 🔴 HIGH (운영 안정성·차단) / 🟡 MEDIUM (운영 영향 작음) / 🟢 LOW (정리·문서)

---

## 활성 작업

### 🟡 본인 Google 계정으로 OAuth 전환

- **상황**: 현재 동료 계정 2개(`voyager`·`donnamoo`)로 운영. 동료가 pickle 발급·갱신 해줘야 하는 의존 구조.
- **목표**: 본인 Google 계정으로 점진 전환 → 동료 의존 끊기.
- **권장 옵션**: B — 점진 전환 (동료 계정 토큰 만료까지 운영하면서 자연스럽게 본인 계정으로 이동)
- **가이드**: [docs/migration_to_personal_google_account.md](migration_to_personal_google_account.md)
- **소요**: 4-1단계만 15~20분 (Google Cloud Console + pickle 발급). 전체 전환은 점진.
- **차단 요소 없음**: 짬 될 때 진행.


### 🟢 04_b 검수 자동화 통합 — **옵션 3 (토글) 1차 구현 완료** (이월: 실전 검증)

- **완료 (2026-05-24)**: 옵션 3 (토글) 1차 구현 완료. 사용자 명시적 호출 시에만 04_b 실행. DB 결과 정상 저장 확인 필요(이번 세션은 코드 구현 검증까지). 첫 실전 호출 시 한 번 확인.
- **남은 일**: 실전에서 한 번 돌려보고 검수 보고서 + 다듬은 콘티 두 블록이 마커로 정상 분리·DB 저장되는지 확인. 마커 파싱 실패율 높으면 04_b instruction.md의 출력 마커 명세 강화 필요.
- **옵션 1로의 전환 경로 (필요해지면)**: DB 테이블 `엠군_상세페이지_검수` 동일 재사용. `run_stage_04_b()` 함수를 `run_stage_04` 직후 항상 호출하도록 `auto_pipeline.py`의 자동 모드(추천·멀티타겟) 코드에 추가 + UI 토글 제거.

### 🟢 04_detail_page 매핑 변경 실전 검증

- **상황**: 2026-05-23 통합 작업에서 `loader.py`의 `AGENT_KEYS["detail_page"]`를 `"04_detail_page"`(부재) → `"04_a_writing"`로 재매핑. 통합 전에는 깨진 상태였음 (사용자가 자동화 04 단계를 실전에서 안 썼을 가능성).
- **작업**: 통합 후 자동화 04 단계 실제 호출 테스트 → 결과 정상 여부 확인. (2단계 검증과 함께 자연스럽게 검증 진행 중)
- **위치**: `pipeline/loader.py:21-22`, `pipeline/lint.py:28-29`
- **관련 호출부**: `pipeline/auto_pipeline.py:run_stage_04`, `pages/2_pipeline.py` Step 3 (04 상세페이지)
- **04_b 통합은 별도 항목**: ↑ 위 "🟡 04_b 검수 자동화 통합" 참조


### 🟡 동시 접속자 식별 / 동시편집 알람 — Streamlit Cloud 한계로 보류 (2026-05-28)

> ⚠️ **반드시 시도 전에 본 섹션 정독**. 단순한 SSO 매핑처럼 보이지만 3중 한계가 있어 한 번에 같이 풀어야 한다. 이번 시도(2026-05-28)는 보류 결정 — 코드는 모두 revert, DB 테이블만 휴면 상태로 남김.

#### 원래 사용자 요청 (질문 두 가지)
1. **동시편집 알람 일반화**: 기존 `편집_세션` 동시편집 ⚠️ 배지가 `APP_ROLE` 기반 username("owner(나)"/"partner(동료)")만 사용하여, 같은 APP_ROLE의 동료끼리(예: partner 4명) 동시 편집 시 자기 자신으로 인식해 배지가 안 뜸. **이메일 단위로 식별**되어야 함.
2. **현재 접속자 사이드바 배지**: 사용자(owner)만 볼 수 있는 사이드바에 `👥 접속 중 N명` 배지. 누가 동시 접속 중인지 표시.

두 기능 모두 **사용자별 식별(username)이 정확해야** 동작한다.

#### 발견한 한계 ① — Streamlit Community Cloud의 SSO 비노출 (가장 큰 함정)

- **가설**: Restricted access의 Google SSO 이메일을 `st.experimental_user.email` / `st.user.email`로 받을 수 있을 것
- **실측**: 디버그 expander로 직접 확인 (스샷 보관: 클라우드 + 로컬 4건)
  ```
  st.user = <UserInfoProxy object at 0x...>      ← 객체는 있음
  .email (attr) = NO_ATTR                          ← attribute 없음
  ['email'] (dict) ERR: 'st.user has no key "email"'  ← dict access 실패
  to_dict() = {}                                   ← 완전 빈 dict
  ```
- **결론**: Streamlit Community Cloud의 **Restricted access는 단순 게이트일 뿐, 앱 코드에 사용자 이메일을 제공하지 않는다**. 별도 OIDC 통합을 명시적으로 설정해야만 `st.user.email`이 채워짐.
- 이 사실은 Streamlit 공식 문서에 명확히 안 적혀 있어 한 번 직접 시도해 본 후에야 알게 됨.

#### 발견한 한계 ② — Streamlit rerun 모델 (presence 기능의 본질적 장벽)

- presence(접속자 배지)는 heartbeat upsert(주기적 DB row 갱신)에 의존
- heartbeat는 **페이지 rerun 시 호출**됨
- Streamlit은 **사용자가 위젯을 건드릴 때만 rerun** — 페이지를 그냥 보고만 있으면 rerun 없음
- **결과**: 활동 중인 사용자(나)는 잡히고, 보고만 있는 partner는 TTL 만료로 사라짐 → 비대칭 → 신뢰성 낮음
- 해결책: `streamlit-autorefresh` 또는 `st.fragment`로 자동 rerun 도입 필요 (페이지 깜빡임/부하 trade-off)

#### 발견한 한계 ③ — session_state 휘발 (카운트 누적 버그)

- `_presence_session_id` UUID를 `st.session_state`에 저장하는 방식 시도
- 새로고침 시 session_state 휘발 → 매번 새 UUID 생성 → DB row 누적 → 카운트 부풀어짐 (8회 새로고침 = 8명 표시 확인)
- 해결책: URL `?sid=xxx`에 박거나 쿠키 사용 (URL 지저분 단점)

#### 본 시도 후 코드 상태 (2026-05-28 보류 결정)

| 파일 | 처리 |
|---|---|
| `app.py` | **revert** (`render_접속자_배지()` 호출/import 제거) |
| `pipeline/role.py` | **revert** (SSO 이메일 fallback 제거, 원래 APP_ROLE 기반으로) |
| `pipeline/supabase_read.py` | **revert** (`upsert/get_active/delete_접속_세션` 3개 함수 제거) |
| `pipeline/presence_ui.py` | **삭제** |
| `db/add_접속_세션.sql` | **유지(휴면)** — 미래 재시도 시 마이그레이션 스킵 또는 DROP & 재실행 |
| `db/run_add_접속_세션.py` | **유지(휴면)** |
| DB `접속_세션` 테이블 | **유지(휴면)** — 데이터 0 row, 무해. DROP 원하면 `DROP TABLE 접속_세션;` 한 줄. |
| DB `편집_세션` 테이블 | **운영 중** (영향 없음). 단 SSO 식별 없어 같은 APP_ROLE 동료끼리 동시편집 알람 작동 안 함 — 질문1 미해결 상태. |

#### 다음 시도 시 — 한 번에 처리해야 할 것 (셋 중 하나라도 빠지면 또 보류)

1. **SSO 사용자 식별** — 옵션 A·B·C 중 선택 (아래)
2. **자동 rerun** — `streamlit-autorefresh` 또는 `st.fragment` (아래)
3. **session_state 휘발 보완** — URL `?sid=` 또는 쿠키

#### 사용자 식별 옵션 (상세)

- **A. Streamlit OIDC 직접 통합 (정통, 작업 多)**
  - Google OAuth client 신규 발급 + redirect URI 등록 (`https://auto-sales-wktrade.streamlit.app/oauth2callback`)
  - Cloud secrets에 `[auth]` / `[auth.google]` 섹션 + `cookie_secret`
  - `requirements.txt`에 `streamlit>=1.42` pin
  - 코드에 `st.login("google")` / `st.logout` 통합, login page 분기
  - 동료가 접속 시 Google 로그인 1회 클릭
  - 결과: `st.user.email` 자동 채워짐
- **B. 쿼리스트링 `?as=voyager` (작업 少, 우선 추천)**
  - 동료에게 각각 다른 URL 알려줌:
    - `https://auto-sales-wktrade.streamlit.app/?as=aboutkyom`
    - `https://auto-sales-wktrade.streamlit.app/?as=voyager`
    - `https://auto-sales-wktrade.streamlit.app/?as=donnamoo`
    - `https://auto-sales-wktrade.streamlit.app/?as=(4번째)`
  - 코드: `st.query_params.get("as")`로 읽어 username. `pipeline/role.py:current_username()`에 끼움
  - 로컬은 `.env`에 `LOCAL_USER=aboutkyom` 추가 fallback
  - 동료는 북마크 1회 → 자동. 단점: URL 위조 가능(4인 내부 도구라 무방)
- **C. 사이드바 수동 입력** — "내 이름" 입력 + session_state 저장. 동료가 매 세션 1회 입력. 잊을 수 있음

#### 자동 rerun 옵션

- **A. `streamlit-autorefresh`** — `pip install streamlit-autorefresh`, requirements.txt에 추가, `st_autorefresh(interval=20_000)` 한 줄 호출. 페이지 전체 rerun. 입력 중 깜빡임 가능.
- **B. `st.fragment` + 부분 autorefresh** — 사이드바 영역만 rerun. 메인 영역 깜빡 X. streamlit 1.37+ 필요. 깔끔하지만 fragment 패턴 학습 필요.

#### session_state 휘발 보완 옵션

- **A. URL `?sid=`에 박기** — `st.query_params["sid"] = uuid` 1회 박고 이후 새로고침에서도 같은 UUID 재사용. multipage navigation에서 query string 보존 여부 확인 필요. URL 지저분.
- **B. 쿠키 lib** — `streamlit-cookies-controller` 등. 의존성 추가. 가장 정확.

#### 관련 git 커밋 (이번 시도 이력)

- `feat: 동시 접속자 사이드바 배지 + SSO 이메일 식별` 류의 커밋 (실패 시도 본체)
- `revert: presence 기능 보류 — SSO/rerun/세션 휘발 3중 한계 발견` 커밋 (이 정리)
- 재시도 시: revert 커밋 이전 코드를 참고하면 사이드바 배지·heartbeat·세션 카운트 패턴 회수 가능 (`git log --all -- pipeline/presence_ui.py`)

#### 관련 파일 (재시도 시 진입점)

- `pipeline/role.py` — `current_username()` 확장 포인트 (옵션 B의 `st.query_params` 분기 여기서)
- `pipeline/supabase_read.py` — 접속_세션 함수 패턴 (git log에서 회수)
- `pipeline/presence_ui.py` (삭제됨, git history) — 사이드바 배지 + heartbeat 패턴
- `db/add_접속_세션.sql` (휴면) — 테이블 스키마 `세션_id PK + 사용자명 + 마지막_활동시각`
- `pages/2_product_edit.py:136~161` — 동시편집 알람 부분 (`current_username()`만 식별되면 자동 동작)

---

## 완료 작업 (참고 이력)

### ✅ 04_b 검수 자동화 통합 — 옵션 3 (토글) 1차 구현

- **완료일**: 2026-05-24
- **결정**: 옵션 3 (사용자 명시적 토글 호출). 옵션 1 (자동 단계)로 전환 가능성 열어두고 DB 구조 별도 테이블로 깔끔하게 분리.
- **결과**:
  - `db/add_엠군_상세페이지_검수.sql` + `run_add_엠군_상세페이지_검수.py` (마이그레이션 실행 완료)
  - `agents/04_b_review/instruction.md` — 출력 블록 마커 명세 추가 (`---REVIEW_REPORT---`/`---REFINED_DRAFT---`)
  - `pipeline/storage.py` — `save_상세페이지_검수`/`get_상세페이지_검수`/`delete_상세페이지_검수` 메서드
  - `pipeline/loader.py` — `build_user_input_04_b()` (04_a 콘티를 검수 입력으로 받음)
  - `pipeline/auto_pipeline.py` — `_extract_review_blocks()` 마커 파서 + `run_stage_04_b()` 함수
  - `pages/2_pipeline.py` — Step 3-B 섹션 (04_a 결과 있을 때만 표시, 검수 보고서·다듬은 콘티 분리 expander)
  - `pages/2_pipeline.py` — **자동 모드(추천·멀티타겟)에도 04_b 체크박스 추가** (기본 OFF). 추천·멀티타겟 자동 실행 코드 두 진입점에서 04 호출 직후 `if _auto_stages.get("04_b")` 분기로 04_b 호출.
- **옵션 3 정책**: 호출 안 된 모델은 빈 행 저장 X (2단계 발견한 Gemini 빈 행 노이즈 회피). 04_a 결과 없는 모델은 FK 매핑 불가 → skip. 자동·수동 모두 사용자가 명시적으로 토글 켰을 때만 실행.
- **실전 검증 남음**: 첫 호출 시 마커 파싱 + DB 저장 두 가지 확인 → "활성 작업" 섹션의 `🟢 04_b 검수 자동화 통합 — 옵션 3 (토글) 1차 구현 완료` 항목 참조.

### ✅ agents 통합 [1단계] — 옵션 A (공통 두뇌 + 모드별 인터페이스 분리)

- **완료일**: 2026-05-23
- **결과**: `_공통 두뇌/` (사고 21파일) + `자동화형/agents/` (인터페이스 25파일) + `대화형/agents/` (인터페이스 24파일)
- **상세**: [docs/agents통합_서버배포_로드맵_2026-05-22.md](agents통합_서버배포_로드맵_2026-05-22.md) § 3 [1단계] + § 5-6

### ✅ 후속 정비 1·3·4·5번 (JSON·yaml 명세 + detail_page + CLAUDE.md)

- **완료일**: 2026-05-23
- **결과**: 자동화형 01·02·04_a instruction.md에 JSON·yaml 명세 / `detail_page` 재매핑 / `detail_review` 신설 / 양쪽 CLAUDE.md 구조 트리 갱신
- **상세**: 위 로드맵 § 5-7

### ✅ Step F — build_user_input_* placeholder fallback

- **완료일**: 2026-05-23
- **결과**: `loader.py:145-169` `_apply_with_fallback` 헬퍼. instruction.md에 placeholder 없어도 product/target/positioning 명시적 prepend.
- **부수**: 03 variant 분기에 `FileNotFoundError` fallback.

### ✅ Step E — VP OAuth 인증 디버깅

- **완료일**: 2026-05-23
- **결과**:
  - 동료에게 새 pickle 받아 임시 교체 (기존 pickle은 `credentials/_old_pickles_20260523/`에 백업)
  - `scripts/refresh_oauth_token.py` 발급 스크립트 + `OAUTH_SETUP.md` 안내 문서 작성
- **남은 후속**: 본인 계정 전환 (위 활성 작업 참조)

### ✅ vision_merge·VP 프롬프트 5개 파일 복구

- **완료일**: 2026-05-23 (BACKLOG 등록 직후 사용자가 즉시 부딪힘)
- **상황**: 사용자가 제품 #1462 작업 중 "시각설명 → 스펙 필드 자동 추출" 단계에서 `[Errno 2] No such file: extract_spec.md` 에러 발생. **🟢 LOW 우선순위로 잘못 평가했던 항목이 실은 운영 차단**.
- **진단**: 통합 직전 백업(`엠타트업식 판매_백업_20260522_통합전`)에 이미 누락 상태였지만, 그 이전 백업(`자동화형/_backups/agents_백업_20260522`)엔 5개 파일 모두 존재. 사용자가 폴더 정리 과정에서 누락된 것으로 추정.
- **복구**: `agents_백업_20260522/00_vision_pass/`에서 5개 파일을 `자동화형/agents/00_vision_pass/`로 복사:
  - `merge.md` (3034 bytes) — Vision Pass 비교용 프롬프트
  - `extract_spec.md` (2710 bytes) — 시각설명 → 스펙 추출 프롬프트
  - `core_claude.md` (3162 bytes) — Claude 엔진 전용 VP 프롬프트
  - `core_gemini.md` (4124 bytes) — Gemini 엔진 전용 VP 프롬프트
  - `core_gemini_video.md` (4335 bytes) — 동영상 VP 전용 프롬프트
- **검증**: `vision_merge.py._load_prompt('merge.md')`·`'extract_spec.md'` 정상 로드. `pages/2_product_edit.py`의 `_vp_resolve()`는 엔진별 분기 파일을 자동화형 agents에서 찾고, 공용 `core.md`는 `_공통 두뇌`에서 fallback.
- **위치 결정 (확정)**:
  - `_공통 두뇌/00_vision_pass/core.md` — 공통 사고 (양쪽 공유)
  - `자동화형/agents/00_vision_pass/core_{claude,gemini,gemini_video}.md` — 엔진별 분기 (자동화 전용)
  - `자동화형/agents/00_vision_pass/merge.md`, `extract_spec.md` — Vision Merge·Spec Extract 자동화 전용 프롬프트
- **학습**: 백업 시점에 따라 파일 누락 가능. "백업본에도 없음 → dead code 추정"은 위험. **여러 시점 백업 비교 + 코드의 실제 호출 패턴 확인** 후 우선순위 판정해야.

### 🟢 스펙 탭 저장 버튼 floating (sticky bottom / fixed) — 2026-05-27 시도 실패, 보류

- **상황**: [pages/2_product_edit.py](../pages/2_product_edit.py) 스펙 탭의 `💾 저장` / `취소` 버튼이 페이지 최하단(JSON expander 위)에만 있어, 위쪽 필드 편집 후 저장하려면 매번 스크롤 끝까지 내려야 함. 충돌 경고 배너도 저장 버튼 직후에 위치해 사용자가 즉시 인지 못 함.
- **목표**: 저장/취소 버튼이 viewport 하단에 floating으로 항상 보이게.
- **2026-05-27 시도 내역 (모두 실패)**:
  1. `position: sticky; bottom: 0;` + 마커 div(`.sticky-save-marker-tab2`) + `:has()` next-sibling selector — 효과 없음 (DOM 변화 무, 버튼 그대로 페이지 끝)
  2. `position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);` + backdrop-filter blur + viewport 중앙 정렬 — 효과 없음 (동일)
- **추정 원인** (확인 안 됨):
  - Streamlit이 `<style>` 태그를 inline 적용 안 하고 head 등으로 이동시킬 가능성
  - selector(`div[data-testid="stElementContainer"]:has(.sticky-save-marker-tab2) + div[data-testid="stElementContainer"]`) 가 Streamlit 1.44 실제 DOM과 불일치
  - `:has()` 셀렉터 자체는 브라우저 지원되지만 Streamlit 내부 컨테이너 중첩 구조가 예상과 다를 수 있음
- **다음 시도 방향** (CSS 일괄 작업 시):
  1. **CSS 주입 자체 검증**: `<style>body{background:red !important}</style>` 같은 자명한 CSS 주입해서 적용되는지부터 확인 (안 되면 주입 방식 문제, 되면 selector 문제)
  2. **브라우저 개발자 도구로 실제 DOM 트리 확인**: 저장 버튼 영역의 부모 체인을 정확히 보고 selector 작성
  3. **외부 패키지 검토**: `streamlit-extras` 의 `bottom_container` 등 fixed positioning 지원 컴포넌트
  4. **st.empty + container 트릭**: page 상단에 placeholder 만들고 늦게 그리는 방식, 또는 `st.sidebar` 활용 검토
- **사용자 결정 (2026-05-27)**: CSS는 우선순위 낮음. 다른 UI/CSS 작업과 함께 일괄 처리. 코드의 CSS 주입 / 마커 div / spacer div 잔재는 정리 (코드 깨끗하게 유지).

---

## 추가 작업 발견 시

새 추후 할일 등록 양식:
```markdown
### {🔴/🟡/🟢} {작업 제목}

- **상황**: ...
- **목표**: ...
- **작업**: ...
- **소요**: ...
- **차단 요소**: ...
- **가이드** (있다면): [경로](경로)
```
