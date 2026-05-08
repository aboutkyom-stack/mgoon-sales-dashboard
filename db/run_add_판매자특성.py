# -*- coding: utf-8 -*-
"""판매자특성_선택 컬럼 마이그레이션 실행기.

MY_SUPABASE_POOLER_URL(.env)로 psycopg2 직접 실행.
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

SQL_FILE = Path(__file__).parent / "add_판매자특성.sql"
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
            WHERE table_name = '상품' AND column_name = '판매자특성_선택';
        """)
        row = cur.fetchone()

if not row:
    print("[FAIL] 컬럼 생성 확인 실패")
    sys.exit(1)

print(f"\n[OK] 판매자특성_선택 컬럼 생성 완료: {row[0]} ({row[1]})")
