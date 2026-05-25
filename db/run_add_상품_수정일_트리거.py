# -*- coding: utf-8 -*-
"""상품 테이블 수정일 자동 갱신 트리거 마이그레이션 실행기.

MY_SUPABASE_POOLER_URL / MY_SUPABASE_DB_URL(.env)로 psycopg2 직접 실행.
멱등(CREATE OR REPLACE + DROP IF EXISTS) — 재실행 안전.
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

SQL_FILE = Path(__file__).parent / "add_상품_수정일_트리거.sql"
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
            SELECT trigger_name, event_manipulation, action_timing
            FROM information_schema.triggers
            WHERE event_object_table = '상품' AND trigger_name = '상품_수정일_갱신';
        """)
        rows = cur.fetchall()

if not rows:
    print("[FAIL] 트리거 생성 확인 실패")
    sys.exit(1)

print("\n[OK] 상품_수정일_갱신 트리거 생성 완료")
for name, ev, timing in rows:
    print(f"  - {name}: {timing} {ev}")
