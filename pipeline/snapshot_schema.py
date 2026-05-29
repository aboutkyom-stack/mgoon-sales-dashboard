"""변경 감지 snapshot 단일 소스 매니페스트.

워크플로 단계(기초입력/엠군/상세페이지) 토글 ON 시점에 박제할 필드/단계 정의.

⚠️ 동기화 규약 (다른 채팅방 클로드에게도 적용)
================================================================
이 모듈은 변경 감지에 관여하는 모든 후보를 한 곳에서 선언한다.
박제 함수(supabase_read._extract_snapshot_field, _build_엠군_snapshot)와
설정 페이지의 멀티셀렉트 후보(settings.SNAPSHOT_FIELD_CANDIDATES)가
이 모듈을 단일 소스로 참조한다.

다음 변경이 일어나면 반드시 이 모듈도 같이 갱신해야 한다:

1. `pages/2_product_edit.py`의 `st.subheader` 그룹명을 바꿀 때
   → `SNAPSHOT_GROUPS`의 키도 같이 바꾼다.
2. `상품` 테이블에 새 컬럼이 추가/삭제될 때
   → `SNAPSHOT_GROUPS` 또는 `SNAPSHOT_SINGLE_FIELDS`도 같이 갱신.
3. `pipeline/storage.py`에 새 엠군 단계 메서드(`get_*`)가 추가될 때
   → `엠군_SNAPSHOT_STAGES`에 한 줄 추가.

규약을 지키지 않으면 새 단계/필드는 박제 후보에 안 잡힌다 (false positive 없음 — safe fallback).
================================================================
"""
from __future__ import annotations

# ── 기초입력 단계 후보 ─────────────────────────────────────

# 그룹 정의 — 그룹명은 pages/2_product_edit.py의 st.subheader 텍스트와 정확히 일치시킨다.
# 그룹이 박제되면 dict 형태로 박제됨: {"컬럼A": 값, "컬럼B": 값, ...}.
SNAPSHOT_GROUPS: dict[str, list[str]] = {
    "기본 정보": [
        "모델명", "제조사", "수입자", "원산지", "사용연령",
    ],
    "재고": [
        "실시간재고", "처리후재고", "재고수량",
        "재입고예정", "단종여부", "온라인판매가능",
    ],
    "가격": [
        "온라인판매가격",
        "소매가", "도매가", "실제받는가격", "평균입고가",
    ],
    "치수 / 무게": [
        "가로_cm", "세로_cm", "높이_cm", "무게_g",
        "박스_가로_cm", "박스_세로_cm", "박스_높이_cm", "박스_무게_g",
    ],
    "소재 / 색상": [
        "재질", "색상", "구성품",
        "박스_재질", "박스_색상",
    ],
    "인증": [
        "kc인증", "kc인증번호",
        "전파인증", "전파인증번호",
        "기타인증",
    ],
    "검수": [
        "검수완료", "검수메모",
    ],
}

# 단일 DB 컬럼 후보 (그룹 X).
SNAPSHOT_SINGLE_FIELDS: list[str] = [
    "카테고리",
    "서브카테고리",
    "시각설명",
    "제품특징_bullet",
    "제품특징_추가",
    "판매자특성_선택",
    "키워드",
]

# 파일 추적 가상 필드 — 상품_파일 테이블의 파일_유형별 동적 박제.
# 박제 형태: [{"id": 드라이브_파일_id, "name": 파일명}, ...] (id 기준 정렬).
# → 추가/삭제 + 파일명 변경 모두 감지 가능.
SNAPSHOT_FILE_FIELDS: list[tuple[str, str, str]] = [
    # (필드명, 파일_유형 매칭 값, UI 라벨)
    ("파일_image", "image", "이미지 파일 (image)"),
    ("파일_video", "video", "동영상 파일 (video)"),
    ("파일_etc",   "etc",   "기타 파일 (etc — image/video 외)"),
]


# ── 엠군 단계 매니페스트 ───────────────────────────────────
#
# 각 항목: (단계 키, UI 라벨, FK 타입, storage 메서드명)
#   - 단계 키:   설정 페이지의 멀티셀렉트 식별자 + snapshot dict 키
#   - UI 라벨:   사람이 읽는 설명
#   - FK 타입:   "run"    → method(run_id)
#                "target" → 각 run의 target 순회 후 method(target_id)
#                "detail" → 각 target의 상세페이지 순회 후 method(detail_id)
#   - 메서드명:  pipeline.storage.Storage 클래스의 메서드명
#
# 새 단계 추가 작업자(다른 채팅방 클로드 포함)는 storage.py에 메서드 추가 시
# 이 list에도 한 줄 추가해야 한다. 누락 시 박제에서 빠짐 (안전 fallback).
엠군_SNAPSHOT_STAGES: list[tuple[str, str, str, str]] = [
    ("엠군_01_타겟",           "01 결핍·타겟 후보",      "run",    "get_targets"),
    ("엠군_02_포지셔닝",       "02 포지셔닝",            "target", "get_positioning"),
    ("엠군_03_네이밍",         "03 네이밍",              "target", "get_네이밍"),
    ("엠군_04_a_상세페이지",   "04_a 상세페이지 콘티",   "target", "get_상세페이지"),
    ("엠군_04_b_검수",         "04_b 상세페이지 검수",   "detail", "get_상세페이지_검수"),
    ("엠군_04_1_이미지디렉션", "04_1 이미지 디렉션",     "target", "get_이미지디렉션"),
    ("엠군_05_채널",           "05 채널",                "target", "get_채널"),
]


# ── 헬퍼 — settings.py가 호출해 동적 candidates 생성 ──────

def 기초입력_candidates() -> list[str]:
    """기초입력 단계 변경 감지 후보 — 그룹 + 단일 + 파일 통합 순서로 반환."""
    return (
        list(SNAPSHOT_GROUPS.keys())
        + list(SNAPSHOT_SINGLE_FIELDS)
        + [f for f, _kind, _label in SNAPSHOT_FILE_FIELDS]
    )


def 엠군_candidates() -> list[str]:
    """엠군 단계 변경 감지 후보 — 엠군_SNAPSHOT_STAGES의 단계 키 순서대로."""
    return [stage_key for stage_key, _label, _fk, _method in 엠군_SNAPSHOT_STAGES]


def 상세페이지_candidates() -> list[str]:
    """상세페이지 단계 변경 감지 후보 — 현재 후속 작업자 없음."""
    return []


def 파일_field_kind(field: str) -> str | None:
    """파일 필드 → 파일_유형 매칭값 ('image'/'video'/'etc') 반환. 파일 필드 아니면 None."""
    for f, kind, _label in SNAPSHOT_FILE_FIELDS:
        if f == field:
            return kind
    return None


def 엠군_stage_info(stage_key: str) -> tuple[str, str, str] | None:
    """엠군 단계 키 → (라벨, FK 타입, 메서드명) 반환. 알 수 없으면 None."""
    for k, label, fk, method in 엠군_SNAPSHOT_STAGES:
        if k == stage_key:
            return label, fk, method
    return None


def 엠군_stage_label(stage_key: str) -> str:
    """엠군 단계 키 → 사람이 읽는 라벨. 없으면 키 그대로."""
    info = 엠군_stage_info(stage_key)
    return info[0] if info else stage_key
