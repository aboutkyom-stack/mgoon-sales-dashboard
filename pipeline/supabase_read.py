"""내 Supabase DB 클라이언트 (read/write).

상품, 상품_파일 테이블 기준. MY_SUPABASE_* 환경변수 사용.
"""
from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

CHUNK = 1000


@lru_cache(maxsize=1)
def _client() -> Client:
    url = os.getenv("MY_SUPABASE_URL", "").strip()
    key = os.getenv("MY_SUPABASE_ANON_KEY", "").strip()
    if not url or not key:
        raise RuntimeError(".env에 MY_SUPABASE_URL과 MY_SUPABASE_ANON_KEY를 설정하세요.")
    return create_client(url, key)


def _fetch_all(table: str, query_fn=None) -> list[dict]:
    """1,000행 제한 우회 페이지네이션."""
    rows, start = [], 0
    while True:
        q = _client().table(table).select("*").range(start, start + CHUNK - 1)
        if query_fn:
            q = query_fn(q)
        batch = q.execute().data or []
        rows.extend(batch)
        if len(batch) < CHUNK:
            break
        start += CHUNK
    return rows


# ── 목록 조회 ─────────────────────────────────────────────

def list_products(
    search: str = "",
    엠군상태: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """상품 목록 조회. 검색·엠군상태 필터 지원.

    limit=None(기본): 1,000행 제한 우회 페이지네이션으로 전체 조회.
    limit=N: N행까지만 조회 (단일 요청, supabase 한도 1,000 적용).
    """
    def _apply_filters(q):
        if search:
            q = q.ilike("제품명", f"%{search}%")
        if 엠군상태 and 엠군상태 != "전체":
            if 엠군상태 == "미시작":
                # NULL 저장된 레코드도 미시작으로 취급
                q = q.or_("엠군상태.eq.미시작,엠군상태.is.null")
            else:
                q = q.eq("엠군상태", 엠군상태)
        return q

    if limit is not None:
        q = _client().table("상품").select("*").order("id", desc=True).limit(limit)
        q = _apply_filters(q)
        return q.execute().data or []

    rows, start = [], 0
    while True:
        q = (
            _client()
            .table("상품")
            .select("*")
            .order("id", desc=True)
            .range(start, start + CHUNK - 1)
        )
        q = _apply_filters(q)
        batch = q.execute().data or []
        rows.extend(batch)
        if len(batch) < CHUNK:
            break
        start += CHUNK
    return rows


def list_엠군상태_values() -> list[str]:
    """엠군상태 필터 선택지."""
    return ["전체", "미시작", "진행중", "완료"]


# ── 단일 상품 조회 ────────────────────────────────────────

def get_product(상품_id: int) -> dict | None:
    """상품 전체 필드 조회."""
    res = (
        _client()
        .table("상품")
        .select("*")
        .eq("id", 상품_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def get_product_spec(상품_id: int) -> dict | None:
    """엠군 01/02 입력용 스펙 딕셔너리.

    반환 구조는 파이프라인 loader.py와 계약된 형식 유지.
    """
    row = get_product(상품_id)
    if not row:
        return None

    return {
        "id":           row["id"],
        "제품명":       row.get("제품명"),
        "카테고리":     row.get("카테고리"),
        "서브카테고리": row.get("서브카테고리"),
        "엠군상태":     row.get("엠군상태"),
        "시각설명":     row.get("시각설명"),
        "스펙": {
            "모델명":     row.get("모델명"),
            "제조사":     row.get("제조사"),
            "수입자":     row.get("수입자"),
            "원산지":     row.get("원산지"),
            "사용연령":   row.get("사용연령"),
            "가로_cm":    row.get("가로_cm"),
            "세로_cm":    row.get("세로_cm"),
            "높이_cm":    row.get("높이_cm"),
            "무게_g":     row.get("무게_g"),
            "박스_가로_cm": row.get("박스_가로_cm"),
            "박스_세로_cm": row.get("박스_세로_cm"),
            "박스_높이_cm": row.get("박스_높이_cm"),
            "박스_무게_g":  row.get("박스_무게_g"),
            "재질":       row.get("재질"),
            "색상":       row.get("색상"),
            "구성품":     row.get("구성품"),
            "박스_재질":  row.get("박스_재질"),
            "박스_색상":  row.get("박스_색상"),
            "치수정보":   row.get("치수정보"),
        },
        "인증": {
            "kc인증":    row.get("kc인증"),
            "kc인증번호": row.get("kc인증번호"),
            "기타인증":  row.get("기타인증"),
        },
        "가격": {
            "온라인판매가격": row.get("온라인판매가격"),
            "소매가":         row.get("소매가"),
            "도매가":         row.get("도매가"),
            "실제받는가격":   row.get("실제받는가격"),
            "평균입고가":     row.get("평균입고가"),
        },
        "재고": {
            "실시간재고": row.get("실시간재고"),
            "처리후재고": row.get("처리후재고"),
            "재고수량":  row.get("재고수량"),
            "재입고예정": row.get("재입고예정"),
            "단종여부":  row.get("단종여부"),
            "온라인판매가능": row.get("온라인판매가능"),
        },
        "제품특징_bullet": row.get("제품특징_bullet") or [],
        "제품특징_추가":   row.get("제품특징_추가"),
        "판매자특성_선택": row.get("판매자특성_선택") or [],
        "키워드":         row.get("키워드"),
        "검수완료":       row.get("검수완료"),
        "검수메모":       row.get("검수메모"),
    }


# ── 파일 조회 ─────────────────────────────────────────────

def get_files(상품_id: int) -> list[dict]:
    """상품_파일에서 상품_id에 연결된 파일 목록."""
    try:
        res = (
            _client()
            .table("상품_파일")
            .select("*")
            .eq("상품_id", 상품_id)
            .execute()
        )
        return res.data or []
    except Exception:
        return []


def get_thumbnail_url(드라이브_파일_id: str, size: int = 400) -> str:
    """Google Drive 썸네일 URL 생성."""
    return f"https://drive.google.com/thumbnail?id={드라이브_파일_id}&sz=w{size}"


# ── 상품 CRUD ────────────────────────────────────────────

def insert_상품(data: dict) -> dict:
    """상품 신규 등록. 생성된 행 반환."""
    res = _client().table("상품").insert(data).execute()
    return res.data[0] if res.data else {}


def update_상품(
    상품_id: int,
    data: dict,
    original_수정일: str | None = None,
) -> bool:
    """상품 필드 업데이트.

    낙관적 락:
        original_수정일이 주어지면 `수정일`이 일치하는 row만 update (동시편집 충돌 감지).
        - 매칭되어 1행 이상 update되면 True
        - 매칭 실패(다른 사용자가 먼저 수정함)면 False
        - original_수정일=None이면 기존 동작 그대로 (항상 True)

    수정일 자동 갱신:
        DB 트리거(상품_수정일_갱신)가 모든 UPDATE에서 NEW.수정일 = NOW()로 강제.
        호출 측에서 data["수정일"]을 명시할 필요 없음 (지정해도 트리거에 덮어씌워짐).
    """
    q = _client().table("상품").update(data).eq("id", 상품_id)
    if original_수정일 is not None:
        q = q.eq("수정일", original_수정일)
    res = q.execute()
    if original_수정일 is not None:
        return bool(res.data)
    return True


def get_account_folder(상품_id: int, 계정: str) -> str | None:
    """상품의 특정 계정에 매핑된 Drive 폴더 ID 반환. 없으면 None.

    계정별_폴더_ids JSON에서 조회. 마이그레이션 안 된 옛 row면 드라이브_폴더_id로 fallback 안 함
    (어느 계정 폴더인지 모르므로 호출 측에서 새로 생성).
    """
    p = get_product(상품_id)
    if not p:
        return None
    folders = p.get("계정별_폴더_ids") or {}
    return folders.get(계정)


def set_account_folder(상품_id: int, 계정: str, folder_id: str) -> dict:
    """상품의 계정별_폴더_ids에 (계정 → folder_id) 매핑 추가/갱신.

    하위 호환: 매핑이 비어 있던 경우 단일 컬럼 드라이브_폴더_id도 함께 업데이트
              (다른 페이지/스크립트가 아직 옛 컬럼을 읽을 수 있어 보존).

    Returns: 갱신된 계정별_폴더_ids dict
    """
    p = get_product(상품_id) or {}
    folders = dict(p.get("계정별_폴더_ids") or {})
    folders[계정] = folder_id

    payload: dict = {"계정별_폴더_ids": folders}
    if not p.get("드라이브_폴더_id"):
        payload["드라이브_폴더_id"] = folder_id

    update_상품(상품_id, payload)
    return folders


def list_account_folders(상품: dict) -> dict:
    """상품 row에서 계정별_폴더_ids dict 반환 (None이면 빈 dict).

    마이그레이션 안 된 row 호환: 계정별_폴더_ids가 비어 있고 드라이브_폴더_id만 있으면
    호출 측에서 사용 가능한 정보 부족으로 빈 dict 반환 (계정 추정 불가).
    """
    return dict(상품.get("계정별_폴더_ids") or {})


def delete_상품(상품_id: int) -> None:
    """상품 삭제 (연결된 상품_파일은 ON DELETE CASCADE로 함께 삭제)."""
    _client().table("상품").delete().eq("id", 상품_id).execute()


def delete_임시_products(exclude_id: int | None = None) -> int:
    """제품명이 '임시_'로 시작하는 모든 레코드 삭제. 삭제 개수 반환.

    exclude_id가 주어지면 그 id는 보존 (현재 편집 중인 임시 레코드 보호용).
    """
    res = (
        _client()
        .table("상품")
        .select("id, 제품명")
        .ilike("제품명", "임시%")
        .execute()
    )
    rows = res.data or []
    count = 0
    for r in rows:
        if not (r.get("제품명") or "").startswith("임시_"):
            continue
        if exclude_id is not None and r["id"] == exclude_id:
            continue
        try:
            delete_상품(r["id"])
            count += 1
        except Exception:
            pass
    return count


# ── 엠군작업대상 토글 ────────────────────────────────────────

def set_엠군작업대상(상품_id: int, value: bool) -> None:
    """상품.엠군작업대상 값을 설정한다."""
    _client().table("상품").update({"엠군작업대상": value}).eq("id", 상품_id).execute()


# ── is_test 토글 (테스트 레코드 구분) ─────────────────────────

def set_is_test(상품_id: int, value: bool) -> None:
    """상품.is_test 값을 설정한다. True면 테스트 레코드로 격리."""
    _client().table("상품").update({"is_test": value}).eq("id", 상품_id).execute()


# ── 엠군상태 업데이트 ─────────────────────────────────────

def update_엠군상태(상품_id: int, 상태: str) -> None:
    """엠군 파이프라인 진행 상태 업데이트. (미시작 / 진행중 / 완료)"""
    _client().table("상품").update({"엠군상태": 상태}).eq("id", 상품_id).execute()


# ── 시각설명 업데이트 (Vision Pass 결과 저장) ──────────────

def update_시각설명(상품_id: int, 시각설명: str) -> None:
    """Vision Pass 결과를 상품.시각설명에 저장."""
    _client().table("상품").update({"시각설명": 시각설명}).eq("id", 상품_id).execute()


# ── 비전패스_이력 CRUD ────────────────────────────────────

def insert_비전패스_이력(
    상품_id: int,
    파일_id: str | None,
    모델명: str,
    프롬프트: str,
    결과: str,
    실행_모드: str = "single",
) -> dict:
    """Vision Pass 실행 결과를 이력 테이블에 영구 저장.

    Args:
        파일_id: 드라이브 파일 ID. 일괄실행 결과면 None.
        실행_모드: 'single' (이미지별) | 'bulk' (일괄)

    Returns: 생성된 행 (id 포함).
    """
    res = _client().table("비전패스_이력").insert({
        "상품_id":   상품_id,
        "파일_id":   파일_id,
        "모델명":    모델명,
        "프롬프트":  프롬프트,
        "결과":      결과,
        "실행_모드": 실행_모드,
    }).execute()
    return res.data[0] if res.data else {}


def list_비전패스_이력(상품_id: int, 파일_id: str | None = None) -> list[dict]:
    """상품의 Vision Pass 이력 조회. 파일_id 지정 시 해당 이미지 이력만.

    최신순 정렬.
    """
    q = (
        _client()
        .table("비전패스_이력")
        .select("*")
        .eq("상품_id", 상품_id)
        .order("생성일", desc=True)
    )
    if 파일_id is not None:
        q = q.eq("파일_id", 파일_id)
    return q.execute().data or []


def delete_비전패스_이력(이력_id: int) -> None:
    """이력 1건 삭제."""
    _client().table("비전패스_이력").delete().eq("id", 이력_id).execute()


# ── 갤러리 관련 ────────────────────────────────────────────

def list_all_images(search: str = "", 계정: str | None = None, limit: int = 500) -> list[dict]:
    """상품_파일에서 이미지 전체 조회. 상품명 JOIN 포함."""
    q = (
        _client()
        .table("상품_파일")
        .select("id, 상품_id, 파일명, 드라이브_파일_id, 드라이브_url, 계정, 상품(id, 제품명)")
        .eq("파일_유형", "image")
        .not_.is_("드라이브_파일_id", "null")
        .order("상품_id")
        .limit(limit)
    )
    if 계정:
        q = q.eq("계정", 계정)
    rows = q.execute().data or []
    result = []
    for r in rows:
        flat = dict(r)
        product = flat.pop("상품", None) or {}
        flat["제품명"] = product.get("제품명", "")
        result.append(flat)
    return result


def get_image_counts() -> dict[int, int]:
    """상품별 이미지 수 딕셔너리 반환. {상품_id: count}"""
    try:
        res = (
            _client()
            .table("상품_파일")
            .select("상품_id")
            .eq("파일_유형", "image")
            .execute()
        )
        counts: dict[int, int] = {}
        for row in res.data or []:
            pid = row["상품_id"]
            counts[pid] = counts.get(pid, 0) + 1
        return counts
    except Exception:
        return {}


def list_계정_values() -> list[str]:
    """상품_파일에 등록된 계정 목록."""
    try:
        res = (
            _client()
            .table("상품_파일")
            .select("계정")
            .not_.is_("계정", "null")
            .execute()
        )
        seen = set()
        result = []
        for row in res.data or []:
            v = row.get("계정")
            if v and v not in seen:
                seen.add(v)
                result.append(v)
        return sorted(result)
    except Exception:
        return []


def count_파일_by_계정() -> dict[str, int]:
    """상품_파일 테이블의 계정별 파일 수 dict. {계정: count}.

    Drive 대시보드 카드의 "이 계정에 업로드된 파일 수" 표시용.
    """
    try:
        res = _client().table("상품_파일").select("계정").execute()
        counts: dict[str, int] = {}
        for row in res.data or []:
            v = row.get("계정")
            if v:
                counts[v] = counts.get(v, 0) + 1
        return counts
    except Exception:
        return {}


def delete_파일(파일_id: int) -> None:
    """상품_파일 레코드 삭제."""
    _client().table("상품_파일").delete().eq("id", 파일_id).execute()


# ── drive_auth (OAuth 토큰 DB 동기화) ─────────────────────

def get_drive_token(account_name: str) -> dict | None:
    """drive_auth 테이블에서 토큰 정보 조회. 없으면 None.

    반환 dict 키: account_name, refresh_token, client_id, client_secret, token_uri, scopes, updated_at.
    """
    try:
        res = (
            _client()
            .table("drive_auth")
            .select("*")
            .eq("account_name", account_name)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception:
        return None


def upsert_drive_token(account_name: str, token_data: dict) -> dict:
    """drive_auth UPSERT. account_name 기준 충돌 해소.

    token_data 인식 키: refresh_token, client_id, client_secret, token_uri, scopes.
    updated_at은 자동으로 현재 시각으로 설정.
    """
    from datetime import datetime, timezone

    payload: dict = {"account_name": account_name}
    for k in ("refresh_token", "client_id", "client_secret", "token_uri", "scopes"):
        if k in token_data and token_data[k] is not None:
            payload[k] = token_data[k]
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()

    res = (
        _client()
        .table("drive_auth")
        .upsert(payload, on_conflict="account_name")
        .execute()
    )
    return res.data[0] if res.data else {}


# ── 편집_세션 (동시편집 보호 — 사회적 조정) ────────────────

def upsert_편집_세션(상품_id: int, 사용자명: str) -> None:
    """편집 세션 UPSERT — (상품_id, 사용자명) 충돌 시 마지막_활동시각만 갱신."""
    from datetime import datetime, timezone

    _client().table("편집_세션").upsert({
        "상품_id": 상품_id,
        "사용자명": 사용자명,
        "마지막_활동시각": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="상품_id,사용자명").execute()


def get_active_편집_세션(
    상품_id: int,
    exclude_사용자명: str | None = None,
    ttl_min: int = 5,
) -> list[dict]:
    """ttl_min 분 이내 활성 편집 세션 목록. exclude_사용자명은 결과에서 제외.

    동시편집 배지(상단 알림)용 — 다른 사용자가 같은 상품을 편집 중인지 확인.
    """
    from datetime import datetime, timezone, timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=ttl_min)).isoformat()
    q = (
        _client()
        .table("편집_세션")
        .select("*")
        .eq("상품_id", 상품_id)
        .gte("마지막_활동시각", cutoff)
    )
    if exclude_사용자명:
        q = q.neq("사용자명", exclude_사용자명)
    return q.execute().data or []


def delete_편집_세션(상품_id: int, 사용자명: str) -> None:
    """편집 세션 row 즉시 삭제 — 페이지 명시적 종료 시 호출.

    상대편 화면에서 ttl 기다리지 않고 즉시 "편집 중 아님"으로 반영되게.
    """
    _client().table("편집_세션").delete().eq("상품_id", 상품_id).eq("사용자명", 사용자명).execute()


def upsert_파일(상품_id: int, files: list[dict], 계정: str) -> int:
    """Drive 스캔 결과를 상품_파일에 upsert. 드라이브_파일_id 기준 중복 방지.

    files: [{"파일명": str, "파일_유형": str, "드라이브_파일_id": str, "드라이브_url": str, "업로드일": str|None}]
    반환: upsert된 행 수
    """
    if not files:
        return 0
    rows = [
        {
            "상품_id": 상품_id,
            "파일명": f.get("파일명"),
            "파일_유형": f.get("파일_유형", "image"),
            "드라이브_파일_id": f.get("드라이브_파일_id"),
            "드라이브_url": f.get("드라이브_url"),
            "상태": "uploaded",
            "업로드일": f.get("업로드일"),
            "계정": 계정,
        }
        for f in files
        if f.get("드라이브_파일_id")
    ]
    if not rows:
        return 0
    _client().table("상품_파일").upsert(rows, on_conflict="드라이브_파일_id").execute()
    return len(rows)
