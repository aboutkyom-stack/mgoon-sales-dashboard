"""Google Drive OAuth pickle 토큰 발급/갱신 스크립트.

drive_client.py의 ACCOUNTS 리스트에 등록된 계정에 대해 OAuth 2.0 플로우를 거쳐
credentials/token{n}_{name}.pickle 생성.

사용법:
    cd 자동화형
    python scripts/refresh_oauth_token.py voyager
    python scripts/refresh_oauth_token.py kyom

새 계정 (ACCOUNTS에 아직 없을 때) — n 번호 지정:
    python scripts/refresh_oauth_token.py kyom --n 1

전제:
    credentials/account{n}_{name}.json (Google Cloud OAuth 2.0 Desktop Client) 존재.
    OAUTH_SETUP.md 가이드 참조.

출력:
    credentials/token{n}_{name}.pickle 생성/갱신.

동작:
    브라우저가 자동으로 열림 → Google 로그인 → "고급" → "안전하지 않은 페이지로 이동"
    (앱이 테스트 단계라 경고 정상) → Drive 권한 동의 → pickle 자동 저장.
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
CREDENTIALS_DIR = ROOT / "credentials"

# drive_client.py와 동일 SCOPE 유지
SCOPES = ["https://www.googleapis.com/auth/drive"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Google Drive OAuth pickle 토큰 발급/갱신",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "name",
        help="계정 이름 (drive_client.ACCOUNTS의 'name' 필드 — 예: voyager, donnamoo, kyom)",
    )
    parser.add_argument(
        "--n",
        default=None,
        help="계정 번호 (ACCOUNTS에 없는 새 계정일 때 지정 — 예: 3)",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT))
    try:
        from pipeline.drive_client import ACCOUNTS
    except ImportError as e:
        print(f"❌ pipeline.drive_client import 실패: {e}")
        return 1

    acc = next((a for a in ACCOUNTS if a["name"] == args.name), None)
    if acc is None:
        if not args.n:
            print(f"❌ '{args.name}' 계정이 ACCOUNTS에 없습니다.")
            print(f"   기존 계정: {[a['name'] for a in ACCOUNTS]}")
            print(f"   새 계정 추가하려면 --n <번호> 지정 (예: --n 3)")
            return 1
        acc = {"label": f"account{args.n}_{args.name}", "n": args.n, "name": args.name}
        print(f"⚠ ACCOUNTS에 없는 새 계정 — 발급 후 drive_client.py의 ACCOUNTS 리스트에 추가하세요.")

    client_json = CREDENTIALS_DIR / f"{acc['label']}.json"
    token_pickle = CREDENTIALS_DIR / f"token{acc['n']}_{acc['name']}.pickle"

    if not client_json.exists():
        print(f"❌ OAuth Client JSON 없음: {client_json}")
        print()
        print("   Google Cloud Console에서 OAuth 2.0 Client (Desktop app) 발급 후 저장.")
        print("   상세 절차: 자동화형/OAUTH_SETUP.md 참조")
        return 1

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("❌ google-auth-oauthlib 패키지 없음")
        print("   pip install google-auth-oauthlib")
        return 1

    print(f"📋 계정     : {acc['label']}")
    print(f"📂 Client   : {client_json}")
    print(f"💾 Pickle   : {token_pickle}")
    if token_pickle.exists():
        print(f"⚠ 기존 pickle 덮어씁니다.")
    print()
    print("🌐 브라우저가 열립니다. Google 로그인 → 권한 동의 → 자동 저장")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(str(client_json), SCOPES)
    creds = flow.run_local_server(port=0)

    with open(token_pickle, "wb") as f:
        pickle.dump(creds, f)

    print()
    print(f"✅ 발급 완료: {token_pickle}")

    # DB 동기화 — Streamlit Cloud(partner)에서도 같은 토큰 사용 가능하게
    try:
        from pipeline.supabase_read import upsert_drive_token
        upsert_drive_token(args.name, {
            "refresh_token": creds.refresh_token,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "token_uri": creds.token_uri,
            "scopes": list(creds.scopes) if creds.scopes else SCOPES,
        })
        print(f"✅ DB drive_auth 동기화 완료: {args.name}")
    except Exception as e:
        print(f"⚠ DB 동기화 실패 (pickle은 정상 저장됨, Cloud에서는 미반영): {e}")

    print()
    print("   이제 자동화형 Streamlit을 재시작하면 VP 정상 작동합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
