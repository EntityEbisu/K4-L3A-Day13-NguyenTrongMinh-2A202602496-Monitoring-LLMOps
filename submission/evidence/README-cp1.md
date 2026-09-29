> Bằng chứng được thu bằng tay từ output thật của ứng dụng. Ảnh chụp màn hình bổ sung sẽ
> đặt cùng thư mục này (xem `../../docs/SUBMISSION.md` §5).

## 00 — Baseline (trước khi sửa code)

| Bằng chứng | File | Kết quả |
|---|---|---|
| Log validator baseline | `02-log-validator-baseline.txt` | **30/100** — thiếu required field, thiếu correlation ID, thiếu enrichment |
| Pytest baseline | `01-pytest-baseline.txt` | 22 passed |
| Log thô baseline | `00-baseline-logs-raw.jsonl` | 21 dòng, 0 correlation ID, đã kiểm tra không chứa PII |

## 01–03 — Validator cuối (CP1)

| Bằng chứng | File | Kết quả |
|---|---|---|
| Log validator | `02-log-validator.txt` | **100/100** — 0 missing, 10 correlation ID, 0 PII leak |
| Dashboard validator | `03-dashboard-validator.txt` | `HỢP LỆ: 6/6 panel` (đạt sẵn từ baseline, contract không sửa) |

## 04 — Structured log thật

Lấy từ `data/logs.jsonl` sau `scripts/load_test.py --concurrency 5`:

```json
{
    "service": "api",
    "payload": {"message_preview": "Can I get help with policy and monitoring?"},
    "event": "request_received",
    "correlation_id": "req-0a2c4b6f",
    "session_id": "s04",
    "env": "dev",
    "feature": "qa",
    "model": "claude-sonnet-4-5",
    "user_id_hash": "u_75af0789",
    "level": "info",
    "ts": "2026-09-29T08:05:40.880940Z"
}
```

Dòng `response_sent` cùng request mang `latency_ms`, `ttft_ms`, `tokens_in`, `tokens_out`,
`cost_usd`, `quality_score`, `tool_name`, `tool_success` và **cùng** `correlation_id`.

## 05 — PII redaction thật

Đếm marker trong `data/logs.jsonl` sau workload:

```text
REDACTED_CREDIT_CARD  1
REDACTED_EMAIL        1
REDACTED_PHONE_VN     1
```

Nguồn PII giả nằm trong `data/sample_queries.jsonl` (`u01` email, `u05` điện thoại,
`u09` số thẻ). Không có chuỗi thô nào tồn tại trong file log — đã kiểm bằng chính
detector của `scripts/validate_logs.py`.
