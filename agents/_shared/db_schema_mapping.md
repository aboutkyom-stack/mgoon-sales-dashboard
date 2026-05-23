# DB 스키마 매핑 — 통합본 agents → Supabase 테이블

> **용도**: 통합본(대화형2 진화) agents의 새 출력 필드들을 기존 Supabase 테이블에 어떻게 저장할지 정리.
>
> **대상 DB**: Supabase (PostgreSQL).
>
> **마이그레이션 파일 위치**: `엠타트업식 판매/자동화형/db/` 폴더 (멱등 SQL + Python 실행기).
>
> **운영 원칙**: 모든 마이그레이션은 **멱등**(`ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS`)으로 작성. 재실행 안전.

---

## 1. 기존 DB 구조 (엠타트업식 판매/자동화형)

```
엠군_실행 (한 제품 × 1회 파이프라인 실행)
  ↓ FK
엠군_타겟 (01 결과, 모델별 후보 N개)
  ↓ FK (선택된 타겟만 02로 진행)
├── 엠군_포지셔닝 (02)
├── 엠군_네이밍 (03)
├── 엠군_상세페이지 (04_a)
├── 엠군_이미지디렉션 (04_1)
└── 엠군_채널 (05)
```

**기존 패턴**: 02·03·05는 `(타겟_id, 모델, 원본_출력, 생성일)` 단순 구조. 04_1만 `섹션들·디자인시스템` JSONB 보유. 01은 구조화 컬럼 다수.

---

## 2. 통합본 신규 필드 vs 기존 컬럼

### 2-1. 00 vision_pass

**신규 필드**: 없음 (대화형2 = 통합본. extract_spec `_특징_bullet`도 이미 흡수돼 있어 변경 없음).

**기존 처리**: `상품_파일.비전패스_이력` 컬럼 활용 (이미 운영 중).

**DB 변경**: ❌ 없음.

---

### 2-2. 01 deficit_target

**신규 필드**: 없음 (구조 그대로). 단 대화형 통합본은 JSON 블록 출력 X → 자동화_업그레이드는 자동화 형식 유지하므로 기존 TARGETS_JSON 그대로 사용.

**기존 처리**: `엠군_타겟` 테이블에 구조화 컬럼(라벨·캐릭터·결핍·구매편익·관여도·욕구깡패 등) 다수.

**DB 변경**: ❌ 없음.

---

### 2-3. 02 positioning ⭐ (가장 큰 변경)

**신규 필드 (대화형2 진화로 추가됨)**:

| 필드 | 의미 | 직접 사용처 |
|------|-----|---------|
| `category_objections` | 카테고리 의심 반론 (objection / counter / source) | 04_a 핵심 반론 선제 처리 블록 (3.5단계) 직접 입력 |
| `rule_engine_inputs` | 6변수 (구매편익·관여도·경쟁강도·타겟지능·결핍유형·R복잡도) | 04_a ENGINE_PLAN 생성 입력 |
| `rule_engine_flags` | 4플래그 (재구매·호환불안·차별점명확·CV이동필요) | 04_a ENGINE_PLAN 생성 입력 |
| `persuasion_method_candidates` | 설득 방식 후보 (method / reason) | 04_a 설득 방식 선택 근거 |

**기존 `엠군_포지셔닝` 테이블**:
```sql
(id, 타겟_id, 모델, 원본_출력, 생성일)
```

**추가할 컬럼 (DDL)**:
```sql
ALTER TABLE 엠군_포지셔닝
  ADD COLUMN IF NOT EXISTS category_objections JSONB,
  ADD COLUMN IF NOT EXISTS rule_engine_inputs JSONB,
  ADD COLUMN IF NOT EXISTS rule_engine_flags JSONB,
  ADD COLUMN IF NOT EXISTS persuasion_method_candidates JSONB;
```

**예시 데이터 (독수리 모형새 02 결과)**:

