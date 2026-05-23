# -*- coding: utf-8 -*-
"""엠군 통합본 업그레이드 마이그레이션 실행기.

통합본(대화형2 진화) 신규 필드를 기존 테이블에 추가.

대상 테이블:
  - 엠군_포지셔닝: category_objections, rule_engine_inputs, rule_engine_flags,
                   persuasion_method_candidates
  - 엠군_상세페이지: engine_plan, 한_축_사슬, 설득_방식_주, 설득_방식_보조

MY_SUPABASE_POOLER_URL(.env) 우선, 없으면 MY_SUPABASE_DB_URL 사용.
멱등(ADD COLUMN IF NOT EXISTS) — 재실행 안전.

매핑 문서: agents/_shared/db_schema_mapping.md
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

DB_URL = (os.getenv("MY_SUPABASE_POOLER_URL", "").strip()
          or os.getenv("MY_SUPABASE_DB_URL", "").strip())
if not DB_URL:
    print("[ERROR] .env에 MY_SUPABASE_POOLER_URL 또는 MY_SUPABASE_DB_URL 필요")
    sys.exit(1)

DIR = Path(__file__).parent

# (DDL 파일, 대상 테이블, 추가될 컬럼 목록)
TARGETS = [
    (
        "add_엠군_02_업그레이드.sql",
        "엠군_포지셔닝",
        [
            "category_objections",
            "rule_engine_inputs",
            "rule_engine_flags",
            "persuasion_method_candidates",
        ],
    ),
    (
        "add_엠군_04a_업그레이드.sql",
        "엠군_상세페이지",
        [
            "engine_plan",
            "한_축_사슬",
            "설득_방식_주",
            "설득_방식_보조",
        ],
    ),
]

# 1) DDL 실행
print("=" * 60)
print("엠군 통합본 업그레이드 마이그레이션")
print("=" * 60)
print()

with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
        for fname, table, _ in TARGETS:
            sql_path = DIR / fname
            if not sql_path.exists():
                print(f"[ERROR] {fname} 파일 없음")
                sys.exit(1)
            sql = sql_path.read_text(encoding="utf-8")
            cur.execute(sql)
            print(f"실행: {fname} → {table}")
    conn.commit()

print()

# 2) 검증 — 추가된 컬럼이 실제로 존재하는지 확인
print("=" * 60)
print("검증: 추가된 컬럼 존재 확인")
print("=" * 60)
print()

all_ok = True
with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
        for _, table, expected_cols in TARGETS:
            cur.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position;
                """,
                (table,),
            )
            rows = cur.fetchall()
            if not rows:
                print(f"[FAIL] {table} 테이블 자체가 없음")
                all_ok = False
                continue

            existing_cols = {col for col, _ in rows}
            missing = [c for c in expected_cols if c not in existing_cols]

            if missing:
                print(f"[FAIL] {table}: 누락된 컬럼 {missing}")
                all_ok = False
            else:
                print(f"[OK] {table}: 추가 컬럼 {expected_cols} 모두 존재")

            # 추가 컬럼만 상세 출력 (전체 컬럼 출력하면 너무 길어짐)
            for col, dtype in rows:
                if col in expected_cols:
                    print(f"  - {col}: {dtype}")
            print()

print("=" * 60)
if all_ok:
    print("[SUCCESS] 모든 업그레이드 완료. 통합본 agents 받을 준비 OK.")
    print("다음: agents 폴더 교체 (Phase B-6)")
else:
    print("[FAIL] 일부 컬럼 누락. 위 [FAIL] 메시지 확인.")
print("=" * 60)

sys.exit(0 if all_ok else 1)
