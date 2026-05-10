# GPT Image 2 공식 프롬프트 가이드 완전 정리

OpenAI의 **GPT Image 2(`gpt-image-2`)는 2026년 4월 21일 API와 ChatGPT에 동시 출시된 현재 플래그십 이미지 생성 모델**로, Image Arena 리더보드 전 부문 1위와 Text-to-Image 부문 +242점 차 신기록을 기록했다. 이 모델은 텍스트 렌더링·인포그래픽·다국어 스크립트·복잡한 구도 지시에서 이전 세대(`gpt-image-1`, `gpt-image-1.5`)를 크게 앞지르며, **최대 2K 해상도와 임의 종횡비**를 지원한다. 본 가이드는 OpenAI 공식 Cookbook(`image-gen-models-prompting-guide`, 2026-04-21), API 가이드, 모델 페이지를 1차 출처로 정리했고, 모든 프롬프트 예시는 공식 영문 원문을 그대로 보존했다. **DALL·E 2/3는 2026년 5월 12일 지원이 종료**되므로 신규 빌드는 모두 GPT Image 시리즈를 사용해야 한다.

---

## 1. 모델 개요와 라인업 한눈에 보기

GPT Image 시리즈는 한 계열 안에 네 모델이 공존하며, 모두 **같은 프롬프팅 원칙을 공유**한다. 차이는 비용·해상도·input fidelity 처리 방식이다.

| 모델 | 출시 | quality | input_fidelity | 해상도 | 권장 용도 |
|---|---|---|---|---|---|
| `gpt-image-2` | 2026-04-21 | low/medium/high | **항상 high (파라미터 비활성)** | 16배수 임의 비율, 변≤3840px, 비율≤3:1, 픽셀 ≤8.29M | **신규 빌드 기본값** |
| `gpt-image-1.5` | 2025-12-16 | low/medium/high | low/high | 1024², 1024×1536, 1536×1024 | 마이그레이션 검증 |
| `gpt-image-1` | 2025-04-23 | low/medium/high | low/high | 1024², 1024×1536, 1536×1024 | 레거시 호환 |
| `gpt-image-1-mini` | 2025-10-06 | low/medium/high | low/high | 동일 | 비용·대량 처리 (gpt-image-1 대비 ~80% 저렴) |

**GPT Image 2의 결정적 신기능**은 네 가지로 요약된다. 첫째, **최대 2K 해상도와 자유로운 종횡비**로 광고·소셜·문서·내부 도구용 자산을 한 모델로 처리한다. 둘째, **다이어그램·인포그래픽·만화·다중 패널·다국어 텍스트 렌더링**이 실용 수준으로 올라왔다. 셋째, **세부 지시 추종, 디테일 보존, 객체 관계, 밀도 높은 구성**이 향상됐다. 넷째, OpenAI 최초의 **reasoning 통합 이미지 모델**로, GPT-5 등 reasoning 모델과 결합하면 검색·다중 이미지 생성·자체 검증을 수행하는 **Thinking mode**가 활성화된다.

지원 입출력은 텍스트/이미지 입력 → 이미지 출력으로, **스트리밍·function calling·structured outputs·fine-tuning은 미지원**이다. 지식 컷오프는 2025년 12월이며, GPT Image 시리즈는 모두 사용 전 **API Organization Verification(정부 발급 신분증 + 안면 인증)** 이 필수다.

DALL·E 대비 차별점을 OpenAI는 이렇게 명시한다. **"Superior instruction following, text rendering, detailed editing, real-world knowledge"** — 즉 단순한 텍스트→이미지를 넘어 *지시를 정확히 따르고, 이미지 안에 글자를 제대로 그리며, 실제 세계 지식으로 추론하는 것*이 핵심 차별 포인트다.

---

## 2. 프롬프트 작성의 9가지 공식 원칙

OpenAI가 알파 테스트에서 일관되게 발견한 패턴은 **순서·구체성·iterate**로 압축된다. 아래는 공식 Cookbook의 *Prompting Fundamentals* 섹션을 한국어로 정리한 것이다.

