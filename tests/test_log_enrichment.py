from __future__ import annotations

import asyncio
import json
import os
import re

import httpx

from app import logging_config
from app.main import app

REQUIRED = {"correlation_id", "user_id_hash", "session_id", "feature", "model", "env"}


def _chat(message: str = "Why is tail latency important?"):
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/chat",
                json={
                    "user_id": "u01",
                    "session_id": "s01",
                    "feature": "qa",
                    "message": message,
                },
            )

    return asyncio.run(run())


def _api_records(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("service") == "api"
    ]


def test_request_received_and_response_sent_are_enriched(monkeypatch, tmp_path):
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    _chat()

    events = {r["event"]: r for r in _api_records(log_path)}
    for name in ("request_received", "response_sent"):
        assert REQUIRED.issubset(events[name]), f"{name} thiếu {REQUIRED - set(events[name])}"


def test_user_id_hash_is_stable_and_not_the_raw_user_id(monkeypatch, tmp_path):
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    _chat()

    record = next(r for r in _api_records(log_path) if r["event"] == "request_received")
    assert record["user_id_hash"] != "u01"
    assert re.match(r"^u_[0-9a-f]{8}$", record["user_id_hash"])


def test_enrichment_values_match_the_request(monkeypatch, tmp_path):
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    _chat()

    record = next(r for r in _api_records(log_path) if r["event"] == "request_received")
    assert record["session_id"] == "s01"
    assert record["feature"] == "qa"
    assert record["env"] == os.getenv("APP_ENV", "dev")
    assert record["model"]


def test_hash_never_looks_like_pii():
    """Regression: hash 12 chữ số ngẫu nhiên có thể all-digit và bị detector CCCD gắn cờ.

    Detector ``\\b\\d{12}\\b`` của validate_logs.py sẽ khớp một hash 12 chữ số và
    trừ 30 điểm PII dù ta không hề ghi PII. Tiền tố 'u_' + 8 hex giữ chuỗi số
    ngắn nhất <= 8, thấp hơn ngưỡng 10 của phone_vn.
    """
    from app.pii import hash_user_id
    from scripts.validate_logs import PII_DETECTORS

    for index in range(5000):
        candidate = hash_user_id(f"u{index}")
        blob = json.dumps({"user_id_hash": candidate}, ensure_ascii=False)
        for name, detector in PII_DETECTORS.items():
            assert not detector.search(blob), f"hash {candidate} khớp detector {name}"
