# Google Drive OAuth 발급 가이드

자동화형 시스템이 Google Drive에서 이미지를 읽고 쓰려면 OAuth 2.0 토큰(pickle)이 필요하다.
`pipeline/drive_client.py`가 `credentials/token{n}_{name}.pickle`을 자동 갱신하지만, refresh token이 무효해지면(수개월 미사용, 비밀번호 변경, 권한 취소 등) 재발급 필요.

## 사전 조건

- Google 계정 (무료 OK, 계정당 Drive 15GB)
- `pip install google-auth-oauthlib` (없으면)

---

## 1. Google Cloud Console 설정 (계정당 1회만)

### 1-1. 프로젝트 생성/선택
- https://console.cloud.google.com/ 접속
- 새 프로젝트 생성 (기존 프로젝트 재사용 가능)

### 1-2. Google Drive API 활성화
- **API 및 서비스 → 라이브러리**
- "Google Drive API" 검색 → **사용 설정**

### 1-3. OAuth 동의 화면 구성
- **API 및 서비스 → OAuth 동의 화면**
- 사용자 유형: **외부**
- 앱 정보:
  - 앱 이름: 임의 (예: `MgoonAutomation`)
  - 사용자 지원 이메일: 본인 Google 이메일
  - 개발자 연락처 이메일: 본인 이메일
- **범위 추가/삭제**: `https://www.googleapis.com/auth/drive` 추가
- **테스트 사용자**: 본인 Google 이메일 추가
  - 앱이 "테스트" 상태일 때는 등록된 사용자만 OAuth 가능
  - 100명까지 테스트 사용자 등록 가능

### 1-4. OAuth 2.0 Client 발급
- **API 및 서비스 → 사용자 인증 정보**
- **사용자 인증 정보 만들기 → OAuth 클라이언트 ID**
- 애플리케이션 유형: **데스크톱 앱**
- 이름: 임의 (예: `auto-selling-desktop`)
- **만들기** → **JSON 다운로드**

---

## 2. OAuth Client JSON 저장

다운로드한 JSON을 다음 경로에 저장:
```
자동화형/credentials/account{n}_{name}.json
```

- `{n}`: 계정 번호 (1, 2, 3, ...)
- `{name}`: 계정 식별자 — 영문 소문자 권장 (예: `kyom`, `main`, `sub1`)

예:
- 첫 본인 계정: `credentials/account1_kyom.json`
- 두 번째 본인 계정: `credentials/account2_kyom2.json`

---

## 3. drive_client.py의 ACCOUNTS 리스트에 등록

`pipeline/drive_client.py`의 `ACCOUNTS` 리스트에 새 계정 추가:

```python
ACCOUNTS: list[dict] = [
    {"label": "account1_kyom",     "n": "1", "name": "kyom"},     # 새 추가
    {"label": "account2_voyager",  "n": "2", "name": "voyager"},  # 기존 (선택)
    # ...
]
```

기존 동료 계정(`account1_voyager`, `account2_donnamoo`)을 본인 계정으로 교체하는 경우:
- 옵션 A: 동료 계정 항목 삭제 + 본인 계정 추가
- 옵션 B: 동료 계정 그대로 두고 본인 계정 추가 (병행 운영)

---

## 4. pickle 토큰 발급

```bash
cd 자동화형
python scripts/refresh_oauth_token.py kyom
```

(ACCOUNTS에 없는 새 계정 발급 시: `python scripts/refresh_oauth_token.py kyom --n 1`)

### 동작

1. 브라우저가 자동으로 열림
2. Google 로그인
3. **"이 앱은 검증되지 않았습니다"** 경고 → **고급** 클릭 → **"앱 이름(안전하지 않음)으로 이동"**
   - 앱이 "테스트" 단계라 정상 (Google이 검증 안 한 상태)
   - 본인이 만든 앱이라 안전함
4. Drive 접근 권한 동의 → **계속**
5. "인증 흐름이 완료됨" 메시지 → 브라우저 닫기 OK
6. 터미널에 `✅ 발급 완료` 출력 + `token{n}_{name}.pickle` 생성

---

## 5. 자동화형 Streamlit 재시작

```bash
cd 자동화형
streamlit run app.py
```

→ VP 단계에서 더 이상 `invalid_grant` 에러 안 남.

---

## 만료 시 재발급

OAuth refresh token이 무효해지면 (수개월 미사용·비밀번호 변경·권한 취소 등):

```bash
python scripts/refresh_oauth_token.py kyom
```

→ 새 pickle 생성. 동일 절차 반복.

자동화 운영 중 토큰 만료 직전이면 `drive_client._get_credentials`가 자동 갱신.
완전 무효화된 후에만 수동 재발급 필요.

---

## 트러블슈팅

### `RefreshError: invalid_grant: Bad Request`
- refresh token이 무효. 위 4번 (재발급) 진행.

### `OAuth Client JSON 없음`
- 1·2번 (Console 발급 + 저장) 누락. 다시 진행.

### `이 앱은 차단되었습니다`
- OAuth 동의 화면의 **테스트 사용자**에 본인 이메일 누락. 1-3번 재확인.

### `redirect_uri_mismatch`
- 발급 시 애플리케이션 유형이 **데스크톱 앱**이 아닐 가능성. 1-4번 재확인.

### 여러 계정 분산 운영
- 무료 계정당 Drive 15GB
- `ACCOUNTS` 리스트에 N개 등록 가능
- 제품 등록 시 어느 계정에 업로드할지 분산 로직은 `drive_client.py`의 잔여 코드에서 확인 (사용자 운영 정책)
