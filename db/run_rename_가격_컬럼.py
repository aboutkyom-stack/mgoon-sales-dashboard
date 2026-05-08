# -*- coding: utf-8 -*-
"""가격 컬럼 정정 + 온라인판매가격 신설 마이그레이션.

- 실제가     → 실제받는가격
- 평균도매가 → 평균입고가
- 온라인판매가격 INTEGER 신설

운영 DB(상품 테이블) 1회 실행 후 영구 폐기.
- 1순위: MY_SUPABASE_DB_URL (psycopg2 직접 연결)
- 2순위: SUPABASE_ACCESS_TOKEN (Supabase Management API)
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

STATEMENTS = [
    'ALTER TABLE 상품 RENAME COLUMN 실제가 TO 실제받는가격',
    'ALTER TABLE 상품 RENAME COLUMN 평균도매가 TO 평균입고가',
    'ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 온라인판매가격 INTEGER',
]


def run_via_psycopg(db_url: str) -> None:
    import psycopg2

    print("PostgreSQL 직접 연결 중...")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()
    for i, sql in enumerate(STATEMENTS, 1):
        print(f"  [{i}/{len(STATEMENTS)}] {sql}")
        try:
            cur.execute(sql)
            print(f"         ✅ 완료 (rowcount={cur.rowcount})")
        except Exception as e:
            # RENAME COLUMN은 이미 적용된 경우 실패 — 안내 후 다음 진행
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
        print(f"  [{i}/{len(STATEMENTS)}] {sql}")
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
    print("✅ 가격 컬럼 정정 + 온라인판매가격 신설 마이그레이션 완료")


if __name__ == "__main__":
    main()