```sql
INSERT INTO 엠군_포지셔닝 (
  타겟_id, 모델, 원본_출력,
  category_objections, rule_engine_inputs, rule_engine_flags, persuasion_method_candidates
) VALUES (
  123, 'claude',
  '[02 마크다운 본문 전체]',
  -- category_objections (JSONB)
  '[
    {
      "objection": "비둘기는 학습력 빠른데 익숙해지면 효과 없는 거 아닌가?",
      "counter": "자리 주기적으로 바꿔주면 새 위협으로 재인식. 우리 제품은 줄에 걸어두는 방식이라 5분이면 옮길 수 있음",
      "source": "AI 카테고리 추론"
    }
  ]'::jsonb,
  -- rule_engine_inputs (JSONB)
  '{
    "구매편익": "기능재",
    "관여도": 5,
    "경쟁강도": "중간",
    "타겟지능": "감정형",
    "결핍유형": "자유",
    "R복잡도": "단순"
  }'::jsonb,
  -- rule_engine_flags (JSONB)
  '{
    "재구매_제품": false,
    "호환성_불안_있음": true,
    "차별점_명확": true,
    "구매핵심가치_이동_필요": false,
    "구매핵심가치_이동_근거": ""
  }'::jsonb,
  -- persuasion_method_candidates (JSONB)
  '[
    {"method": "소거법", "reason": "기존 비둘기 퇴치 대안(망·전기)이 시각적·법적 단점 명확"},
    {"method": "포지셔닝", "reason": "5분 이동성 + 활공 위장으로 까고 넣기 가능"}
  ]'::jsonb
);
```

---

### 2-4. 03 naming

**신규 필드**: 없음 (KIPRIS 의무화·분류 호출 등 절차적 진화. 출력 구조는 유지).

**기존 처리**: `엠군_네이밍` 테이블 `원본_출력` 단일 컬럼으로 충분.

**DB 변경**: ❌ 없음.

---

### 2-5. 04_a writing ⭐ (두 번째 큰 변경)

**신규 필드**: ENGINE_PLAN (Rule Engine 사전 적용 결과).

ENGINE_PLAN 구조:
```yaml
타겟_라벨: "..."
설득_방식_주: "구매편익|소거법|이지선다|포지셔닝|스토리텔링"
설득_방식_보조: ["..."]
보정_요약: ["..."]
블록_시퀀스: [{순번, 블록명, 장수, 보정메모}, ...]
꺼진_블록_사유: [{블록명, 사유}, ...]
추가_권고: ["..."]
참고_장수_합계: N
```

**기존 `엠군_상세페이지` 테이블**:
```sql
(id, 타겟_id, 모델, 원본_출력, 생성일)
```

**추가할 컬럼 (DDL)**:
```sql
ALTER TABLE 엠군_상세페이지
  ADD COLUMN IF NOT EXISTS engine_plan JSONB,
  ADD COLUMN IF NOT EXISTS 한_축_사슬 TEXT,
  ADD COLUMN IF NOT EXISTS 설득_방식_주 TEXT,
  ADD COLUMN IF NOT EXISTS 설득_방식_보조 JSONB;
```

**예시 데이터 (독수리 모형새 04_a 결과)**:

```sql
INSERT INTO 엠군_상세페이지 (
  타겟_id, 모델, 원본_출력,
  engine_plan, 한_축_사슬, 설득_방식_주, 설득_방식_보조
) VALUES (
  123, 'claude',
  '[04_a 콘티 마크다운 본문 전체]',
  -- engine_plan (JSONB)
  '{
    "타겟_라벨": "전원생활 비둘기 피해 가구",
    "설득_방식_주": "소거법",
    "설득_방식_보조": ["포지셔닝"],
    "보정_요약": [
      "결핍=자유 → 가치더하기에 시간 절약 각도",
      "타겟지능=감정형 → 헤드카피 감정·관계 어휘 우선"
    ],
    "블록_시퀀스": [
      {"순번": 1, "블록명": "헤드카피", "장수": 1, "보정메모": "관여도 5"},
      {"순번": 2, "블록명": "결핍심화", "장수": 1, "보정메모": ""},
      {"순번": 3, "블록명": "배제설득", "장수": 1, "보정메모": ""},
      {"순번": 4, "블록명": "핵심반론선제처리", "장수": 1, "보정메모": "category_objections 활용"},
      {"순번": 5, "블록명": "소거법", "장수": 1, "보정메모": "중간 경쟁"},
      {"순번": 6, "블록명": "CV선언", "장수": 1, "보정메모": ""},
      {"순번": 7, "블록명": "사용상황·호환", "장수": 2, "보정메모": "호환성_불안=true"},
      {"순번": 8, "블록명": "CTA", "장수": 1, "보정메모": ""}
    ],
    "꺼진_블록_사유": [
      {"블록명": "구매 후 매몰비용", "사유": "재구매_제품=false"},
      {"블록명": "스토리텔링", "사유": "기능재 + 감정형이지만 사슬 깊이 부족"}
    ],
    "추가_권고": [
      "약점 인정 카피에 권위 필드 null 항목(KC無 등) 박지 말 것 (Authority-02)"
    ],
    "참고_장수_합계": 9
  }'::jsonb,
  '활공 위장 한 축 — 표면(비둘기 똥) → 이면(반복 청소·악취) → 본질(전원생활 평온 깨짐)',
  '소거법',
  '["포지셔닝"]'::jsonb
);
```

