# -*- coding: utf-8 -*-
"""상품_파일.상품_id 컬럼을 NULLABLE로 변경.

매칭 해제(상품_id=NULL) 저장이 NOT NULL 제약에 막혀 실패하던 문제 수정.
멱등 — 이미 NULLABLE이면 no-op.
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

SQL_FILE = Path(__file__).parent / "alter_상품_파일_상품id_nullable.sql"
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
            SELECT is_nullable
            FROM information_schema.columns
            WHERE table_name = '상품_파일' AND column_name = '상품_id';
        """)
        row = cur.fetchone()

print()
if not row:
    print("[FAIL] 상품_파일.상품_id 컬럼을 찾을 수 없습니다.")
    sys.exit(1)

is_nullable = row[0]
if is_nullable != "YES":
    print(f"[FAIL] is_nullable = {is_nullable}")
    sys.exit(1)

print("[OK] 상품_파일.상품_id NULLABLE 변경 완료")
sys.exit(0)
