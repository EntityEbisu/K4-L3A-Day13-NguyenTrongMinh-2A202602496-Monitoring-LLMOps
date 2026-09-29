from __future__ import annotations

import json

import yaml

from app import observability

REPO_ROOT = observability.REPO_ROOT
CONTRACT = yaml.safe_load(
    (REPO_ROOT / "config" / "dashboard.yaml").read_text(encoding="utf-8")
)
PANEL_IDS = [p["id"] for p in CONTRACT["dashboard"]["panels"]]


def _records(tmp_path, monkeypatch):
    log_path = tmp_path / "logs.jsonl"
    lines = []
    for index in range(20):
        base = {
            "ts": f"2026-09-29T14:{30 + index % 30:02d}:00.000000Z",
            "level": "info",
            "service": "api",
            "correlation_id": f"req-{index:08x}",
            "env": "dev",
            "user_id_hash": "u_9dc02223",
            "session_id": "s01",
            "feature": "qa",
            "model": "claude-sonnet-4-5",
        }
        lines.append({**base, "event": "request_received"})
        lines.append(
            {
                **base,
                "event": "response_sent",
                "latency_ms": 100 + index * 10,
                "ttft_ms": 50,
                "tokens_in": 100,
                "tokens_out": 150,
                "cost_usd": 0.0015,
                "quality_score": 0.9,
                "tool_name": "retrieval",
                "tool_success": index % 10 != 0,
            }
        )
    lines.append(
        {
            "ts": "2026-09-29T14:35:00.000000Z",
            "level": "error",
            "service": "api",
            "correlation_id": "req-0000ffff",
            "env": "dev",
            "user_id_hash": "u_9dc02223",
            "session_id": "s02",
            "feature": "qa",
            "model": "claude-sonnet-4-5",
            "event": "request_failed",
            "error_type": "RuntimeError",
            "tool_name": "retrieval",
            "tool_success": False,
        }
    )
    log_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in lines) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(observability, "LOG_PATH", log_path)
    return log_path


def test_load_records_returns_every_line(monkeypatch, tmp_path):
    _records(tmp_path, monkeypatch)
    assert len(observability.load_records()) == 41


def test_percentiles_reuse_the_shared_metric_helper(monkeypatch, tmp_path):
    from app.metrics import percentile

    _records(tmp_path, monkeypatch)
    records = observability.load_records()
    stats = observability.compute_stats(records)
    sent = [r for r in records if r.get("event") == "response_sent"]
    assert stats["latency_p50"] == percentile([r["latency_ms"] for r in sent], 50)
    assert stats["latency_p95"] == percentile([r["latency_ms"] for r in sent], 95)
    assert stats["latency_p99"] == percentile([r["latency_ms"] for r in sent], 99)
    assert stats["ttft_p95"] == percentile([r["ttft_ms"] for r in sent], 95)


def test_stats_cover_every_contract_panel(monkeypatch, tmp_path):
    _records(tmp_path, monkeypatch)
    stats = observability.compute_stats(observability.load_records())
    for key in (
        "latency_p50",
        "latency_p95",
        "latency_p99",
        "ttft_p95",
        "traffic",
        "error_rate_pct",
        "retrieval_success_pct",
        "cost_total",
        "tokens_in",
        "tokens_out",
        "quality_mean",
    ):
        assert key in stats, f"thiếu số liệu cho panel: {key}"


def test_panel_specs_cover_every_contract_panel(monkeypatch, tmp_path):
    _records(tmp_path, monkeypatch)
    specs = observability.panel_specs()
    assert {spec["id"] for spec in specs} == set(PANEL_IDS)
    for spec in specs:
        for key in ("title", "unit", "series", "threshold", "aggregation"):
            assert spec.get(key) not in (None, "", []), f"{spec['id']} thiếu {key}"


def test_threshold_line_is_respected_by_every_panel(monkeypatch, tmp_path):
    _records(tmp_path, monkeypatch)
    by_id = {p["id"]: p for p in CONTRACT["dashboard"]["panels"]}
    for spec in observability.panel_specs():
        declared = by_id[spec["id"]]["threshold"]
        assert spec["threshold"] == declared["value"]
        assert spec["aggregation"] == declared["aggregation"]
        assert declared["aggregation"] in by_id[spec["id"]]["aggregations"]


def test_dashboard_metadata_matches_the_contract(monkeypatch, tmp_path):
    _records(tmp_path, monkeypatch)
    meta = observability.dashboard_meta()
    assert meta["time_range_minutes"] == 60
    assert 15 <= meta["refresh_seconds"] <= 30


def test_error_rate_and_retrieval_success_use_the_right_denominator(monkeypatch, tmp_path):
    _records(tmp_path, monkeypatch)
    records = observability.load_records()
    stats = observability.compute_stats(records)
    received = [r for r in records if r.get("event") == "request_received"]
    failed = [r for r in records if r.get("event") == "request_failed"]
    tool_rows = [r for r in records if r.get("tool_success") is not None]
    assert stats["error_rate_pct"] == round(len(failed) / len(received) * 100, 2)
    assert stats["retrieval_success_pct"] == round(
        sum(1 for r in tool_rows if r["tool_success"]) / len(tool_rows) * 100, 2
    )


def test_empty_log_file_yields_zeroed_stats_not_a_crash(monkeypatch, tmp_path):
    log_path = tmp_path / "logs.jsonl"
    log_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(observability, "LOG_PATH", log_path)
    assert observability.load_records() == []
    stats = observability.compute_stats([])
    assert stats["latency_p95"] == 0
    assert stats["error_rate_pct"] == 0


def test_corrupt_lines_are_skipped_not_fatal(monkeypatch, tmp_path):
    log_path = tmp_path / "logs.jsonl"
    log_path.write_text('{"event": "request_received"}\nnot json\n\n', encoding="utf-8")
    monkeypatch.setattr(observability, "LOG_PATH", log_path)
    assert len(observability.load_records()) == 1
