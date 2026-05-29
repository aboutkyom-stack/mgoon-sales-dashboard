# -*- coding: utf-8 -*-
"""워크플로 토글 + 변경 감지 마이그레이션.

상품 테이블에 3단계 × (at·snapshot) = 6개 컬럼 추가:
- 기초입력_완료_at           TIMESTAMPTZ  — 동료가 기초자료 입력 끝났음 토글 ON 시각
- 기초입력_완료_snapshot     JSONB        — 토글 ON 시점의 기초입력 핵심 필드 박제
- 엠군_완료_at               TIMESTAMPTZ  — 엠군 결과 넘기기 적합 상태 토글 ON 시각
- 엠군_완료_snapshot         JSONB        — 토글 ON 시점의 엠군 결과(runs) 박제
- 상세페이지_완료_at         TIMESTAMPTZ  — 동료가 상세페이지 생성 끝났음 토글 ON 시각
- 상세페이지_완료_snapshot   JSONB        — 향후 채널 단계 작업자용 (지금은 빈 {})

기존 데이터: 모두 NULL → 자동으로 ⬛ 일반 박스에 배치 (옵션 C).
동료가 진행 완료한 제품은 UI에서 수동 토글로 ON.

운영 DB 1회 실행 후 영구 폐기.
- 1순위: MY_SUPABASE_POOLER_URL / MY_SUPABASE_DB_URL (psycopg2 직접 연결)
- 2순위: SUPABASE_ACCESS_TOKEN (Supabase Management API)
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

STATEMENTS = [
    "ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 기초입력_완료_at TIMESTAMPTZ",
    "ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 기초입력_완료_snapshot JSONB",
    "ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 엠군_완료_at TIMESTAMPTZ",
    "ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 엠군_완료_snapshot JSONB",
    "ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 상세페이지_완료_at TIMESTAMPTZ",
    "ALTER TABLE 상품 ADD COLUMN IF NOT EXISTS 상세페이지_완료_snapshot JSONB",
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
    print("✅ 워크플로 토글 + 변경 감지 컬럼 6개 추가 완료")
    print("    (기존 row는 모두 NULL → 자동으로 ⬛ 일반 박스에 배치)")


if __name__ == "__main__":
    main()
