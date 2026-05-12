# -*- coding: utf-8 -*-
"""상품.구_카탈로그_id / 구_v2_id 컬럼 제거 마이그레이션 실행기.

이관 작업이 1회 끝났고 어떤 페이지·동료 프로그램에서도 읽지 않음.
멱등(DROP COLUMN IF EXISTS) — 재실행 안전.
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

SQL_FILE = Path(__file__).parent / "drop_구_id_컬럼.sql"
sql = SQL_FILE.read_text(encoding="utf-8")

print(f"실행: {SQL_FILE.name}")
with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()

# 검증 — 두 컬럼이 모두 사라졌는지 확인
DROPPED = {"구_카탈로그_id", "구_v2_id"}
with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = '상품'
              AND column_name = ANY(%s);
        """, (list(DROPPED),))
        remaining = {row[0] for row in cur.fetchall()}

print()
if remaining:
    print(f"[FAIL] 아직 존재하는 컬럼: {remaining}")
    sys.exit(1)

print("[OK] 컬럼 제거 완료")
for col in sorted(DROPPED):
    print(f"  - 상품.{col} 제거됨")

sys.exit(0)
