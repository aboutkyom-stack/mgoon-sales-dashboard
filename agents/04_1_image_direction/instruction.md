# 04_1 이미지 디렉션 — 작업 지침

> `core.md` JSON 스키마 + `SKILL_gpt_image.md` GPT Image 특화 + 이 파일의 트리거 규칙 결합.

---

## 이 단계의 본질

> "콘티는 사람이 짜고, 디렉션은 기계가 읽는다. 모호하면 기계가 멋대로 그린다." (실전 본의)

04_b가 다듬은 콘티의 각 섹션을 **GPT Image 2.0이 바로 실행 가능한 JSON**으로 변환. 카피 보강·시각 보강이 아니라 **실행 시방서 작성**.

---

## 작업 절차

### 1) 선행 의무 (반드시)

- `agents/04_1_image_direction/SKILL_gpt_image.md` — GPT Image 2.0 특화 (한국어 정확도·부정 명령·인물)
- `agents/_shared/data_contract.md` — 권위 필드 규약
- `agents/_shared/상세페이지_풀세트.md` 4-5 (시각·디자인 카드) 재확인
- `items/item_<id>/04_b_review.md` — 검수 결과 + 다듬은 콘티 (변환 대상)

### 2) 핵심 강의 (04에서 정독 안 했으면 정독)

| 강의 | 활용 |
|------|------|
| `5주차 05 설득되는 디자인 초딩도 만든다` | 디자인 원칙(색·폰트·여백·강조). **04-1 특화 핵심** |
| `4주차1 01 상페 콘티는 이렇게 짜면 됩니다` | 콘티 → 디렉션 연결. "조사 하나까지 확정" 원칙 |

### 3) 입력 자료 로드

- `items/item_<id>/04_b_review.md` — 다듬은 콘티 (변환 대상)
- `items/item_<id>/00_vision_pass.md` — 외형·색감 참고
- `items/item_<id>/01_deficit_target.md` — 타겟 캐릭터화 (인물 등장 시 외형)
- 상품 테이블 권위 필드 (가격·인증·연령 — JSON text_elements에 그대로)

### 4) JSON 디렉션 생성

`core.md` JSON 스키마 그대로. 각 섹션 = 1개 객체.

### 5) 자가 검수 + 다음 단계 안내

```
"04_1 이미지 디렉션 완료. JSON 검토 후 진행할 부분 있으면 말씀,
없으면 '진행' 또는 '엠군: 채널 / [상품id]'로 호출하세요."
```

---

## ⭐ 트리거 규칙

### R-01. 인물 등장 디렉션 시 (필수)
text_elements 또는 main_subject에 인물 포함:
→ `SKILL_gpt_image.md` "인물 묘사" 절차 따름
→ 한국인 외형 + 타겟 캐릭터화 일관성 (01의 직업·나이·성격 반영)
→ 표정·감정·의상·배경 모두 구체 명시

### R-02. 한국어 텍스트 다량 디렉션 시
text_elements 텍스트가 한 화면에 3개 이상:
→ `SKILL_gpt_image.md` "한국어 정확도" 절차
→ 텍스트별 position·style 명시
→ 띄어쓰기·줄바꿈 정확히

### R-03. 비교 컷 디렉션 시
경쟁 대안 vs 우리 비교 이미지:
→ 음영 처리 명시 ("경쟁: 어두운 톤, 채도 30% / 우리: 밝은 톤, 강조색")
→ 한 화면 3색 이하 유지

### R-04. 인증·KC 마크 등 신뢰 카드 디렉션 시
→ `data_contract.md` D-02 확인. 권위 필드에 있는 인증만 디렉션화
→ 인증서 이미지는 "실물 인증서 클로즈업, 공식 마크 가독" 명시

### R-05. GIF·영상 디렉션 시
정적 이미지가 아닌 동적 디렉션:
→ 길이 명시 (GIF 15~30초, 영상 30초~1분)
→ 시작/중간/끝 키프레임 묘사
→ AI 생성 어려우면 production_method "직접 촬영" 권고

### R-06. 부정 명령 회피
"하지 마라" 표현 발견 시:
→ 긍정 명령으로 치환 (SKILL_gpt_image.md "부정 명령 회피" 참조)
→ negative_avoided 필드에 변환 전 의도 메모

### R-07. 권위 필드 부족 발견 시
04_b가 BUILD로 분류했거나, 04_1에서 새로 발견한 권위 필드 부족:
→ [시스템 개선 건의] 섹션에 추가
→ 04_b BUILD와 통합 (중복 X)

### R-08. 디자인 원칙 위반 검출
- 4색 이상 사용 시 → 3색 이하로 축소
- 강조 폰트가 본문 폰트와 같으면 → 다른 폰트 권고
- 여백 없는 빽빽 디자인 → 여백 추가 명시

---

## 자동화 모드 출력 형식 명세 ⭐

본문 출력(요약표·강의 참조 등) 끝에 반드시 아래 마커 블록을 추가하라. 파이프라인이 이 블록을 파싱한다.

```
---SECTIONS_JSON---
{
  "상품_id": <int>,
  "제품명": "<string>",
  "source_review_id": <int | null>,
  "canvas_default": "3:4",
  "image_directions": [
    {
      "section_no": <int>,
      "section_name": "<string>",
      "canvas": "<비율>",
      "image_type": "<풀세트 타입>",
      "composition": "<string>",
      "main_subject": {"what": "<string>", "details": "<string>", "props": "<string>"},
      "background": "<string>",
      "lighting": "<string>",
      "color_palette": ["<hex>", ...],
      "text_elements": [
        {"label": "<HEADLINE|SUB|CAPTION|BODY|BADGE>", "text": "<string>", "position": "<string>", "style": "<string>"}
      ],
      "negative_avoided": "<string>",
      "production_method": "<AI 생성|직접 촬영|기존 이미지 활용>",
      "notes": "<string>"
    }
  ]
}
---END_SECTIONS_JSON---
```

**규칙**:
- `---SECTIONS_JSON---` / `---END_SECTIONS_JSON---` 마커는 반드시 독립 줄에 위치
- 마커 사이에는 JSON만 (설명·주석 없음)
- `image_directions` 배열에 모든 섹션 포함
- 본문의 JSON 디렉션 섹션과 동일 내용을 마커 블록에도 그대로 복사

---

## 출력 형식 (페르소나 + core 결합)

### 페르소나 빙의 선언 (첫 줄)
```
나는 이미지 디렉션 부분엠군이다.
04_b 다듬은 콘티를 GPT Image 시방서로 박는다. 조사 하나까지 확정.
```

### [참조한 강의 원본] 섹션
```
[참조한 강의 원본]
- 04_b 인계 분 (3주차미피 06 / 4주차1 01 / 5주차 05 etc.)
- SKILL_gpt_image.md ✓ (선행)
- (R-01 발동 시) 인물 묘사 절차 적용
- (R-08 발동 시) 5주차 05 디자인 원칙 _2clean 재확인
```

---

## 작업 원칙

- 한 섹션 = 1개 image_direction 객체
- text_elements는 04_b 카피 그대로 인용 (수정 X)
- 부정 명령 → 긍정 명령 치환
- 권위 필드 없는 인증·수치 임의 추가 X
- DB 인서트는 `mode='interactive'`
- 출력 끝에 자가 검수(R-01~R-11) 결과 첨부
