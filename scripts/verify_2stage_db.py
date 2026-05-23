# -*- coding: utf-8 -*-
"""2단계 DB 검증 — Gemini 실제 출력 있는 이전 행 찾기"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from supabase import create_client

url = os.environ["MY_SUPABASE_URL"]
key = os.environ["MY_SUPABASE_SERVICE_KEY"]
sb = create_client(url, key)

ok = lambda v: "[OK]" if v else "[NG]"

# 1. 포지셔닝 전체 Gemini 행 — 원본_출력 있는 것만 찾기
print("=== 엠군_포지셔닝 Gemini 행 (전체, 원본_출력 길이 확인) ===")
res = sb.table("엠군_포지셔닝").select("id, 타겟_id, 모델, 원본_출력").eq("모델", "gemini").order("id", desc=True).limit(20).execute()
for row in res.data:
    out = row['원본_출력'] or ""
    has_json = "---POSITIONING_JSON---" in out
    print(f"id={row['id']} target={row['타겟_id']}  len={len(out)}  has_POSITIONING_JSON={has_json}")

print()
print("=== 엠군_포지셔닝 Claude 행 (최근 5, 신규 컬럼 확인) ===")
res = sb.table("엠군_포지셔닝").select("id, 타겟_id, 모델, category_objections, rule_engine_inputs").eq("모델", "claude").order("id", desc=True).limit(5).execute()
for row in res.data:
    print(f"id={row['id']} target={row['타겟_id']}  category_obj={ok(row['category_objections'])}  re_inputs={ok(row['rule_engine_inputs'])}")

print()
print("=== 엠군_상세페이지 Gemini 행 (전체, 원본_출력 길이 확인) ===")
res = sb.table("엠군_상세페이지").select("id, 타겟_id, 모델, 원본_출력").eq("모델", "gemini").order("id", desc=True).limit(20).execute()
for row in res.data:
    out = row['원본_출력'] or ""
    fence = "```"
    has_yaml = (fence + "yaml") in out
    print(f"id={row['id']} target={row['타겟_id']}  len={len(out)}  has_yaml={has_yaml}")

print()
print("=== 결론 ===")
print("Gemini 행이 len=0이면 해당 실행에서 Gemini 모델 비활성화(gemini_model=None)였음")
print("Claude 행이 모두 [OK]이면 2단계 코드 정상 — Gemini 활성화 시 동작 별도 검증 필요")
