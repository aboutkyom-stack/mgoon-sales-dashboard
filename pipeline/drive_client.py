"""Google Drive 클라이언트.

서비스 계정(credentials/ 폴더의 JSON)으로 인증 후 Drive를 읽기/쓰기.

브라우저 인증 불필요 — 완전 자동화 가능.
단, 드라이브 폴더를 서비스 계정 이메일과 공유해야 한다.
"""
from __future__ import annotations

import io
from pathlib import Path

CREDENTIALS_DIR = Path(__file__).parent.parent / "credentials"

# drive.file: 앱이 생성한 파일만 접근 (보안) + 공유된 폴더 읽기는 drive 필요
# 업로드/폴더생성을 위해 drive 전체 스코프 사용
SCOPES = ["https://www.googleapis.com/auth/drive"]

# 확장자 → MIME 타입
_EXT_TO_MIME: dict[str, str] = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".webp": "image/webp",
    ".gif":  "image/gif",
    ".bmp":  "image/bmp",
    ".mp4":  "video/mp4",
    ".mov":  "video/quicktime",
    ".webm": "video/webm",
    ".pdf":  "application/pdf",
}

# 무료 계정 기준 15 GB (서비스 계정 about() 쿼터 미지원 → 하드코딩)
ASSUMED_LIMIT_BYTES: int = 15 * 1024 ** 3

# 계정 목록. 추가 시 여기에만 넣으면 됨.
ACCOUNTS: list[dict] = [
    {"label": "account1_voyager",  "n": "1", "name": "voyager"},
    {"label": "account2_donnamoo", "n": "2", "name": "donnamoo"},
]

# MIME 타입 → 파일_유형 매핑
_MIME_TO_TYPE: dict[str, str] = {
    "image/jpeg": "image",
    "image/png":  "image",
    "image/webp": "image",
    "image/gif":  "image",
    "video/mp4":  "video",
    "video/quicktime": "video",
    "video/webm": "video",
    "application/pdf": "detail_page",
}


def _get_credentials(label: str):
    """OAuth2 Credentials 반환.

    토큰 소스 우선순위:
        1) 로컬: credentials/token{n}_{name}.pickle 우선
        2) Streamlit Cloud 또는 pickle 없음: Supabase `drive_auth` 테이블 fallback

    만료 시 자동 refresh + 사본 동기화:
        - 로컬 + pickle 사용 중: pickle 갱신 + DB upsert (refresh_token 회전 대비)
        - Cloud 또는 DB만 사용 중: DB upsert만

    실패 케이스:
        - pickle 없음 + drive_auth에도 미등록 → FileNotFoundError
        - refresh_token 없는 만료 토큰 → RuntimeError
    """
    import pickle
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        raise ImportError(
            "Google Drive 패키지가 없습니다.\n"
            "pip install google-auth google-api-python-client"
        )

    from .runtime import is_streamlit_cloud

    acc = next((a for a in ACCOUNTS if a["label"] == label), None)
    if acc is None:
        raise ValueError(f"알 수 없는 계정: {label}")

    token_path = CREDENTIALS_DIR / f"token{acc['n']}_{acc['name']}.pickle"
    creds: Credentials | None = None
    token_source: str = ""  # "pickle" | "db"

    # 1. 로컬에서 pickle 우선
    if not is_streamlit_cloud() and token_path.exists():
        with open(token_path, "rb") as f:
            creds = pickle.load(f)
        token_source = "pickle"

    # 2. fallback — DB drive_auth (Cloud이거나 로컬에서 pickle 부재)
    if creds is None:
        from .supabase_read import get_drive_token
        db_token = get_drive_token(acc["name"])
        if db_token is None:
            raise FileNotFoundError(
                f"OAuth 토큰을 찾을 수 없음 (pickle 부재 + drive_auth 미등록): {acc['name']}\n"
                "로컬에서 'python scripts/refresh_oauth_token.py {name}' 실행해 재발급 + DB 동기화 필요."
            )
        creds = Credentials(
            token=None,
            refresh_token=db_token.get("refresh_token"),
            client_id=db_token.get("client_id"),
            client_secret=db_token.get("client_secret"),
            token_uri=db_token.get("token_uri") or "https://oauth2.googleapis.com/token",
            scopes=db_token.get("scopes") or SCOPES,
        )
        token_source = "db"

    # 3. 만료 처리 + 양쪽 동기화
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # pickle 갱신 (로컬에서 pickle 쓰던 경우만)
            if token_source == "pickle":
                with open(token_path, "wb") as f:
                    pickle.dump(creds, f)
            # DB 갱신 (refresh_token이 회전될 수 있음 + Cloud 사용 케이스 보강)
            try:
                from .supabase_read import upsert_drive_token
                upsert_drive_token(acc["name"], {
                    "refresh_token": creds.refresh_token,
                    "client_id": creds.client_id,
                    "client_secret": creds.client_secret,
                    "token_uri": creds.token_uri,
                    "scopes": list(creds.scopes) if creds.scopes else SCOPES,
                })
            except Exception:
                # DB upsert 실패는 치명적이지 않음 (메모리상 토큰은 이미 유효)
                pass
        else:
            raise RuntimeError(
                f"토큰 갱신 불가 — refresh_token 없음: {acc['name']}\n"
                "scripts/refresh_oauth_token.py로 재발급 필요."
            )

    return creds


