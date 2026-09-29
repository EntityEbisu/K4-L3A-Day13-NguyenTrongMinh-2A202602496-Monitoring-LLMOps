from __future__ import annotations

import asyncio
import json
import re

import httpx

from app import logging_config
from app.main import app

REQUEST_ID_RE = re.compile(r"^req-[0-9a-f]{8}$")


def _post(message: str, headers: dict | None = None):
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/chat",
                json={
                    "user_id": "student-01",
                    "session_id": "session-01",
                    "feature": "qa",
                    "message": message,
                },
                headers=headers or {},
            )

    return asyncio.run(run())


def _records(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_generated_correlation_id_is_returned_in_header(monkeypatch, tmp_path):
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")

    response = _post("Explain observability")

    assert response.status_code == 200
    assert REQUEST_ID_RE.match(response.headers["x-request-id"])
    assert float(response.headers["x-response-time-ms"]) >= 0


def test_incoming_x_request_id_is_propagated(monkeypatch, tmp_path):
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")

    response = _post("Explain observability", headers={"x-request-id": "req-abcd1234"})

    assert response.headers["x-request-id"] == "req-abcd1234"


def test_malformed_incoming_id_is_replaced(monkeypatch, tmp_path):
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")

    response = _post("Explain observability", headers={"x-request-id": "not-a-valid-id"})

    assert REQUEST_ID_RE.match(response.headers["x-request-id"])


def test_context_does_not_leak_between_requests(monkeypatch, tmp_path):
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    first = _post("First question about latency")
    second = _post("Second question about latency")

    assert first.headers["x-request-id"] != second.headers["x-request-id"]
    api_ids = {r["correlation_id"] for r in _records(log_path) if r.get("service") == "api"}
    assert first.headers["x-request-id"] in api_ids
    assert second.headers["x-request-id"] in api_ids


def test_every_api_record_carries_the_same_correlation_id(monkeypatch, tmp_path):
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    response = _post("Explain traces and spans")

    api_records = [r for r in _records(log_path) if r.get("service") == "api"]
    assert len(api_records) >= 2
    assert {r["correlation_id"] for r in api_records} == {response.headers["x-request-id"]}