**구조와 목표.** 프롬프트는 일관된 순서로 — `background/scene → subject → key details → constraints` — 작성하고, **의도된 용도(ad / UI mock / infographic 등)를 명시**해 모델의 "모드"와 폴리시 수준을 설정한다. 포맷은 자유다. 짧은 미니멀 프롬프트, 긴 서술 단락, JSON-like 구조, 인스트럭션 스타일, 태그 기반 모두 동작한다. 프로덕션에서는 *clever syntax*보다 **읽기 쉬운 템플릿**이 유지보수에 좋다.

**구체성과 품질 큐.** 재질·형태·텍스처·시각 매체(photo / watercolor / 3D render)를 구체적으로 지정한다. 포토리얼리즘이 필요하면 **`photorealistic` 단어를 직접** 넣어 모델의 photorealistic mode를 강하게 활성화한다. `real photograph`, `taken on a real camera`, `professional photography`, `iPhone photo`도 같은 효과를 낸다. 흥미롭게도 **"8K"·"ultra-detailed" 같은 제네릭 키워드보다 카메라·렌즈·조명 용어가 더 잘 먹힌다**(예: `35mm film`, `50mm lens`, `shallow depth of field`).

**구도(Composition) 4요소.** Framing/viewpoint(`close-up`, `wide`, `top-down`), perspective/angle(`eye-level`, `low-angle`), lighting/mood(`soft diffuse`, `golden hour`, `high-contrast`), layout placement(`logo top-right`, `centered with negative space on left`)을 **각각 한 줄로 분리해 명시**하면 안정성이 크게 오른다.

**인물·포즈·액션.** `full body visible, feet included` / `child-sized relative to the table` / `looking down at the open book, not at the camera` / `hands naturally gripping the handlebars` 같이 **신체 비율·시선·접점**을 짧은 문장으로 박아 넣으면 해부학적 오류가 줄어든다.

**이미지 안의 텍스트 렌더링** — GPT Image의 핵심 강점. (1) 리터럴 텍스트는 **따옴표 또는 ALL CAPS**로 감싼다. (2) 폰트 스타일·크기·색·배치 같은 타이포그래피 디테일을 명시한다. (3) 까다로운 단어(브랜드명, 비표준 철자)는 **letter-by-letter spell out**한다(`O-P-E-N-A-I`). (4) 작은 텍스트나 다중 폰트 레이아웃은 `quality="medium"` 이상으로 올린다. (5) **특정 폰트명보다 일반 폰트 키워드**(`bold sans-serif`, `clean serif`)가 더 안정적이다.

**제약과 보존(편집의 핵심).** 제외 사항을 끝에 모아 명시한다 — `no watermark`, `no extra text`, `no logos/trademarks`. 편집 시에는 **`change only X` + `keep everything else the same`** 패턴을 쓰고, **매 iteration마다 preserve list를 반복**한다. saturation·contrast·layout·arrows·labels·camera angle·surrounding objects도 변경 금지가 필요하면 모두 명시해야 한다.

**다중 이미지 입력.** 각 입력을 인덱스+설명으로 참조한다 — `Image 1: product photo… Image 2: style reference…` — 그리고 어떻게 상호작용하는지(예: `apply Image 2's style to Image 1`)를 명시한다.

**Latency vs Fidelity.** 기본은 `quality="low"`로 시작해 충분하면 그대로 둔다. **작은 텍스트, 밀집 인포그래픽, 클로즈업 인물, identity-sensitive 편집, 고해상도**일 때만 medium/high로 올려 비교한다.

**한 번에 욱여넣지 말고 iterate하라.** 가장 강조되는 메타 원칙이다. 깨끗한 base prompt → 작은 single-change 후속 프롬프트로 디버깅한다. `same style as before`, `the subject` 같은 표현으로 컨텍스트를 활용하되, drift 시 핵심 디테일을 재명시한다.

---

## 3. 파라미터 레퍼런스 — quality·size·background·moderation

