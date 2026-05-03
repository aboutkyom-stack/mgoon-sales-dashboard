# 자동화 판매 프로젝트 — Claude 작업 안내

## 프로젝트 개요
엠군 강의 기반 온라인 쇼핑몰 자동화 판매 시스템.
부분엠군 페르소나(01 결핍·타겟 → 02 포지셔닝 → 03 네이밍 → 04 상세페이지 → 05 채널)로 판매 전략을 자동 생성한다.

## 작업 시작 전 반드시 확인할 문서

1. **`PROJECT_STATUS.md`** ⭐ — 채팅방 인계용 누적 현황. 모든 결정사항이 기록됨. **작업 시작 시 가장 먼저 읽기**.
2. **`PLAN.md`** — 마스터 플랜 (시스템 목적, 페르소나 구조, 운영 모드 등 큰 그림).
3. **`docs/decisions/`** — 시점별 기획 결정 로그. 최신 파일 확인 시 최근 결정 사유 파악 가능.

## git 운영
- **로컬 git만 사용** (GitHub 미사용). 미래 `aboutkyom-stack/auto-selling`으로 push 예정.
- 상위 "자동화 공장" 폴더에는 별도 git 있음 (tistory 작업용) — 이 폴더 git과 완전히 독립 (nested 구조).
- 부수 자료(`강의 원본/`, `테스트용 제품 정보/`) 및 민감 파일(`.env`, `credentials/`, `*.pickle`, `계정정보(API키-DB정보 등).txt`)은 `.gitignore`에 등록됨.

## 핵심 폴더 구조

```
자동화 판매/
├── PLAN.md, PROJECT_STATUS.md      ← 작업 전 필독
├── agents/                          ← 페르소나 프롬프트
│   ├── 00_vision_pass/             ← 비전패스 (이미지/동영상)
│   │   ├── core_claude.md          ← 이미지 VP — Claude 전용
│   │   ├── core_gemini.md          ← 이미지 VP — Gemini 전용
│   │   └── core_gemini_video.md    ← 동영상 VP 전용 (제품시연 특화)
│   ├── 01_deficit_target/          ← 결핍·타겟 (G1~G3)
│   ├── 02_positioning/             ← 포지셔닝 (G5~G6)
│   ├── 03_naming/                  ← 네이밍 (옵셔널)
│   ├── 04_detail_page/             ← 상세페이지
│   └── 05_channel/                 ← 채널 전략
├── pages/                          ← Streamlit UI
├── pipeline/                       ← LLM 호출, DB, 파일, 드라이브 등
├── db/                             ← DB 마이그레이션 스크립트
└── docs/
    ├── decisions/                  ← 시점별 기획 결정 로그
    └── colleague_README.md         ← 동료 공유용 README
```

## 사용자 본질 의도 (Always Remember)

> "볼 수 있는 건 모두 보고 최대한 상세히 기록 — 어떤 질문/작업이 와도 대응 가능하게"

비전패스 같은 정보 추출 작업에서 **카테고리에 갇혀 시야가 좁아지는 현상은 사용자 의도의 정반대**임을 기억할 것.

## 🚫 절대 규칙 — agents/*/core*.md 보호

**`agents/0N_*/core.md`, `core_claude.md`, `core_gemini.md`, `core_gemini_video.md` 등 모든 `core*.md` 파일은 사용자와의 사전 상의·승인 없이 절대 수정·삭제하지 않는다.**

- 이유: core.md는 강의 원본에서 추출한 페르소나의 사고 프레임워크. 강의 본질이 담긴 자료라 임의 변경 시 페르소나 자체가 망가진다.
- 호출별 작업 범위 조정·강조점 변경은 **`pipeline/loader.py`의 `build_user_input_*`** 또는 UI 측에서만 처리한다 (system prompt는 풀 지식, user input이 호출별 지시).
- `examples.md`, `expressions.md`, `qa_checklist.md` 등 보조 파일도 동일 규칙 적용 — 사전 승인 없이 수정 금지.
- 예외: 새 core 파일을 처음 만드는 경우(예: `core_gemini_video.md` 신규 생성)는 사용자 요청·승인 하에 신규 작성 가능.

## 자주 헷갈리는 포인트

- **상위 "자동화 공장" 폴더의 git**: tistory(자동화 블로그) 작업용. 이 프로젝트와 무관.
- **이미지 VP vs 동영상 VP**: 프롬프트가 분리되어 있음 (2026-04-29 결정). `vp_editor_gemini`(이미지)와 `vp_editor_gemini_video`(동영상) 세션 키도 분리.
- **결정 로그는 `docs/decisions/`에 날짜별로 누적**: 마지막 작업 사유는 최신 파일에 기록됨.
