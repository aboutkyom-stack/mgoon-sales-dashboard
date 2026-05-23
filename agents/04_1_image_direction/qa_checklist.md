# 04_1 이미지 디렉션 — 자가 검수 체크리스트

> **로드 시점**: 디렉션 JSON 출력 직후.

---

## R-01. 한 섹션 = 1개 객체
04_b 다듬은 콘티의 각 섹션에 대해 1개씩만 image_direction 객체가 생성됐는가.

- 위반 예: 한 섹션에 2개 디렉션 (의도가 갈라짐)
- 통과 예: N섹션 → N개 디렉션 객체

---

## R-02. 캔버스 비율 명시
모든 객체에 `canvas` 비율이 명시됐는가. (1:1 / 4:5 / 3:4 / 9:16 / 16:9 중 하나)

---

## R-03. image_type 풀세트 매핑
모든 객체의 `image_type`이 풀세트 12장 매핑 중 하나인가.

(자료화면 캡처 / 인포그래픽 / 제품 정면샷 / 제품 장착·사용샷 / 인증·마크 클로즈업 / 비교 컷 / GIF / 영상 / 타겟 라이프스타일 / 텍스트 강조 패널 등)

---

## R-04. text_elements 04_b 카피 일치
모든 text_elements의 `text`가 04_b 다듬은 콘티의 HEADLINE/SUB/CAPTION/BODY/BADGE와 글자 단위 일치하는가. 임의 수정 X.

---

## R-05. text_elements position/style 명시
모든 text_elements에 `position`과 `style`이 명시됐는가.

- 위반 예: text만 있고 position 없음
- 통과 예: position "상단 중앙", style "굵게·강조색"

---

## R-06. 부정 명령 회피 (R-06 트리거)
"하지 마라", "보이지 않게" 같은 부정 명령이 직접 쓰이지 않았는가. 긍정 명령으로 치환됐는가.

- 위반 예: "사람 얼굴 보이지 않게"
- 통과 예: "뒷모습만 보이게, 어깨선 위로 크롭"

---

## R-07. 인물 등장 시 한국인 외형 + 타겟 일관성 (R-01 트리거)
인물 등장 디렉션에 한국인 외형 + 01의 타겟 캐릭터(나이·성별·직업·상황) 일관성이 반영됐는가.

- 위반 예: "여성" 만 명시 (서양인으로 생성될 수 있음)
- 통과 예: "한국인 30대 여성, 단발머리, 자연스러운 메이크업, 캐주얼 정장"

---

## R-08. 색 팔레트 3색 이하
모든 객체의 `color_palette`가 3색 이하인가. (5주차 05 디자인 원칙)

---

## R-09. production_method 명시
모든 객체에 `production_method`가 명시됐는가. (AI 생성 / 직접 촬영 / 기존 이미지 활용)

---

## R-10. 권위 필드 일치 (D-01·D-02)
인증·연령·수치·가격이 디렉션에 포함됐으면 권위 필드와 일치하는가. VP 박스 인쇄 라벨을 사실로 사용하지 않았는가.

---

## R-11. JSON 스키마 유효성
출력 JSON이 core.md 스키마와 일치하는가. 누락 필드 없는가.

- 필수 필드: section_no, section_name, canvas, image_type, composition, main_subject, background, lighting, color_palette, text_elements, production_method
- 권장 필드: negative_avoided, notes

---

## Deep-01. SKILL_gpt_image.md 선행 정독
디렉션 작성 전 SKILL_gpt_image.md 정독했는가.

## Deep-02. 5주차 05 디자인 원칙 흡수
04에서 정독 안 했으면 5주차 05 _3summary 정독.

## Deep-03. [참조한 강의 원본] 섹션
출력 끝에 명시.

---

## 항목 추가 기준

- 새로운 디렉션 실패 패턴 발견 시 R-12 이후로 추가
- 추가는 사용자 OK 후