API는 `v1/images/generations`(생성), `v1/images/edits`(편집), `v1/responses`(Responses API), `v1/chat/completions` 네 엔드포인트로 호출한다. 핵심 파라미터는 다음과 같다.

| 파라미터 | 값 | 핵심 메모 |
|---|---|---|
| `quality` | `low`, `medium`, `high`, `auto` | 기본 `auto`. low 토큰가 ~$0.006/장(1024²), high ~$0.211/장. 텍스트·디테일은 medium 이상 권장 |
| `size` | `1024x1024`, `1536x1024`, `1024x1536`, `auto` (1.x); gpt-image-2는 임의 비율 | 변 < 3840px, 16의 배수, 비율 ≤ 3:1, 픽셀 655K~8.29M |
| `output_format` | `png`(기본), `jpeg`, `webp` | latency 우선 시 jpeg |
| `output_compression` | 0~100 | jpeg/webp 전용 |
| `background` | `transparent`, `opaque`, `auto` | png/webp만 transparent 지원. 프롬프트에 `transparent background`라 적으면 자동 적용 |
| `moderation` | `auto`(기본), `low` | low는 덜 엄격하지만 핵심 정책은 동일 |
| `n` | int | 변형 동시 생성 (예: 로고 4개) |
| `input_fidelity` | `low`(기본), `high` | gpt-image-1/1.5/mini 전용. **gpt-image-2는 항상 high** |
| `partial_images` | 0~3 | 스트리밍용. partial당 +100 image output tokens |
| `mask` | 이미지 파일 | inpainting. **alpha channel 필수**, 50MB 미만, 원본과 동일 형식·크기 |

**가격(2026-04-21 기준).** Image modality는 1M 토큰당 input $8.00 / cached input $2.00 / output $30.00. Text modality는 input $5.00 / cached $1.25 / output $10.00. 이미지 토큰 수는 quality와 해상도에 비례한다(1024² 기준 low 272 / medium 1056 / **high 4160**). Rate limit은 Tier 1에서 분당 5장(IPM), Tier 5에서 250장까지 확장된다.

**최소 호출 예시(Python).**

```python
from openai import OpenAI
import base64
client = OpenAI()

result = client.images.generate(
    model="gpt-image-2",
    prompt="A children's book drawing of a veterinarian using a stethoscope to listen to the heartbeat of a baby otter."
)
image_bytes = base64.b64decode(result.data[0].b64_json)
open("otter.png", "wb").write(image_bytes)
```

**Responses API에서 도구로 호출**하면 GPT-5 같은 mainline 모델이 자동으로 prompt를 다듬어 `revised_prompt`로 반환하고, `previous_response_id`로 멀티턴 편집 컨텍스트를 이어갈 수 있다.

---

## 4. 이미지 편집(Edits)과 Inpainting의 실전 패턴

편집 API는 단일 이미지 또는 **최대 10개의 reference 이미지**를 입력받고, 선택적으로 mask로 영역을 지정한다. **마스크는 가이드일 뿐 정확한 형태를 따르지 않을 수 있다**는 것이 DALL·E 2와의 결정적 차이다 — 공식 문서: *"masking with GPT Image is entirely prompt-based … may not follow its exact shape with complete precision."* 마스크가 여러 이미지에 적용되지 않고 **첫 번째 이미지에만** 작동한다는 점도 주의해야 한다.

**다중 reference 결합.** 여러 제품 사진을 합쳐 선물 바구니를 만드는 공식 예시:

```
Generate a photorealistic image of a gift basket on a white background 
labeled 'Relax & Unwind' with a ribbon and handwriting-like font, 
containing all the items in the reference pictures.
```

```python
result = client.images.edit(
    model="gpt-image-2",
    image=[open("body-lotion.png","rb"), open("bath-bomb.png","rb"),
           open("incense-kit.png","rb"), open("soap.png","rb")],
    prompt=prompt
)
```

**Mask 기반 inpainting.** mask는 알파 채널을 포함해야 한다. PIL로 흑백 mask를 alpha로 변환하는 패턴:

```python
mask = Image.open(path).convert("L")
mask_rgba = mask.convert("RGBA")
mask_rgba.putalpha(mask)   # 흰색 영역이 편집 대상
```