def build_service(label: str):
    """Drive v3 service 객체 반환."""
    try:
        from googleapiclient.discovery import build
    except ImportError:
        raise ImportError(
            "google-api-python-client가 없습니다.\n"
            "pip install google-api-python-client"
        )
    creds = _get_credentials(label)
    return build("drive", "v3", credentials=creds)


def list_files_in_folder(service, folder_id: str) -> list[dict]:
    """폴더 내 파일 목록 (서브폴더 미포함)."""
    results = []
    page_token = None
    while True:
        params = {
            "q": (
                f"'{folder_id}' in parents "
                "and mimeType != 'application/vnd.google-apps.folder' "
                "and trashed = false"
            ),
            "fields": "nextPageToken, files(id, name, mimeType, size, createdTime, webViewLink)",
            "pageSize": 200,
        }
        if page_token:
            params["pageToken"] = page_token
        resp = service.files().list(**params).execute()
        results.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return results


def list_subfolders(service, root_folder_id: str) -> list[dict]:
    """루트 폴더 내 서브폴더 목록. {"id": ..., "name": ...}"""
    resp = service.files().list(
        q=(
            f"'{root_folder_id}' in parents "
            "and mimeType = 'application/vnd.google-apps.folder' "
            "and trashed = false"
        ),
        fields="files(id, name)",
        pageSize=500,
    ).execute()
    return resp.get("files", [])


def scan_folder_to_파일_rows(service, folder_id: str) -> list[dict]:
    """폴더 스캔 후 상품_파일 upsert용 row 리스트 반환.

    서브폴더(image/, video/, detail/)가 있으면 재귀 스캔.
    없으면 현재 폴더의 파일만 스캔.
    """
    files = list_files_in_folder(service, folder_id)
    subfolders = list_subfolders(service, folder_id)

    # 서브폴더가 있으면 재귀
    if subfolders:
        for sub in subfolders:
            sub_files = list_files_in_folder(service, sub["id"])
            for f in sub_files:
                # 서브폴더명으로 유형 추론 (image/, video/, detail_page/ 등)
                inferred = _infer_type_from_folder(sub["name"]) or _mime_to_type(f.get("mimeType", ""))
                f["_유형"] = inferred
            files.extend(sub_files)

    rows = []
    for f in files:
        유형 = f.get("_유형") or _mime_to_type(f.get("mimeType", ""))
        if not 유형:
            continue  # 알 수 없는 파일 타입 스킵
        rows.append({
            "파일명": f.get("name"),
            "파일_유형": 유형,
            "드라이브_파일_id": f.get("id"),
            "드라이브_url": f.get("webViewLink"),
            "업로드일": f.get("createdTime"),
        })
    return rows


def _guess_mime(filename: str) -> str:
    """파일 확장자로 MIME 타입 추정."""
    return _EXT_TO_MIME.get(Path(filename).suffix.lower(), "application/octet-stream")


def _guess_type(filename: str) -> str:
    """파일 확장자로 파일_유형(image/video/detail_page) 추정."""
    return _mime_to_type(_guess_mime(filename)) or "기타"


def parse_folder_id(url_or_id: str) -> str:
    """Drive 폴더 URL 또는 ID에서 ID만 추출."""
    s = url_or_id.strip()
    if "folders/" in s:
        s = s.split("folders/")[-1].split("?")[0].strip()
    return s


