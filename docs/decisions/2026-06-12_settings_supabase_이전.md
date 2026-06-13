# 2026-06-12 — 전역 설정(settings.json) Supabase 이전

## 배경 / 문제
- 전역 앱 설정이 `settings.json` **로컬 파일**에만 저장됨.
- 운영 구조: **owner(나)는 로컬**에서, **partner(동료)는 Streamlit Cloud**에서 작업.
- 제품 데이터(DB)는 양쪽이 실시간 공유되지만, **설정은 동기화되지 않음**:
  - 로컬에서 UI로 설정 변경 → git commit·push 전까지 Cloud 미반영.
  - Cloud에서 설정 변경 → 서버 메모리에만 반영, 재배포 시 초기화.
- 동료도 **판매자특성** 정도는 직접 수정함 → 동기화 필수.

## 결정
1. `settings.json` 전체를 Supabase **`app_settings`** 테이블로 이전.
   - **단일 행(id=1)에 전체 설정을 JSONB로** 보관 (항목별 행 분리 안 함).
   - **DB가 진실의 원천**. 로컬 `settings.json`은 오프라인/DB 장애 시 폴백 캐시로 강등.
2. **충돌 처리: last-write-wins** — 저장 시점의 전체 설정으로 DB 단일 행을 통째 교체.
   - 둘이 동시에 같은 설정을 만지는 일은 드물어 실무상 충분.
   - 이미 운영 중인 `drive_auth`(OAuth 토큰 pickle↔DB 이중화)와 동일 철학.
3. **읽기 캐시 3초 TTL** — Streamlit은 인터랙션마다 스크립트를 전체 재실행하므로
   `load()`가 한 렌더에 여러 번 호출됨. 메모리 캐시로 중복 DB 조회 방지.
   동료 변경은 최대 3초 후 반영(허용 범위).

## 범위에서 제외 (의도적으로 로컬 유지)
- **`settings_columns.json`** (제품목록 화면 컬럼 순서·박스 역순):
  "개인 화면 취향"에 가까움. 동기화하면 owner/partner가 서로 화면을 덮어씀 → **각자 로컬 유지**.
- **프롬프트 파일** (`core_*.md`, `instruction.md`): git으로 관리 + CLAUDE.md 보호 대상.
  같은 동기화 문제가 있으나 성격이 달라 **별도 논의**로 미룸.

## 변경 파일
| 파일 | 변경 |
|------|------|
| `db/add_app_settings.sql` | (신규) `app_settings` 테이블 정의 |
| `db/run_add_app_settings.py` | (신규) 테이블 생성 + 현재 settings.json 시드(ON CONFLICT DO NOTHING) |
| `pipeline/supabase_read.py` | `get_app_settings()` / `upsert_app_settings()` 추가 (drive_auth 패턴 복제) |
| `pipeline/settings.py` | `load()`/`save()` 내부를 DB 연동으로 교체 + 메모리 캐시. **시그니처 불변 → 호출부 무수정** |
| `pages/0_settings.py` | 캡션 갱신 + 저장 시 DB 실패 경고 |
| `pages/2_product_edit.py` | VP 엔진 영속화 콜백을 try/except로 감싸 DB 실패 시 toast |
| `.gitignore` | `settings.json` 추가 (DB가 진실이므로 로컬 파일은 추적 해제) |

## 마이그레이션 절차
1. `python db/run_add_app_settings.py` 실행 — 테이블 생성 + 현재 설정 시드.
2. `settings.json`을 git 추적에서 제거: `git rm --cached "엠타트업식 판매/자동화형/settings.json"`.
3. 이후 설정 변경은 0_settings.py 또는 상품편집 페이지에서 → 자동으로 DB 동기화.

## 동작 흐름 (요약)
- **load()**: `app_settings`(DB) → 실패 시 로컬 `settings.json` → DEFAULTS. 3초 캐시.
- **save()**: 로컬 미러 + 캐시 먼저 확정 → DB upsert(실패 시 예외 전파 → UI 경고).
