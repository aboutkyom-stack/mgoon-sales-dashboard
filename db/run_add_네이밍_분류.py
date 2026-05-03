# -*- coding: utf-8 -*-
"""엠군_네이밍.분류 컬럼 마이그레이션 실행기.

멱등(IF NOT EXISTS) — 재실행 안전.
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

SQL_FILE = Path(__file__).parent / "add_엠군_네이밍_분류.sql"
sql = SQL_FILE.read_text(encoding="utf-8")

print(f"실행: {SQL_FILE.name}")
with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()

# 검증
with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = '엠군_네이밍'
            ORDER BY ordinal_position;
        """)
        rows = cur.fetchall()

print("\n[OK] 엠군_네이밍 컬럼:")
for col, dtype in rows:
    print(f"  - {col}: {dtype}")