# ── 폴더 생성 ─────────────────────────────────────────────

def create_folder(service, name: str, parent_id: str | None = None) -> str:
    """Drive에 폴더 생성 후 folder_id 반환."""
    metadata: dict = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        metadata["parents"] = [parent_id]
    result = service.files().create(body=metadata, fields="id").execute()
    return result["id"]


def get_or_create_folder(service, folder_name: str, parent_id: str | None = None) -> str:
    """폴더명으로 검색 → 있으면 기존 ID, 없으면 생성 후 반환."""
    safe = folder_name.replace("'", "\\'")
    query = (
        f"name = '{safe}' "
        "and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    if parent_id:
        query += f" and '{parent_id}' in parents"

    resp = service.files().list(q=query, fields="files(id)", pageSize=1).execute()
    hits = resp.get("files", [])
    if hits:
        return hits[0]["id"]
    return create_folder(service, folder_name, parent_id)


# ── 파일 업로드 ────────────────────────────────────────────

def upload_file(
    service,
    file_bytes: bytes,
    filename: str,
    parent_id: str,
    mime_type: str | None = None,
) -> dict:
    """파일 업로드 후 {"id", "name", "webViewLink", "mimeType"} 반환.

    업로드 후 자동으로 '링크 있는 누구나 보기' 권한 부여 → 썸네일 URL 정상 표시.
    """
    try:
        from googleapiclient.http import MediaIoBaseUpload
    except ImportError:
        raise ImportError(
            "google-api-python-client가 없습니다.\n"
            "pip install google-api-python-client"
        )
    if mime_type is None:
        mime_type = _guess_mime(filename)

    metadata = {"name": filename, "parents": [parent_id]}
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=False)
    result = service.files().create(
        body=metadata,
        media_body=media,
        fields="id, name, webViewLink, mimeType",
    ).execute()

    # 썸네일 표시를 위해 '링크 있는 누구나 보기' 권한 부여
    service.permissions().create(
        fileId=result["id"],
        body={"type": "anyone", "role": "reader"},
    ).execute()

    return result


def download_file(service, file_id: str) -> tuple[bytes, str]:
    """Drive 파일 다운로드 후 (bytes, mime_type) 반환."""
    try:
        from googleapiclient.http import MediaIoBaseDownload
    except ImportError:
        raise ImportError("pip install google-api-python-client")

    meta = service.files().get(fileId=file_id, fields="mimeType").execute()
    mime = meta.get("mimeType", "image/jpeg")

    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, service.files().get_media(fileId=file_id))
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue(), mime


def get_usage_bytes(service) -> int:
    """서비스 계정이 접근 가능한 모든 파일 크기 합산 (폴더 제외)."""
    total = 0
    page_token = None
    while True:
        params: dict = {
            "q": "trashed = false and mimeType != 'application/vnd.google-apps.folder'",
            "fields": "nextPageToken, files(size)",
            "pageSize": 1000,
        }
        if page_token:
            params["pageToken"] = page_token
        resp = service.files().list(**params).execute()
        for f in resp.get("files", []):
            try:
                total += int(f.get("size", 0))
            except (ValueError, TypeError):
                pass
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return total


def get_all_quota_info() -> list[dict]:
    """모든 계정의 Drive 사용량 조회.

    Returns:
        [{"label", "name", "used_bytes", "limit_bytes", "pct", "error"}]
    """
    results = []
    for acc in ACCOUNTS:
        entry: dict = {
            "label": acc["label"],
            "name": acc["name"],
            "used_bytes": 0,
            "limit_bytes": ASSUMED_LIMIT_BYTES,
            "pct": 0.0,
            "error": None,
        }
        try:
            svc = build_service(acc["label"])
            used = get_usage_bytes(svc)
            entry["used_bytes"] = used
            entry["pct"] = min(used / ASSUMED_LIMIT_BYTES, 1.0)
        except Exception as e:
            entry["error"] = str(e)
        results.append(entry)
    return results


def _mime_to_type(mime: str) -> str | None:
    return _MIME_TO_TYPE.get(mime)


def _infer_type_from_folder(folder_name: str) -> str | None:
    name = folder_name.lower()
    if "image" in name or "이미지" in name or "img" in name:
        return "image"
    if "video" in name or "영상" in name:
        return "video"
    if "detail" in name or "상세" in name:
        return "detail_page"
    return None
