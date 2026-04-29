# -*- coding: utf-8 -*-
"""
Supabase 데이터 마이그레이션 스크립트
- 소스: 동료 DB (COLLEAGUE_*) — 읽기 전용
- 대상: 내 DB (MY_*) — service_role로 INSERT/UPDATE
- 전제: 상품, 상품_파일 테이블은 SQL Editor에서 이미 생성 완료
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

src = create_client(
    os.getenv("COLLEAGUE_SUPABASE_URL").strip(),
    os.getenv("COLLEAGUE_SUPABASE_KEY").strip(),
)
dst = create_client(
    os.getenv("MY_SUPABASE_URL").strip(),
    os.getenv("MY_SUPABASE_SERVICE_KEY").strip(),
)

CHUNK = 1000


def fetch_all(client, table: str) -> list:
    """Supabase 1,000행 제한을 우회해 전체 데이터 페이지네이션 조회"""
    rows, start = [], 0
    while True:
        batch = client.table(table).select("*").range(start, start + CHUNK - 1).execute().data
        rows.extend(batch)
        if len(batch) < CHUNK:
            break
        start += CHUNK
    return rows


# ── 1단계: 동료 DB 데이터 읽기 ───────────────────────────

print("\n[1단계] 동료 DB 읽기")

catalog_rows = fetch_all(src, "product_catalog")
print(f"  product_catalog: {len(catalog_rows)}개")

v2_rows = fetch_all(src, "products_v2")
print(f"  products_v2: {len(v2_rows)}개")

file_rows = fetch_all(src, "drive_files")
print(f"  drive_files: {len(file_rows)}개")

# ── 2단계: 기존 상품 데이터 초기화 ──────────────────────
# 재실행 시 중복 방지

print("\n[2단계] 기존 데이터 초기화 (재실행 안전)")
existing = dst.table("상품").select("id", count="exact").execute()
if existing.count and existing.count > 0:
    dst.table("상품_파일").delete().neq("id", 0).execute()
    dst.table("상품").delete().neq("id", 0).execute()
    print(f"  기존 {existing.count}개 삭제 완료")
else:
    print("  기존 데이터 없음, 스킵")

# ── 3단계: 상품 INSERT ────────────────────────────────────

print("\n[3단계] 상품 INSERT")

sangpum_rows = [
    {
        "구_카탈로그_id": r["id"],
        "제품명":        r["name"],
        "소매가":        r.get("price_retail"),
        "도매가":        r.get("price_wholesale"),
        "실제가":        r.get("price_actual"),
        "평균도매가":    r.get("price_avg_wholesale"),
        "실시간재고":    r.get("stock_realtime") or 0,
        "처리후재고":    r.get("stock_afterprocess") or 0,
    }
    for r in catalog_rows
]

for i in range(0, len(sangpum_rows), CHUNK):
    dst.table("상품").insert(sangpum_rows[i:i+CHUNK]).execute()
    print(f"  {min(i+CHUNK, len(sangpum_rows))}/{len(sangpum_rows)}개 삽입 중...")

print(f"  완료: {len(sangpum_rows)}개")

# ── 4단계: products_v2 스펙 UPDATE ───────────────────────
# PostgreSQL unquoted 식별자는 소문자로 저장됨
# KC인증 → kc인증, KC인증번호 → kc인증번호

print("\n[4단계] products_v2 스펙 UPDATE")

all_sangpum = fetch_all(dst, "상품")
catalog_to_my_id = {r["구_카탈로그_id"]: r["id"] for r in all_sangpum}

for v in v2_rows:
    my_id = catalog_to_my_id.get(v.get("catalog_id"))
    if not my_id:
        print(f"  [경고] products_v2 id={v['id']} catalog_id={v.get('catalog_id')} 매칭 없음, 스킵")
        continue

    dst.table("상품").update({
        "구_v2_id":         v["id"],
        "카테고리":         v.get("category"),
        "서브카테고리":     v.get("subcategory"),
        "모델명":           v.get("spec_model"),
        "제조사":           v.get("spec_manufacturer"),
        "원산지":           v.get("spec_origin") or "중국",
        "재고수량":         v.get("stock_qty") or 0,
        "재입고예정":       bool(v.get("restock_yn")),
        "단종여부":         bool(v.get("discontinued_yn")),
        "가로_cm":          v.get("spec_width_cm"),
        "세로_cm":          v.get("spec_depth_cm"),
        "높이_cm":          v.get("spec_height_cm"),
        "무게_g":           v.get("spec_weight_g"),
        "재질":             v.get("spec_material"),
        "색상":             v.get("spec_color"),
        "구성품":           v.get("spec_components"),
        "kc인증":           bool(v.get("cert_kc_yn")),       # PostgreSQL 소문자 저장
        "kc인증번호":       v.get("cert_kc_number"),          # PostgreSQL 소문자 저장
        "기타인증":         v.get("cert_other"),
        "온라인판매가능":   v.get("online_sale_yn") if v.get("online_sale_yn") is not None else True,
        "판매채널":         v.get("sale_channel"),
        "박스재사용":       bool(v.get("box_reuse_yn")),
        "특징":             v.get("features"),
        "키워드":           v.get("keywords"),
        "치수정보":         str(v["dimensions"]) if v.get("dimensions") else None,
        "판매자메모":       v.get("seller_notes"),
        "주의사항":         v.get("cautions"),
        "검수완료":         bool(v.get("inspection_yn")),
        "검수메모":         v.get("inspection_note"),
        "드라이브_폴더_id": v.get("drive_folder_id"),
    }).eq("id", my_id).execute()

print(f"  완료: {len(v2_rows)}개")

# ── 5단계: 상품_파일 INSERT ───────────────────────────────

print("\n[5단계] 상품_파일 INSERT")

v2_id_to_catalog = {v["id"]: v.get("catalog_id") for v in v2_rows}

file_rows_to_insert = []
for f in file_rows:
    cat_id = v2_id_to_catalog.get(f.get("product_id"))
    my_id  = catalog_to_my_id.get(cat_id)
    if not my_id:
        print(f"  [경고] drive_files id={f['id']} 매칭 없음, 스킵")
        continue
    file_rows_to_insert.append({
        "상품_id":           my_id,
        "파일명":            f.get("file_name"),
        "파일_유형":         f.get("file_type"),
        "드라이브_파일_id":  f.get("drive_file_id"),
        "드라이브_url":      f.get("drive_url"),
        "상태":              f.get("status") or "uploaded",
        "업로드일":          f.get("uploaded_at"),
    })

for i in range(0, len(file_rows_to_insert), CHUNK):
    dst.table("상품_파일").insert(file_rows_to_insert[i:i+CHUNK]).execute()

print(f"  완료: {len(file_rows_to_insert)}개")

# ── 6단계: 검증 ───────────────────────────────────────────

print("\n[6단계] 검증")

cnt_s  = dst.table("상품").select("id", count="exact").execute().count
cnt_f  = dst.table("상품_파일").select("id", count="exact").execute().count
cnt_v2 = dst.table("상품").select("id", count="exact").neq("구_v2_id", None).execute().count

print(f"  상품 행수:       {cnt_s}  (기대: {len(catalog_rows)})")
print(f"  상품_파일 행수:  {cnt_f}  (기대: {len(file_rows_to_insert)})")
print(f"  v2 스펙 매칭:    {cnt_v2}  (기대: {len(v2_rows)})")
print("\n마이그레이션 완료")
