from __future__ import annotations

import asyncio
import json

import httpx

from app import logging_config
from app.main import app
from app.pii import PII_PATTERNS, scrub_text
from scripts.validate_logs import PII_DETECTORS

SAMPLES = {
    "email": "student@vinuni.edu.vn",
    "phone_vn": "0901234567",
    "cccd": "001203012345",
    "credit_card": "4111 1111 1111 1111",
    "cccd_spaced": "001 203 012 345",
    "passport_vn": "C1234567",
}


def test_new_patterns_exist():
    for name in ("cccd_spaced", "passport_vn"):
        assert name in PII_PATTERNS, f"thiếu pattern {name}"


def test_scrub_text_redacts_every_sample():
    for name, raw in SAMPLES.items():
        out = scrub_text(raw)
        assert raw not in out, f"{name}: chưa che {raw!r}"
        assert "[REDACTED_" in out


def test_scrub_is_idempotent():
    for raw in SAMPLES.values():
        once = scrub_text(raw)
        assert scrub_text(once) == once


def test_scrub_does_not_corrupt_identifiers():
    for value in ("req-12345678", "u_9dc02223", "2026-09-29T14:31:00.000000Z", "claude-sonnet-4-5"):
        assert scrub_text(value) == value, f"scrub làm hỏng {value}"


def test_scrub_never_leaves_a_detectable_pii_string():
    for raw in SAMPLES.values():
        out = scrub_text(raw)
        for name, detector in PII_DETECTORS.items():
            assert not detector.search(out), f"{raw!r} -> {out!r} còn khớp {name}"


def test_pii_never_reaches_the_log_file(monkeypatch, tmp_path):
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)
    message = (
        "Liên hệ 0901234567, email a@vinuni.edu.vn, CCCD 001203012345, "
        "thẻ 4111 1111 1111 1111"
    )

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/chat",
                json={"user_id": "u01", "session_id": "s01", "feature": "qa", "message": message},
            )

    response = asyncio.run(run())
    assert response.status_code == 200

    blob = log_path.read_text(encoding="utf-8")
    for literal in ("0901234567", "a@vinuni.edu.vn", "001203012345", "4111 1111 1111 1111"):
        assert literal not in blob, f"PII {literal} vẫn còn trong log file"
    for name, detector in PII_DETECTORS.items():
        assert not detector.search(blob), f"log file còn khớp detector {name}"


def test_pii_in_error_detail_is_also_scrubbed(monkeypatch, tmp_path):
    """Processor cũ chỉ quét payload cấp 1 nên detail/error_type lọt PII."""
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/chat",
                json={
                    "user_id": "u01",
                    "session_id": "s01",
                    "feature": "qa",
                    "message": "Refund cho email a@vinuni.edu.vn",
                },
            )

    asyncio.run(run())
    blob = log_path.read_text(encoding="utf-8")
    for record in (json.loads(line) for line in blob.splitlines() if line.strip()):
        for value in record.values():
            if isinstance(value, str):
                for name, detector in PII_DETECTORS.items():
                    assert not detector.search(value), f"{record['event']}.{name}"
