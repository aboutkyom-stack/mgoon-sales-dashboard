# 엠타트업식 판매/자동화형 프로젝트 — Claude 작업 안내

## 프로젝트 개요
엠군 강의 기반 온라인 쇼핑몰 엠타트업식 판매/자동화형 시스템.
부분엠군 페르소나(01 결핍·타겟 → 02 포지셔닝 → 03 네이밍 → 04 상세페이지 → 05 채널)로 판매 전략을 자동 생성한다.

## agents 통합 구조 (2026-05-23 적용) ⭐

사고(`core`·`examples`·`expressions`·`_shared/상세페이지_풀세트`·`강의원본_매핑`·`field_log_meta`)는 상위 `../_공통 두뇌/`로 분리되어 대화형과 공유된다.
`자동화형/agents/`에는 자동화 전용 인터페이스만 남는다 (각 단계의 `instruction.md`·`qa_checklist.md`·`field_log.md` + `_shared/data_contract.md`·`db_schema_mapping.md`·`rule_engine.md`).

- `pipeline/loader.py`는 두 폴더를 합쳐 시스템 프롬프트를 만든다 (`load_agent_prompt`).
- 사고 파일 수정 시 양쪽(자동화·대화형)에 동시 반영됨. **수정 전 반드시 영향 검토.**
- 자동화 인터페이스 수정은 `자동화형/agents/`에서, 대화형 인터페이스 수정은 `../대화형/agents/`에서 독립적으로 가능.

## 작업 시작 전 반드시 확인할 문서

1. **`PROJECT_STATUS.md`** ⭐ — 채팅방 인계용 누적 현황. 모든 결정사항이 기록됨. **작업 시작 시 가장 먼저 읽기**.
2. **`PLAN.md`** — 마스터 플랜 (시스템 목적, 페르소나 구조, 운영 모드 등 큰 그림).
3. **`docs/decisions/`** — 시점별 기획 결정 로그. 최신 파일 확인 시 최근 결정 사유 파악 가능.

## git 운영
- **로컬 git만 사용** (GitHub 미사용). 미래 `aboutkyom-stack/auto-selling`으로 push 예정.
- 상위 "자동화 공장" 폴더에는 별도 git 있음 (tistory 작업용) — 이 폴더 git과 완전히 독립 (nested 구조).
- 부수 자료(`강의 원본/`, `테스트용 제품 정보/`) 및 민감 파일(`.env`, `credentials/`, `*.pickle`, `계정정보(API키-DB정보 등).txt`)은 `.gitignore`에 등록됨.

## 핵심 폴더 구조 (2026-05-23 통합 후)

```
엠타트업식 판매/
├── _공통 두뇌/                       ← 사고 파일 (대화형과 공유) ⭐
│   ├── 00_vision_pass/              ← VP core.md (엔진별 분기 core_* 있으면 우선)
│   ├── 01_deficit_target/           ← core.md + examples.md
│   ├── 02_positioning/              ← core.md + examples.md
│   ├── 03_naming/                   ← core.md + examples.md + expressions.md
│   ├── 04_a_writing/                ← core.md + examples.md + expressions.md
│   ├── 04_b_review/                 ← core.md + expressions.md
│   ├── 04_1_image_direction/        ← core.md + SKILL_gpt_image.md
│   ├── 05_channel/                  ← core.md + examples.md + expressions.md
│   └── _shared/                     ← 상세페이지_풀세트·강의원본_매핑·field_log_meta
│
└── 자동화형/
    ├── PLAN.md, PROJECT_STATUS.md   ← 작업 전 필독
    ├── agents/                      ← 자동화 전용 인터페이스만 ⭐
    │   ├── 0N_*/                    ← instruction.md + qa_checklist.md + field_log.md
    │   │                              (각 단계의 자동화 모드 절차·검수·이전 가설)
    │   └── _shared/                 ← data_contract·db_schema_mapping·rule_engine
    │                                  (자동화 전용: 권위 규약·DB 매핑·Rule Engine)
    ├── pages/                       ← Streamlit UI
    ├── pipeline/                    ← LLM 호출, DB, 파일, 드라이브 등
    │                                  loader.py가 _공통 두뇌 + agents 합성 로드
    ├── db/                          ← DB 마이그레이션 스크립트
    └── docs/
        ├── decisions/               ← 시점별 기획 결정 로그
        └── colleague_README.md      ← 동료 공유용 README
```

## 사용자 본질 의도 (Always Remember)

> "볼 수 있는 건 모두 보고 최대한 상세히 기록 — 어떤 질문/작업이 와도 대응 가능하게"

비전패스 같은 정보 추출 작업에서 **카테고리에 갇혀 시야가 좁아지는 현상은 사용자 의도의 정반대**임을 기억할 것.

## 🚫 절대 규칙 — _공통 두뇌/ 사고 파일 + agents 인터페이스 보호

**다음 파일은 사용자와의 사전 상의·승인 없이 절대 수정·삭제하지 않는다.**

### 1순위 — `_공통 두뇌/` 사고 파일 (대화형과 공유) ⭐
- `_공통 두뇌/0N_*/core.md`, `core_claude.md`, `core_gemini.md`, `core_gemini_video.md` 등 모든 `core*.md`
- `_공통 두뇌/0N_*/examples.md`, `expressions.md`
- `_공통 두뇌/_shared/상세페이지_풀세트.md`, `강의원본_매핑.md`, `field_log_meta.md`

이유: 강의 원본에서 추출한 페르소나의 사고 프레임워크. 강의 본질이 담긴 자료라 임의 변경 시 페르소나 자체가 망가진다. **자동화·대화형 양쪽에 동시 반영**되므로 한쪽만 보고 수정하면 다른 쪽이 깨질 수 있음.

### 2순위 — `agents/` 자동화 전용 인터페이스
- `agents/0N_*/qa_checklist.md` (자동화 모드 자가 검수 규칙)
- `agents/0N_*/instruction.md` (자동화 모드 작업 절차 + JSON·yaml 출력 명세)
- `agents/0N_*/field_log.md` (이전 세션 가설)
- `agents/_shared/data_contract.md`, `db_schema_mapping.md`, `rule_engine.md`

이유: 자동화 모드의 운영 규약·DB 매핑·Rule Engine. 변경 시 자동화 LLM 출력이 깨질 수 있음. **대화형에는 영향 없음** (대화형은 `../대화형/agents/`에 별도 인터페이스 보유).

### 공통 원칙
- 호출별 작업 범위 조정·강조점 변경은 **`pipeline/loader.py`의 `build_user_input_*`** 또는 UI 측에서만 처리한다 (system prompt는 풀 지식, user input이 호출별 지시).
- 예외: 새 사고 파일 신규 생성(예: 새 단계 추가, 엔진별 분기 신규)은 사용자 요청·승인 하에 가능.

## 자주 헷갈리는 포인트

- **상위 "자동화 공장" 폴더의 git**: tistory(자동화 블로그) 작업용. 이 프로젝트와 무관.
- **이미지 VP vs 동영상 VP**: 프롬프트가 분리되어 있음 (2026-04-29 결정). `vp_editor_gemini`(이미지)와 `vp_editor_gemini_video`(동영상) 세션 키도 분리.
- **결정 로그는 `docs/decisions/`에 날짜별로 누적**: 마지막 작업 사유는 최신 파일에 기록됨.
