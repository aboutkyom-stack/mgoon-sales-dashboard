# -*- coding: utf-8 -*-
"""박스(패키지) 치수/소재/색상 + 수입자 + 사용연령 컬럼 추가 마이그레이션.

운영 DB 1회 실행 후 영구 폐기.
- 1순위: MY_SUPABASE_POOLER_URL 또는 MY_SUPABASE_DB_URL (psycopg2 직접 연결)
- 2순위: SUPABASE_ACCESS_TOKEN (Supabase Management API)
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

STATEMENTS = [
    "ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 수입자       TEXT",
    "ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 사용연령     TEXT",
    "ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 박스_가로_cm NUMERIC",
    "ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 박스_세로_cm NUMERIC",
    "ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 박스_높이_cm NUMERIC",
    "ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 박스_무게_g  NUMERIC",
    "ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 박스_재질    TEXT",
    "ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 박스_색상    TEXT",
]


def run_via_psycopg(db_url: str) -> None:
    import psycopg2

    print("PostgreSQL 직접 연결 중...")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()
    for i, sql in enumerate(STATEMENTS, 1):
        head = sql.strip().split("\n")[0]
        print(f"  [{i}/{len(STATEMENTS)}] {head}")
        try:
            cur.execute(sql)
            print(f"         ✅ 완료 (rowcount={cur.rowcount})")
        except Exception as e:
            print(f"         ⚠️  {e}")
            conn.rollback()
            conn.autocommit = True
    cur.close()
    conn.close()


def run_via_management_api(token: str) -> None:
    import requests

    PROJECT_REF = "eikuzgymjzyjauzeghfg"
    print(f"Supabase Management API 사용... (project: {PROJECT_REF})")
    for i, sql in enumerate(STATEMENTS, 1):
        head = sql.strip().split("\n")[0]
        print(f"  [{i}/{len(STATEMENTS)}] {head}")
        resp = requests.post(
            f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"query": sql.strip()},
            timeout=30,
        )
        if resp.status_code >= 400:
            print(f"         ⚠️  API 오류 {resp.status_code}: {resp.text}")
        else:
            print(f"         ✅ 완료")


def main():
    db_url = (
        os.getenv("MY_SUPABASE_POOLER_URL", "").strip()
        or os.getenv("MY_SUPABASE_DB_URL", "").strip()
    )
    token = os.getenv("SUPABASE_ACCESS_TOKEN", "").strip()

    if db_url:
        run_via_psycopg(db_url)
    elif token:
        run_via_management_api(token)
    else:
        print("[오류] .env에 MY_SUPABASE_DB_URL 또는 SUPABASE_ACCESS_TOKEN 필요.")
        sys.exit(1)

    print()
    print("✅ 박스 + 수입자 + 사용연령 컬럼 추가 완료")


if __name__ == "__main__":
    main()
