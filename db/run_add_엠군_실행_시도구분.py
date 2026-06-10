# -*- coding: utf-8 -*-
"""엠군_실행 '시도 구분' 컬럼 추가 마이그레이션 실행기.

대화형 → Supabase 적재를 위해 엠군_실행에 시도 식별 컬럼을 추가한다.
한 상품(상품_id 고정)에 여러 대화형 시도(타겟·결핍 조합)를 엠군_실행 행으로 구분.

추가 컬럼: 시도_키, 시도_라벨, 타겟_가설, 결핍_가설, 모드, 대화형_폴더명, 버전
추가 인덱스: uq_엠군_실행_시도 (상품_id, 시도_키, 버전) UNIQUE

MY_SUPABASE_POOLER_URL(.env) 우선, 없으면 MY_SUPABASE_DB_URL 사용.
멱등(ADD COLUMN IF NOT EXISTS / CREATE UNIQUE INDEX IF NOT EXISTS) — 재실행 안전.

매핑 문서: 대화형/agents/_shared/db_적재_매핑.md (5장)
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
SQL_FILE = "add_엠군_실행_시도구분.sql"
TABLE = "엠군_실행"
EXPECTED_COLS = ["시도_키", "시도_라벨", "타겟_가설", "결핍_가설",
                 "모드", "대화형_폴더명", "버전"]
EXPECTED_INDEX = "uq_엠군_실행_시도"

# 1) DDL 실행
print("=" * 60)
print("엠군_실행 시도 구분 컬럼 마이그레이션")
print("=" * 60)
print()

sql_path = DIR / SQL_FILE
if not sql_path.exists():
    print(f"[ERROR] {SQL_FILE} 파일 없음")
    sys.exit(1)

with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
        cur.execute(sql_path.read_text(encoding="utf-8"))
        print(f"실행: {SQL_FILE} → {TABLE}")
    conn.commit()

print()

# 2) 검증 — 컬럼 + 인덱스 존재 확인
print("=" * 60)
print("검증: 추가된 컬럼 / 인덱스 존재 확인")
print("=" * 60)
print()

all_ok = True
with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
        # 컬럼 확인
        cur.execute(
            """
            SELECT column_name, data_type, column_default
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position;
            """,
            (TABLE,),
        )
        rows = cur.fetchall()
        if not rows:
            print(f"[FAIL] {TABLE} 테이블 자체가 없음")
            all_ok = False
        else:
            existing = {c for c, _, _ in rows}
            missing = [c for c in EXPECTED_COLS if c not in existing]
            if missing:
                print(f"[FAIL] {TABLE}: 누락 컬럼 {missing}")
                all_ok = False
            else:
                print(f"[OK] {TABLE}: 추가 컬럼 {EXPECTED_COLS} 모두 존재")
            for col, dtype, default in rows:
                if col in EXPECTED_COLS:
                    d = f" (default {default})" if default else ""
                    print(f"  - {col}: {dtype}{d}")
        print()

        # 인덱스 확인
        cur.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = %s AND indexname = %s;",
            (TABLE, EXPECTED_INDEX),
        )
        if cur.fetchone():
            print(f"[OK] 유니크 인덱스 {EXPECTED_INDEX} 존재")
        else:
            print(f"[FAIL] 유니크 인덱스 {EXPECTED_INDEX} 없음")
            all_ok = False

print()
print("=" * 60)
if all_ok:
    print("[SUCCESS] 시도 구분 마이그레이션 완료.")
    print("다음: ingest_to_supabase.py 구현 (대화형 → Supabase 적재)")
else:
    print("[FAIL] 일부 누락. 위 [FAIL] 메시지 확인.")
print("=" * 60)

sys.exit(0 if all_ok else 1)