mask와 함께 보낼 prompt는 **편집된 영역만이 아니라 결과 이미지 전체를 묘사**해야 한다. 공식 예시:

```
A sunlit indoor lounge area with a pool containing a flamingo
```

**정체성 보존이 중요한 편집(가상 피팅 등)** 은 보존 목록을 길게 나열하는 것이 정답이다:

```
Edit the image to dress the woman using the provided clothing images. 
Do not change her face, facial features, skin tone, body shape, pose, or identity in any way. 
Preserve her exact likeness, expression, hairstyle, and proportions. 
Replace only the clothing, fitting the garments naturally to her existing pose and body geometry 
with realistic fabric behavior. Match lighting, shadows, and color temperature to the original photo 
so the outfit integrates photorealistically, without looking pasted on. 
Do not change the background, camera angle, framing, or image quality, 
and do not add accessories, text, logos, or watermarks.
```

**캐릭터 일관성 워크플로우** 는 두 단계 패턴이다. (1) **Anchor 이미지 생성**: 외형·비율·의상·톤을 lock한 첫 컷을 생성한다. (2) **같은 이미지를 입력으로 사용**해 새 장면을 `images.edit`로 만들고, prompt에 *"Same green hooded tunic / Same facial features, proportions, and color palette / Do not redesign the character"* 같은 일관성 락을 반복한다. 이 패턴이 그림책·시리즈·만화 파이프라인에서 character drift를 방지한다.

`gpt-image-1.5`는 **첫 5장의 입력 이미지를 고충실도로 보존**하고, `gpt-image-1`/mini는 첫 1장만 보존한다. 따라서 **얼굴·정체성이 중요한 reference는 항상 첫 번째 위치**에 둔다. `gpt-image-2`는 default가 high fidelity이므로 이 고려가 사라진다.

---

## 5. 사용 사례별 공식 프롬프트 — 영문 원문 그대로

아래 모든 예시는 OpenAI Cookbook 공식 노트북에서 인용한 원문이다. **영문 원문을 그대로 사용하는 것**이 모델 성능에 가장 좋다.

### 포토리얼리즘 인물 (`quality="medium"`, `1024x1536` 권장)

```
Create a photorealistic candid photograph of an elderly sailor standing on a small fishing boat. 
He has weathered skin with visible wrinkles, pores, and sun texture, and a few faded traditional sailor tattoos on his arms. 
He is calmly adjusting a net while his dog sits nearby on the deck. 
Shot like a 35mm film photograph, medium close-up at eye level, using a 50mm lens. 
Soft coastal daylight, shallow depth of field, subtle film grain, natural color balance. 
The image should feel honest and unposed, with real skin texture, worn materials, and everyday detail. 
No glamorization, no heavy retouching.
```

핵심 패턴: `candid` / `honest and unposed` / `no glamorization, no heavy retouching` 같은 **anti-staging 키워드**가 photorealism을 안정화한다.

### 시대 추론(World Knowledge)

```
Create a realistic outdoor crowd scene in Bethel, New York on August 16, 1969.
Photorealistic, period-accurate clothing, staging, and environment.
```

모델은 "Woodstock"이라 명시하지 않아도 시대 고증을 적용한다.

### 인포그래픽 (`size="1536x1024"`, `quality="high"`)

```
Create a simple biology diagram titled "Cellular Respiration at a Glance" for high school students.

Show how glucose turns into energy inside a cell. Include glycolysis, the Krebs cycle, and the electron transport chain.
Use arrows to connect the steps, and label the main molecules: glucose, pyruvate, ATP, NADH, FADH2, CO2, O2, and H2O.
Make it look like a clean classroom handout or slide, with a white background, simple icons, clear labels, and easy-to-read text.

Avoid tiny text, extra decoration, or anything that makes the diagram hard to understand.
```

### 로고 (변형 4개 동시 — `n=4`)

