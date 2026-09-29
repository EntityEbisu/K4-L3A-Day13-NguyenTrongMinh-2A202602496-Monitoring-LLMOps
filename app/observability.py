from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from .metrics import percentile

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"
CONFIG_PATH = REPO_ROOT / "config" / "dashboard.yaml"


def load_records(path: Path | None = None) -> list[dict[str, Any]]:
    """Đọc toàn bộ data/logs.jsonl, bỏ qua dòng hỏng thay vì crash."""
    source = Path(path) if path else LOG_PATH
    if not source.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def within_time_range(records: list[dict[str, Any]], minutes: int) -> list[dict[str, Any]]:
    """Giữ record nằm trong cửa sổ phút gần nhất; timestamp hỏng thì giữ lại."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    kept = []
    for record in records:
        stamp = _parse_ts(record.get("ts", ""))
        if stamp is None or stamp >= cutoff:
            kept.append(record)
    return kept


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def compute_stats(records: list[dict[str, Any]]) -> dict[str, float]:
    """Tính số liệu cho cả 6 panel trong contract/dashboard.yaml."""
    sent = [r for r in records if r.get("event") == "response_sent"]
    received = [r for r in records if r.get("event") == "request_received"]
    failed = [r for r in records if r.get("event") == "request_failed"]

    latencies = [r["latency_ms"] for r in sent if isinstance(r.get("latency_ms"), int)]
    ttfts = [r["ttft_ms"] for r in sent if isinstance(r.get("ttft_ms"), int)]
    tool_rows = [r for r in records if r.get("tool_success") is not None]

    return {
        "latency_p50": percentile(latencies, 50) if latencies else 0.0,
        "latency_p95": percentile(latencies, 95) if latencies else 0.0,
        "latency_p99": percentile(latencies, 99) if latencies else 0.0,
        "ttft_p95": percentile(ttfts, 95) if ttfts else 0.0,
        "traffic": len(received),
        "error_rate_pct": round(len(failed) / len(received) * 100, 2) if received else 0.0,
        "retrieval_success_pct": (
            round(sum(1 for r in tool_rows if r["tool_success"]) / len(tool_rows) * 100, 2)
            if tool_rows
            else 0.0
        ),
        "cost_total": round(sum(r.get("cost_usd", 0.0) for r in sent), 6),
        "tokens_in": sum(r.get("tokens_in", 0) for r in sent),
        "tokens_out": sum(r.get("tokens_out", 0) for r in sent),
        "quality_mean": _mean([r.get("quality_score", 0.0) for r in sent]),
    }


def load_dashboard_contract() -> dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["dashboard"]


def dashboard_meta() -> dict[str, Any]:
    contract = load_dashboard_contract()
    return {
        "title": contract["title"],
        "time_range_minutes": contract["time_range_minutes"],
        "refresh_seconds": contract["refresh_seconds"],
    }


PANEL_SERIES: dict[str, tuple[tuple[str, str], ...]] = {
    "latency": (
        ("latency_p50", "P50"),
        ("latency_p95", "P95"),
        ("latency_p99", "P99"),
        ("ttft_p95", "TTFT P95"),
    ),
    "traffic": (("traffic", "requests"),),
    "errors": (
        ("error_rate_pct", "error rate %"),
        ("retrieval_success_pct", "retrieval success %"),
    ),
    "cost": (("cost_total", "total cost"),),
    "tokens": (("tokens_in", "tokens in"), ("tokens_out", "tokens out")),
    "quality": (("quality_mean", "quality mean"),),
}


def panel_specs() -> list[dict[str, Any]]:
    """Trả về đúng 6 panel theo contract, kèm số liệu và threshold tương ứng."""
    contract = load_dashboard_contract()
    stats = compute_stats(within_time_range(load_records(), contract["time_range_minutes"]))
    specs = []
    for panel in contract["panels"]:
        series = PANEL_SERIES.get(panel["id"], ())
        specs.append(
            {
                "id": panel["id"],
                "title": panel["title"],
                "unit": panel["unit"],
                "query": panel["query"],
                "series": [
                    {"key": key, "label": label, "value": stats.get(key, 0.0)}
                    for key, label in series
                ],
                "aggregation": panel["threshold"]["aggregation"],
                "operator": panel["threshold"]["operator"],
                "threshold": panel["threshold"]["value"],
            }
        )
    return specs
