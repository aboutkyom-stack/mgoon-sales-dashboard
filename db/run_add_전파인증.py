# -*- coding: utf-8 -*-
"""전파인증 컬럼 추가 마이그레이션.

상품 테이블에 전파인증(BOOLEAN), 전파인증번호(TEXT) 컬럼을 추가한다.
멱등(IF NOT EXISTS) — 재실행 안전.

실행:
  python db/run_add_전파인증.py
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = (os.getenv("MY_SUPABASE_POOLER_URL", "").strip()
          or os.getenv("MY_SUPABASE_DB_URL", "").strip())
if not DB_URL:
    print("[ERROR] .env에 MY_SUPABASE_POOLER_URL 또는 MY_SUPABASE_DB_URL 필요")
    sys.exit(1)

DDL_STATEMENTS = [
    'ALTER TABLE "상품" ADD COLUMN IF NOT EXISTS 전파인증 BOOLEAN DEFAULT FALSE',
    'ALTER TABLE "상품" ADD COLUMN IF NOT EXISTS 전파인증번호 TEXT',
]

print("실행: 상품 테이블에 전파인증 컬럼 추가")
with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
        for sql in DDL_STATEMENTS:
            print(f"  {sql[:70]}...")
            cur.execute(sql)
    conn.commit()

# 검증
with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = '상품'
              AND column_name IN ('전파인증', '전파인증번호')
            ORDER BY ordinal_position;
        """)
        rows = cur.fetchall()

if not rows:
    print("[FAIL] 컬럼 생성 확인 실패")
    sys.exit(1)

print("\n✅ 완료")
for col, dtype in rows:
    print(f"  - {col}: {dtype}")
