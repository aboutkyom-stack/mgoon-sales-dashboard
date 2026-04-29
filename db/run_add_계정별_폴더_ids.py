# -*- coding: utf-8 -*-
"""상품.계정별_폴더_ids 컬럼 마이그레이션 실행기.

MY_SUPABASE_POOLER_URL(.env)을 사용해 psycopg2로 DDL 직접 실행.
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

# Pooler 우선 (IPv4), 직접 연결 fallback
DB_URL = (os.getenv("MY_SUPABASE_POOLER_URL", "").strip()
          or os.getenv("MY_SUPABASE_DB_URL", "").strip())
if not DB_URL:
    print("[ERROR] .env에 MY_SUPABASE_POOLER_URL 또는 MY_SUPABASE_DB_URL 필요")
    sys.exit(1)

SQL_FILE = Path(__file__).parent / "add_계정별_폴더_ids.sql"
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
            SELECT column_name, data_type, column_default
            FROM information_schema.columns
            WHERE table_name = '상품' AND column_name = '계정별_폴더_ids';
        """)
        row = cur.fetchone()

        # 마이그레이션된 데이터 샘플 확인
        cur.execute("""
            SELECT COUNT(*) AS 전체,
                   COUNT(*) FILTER (WHERE 계정별_폴더_ids != '{}'::jsonb) AS 마이그_완료
            FROM 상품;
        """)
        stats = cur.fetchone()

        cur.execute("""
            SELECT id, 제품명, 드라이브_폴더_id, 계정별_폴더_ids
            FROM 상품
            WHERE 계정별_폴더_ids != '{}'::jsonb
            ORDER BY id
            LIMIT 5;
        """)
        samples = cur.fetchall()

if not row:
    print("[FAIL] 컬럼 생성 확인 실패")
    sys.exit(1)

print(f"\n[OK] 상품.계정별_폴더_ids 컬럼 추가 완료")
print(f"  - column: {row[0]} ({row[1]}, default={row[2]})")
print(f"  - 전체 상품: {stats[0]}개, 마이그레이션 완료: {stats[1]}개")
if samples:
    print(f"\n  샘플 (최대 5개):")
    for sid, name, old_fid, new_ids in samples:
        print(f"    #{sid} {name[:30] if name else '?'}")
        print(f"        old: {old_fid}")
        print(f"        new: {new_ids}")