```
Create an original, non-infringing logo for a company called Field & Flour, a local bakery. 
The logo should feel warm, simple, and timeless. Use clean, vector-like shapes, a strong silhouette, 
and balanced negative space. Favor simplicity over detail so it reads clearly at small and large sizes. 
Flat design, minimal strokes, no gradients unless essential. 
Plain background. Deliver a single centered logo with generous padding. No watermark.
```

### 광고 크리에이티브(브랜드 + 카피)

```
Give me a cool in culture ad / fashion shot for a brand called Thread. 
It's a hip young street brand. The ad shows a group of friends hanging out together with the tagline "Yours to Create."
Make it feel like a polished campaign image for a youth streetwear audience: stylish, contemporary, energetic, and tasteful.
Use clean composition, strong color direction, natural poses, and premium fashion photography cues.
Render the tagline exactly once, clearly and legibly, integrated into the ad layout.
No extra text, no watermarks, no unrelated logos.
```

### UI/UX 모킹업

```
Create a realistic mobile app UI mockup for a local farmers market. 
Show today's market with a simple header, a short list of vendors with small photos and categories, 
a small "Today's specials" section, and basic information for location and hours. 
Design it to be practical, and easy to use. White background, subtle natural accent colors, 
clear typography, and minimal decoration. 
It should look like a real, well-designed, beautiful app for a small local market. 
Place the UI mockup in an iPhone frame.
```

핵심 원칙: **"이미 출시된 제품처럼 묘사하라"** — concept-art 언어 회피, *shipped interface* 톤으로.

### 피치덱 슬라이드 (텍스트·데이터 밀집, `quality="high"`)

```
Create one pitch-deck slide titled **"Market Opportunity"** that feels like a real Series A fundraising slide from a YC-backed startup.

Use a clean white background, modern sans-serif typography like Inter, and a crisp, minimal layout. The slide should include:

* A TAM/SAM/SOM concentric-circle diagram in muted blues and grays
* Specific, believable market sizing numbers:
  * **TAM:** $42B
  * **SAM:** $8.7B
  * **SOM:** $340M
* A clean bar chart below showing market growth from **2021 to 2026**, with a subtle upward trend
* Small footnotes: **"AGI Research, 2024"** and **"Internal analysis"**
* A company logo placeholder in the bottom-right corner

Avoid clip art, stock photography, gradients, shadows, decorative elements, or anything that feels generic or overdesigned.
```

### 4컷 만화/스토리보드

```
Create a short vertical comic-style reel with 4 equal-sized panels.
Panel 1: The owner leaves through the front door. The pet is framed in the window behind them, small against the glass, eyes wide, paws pressed high, the house suddenly quiet.
Panel 2: The door clicks shut. Silence breaks. The pet slowly turns toward the empty house, posture shifting, eyes sharp with possibility.
Panel 3: The house transformed. The pet sprawls across the couch like it owns the place, crumbs nearby, sunlight cutting across the room like a spotlight.
Panel 4: The door opens. The pet is seated perfectly by the entrance, alert and composed, as if nothing happened.
```

### 인-이미지 텍스트가 정확해야 하는 빌보드

```
Create a realistic billboard mockup of the shampoo on a highway scene during sunset.
Billboard text (EXACT, verbatim, no extra characters):
"Fresh and clean"
Typography: bold sans-serif, high contrast, centered, clean kerning.
Ensure text appears once and is perfectly legible.
No watermarks, no logos.
```

### 투명 배경 자산(스티커·아이콘)

```
generate a pixel-art style picture of a green bucket hat with a pink quill on a transparent background.
```

프롬프트에 `transparent background`라 적으면 `background` 파라미터가 자동으로 transparent로 설정되며, **PNG 또는 WEBP 출력만** 가능하다.

### 캐릭터 디자인 — 디테일한 sub-spec 추종