---

### 2-6. 04_b review

**신규 필드**: 없음. 04_b는 검수 보고서 + 다듬은 콘티 출력이라 별도 DB 테이블 없음 (04_a 콘티에 update 또는 별도 검수 로그).

**현 상태**: 04_b는 운영 중 별도 저장 X. 04_a `원본_출력` 업데이트만.

**DB 변경**: ❌ 없음 (필요 시 별도 `엠군_상세페이지_검수` 테이블 신설 가능. 현재는 보류).

---

### 2-7. 04_1 image_direction

**신규 필드**: 없음 (대화형2 = 통합본).

**기존 처리**: `엠군_이미지디렉션` 테이블에 이미 `섹션들`·`디자인시스템` JSONB.

**DB 변경**: ❌ 없음.

---

### 2-8. 05 channel

**신규 필드**: 없음. 단 통합본에서 절차 6가지(파워컨텐츠·카페 내부 물길·지식인 IP 등)가 흡수돼 사고 깊이 ↑. 출력 구조는 자연어 표·항목화 유지.

**기존 처리**: `엠군_채널` 테이블 `원본_출력` 단일 컬럼.

**DB 변경**: ❌ 없음 (추후 필요 시 `허브_키워드`·`접촉지점_우선순위` JSONB 추가 검토).

---

## 3. 마이그레이션 요약

### 3-1. 변경 대상 테이블 (2개)

| 테이블 | 추가 컬럼 |
|--------|----------|
| `엠군_포지셔닝` | `category_objections`, `rule_engine_inputs`, `rule_engine_flags`, `persuasion_method_candidates` (모두 JSONB) |
| `엠군_상세페이지` | `engine_plan` (JSONB), `한_축_사슬` (TEXT), `설득_방식_주` (TEXT), `설득_방식_보조` (JSONB) |

### 3-2. 마이그레이션 파일

```
엠타트업식 판매/자동화형/db/
├── add_엠군_02_업그레이드.sql        ← 02 ALTER TABLE
├── add_엠군_04a_업그레이드.sql       ← 04_a ALTER TABLE
└── run_add_엠군_업그레이드.py       ← 실행기 (멱등·안전, 자동 검증)
```

### 3-3. 실행 방법

```bash
cd "엠타트업식 판매/자동화형/db/"
python run_add_엠군_업그레이드.py
```

→ 멱등 (`ADD COLUMN IF NOT EXISTS`)이므로 재실행 안전. 출력에 변경된 테이블의 컬럼 구조 확인 표시.

→ `feedback_db_migration_auto.md` 원칙대로 Claude가 직접 실행.

---

## 4. pipeline 코드 영향 (참고)

`엠타트업식 판매/자동화형/pipeline/` 코드가 02·04_a 결과를 어떻게 저장하는지에 따라 추가 작업 필요:

| 영향 | 처리 |
|------|------|
| pipeline이 `원본_출력`만 저장 | ✅ 자동 호환. 새 컬럼은 NULL로 비어있음. UI·후속 단계 영향 없음 |
| pipeline이 구조화 필드 추출해서 컬럼별 저장 | ⚠️ pipeline 코드 수정 필요. ENGINE_PLAN·category_objections 등을 파싱해서 새 컬럼에 저장 |

→ Phase B-4 Streamlit 영향 점검에서 확인.

---

## 5. 운영 시 활용 예시

새 컬럼들이 채워지면 다음 활용 가능:

```sql
-- 1. 카테고리 의심이 "익숙해지면 효과 없음" 류인 제품 찾기
SELECT * FROM 엠군_포지셔닝
WHERE category_objections::text LIKE '%익숙해지면%';

-- 2. 결핍=안정 + 관여도 7+ 제품의 콘티 ENGINE_PLAN 추출
SELECT 타겟_id, engine_plan->'블록_시퀀스' AS 시퀀스
FROM 엠군_상세페이지 a
JOIN 엠군_포지셔닝 p ON a.타겟_id = p.타겟_id
WHERE p.rule_engine_inputs->>'결핍유형' = '안정'
  AND (p.rule_engine_inputs->>'관여도')::int >= 7;

-- 3. 핵심 반론 선제 처리 블록이 ON된 콘티만 보기
SELECT * FROM 엠군_상세페이지
WHERE engine_plan->'블록_시퀀스' @> '[{"블록명": "핵심반론선제처리"}]'::jsonb;
```

---

## 6. 변경 이력

| 날짜 | 변경 |
|------|------|
| 2026-05-22 | 초안 작성. 통합본 02·04_a 신규 필드 매핑 정의. SQL DDL + Python 마이그레이션 스크립트 동봉. |
