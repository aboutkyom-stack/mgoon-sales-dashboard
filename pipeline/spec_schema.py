"""스펙 필드 단일 정의.

스펙 탭의 필드가 추가/제거/변경될 때 이 파일만 수정하면
- extract_스펙 LLM 프롬프트
- 자동 채우기 UI
가 모두 자동 반영된다.

각 항목:
    name      : DB 컬럼명 (= Streamlit 위젯 key prefix와 매칭)
    label     : 사용자 표시 라벨
    type      : 'text' | 'number' | 'bool'
    desc      : LLM에 추출 기준을 설명할 때 사용
    unit      : (선택) 'cm', 'g' 등 단위
"""
from __future__ import annotations

from typing import Literal, TypedDict


class SpecField(TypedDict, total=False):
    name: str
    label: str
    type: Literal["text", "number", "bool"]
    desc: str
    unit: str


# 시각설명에서 추출 가능한 스펙 필드만 정의 (KC인증·가격 등은 제외)
SPEC_FIELDS: list[SpecField] = [
    {"name": "카테고리",     "label": "카테고리",     "type": "text",
     "desc": "제품의 대분류 (예: 완구, 주방용품, 생활가전)"},
    {"name": "서브카테고리", "label": "서브카테고리", "type": "text",
     "desc": "제품의 소분류 (예: 유아완구, 베이킹도구)"},
    {"name": "모델명",       "label": "모델명",       "type": "text",
     "desc": "제품 박스/본체에 표기된 모델 번호. 없으면 null"},
    {"name": "제조사",       "label": "제조사",       "type": "text",
     "desc": "제조사명. 이미지 텍스트에서 명시적으로 보일 때만"},
    {"name": "원산지",       "label": "원산지",       "type": "text",
     "desc": "원산지/제조국. 이미지에 표기되어 있을 때만"},
    {"name": "가로_cm",      "label": "가로 (cm)",    "type": "number", "unit": "cm",
     "desc": "가로 치수. 이미지 텍스트에 명시된 수치만 인정. 추정 금지"},
    {"name": "세로_cm",      "label": "세로 (cm)",    "type": "number", "unit": "cm",
     "desc": "세로/깊이 치수. 명시된 수치만"},
    {"name": "높이_cm",      "label": "높이 (cm)",    "type": "number", "unit": "cm",
     "desc": "높이 치수. 명시된 수치만"},
    {"name": "무게_g",       "label": "무게 (g)",     "type": "number", "unit": "g",
     "desc": "무게(g 단위). kg 표기는 1000을 곱해 변환. 명시된 수치만"},
    {"name": "재질",         "label": "재질",         "type": "text",
     "desc": "주 재질 (예: ABS 플라스틱, 알루미늄, 패브릭)"},
    {"name": "색상",         "label": "색상",         "type": "text",
     "desc": "주조색. 보조색은 ',' 로 나열"},
    {"name": "구성품",       "label": "구성품",       "type": "text",
     "desc": "박스에 포함된 부속품 목록"},
]


def field_names() -> list[str]:
    """필드 이름 리스트만 반환."""
    return [f["name"] for f in SPEC_FIELDS]


def build_extraction_schema_text() -> str:
    """LLM 프롬프트에 삽입할 스펙 추출 가이드 텍스트 생성.

    스펙 필드가 변경되면 이 텍스트도 자동 갱신된다.
    """
    lines = []
    for f in SPEC_FIELDS:
        unit = f" ({f.get('unit')})" if f.get("unit") else ""
        type_hint = {"text": "문자열", "number": "숫자", "bool": "true/false"}[f["type"]]
        lines.append(f'  "{f["name"]}"{unit} [{type_hint}]: {f["desc"]}')
    return "\n".join(lines)