```
Render a realistic image of this character:
Blobby Alien Character Spec — Name: Glorptak (or "Glorp")

Body Shape: Amorphous and gelatinous … resembles a teardrop or melting marshmallow.
Material Texture: Semi-translucent, bio-luminescent goo with a jelly-like wobble.
Color Palette:
- Base: Iridescent lavender or seafoam green
- Accents: Subsurface glowing veins of neon pink, electric blue, or golden yellow
- Mood-based color shifts (anger = dark red, joy = bright aqua, fear = pale gray)
Facial Features:
- Eyes: 3–5 asymmetrical floating orbs that rotate or blink independently
- Mouth: Optional rippling crescent on the surface when speaking
- Limbs: None by default; can extrude pseudopods when needed
Movement: Slides, bounces, rolls. Sticks to walls via suction.
Mannerisms: Constant wiggling; leaves harmless glowing slime trails.
```

### 다국어 로컬라이제이션(인포그래픽 텍스트만 번역)

```
Translate the text in the infographic to Spanish. Do not change any other aspect of the image.
```

### 객체 제거·교체·외과적 편집

```
Remove the tree logo from the white t-shirt of the man. Do not change anything else.
```

```
Change the color of the red hat to light blue as velvet. Do not change anything else.
```

```
In this room photo, replace ONLY white with chairs made of wood.
Preserve camera angle, room lighting, floor shadows, and surrounding objects.
Keep all other aspects of the image unchanged.
Photorealistic contact shadows and fabric texture.
```

### 다중 이미지 합성

```
Place the dog from the second image into the setting of image 1, right next to the woman, 
use the same style of lighting, composition and background. Do not change anything else.
```

### 스케치 → 포토리얼

```
Turn this drawing into a photorealistic image.
Preserve the exact layout, proportions, and perspective.
Choose realistic materials and lighting consistent with the sketch intent.
Do not add new elements or text.
```

### 16개 객체 그리드(객체 수 한계 테스트)

```
A square image containing a 4 row by 4 column grid containing 16 objects on a white background. 
Go from left to right, top to bottom. 1. a blue star  2. red triangle  3. green square  4. pink circle  
5. orange hourglass  6. purple infinity sign  7. black and white polka dot bowtie  8. tiedye "42"  
9. an orange cat wearing a black baseball cap  10. a map with a treasure chest  11. a pair of googly eyes  
12. a thumbs up emoji  13. a pair of scissors  14. a blue and white giraffe  
15. the word "OpenAI" written in cursive  16. a rainbow-colored lightning bolt
```

---

## 6. 한계와 콘텐츠 정책 — 실패 패턴을 알면 회피할 수 있다

**기술적 한계.** 공식 문서가 명시하는 약점은 네 가지다. (1) **Latency** — 복잡한 프롬프트는 최대 2분이 걸릴 수 있다. (2) **Text rendering** — 크게 개선됐지만 정확한 위치·선명도가 항상 보장되진 않는다. (3) **Consistency** — 시리즈 생성 시 캐릭터·브랜드 요소가 흔들릴 수 있다. (4) **Composition control** — 레이아웃 민감한 구성에서 정확한 배치가 어렵다.

**자주 실패하는 프롬프트 패턴**은 경험적으로 다음과 같다. **곡면·회전된 텍스트**(병 라벨, 곡선 경로 위 글자)는 자주 왜곡된다. **20–30단어 이상의 본문**은 철자 오류가 빈발한다. **장식성·필기체 폰트**는 일관성이 떨어진다. **18pt 미만 작은 텍스트**는 깨끗하게 렌더되지 않는다. **비라틴 문자**(한국어·일본어·중국어·아랍어)는 결과가 불안정하다 — gpt-image-2에서 크게 개선됐지만 여전히 영어 대비 신뢰도가 낮다. 한 프롬프트에 **7개 이상의 핵심 요소**를 욱여넣으면 일부가 누락되므로 3–5개로 제한하고 나머지는 iterate한다.

