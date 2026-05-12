"""기존 파이프라인 실행 이력을 보고 상품.엠군상태를 일괄 업데이트.

완료 기준: 상품_id의 가장 최근 run에서 has_채널 == True (01/02/04/04_1/05 완료)
진행중 기준: run이 하나라도 있으면

실행 방법:
    cd "C:\\Users\\kyum\\Desktop\\자동화 공장\\자동화 판매"
    python db/backfill_엠군상태.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from pipeline.storage import get_storage
from pipeline.supabase_read import _client, update_엠군상태


def main() -> None:
    storage = get_storage()

    # 전체 실행 이력에서 상품_id별 최신 run_id 수집
    res = _client().table("엠군_실행").select("id, 상품_id").order("id", desc=True).execute()
    runs = res.data or []

    latest_run: dict[int, int] = {}  # {상품_id: run_id}
    for run in runs:
        pid = run.get("상품_id")
        if pid and pid not in latest_run:
            latest_run[pid] = run["id"]

    if not latest_run:
        print("엠군_실행 이력 없음. 종료.")
        return

    print(f"실행 이력 있는 상품: {len(latest_run)}개\n")

    done: list[int] = []
    progress: list[int] = []

    for pid, run_id in latest_run.items():
        summary = storage.get_run_summary(run_id)
        if summary.get("has_채널"):
            done.append(pid)
        else:
            progress.append(pid)

    print(f"완료 대상: {len(done)}개")
    print(f"진행중 대상: {len(progress)}개\n")

    for pid in done:
        update_엠군상태(pid, "완료")
        print(f"  [완료] 상품 #{pid}")

    for pid in progress:
        update_엠군상태(pid, "진행중")
        print(f"  [진행중] 상품 #{pid}")

    print(f"\n완료! 총 {len(done) + len(progress)}개 상품 업데이트.")


if __name__ == "__main__":
    main()
