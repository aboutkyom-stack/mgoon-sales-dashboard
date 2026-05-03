# -*- coding: utf-8 -*-
"""Supabase 테이블 초기화 스크립트. 한 번만 실행하면 됩니다.

사전 준비:
  .env에 SUPABASE_ACCESS_TOKEN 추가
  → https://supabase.com/dashboard/account/tokens
  → "Generate new token" 클릭 → 이름 입력 → 복사

실행:
  python db/init_supabase.py
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

import requests
from dotenv import load_dotenv

load_dotenv()

PROJECT_REF = "eikuzgymjzyjauzeghfg"

DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS mgoon_runs (
        id                BIGSERIAL PRIMARY KEY,
        source_db         TEXT NOT NULL DEFAULT 'supabase_v2',
        source_product_id BIGINT,
        product_name      TEXT NOT NULL,
        product_snapshot  TEXT NOT NULL,
        created_at        TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mgoon_targets (
        id               BIGSERIAL PRIMARY KEY,
        run_id           BIGINT NOT NULL REFERENCES mgoon_runs(id) ON DELETE CASCADE,
        rank             INTEGER,
        character        TEXT,
        deficit          TEXT,
        deficit_source   TEXT,
        purchase_benefit TEXT,
        involvement      INTEGER,
        channel          TEXT,
        note             TEXT,
        desire_layer3    TEXT,
        raw_output       TEXT,
        model            TEXT NOT NULL,
        selected         BOOLEAN DEFAULT FALSE,
        created_at       TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mgoon_positioning (
        id              BIGSERIAL PRIMARY KEY,
        target_id       BIGINT NOT NULL REFERENCES mgoon_targets(id) ON DELETE CASCADE,
        cv_analysis     TEXT,
        positioning_map TEXT,
        two_down_two_up TEXT,
        opening_copy    TEXT,
        value_additions TEXT,
        product_essence TEXT,
        raw_output      TEXT,
        model           TEXT NOT NULL,
        created_at      TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_targets_run ON mgoon_targets(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_positioning_target ON mgoon_positioning(target_id)",
    'ALTER TABLE "상품_파일" ADD COLUMN IF NOT EXISTS 계정 TEXT',
]


def run_sql(token: str, sql: str) -> dict:
    resp = requests.post(
        f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"query": sql.strip()},
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"API 오류 {resp.status_code}: {resp.text}")
    return resp.json()


def main():
    token = os.getenv("SUPABASE_ACCESS_TOKEN", "").strip()
    if not token:
        print()
        print("[오류] .env에 SUPABASE_ACCESS_TOKEN이 없습니다.")
        print()
        print("발급 방법:")
        print("  1. https://supabase.com/dashboard/account/tokens 접속")
        print("  2. 'Generate new token' 클릭")
        print("  3. 이름 입력 후 토큰 복사")
        print("  4. .env에 추가:")
        print("     SUPABASE_ACCESS_TOKEN=sbp_xxxxxxxxxxxx")
        sys.exit(1)

    print(f"Supabase Management API 연결 중... (project: {PROJECT_REF})")
    print()

    for i, sql in enumerate(DDL_STATEMENTS, 1):
        label = sql.strip().split("\n")[0].strip()[:60]
        print(f"  [{i}/{len(DDL_STATEMENTS)}] {label}...")
        try:
            run_sql(token, sql)
            print(f"         ✅ 완료")
        except RuntimeError as e:
            print(f"         ❌ 실패: {e}")
            sys.exit(1)

    print()
    print("✅ 초기화 완료!")
    print("   · mgoon_runs / mgoon_targets / mgoon_positioning 생성")
    print("   · 상품_파일.계정 컬럼 추가")
    print()
    print("이제 앱을 정상적으로 사용할 수 있습니다.")


if __name__ == "__main__":
    main()
