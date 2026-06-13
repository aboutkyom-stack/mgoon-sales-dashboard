# -*- coding: utf-8 -*-
"""app_settings 테이블 마이그레이션 + 현재 settings.json 시드.

MY_SUPABASE_POOLER_URL / MY_SUPABASE_DB_URL(.env)로 psycopg2 직접 실행.
멱등:
  - 테이블 생성은 IF NOT EXISTS
  - 시드는 INSERT ... ON CONFLICT (id) DO NOTHING
    → 재실행해도 이미 있는 DB 설정을 덮어쓰지 않음 (최초 1회만 시드)
"""
from __future__ import annotations

import json
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

HERE = Path(__file__).parent
SQL_FILE = HERE / "add_app_settings.sql"
SETTINGS_FILE = HERE.parent / "settings.json"

sql = SQL_FILE.read_text(encoding="utf-8")

print(f"실행: {SQL_FILE.name}")
with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
        # 1. 테이블 생성 (멱등)
        cur.execute(sql)

        # 2. 현재 settings.json을 id=1 행으로 시드 (이미 있으면 보존)
        seeded = False
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            cur.execute(
                "INSERT INTO app_settings (id, data) VALUES (1, %s::jsonb) "
                "ON CONFLICT (id) DO NOTHING",
                (json.dumps(data, ensure_ascii=False),),
            )
            seeded = cur.rowcount > 0
        else:
            print(f"  [경고] {SETTINGS_FILE.name} 없음 — 빈 설정으로 시작")
    conn.commit()

# 검증
with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT id, jsonb_object_keys(data) FROM app_settings WHERE id = 1;")
        keys = [r[1] for r in cur.fetchall()]

print("\n[OK] app_settings 테이블 준비 완료")
print(f"  - 시드 여부: {'신규 시드함' if seeded else '기존 행 유지(시드 생략)'}")
print(f"  - 저장된 설정 키 개수: {len(keys)}")
if keys:
    print(f"  - 키 일부: {', '.join(sorted(keys)[:8])} ...")