**콘텐츠 정책.** 입력과 출력 모두 모더레이션이 적용된다. 미성년 공인 사진 생성, 폭력 정책 위반, 성적·차별적 콘텐츠는 차단된다. 정치인 등 성인 공인은 일정 조건 하에 허용되며, 사진 업로드 편집과 동일한 safeguard가 적용된다. `moderation="low"`로 일부 완화 가능하지만 **핵심 정책은 그대로** 유지된다. 정당한 사용 시 거부 회피 패턴은 다음과 같다. *brand-safe* 디자인을 원하면 `original, non-infringing`처럼 명시한다. 액션 장면이 거부되면 `fight`/`war` 대신 `dynamic cinematic action`, `heroic struggle`로 reframe한다. 의학·해부 시각화는 `classical marble sculpture anatomy` 또는 `Renaissance-style figure drawing` 톤으로 전환한다.

**프로비넌스(C2PA).** ChatGPT·Codex·API에서 생성된 모든 이미지는 **C2PA 메타데이터**가 자동 임베드된다. Content Credentials Verify 사이트에서 출처를 확인할 수 있고, 일부 이미지에는 좌상단에 CR(Content Credentials) 심볼이 표시되기도 한다. 단 C2PA는 silver bullet이 아니다 — **스크린샷이나 재인코딩 시 메타데이터가 사라지므로**, 메타데이터 없는 이미지가 곧 비-OpenAI 산출물이라는 뜻은 아니다.

---

## 7. 프로덕션에 바로 적용할 수 있는 9개 휴리스틱

가이드 전체를 압축한 워킹 휴리스틱이다. 새 프로젝트를 시작할 때 체크리스트로 사용하면 좋다.

1. **구조 고정**: scene → subject → details → constraints + 의도된 용도 한 줄 명시.
2. **포토리얼**: `photorealistic` + 카메라/렌즈/조명 용어 + `candid/unposed/no glamorization`.
3. **텍스트는 따옴표 또는 ALL CAPS**, `verbatim, no extra characters` 명시, 어려운 단어는 letter-by-letter spell out.
4. **편집은 `change only X` + `keep everything else the same`**, preserve list를 매번 반복.
5. **마스크는 alpha channel 필수**, prompt는 *결과 이미지 전체*를 묘사.
6. **다중 이미지는 인덱스 + 설명**으로 참조하고 상호작용을 명시.
7. **캐릭터 일관성**은 anchor 이미지 → 같은 이미지를 입력으로 새 장면 편집, "Do not redesign" 반복.
8. **iterate**: 한 프롬프트에 모든 걸 넣지 말고 작은 single-change 후속 프롬프트로 다듬는다.
9. **품질은 기본 low**, 텍스트·디테일·identity 필요 시 medium~high로 단계별 비교 후 결정.

---

## 결론 — 텍스트가 그려지는 시대의 프롬프트 전략

GPT Image 2의 진짜 변화는 *해상도가 더 커진 것*이 아니라, **이미지가 디자인 산출물이 되는 단계로 넘어간 것**이다. 인포그래픽·피치덱·UI·광고 카피·다중 패널 만화처럼 **텍스트와 레이아웃이 의미를 결정하는 자산**을 한 모델로 제작할 수 있게 되면서, 프롬프트는 *예술적 묘사*가 아니라 *디자인 브리프*에 가까워졌다. 따라서 잘 쓴 프롬프트는 시각적 미사여구가 아니라 **scene → subject → details → constraints + use case + 보존 규칙**이라는 건조한 구조를 따른다.

흥미로운 함의는 두 가지다. 첫째, **반복(iteration)이 일급(first-class) 워크플로**가 됐다 — anchor 생성 후 `images.edit`로 외과적 변경을 반복하는 패턴이 한 번에 완벽한 프롬프트를 작성하려는 시도를 압도한다. 둘째, **편집 가이드가 실질적으로 모델의 가장 강력한 인터페이스**다. inpainting의 mask는 프롬프트의 보조 가이드일 뿐이며, 정작 결과를 결정하는 것은 *"무엇을 보존할지"* 를 얼마나 명시적으로 적었는가다. 신규 프로덕트를 빌드한다면 `gpt-image-2`를 기본값으로, 비용 민감 워크로드는 `gpt-image-1-mini`로 분기하고, 두 모델 모두 위의 9개 휴리스틱을 템플릿화해 reusable prompt 라이브러리로 운영하는 것이 가장 빠른 길이다.
