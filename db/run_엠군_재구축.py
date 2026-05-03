# -*- coding: utf-8 -*-
"""엠군 결과 테이블 재구축 마이그레이션 실행기.

영문 mgoon_runs / mgoon_targets / mgoon_positioning 폐기 →
한글 엠군_실행 / 엠군_타겟 / 엠군_포지셔닝 신규 생성.

⚠️ 기존 mgoon_* 데이터는 모두 삭제됨.
실행: python db/run_엠군_재구축.py
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

SQL_FILE = Path(__file__).parent / "엠군_재구축.sql"
sql = SQL_FILE.read_text(encoding="utf-8")

print(f"실행: {SQL_FILE.name}")
with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()

# 검증 — 새 한글 테이블이 생겼는지, 영문 테이블이 사라졌는지
with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN ('엠군_실행', '엠군_타겟', '엠군_포지셔닝',
                                 'mgoon_runs', 'mgoon_targets', 'mgoon_positioning')
            ORDER BY table_name;
        """)
        existing = {row[0] for row in cur.fetchall()}

new_tables = {"엠군_실행", "엠군_타겟", "엠군_포지셔닝"}
old_tables = {"mgoon_runs", "mgoon_targets", "mgoon_positioning"}

missing = new_tables - existing
remaining_old = old_tables & existing

print()
if missing:
    print(f"[FAIL] 신규 테이블 누락: {missing}")
    sys.exit(1)
if remaining_old:
    print(f"[FAIL] 영문 테이블 잔존: {remaining_old}")
    sys.exit(1)

print("[OK] 엠군 테이블 재구축 완료")
print("  생성: 엠군_실행, 엠군_타겟, 엠군_포지셔닝")
print("  폐기: mgoon_runs, mgoon_targets, mgoon_positioning")

# 컬럼 구조 출력
for table in ("엠군_실행", "엠군_타겟", "엠군_포지셔닝"):
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = '{table}'
                ORDER BY ordinal_position;
            """)
            rows = cur.fetchall()
    print(f"\n  [{table}]")
    for col, dtype in rows:
        print(f"    - {col}: {dtype}")
