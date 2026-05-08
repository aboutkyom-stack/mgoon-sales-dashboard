# -*- coding: utf-8 -*-
"""제품특징 영역 재구성 마이그레이션.

- 제품특징_bullet JSONB DEFAULT '[]' 신설 (비전패스 + 판매자 수정, 01~05 참고)
- 제품특징_추가   TEXT 신설            (판매자 수동, 01~05 참고)
- 기존 '특징' 텍스트 → 줄바꿈 split → 제품특징_bullet에 JSONB 배열로 이관
- 기존 '특징' 컬럼은 일정 기간 유지 후 별도 마이그레이션으로 제거.

운영 DB 1회 실행 후 영구 폐기.
- 1순위: MY_SUPABASE_DB_URL (psycopg2 직접 연결)
- 2순위: SUPABASE_ACCESS_TOKEN (Supabase Management API)
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

STATEMENTS = [
    "ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 제품특징_bullet JSONB DEFAULT '[]'::jsonb",
    "ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 제품특징_추가 TEXT",
    """UPDATE 상품
       SET 제품특징_bullet = COALESCE((
           SELECT jsonb_agg(trim(line))
           FROM unnest(string_to_array(특징, E'\n')) AS line
           WHERE trim(line) <> ''
       ), '[]'::jsonb)
       WHERE 특징 IS NOT NULL
         AND trim(특징) <> ''
         AND (제품특징_bullet IS NULL OR 제품특징_bullet = '[]'::jsonb)""",
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
    print("✅ 제품특징 영역 재구성 완료")


if __name__ == "__main__":
    main()
