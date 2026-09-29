"""Phân tích incident CP3 từ data/logs.jsonl: metric -> log -> span.

Cách dùng:

    python scripts/analyze_incident.py

Chỉ đọc log, không sửa gì. Tách riêng cửa sổ trước sự cố và cửa sổ sự cố để
metric tăng không bị tính lẫn vào baseline.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.metrics import percentile

LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"
CHALLENGE = REPO_ROOT / "config" / "challenge.json"


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load() -> list[dict]:
    return [
        json.loads(line)
        for line in LOG_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def summarize(rows: list[dict], label: str) -> None:
    sent = [r for r in rows if r.get("event") == "response_sent"]
    if not sent:
        print(f"{label}: không có response_sent")
        return
    lat = [r["latency_ms"] for r in sent]
    ttft = [r["ttft_ms"] for r in sent if isinstance(r.get("ttft_ms"), int)]
    print(f"\n--- {label} ---")
    print(f"  số request      : {len(sent)}")
    print(f"  latency P50/P95 : {percentile(lat,50):.0f} / {percentile(lat,95):.0f} ms")
    print(f"  latency max     : {max(lat)} ms")
    print(f"  TTFT P95        : {percentile(ttft,95):.0f} ms")
    print(f"  khoảng thời gian: {sent[0]['ts']}  ->  {sent[-1]['ts']}")


def main() -> int:
    if not LOG_PATH.exists():
        print("Chưa có data/logs.jsonl; chạy load test trước.")
        return 1

    threshold = 0
    challenge_id = "(không đọc được challenge.json)"
    if CHALLENGE.exists():
        payload = json.loads(CHALLENGE.read_text(encoding="utf-8"))
        challenge_id = payload.get("challenge_id", challenge_id)
        threshold = int(payload.get("latency_threshold_ms", 0))

    rows = load()
    sent = [r for r in rows if r.get("event") == "response_sent"]
    slow = [r for r in sent if r.get("latency_ms", 0) > threshold]
    fast = [r for r in sent if r.get("latency_ms", 0) <= threshold]

    print("=" * 70)
    print(f"PHÂN TÍCH INCIDENT — challenge: {challenge_id}")
    print(f"Ngưỡng latency trong challenge: {threshold} ms")
    print("=" * 70)

    summarize(fast, "TRƯỚC sự cố (latency <= ngưỡng)")
    summarize(slow, "TRONG sự cố (latency > ngưỡng)")

    if not slow:
        print("\nKhông có request nào vượt ngưỡng.")
        return 0

    print("\n--- Nhận định dựa trên TTFT ---")
    fast_ttft = [r["ttft_ms"] for r in fast if isinstance(r.get("ttft_ms"), int)]
    slow_ttft = [r["ttft_ms"] for r in slow if isinstance(r.get("ttft_ms"), int)]
    if fast_ttft and slow_ttft:
        print(f"  TTFT P95 trước sự cố : {percentile(fast_ttft,95):.0f} ms")
        print(f"  TTFT P95 trong sự cố : {percentile(slow_ttft,95):.0f} ms")
        delta = percentile(slow_ttft, 95) - percentile(fast_ttft, 95)
        print(
            "  => TTFT gần như không đổi; độ trễ tăng KHÔNG nằm ở bước sinh câu "
            "trả lời."
            if abs(delta) < 100
            else "  => TTFT tăng rõ; cần xem cả bước sinh câu trả lời."
        )

    print("\n--- Request bất thường, chậm nhất trước (dùng để tra trace) ---")
    for r in sorted(slow, key=lambda x: -x["latency_ms"])[:5]:
        print(
            f"  {r['ts']}  {r['correlation_id']}  "
            f"latency={r['latency_ms']}ms  ttft={r['ttft_ms']}ms  "
            f"feature={r.get('feature')}"
        )

    print(
        "\nBước tiếp theo: dùng correlation_id ở trên để mở trace cùng ID trên "
        "Langfuse và so sánh span `retrieval` với `llm-generation`."
    )
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
