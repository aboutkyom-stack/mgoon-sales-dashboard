# -*- coding: utf-8 -*-
"""엠군 04/05/03 단계 출력 테이블 마이그레이션 실행기.

대상 테이블:
  - 엠군_상세페이지 (04 결과)
  - 엠군_채널 (05 결과)
  - 엠군_네이밍 (03 결과, 별도 페이지에서 사용)

MY_SUPABASE_POOLER_URL(.env) 우선, 없으면 MY_SUPABASE_DB_URL 사용.
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

DIR = Path(__file__).parent
TARGETS = [
    ("add_엠군_상세페이지.sql", "엠군_상세페이지"),
    ("add_엠군_채널.sql",       "엠군_채널"),
    ("add_엠군_네이밍.sql",     "엠군_네이밍"),
]

# 1) DDL 실행
with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
        for fname, _ in TARGETS:
            sql = (DIR / fname).read_text(encoding="utf-8")
            cur.execute(sql)
            print(f"실행: {fname}")
    conn.commit()

# 2) 검증
print()
all_ok = True
with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
        for _, table in TARGETS:
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position;
            """, (table,))
            rows = cur.fetchall()
            if not rows:
                print(f"[FAIL] {table} 생성 확인 실패")
                all_ok = False
                continue
            print(f"[OK] {table}")
            for col, dtype in rows:
                print(f"  - {col}: {dtype}")
            print()

sys.exit(0 if all_ok else 1)
