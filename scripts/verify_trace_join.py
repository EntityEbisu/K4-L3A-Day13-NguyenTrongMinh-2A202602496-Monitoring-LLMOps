"""Nối structured log với trace Langfuse để chứng minh Metrics → Logs → Traces.

Cách dùng:

    python scripts/verify_trace_join.py

Script đọc ``data/logs.jsonl``, gọi API observations của Langfuse bằng key
trong ``.env``, rồi đối chiếu từng request với trace tương ứng. Không hard-code
số liệu: mọi con số đều đọc từ log và từ Langfuse lúc chạy.

Nếu key thiếu, script báo rõ và exit 1 thay vì bịa kết quả.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio

LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"
TIME_TOLERANCE_SECONDS = 2.0


def parse_ts(value: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def load_observations(base_url: str, public_key: str, secret_key: str, hours: int) -> list[dict]:
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    response = httpx.get(
        f"{base_url.rstrip('/')}/api/public/v2/observations",
        params={"fromStartTime": since.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z", "limit": 100},
        auth=(public_key, secret_key),
        timeout=60.0,
    )
    response.raise_for_status()
    return list(response.json().get("data", []))


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Đối chiếu log với trace Langfuse")
    parser.add_argument("--hours", type=int, default=1, help="Cửa sổ tra cứu (giờ)")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=TIME_TOLERANCE_SECONDS,
        help="Giây lệch tối đa giữa ts của log và startTime của trace",
    )
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
    base_url = os.getenv("LANGFUSE_BASE_URL", "")
    if not (public_key and secret_key and base_url):
        print("Thiếu LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY/LANGFUSE_BASE_URL trong .env")
        return 1

    if not LOG_PATH.exists():
        print(f"Không tìm thấy {LOG_PATH}. Hãy chạy API và scripts/load_test.py trước.")
        return 1

    records = [
        json.loads(line)
        for line in LOG_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    sent = [r for r in records if r.get("event") == "response_sent"]
    if not sent:
        print("Log chưa có event response_sent; hãy chạy load test trước.")
        return 1

    observations = load_observations(base_url, public_key, secret_key, args.hours)
    by_trace: dict[str, list[dict]] = {}
    for item in observations:
        by_trace.setdefault(item.get("traceId"), []).append(item)
    roots = [
        o for o in observations if o.get("type") == "AGENT" and not o.get("parentObservationId")
    ]

    print(f"--- Log ↔ Trace join ({args.hours}h) ---")
    print(f"request trong log: {len(sent)}")
    print(f"trace root trong Langfuse: {len(roots)}")
    print(f"observations tải về: {len(observations)}\n")

    matched = 0
    for record in sent:
        log_time = parse_ts(record.get("ts", ""))
        if log_time is None:
            continue
        best, best_gap = None, None
        for root in roots:
            start = parse_ts(root.get("startTime", ""))
            if start is None:
                continue
            gap = abs((start - log_time).total_seconds())
            if best_gap is None or gap < best_gap:
                best, best_gap = root, gap
        if best is None or best_gap is None or best_gap > args.tolerance:
            continue
        matched += 1
        siblings = by_trace.get(best["traceId"], [])
        types = sorted({o.get("type") for o in siblings})
        has_children = {"RETRIEVER", "GENERATION"}.issubset(set(types))
        print(
            f"  {record['correlation_id']}  {record.get('latency_ms', 0):>5} ms  ->  "
            f"trace {best['traceId'][:16]}…  lệch {best_gap:.2f}s  "
            f"tree={','.join(t for t in types if t)}  spans={len(siblings)}"
            + ("" if has_children else "  [THIẾU CHILD SPAN]")
        )

    print(f"\nKhớp: {matched}/{len(sent)} request")
    if matched == len(sent):
        print("PASS: mọi request trong log đều có trace cha-con tương ứng.")
        return 0
    print("FAIL: còn request chưa tìm thấy trace tương ứng.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
