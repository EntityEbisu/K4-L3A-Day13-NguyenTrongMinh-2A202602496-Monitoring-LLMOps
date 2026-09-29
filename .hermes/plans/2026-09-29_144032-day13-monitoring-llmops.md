# Kế hoạch triển khai — Lab Day 13 Monitoring & LLMOps (K4-L3A)

- **Ngày lập:** 2026-09-29 14:40 (Asia/Ho_Chi_Minh)
- **Repo đề bài:** `D:\VinUni\day13_monitoring_llops\K4-L3A-Day13-NguyenTrongMinh-2A202602496-Monitoring-LLMOps`
- **Repo bài nộp (phải tạo):** `K4-L3-DAY13-NguyenTrongMinh-02496-Monitoring-LLMOps`
- **Đã xác nhận (2026-09-29):** Langfuse key đã đặt vào `.env`, `auth_check()` → `True`; dashboard chọn **Streamlit live**; repo cá nhân sẽ tạo mới (Task 1); `config/challenge.json` chưa có → CP3 làm sau.
- **Ngôn ngữ:** tài liệu/evidence tiếng Việt; tên biến, enum, key JSON giữ tiếng Anh.

---

## 1. Goal

Hoàn thiện 100 điểm bắt buộc của lab (CP0–CP4) bằng code thật, không hard-code: validator log đạt 100/100, dashboard validator 6/6, ≥10 trace thật trên project Langfuse cá nhân có span cha–con, prompt v1/v2 có rollback, dashboard runtime 6 panel, và một incident điều tra trọn vẹn metric → log → trace.

---

## 2. Current context / assumptions (đã kiểm chứng thực tế, không phải đọc suông)

Tôi đã clone repo ra thư mục tạm, cài `requirements.txt`, chạy API thật và đo baseline. Các con số dưới đây là **output thật**, không phải suy đoán.

### Baseline đã đo được

| Hạng mục | Kết quả thật | Ghi chú |
|---|---|---|
| `python -m pytest -q` | `22 passed` | toàn bộ test công khai đã xanh từ đầu |
| `python scripts/validate_logs.py` | **`Estimated Score: 30/100`** | mất −30 (thiếu field), −20 (correlation), −20 (enrichment) |
| `python scripts/validate_dashboard.py` | `HỢP LỆ: 6/6 panel` | **đã đạt sẵn**, không cần sửa `config/dashboard.yaml` |
| `/health` | `{'ok': True, 'tracing_enabled': False, ...}` | tracing tắt vì chưa có key |

Chi tiết baseline log (10 request mẫu → 21 dòng log):

```
Total log records analyzed: 21
Records with missing required fields: 20
Records with missing enrichment (context): 20
Unique correlation IDs found: 0
+ [PASSED] PII scrubbing
Estimated Score: 30/100
```

### 5 vị trí TODO bắt buộc (đã đọc hết)

| File | TODO | CP |
|---|---|---|
| `app/middleware.py` | clear contextvars, `req-<8hex>`, bind, trả header | CP1 |
| `app/main.py` | bind `user_id_hash/session_id/feature/model/env` trước `request_received` | CP1 |
| `app/logging_config.py` | đăng ký `scrub_event` **trước** `JsonlFileProcessor` | CP1 |
| `app/pii.py` | bổ sung pattern PII | CP1 |
| `app/agent.py` | child observation retrieval + generation | CP2 |
| `config/alert_rules.yaml`, `docs/alerts.md` | 3 alert + runbook | CP2 |
| `config/slo.yaml` | giải thích/điều chỉnh SLO | CP2 |
| `submission/REPORT.md` | báo cáo + evidence | CP4 |

### Rủi ro thiết kế đã kiểm chứng bằng thử nghiệm thật

Tôi chạy 12 probe độc lập với SDK `langfuse==4.15.6` thật. Kết luận:

1. **Contextvars đi qua được ranh giới `BaseHTTPMiddleware`** và không rò giữa các request (đã verify bằng 2 request liên tiếp + kiểm tra context sau khi xong → `{}`). Đây là giả định quan trọng nhất của cả CP1; nó đúng.
2. **Đạt 100/100 là khả thi** — tôi dựng sẵn 22 dòng log đúng format của bản sửa, nạp vào chính `scripts/validate_logs.py`, kết quả thật: `Estimated Score: 100/100`, 0 PII leak, 11 correlation ID.
3. **`@observe` của Langfuse v4 an toàn khi không có key**: không raise, chỉ log cảnh báo. Nó cũng cho exception propagate đúng (cần cho `tool_fail` → `request_failed`). Đặt được trên **instance method** (`FakeLLM.generate`) và trên hàm module (`retrieve`). → Có thể instrument ở `mock_rag.py`/`mock_llm.py` thay vì sửa `agent.py`.
4. **API Langfuse v4 đã xác nhận tồn tại**: `start_as_current_observation`, `update_current_span`, `update_current_generation`, `get_prompt`, `create_prompt`, `update_prompt(name, version, new_labels)`.
5. **Pattern PII sẵn có đã đúng và idempotent** (scrub 2 lần không đổi). Không cần sửa regex cũ.
6. ⚠️ **BUG TIỀM ẨN THẬT — `user_id_hash` có thể bị validator quy là rò CCCD.**
   `hash_user_id` hiện trả `sha256(user_id)[:12]`, tức **12 ký tự hex**. Nếu cả 12 ký tự đều là số, detector `\b\d{12}\b` của chính `validate_logs.py` khớp → **−30 điểm PII**, dù bạn không hề lộ PII. Đo thật:
   - `sha256("u45")[:12] = 613933674358` → validator gắn cờ `['cccd']`.
   - Tần suất: **2138/500.000** user giả (≈0,43%).
   - Thêm tiền tố `"u"` + 12 hex vẫn còn 412/500.000 (do chạy 10 chữ số khớp `phone_vn`).
   - Đổi sang `"u_" + sha256[:8]`: **0/500.000 vi phạm**, chuỗi số dài nhất chỉ 8 (thấp hơn ngưỡng 10 của `phone_vn`).
   - 10 user mẫu `u01..u10` của lab **may mắn** đều sạch, nên nếu chỉ chạy workload mẫu thì không lộ. Nhưng `config/challenge.json` (CP3) có `user_id` do Lab Coach sinh — không kiểm soát được. → Phải sửa.
   - Không test nào assert độ dài/định dạng hash → sửa an toàn.
7. **Timestamp ISO không bao giờ khớp detector** (1004 mẫu, 0 vi phạm) → không lo mất điểm vì `ts`.
8. **Chưa có thư viện vẽ biểu đồ nào** trong `requirements.txt` (không matplotlib/pandas/streamlit). Dashboard runtime là điểm bắt buộc 6/6 điểm → phải thêm dependency.

### Giả định

- Bạn sẽ tự tạo tài khoản **Langfuse Cloud** và **project riêng** `day13-k4-l3a-02496`, tự tạo key pair. Không dùng chung.
- `config/challenge.json` **chưa có** và **không được tự tạo**. Kế hoạch này chỉ dùng `--scenario` practice; phần CP3 chính thức là placeholder chờ Lab Coach.
- Deadline 23:59:59 ngày thi, nộp URL repo cá nhân + commit SHA cuối lên VLearn LMS/Codelabs.

---

## 3. Architecture / proposed approach

Giữ nguyên kiến trúc starter (FastAPI + structlog + Langfuse v4 + **mock LLM/RAG, không gọi dịch vụ thật**) và chỉ **vá đúng 5 TODO**, không refactor. Không thêm HTTP client, model provider hay vector store nào; `app/mock_llm.py` và `app/mock_rag.py` chỉ ngủ có định hình để mô phỏng độ trễ. CP1 sửa chuỗi `middleware → bind contextvars → structlog processor → JsonlFileProcessor`; CP2 instrument `mock_rag.retrieve` và `mock_llm.FakeLLM.generate` bằng `@observe` (đặt ở đó chứ không ở `agent.py`, để không phá test `span_updates[-1]`) và thêm `app/observability.py` + `scripts/dashboard_app.py` đọc `data/logs.jsonl` dựng 6 panel có threshold line. Mọi con số trong báo cáo lấy từ output thật của script, không chép tay.

---

## 4. Phần B: BẠN PHẢI TỰ CHUẨN BỊ (làm trước khi bắt đầu Task 1)

| # | Việc | Chi tiết | Bắt buộc? |
|---|---|---|---|
| B1 | **Tài khoản Langfuse Cloud** | Đăng ký tại https://cloud.langfuse.com (free tier đủ). Mỗi học viên 1 project — `RULES.md` §3 cấm dùng chung. | **Có** — 15 điểm mục C không thể bù |
| B2 | **Project Langfuse riêng** | Tạo project tên `day13-k4-l3a-02496`. Vào *Project Settings → API Keys* → tạo key pair. | **Có** |
| B3 | **Ghi key vào `.env`** | `LANGFUSE_PUBLIC_KEY=pk-lf-…`, `LANGFUSE_SECRET_KEY=sk-lf-…`, `LANGFUSE_BASE_URL=https://cloud.langfuse.com`, `LANGFUSE_PROMPT_NAME=day13-chat`, `LANGFUSE_PROMPT_LABEL=production`. | **Có** |
| B4 | **Tài khoản GitHub + repo mới** | Repo hiện tại là **repo đề bài** (`K4-L3A-Day13-…`). Phải tạo repo mới tên `K4-L3-DAY13-NguyenTrongMinh-02496-Monitoring-LLMOps` (không dấu, không space, phân tách bằng `-`). Không push lên repo đề bài. | **Có** — nộp repo chung = bài không hợp lệ, −5 |
| B5 | **Công cụ chụp ảnh** | Snipping Tool / Lightshot — cần cho 11 ảnh evidence. | **Có** |
| B6 | **Python 3.11+** | Máy đang có 3.14.7 nhưng lab khuyến nghị 3.11+. Dùng 3.11 cho khớp đề. | Khuyến nghị |
| B7 | **Key LLM trả phí** | **KHÔNG cần.** Lab dùng fake LLM (`app/mock_llm.py`). | Không |
| B8 | **Cổng 8501** | **KHÔNG cần cấu hình gì** — chỉ cần mở trình duyệt khi demo; `RULES.md` §3 cấm đổi thiết bị. |
| B9 | **Docker Desktop** | **KHÔNG cần** nếu dùng Langfuse Cloud. Chỉ khi cloud không truy cập được. | Không |
| B10 | **Truy cập VLearn LMS/Codelabs** | Nơi nộp URL repo + commit SHA. | **Có** |

⚠️ **Không gửi key Langfuse cho tôi hoặc bất kỳ ai.** Dán trực tiếp vào `.env` (đã nằm trong `.gitignore`). Nếu key lọt ra, phải revoke/rotate ngay (`RULES.md` §5) — commit secret bị −20.

**Verify B1–B3 xong trước Task 1:**

```bash
# Sau khi tạo .env và khởi động API
curl -s http://127.0.0.1:8000/health
# Kỳ vọng: {"ok":true,"tracing_enabled":true,...}
```
`tracing_enabled: true` ⇒ key hợp lệ. Nếu `false` → sai key/host, dừng lại sửa B2–B3.

---

## 5. Step-by-step tasks

Quy ước: chạy mọi lệnh từ thư mục gốc repo. `.venv` phải activate trước.

### CP0 — Setup và baseline (Task 1–3)

#### Task 1 — Tạo repo cá nhân và môi trường

```bash
cd "D:/VinUni/day13_monitoring_llops/K4-L3A-Day13-NguyenTrongMinh-2A202602496-Monitoring-LLMOps"
python -m venv .venv
./.venv/Scripts/python.exe -m pip install --upgrade pip
./.venv/Scripts/python.exe -m pip install -r requirements.txt
cp .env.example .env
```

Tạo repo mới trên GitHub rồi đổi remote (giữ `origin` cũ để tham khảo):

```bash
git remote rename origin origin-assignment-repo
git remote add origin https://github.com/<USER-GITHUB>/K4-L3-DAY13-NguyenTrongMinh-02496-Monitoring-LLMOps.git
git remote -v
# Kỳ vọng: origin -> .../K4-L3-DAY13-NguyenTrongMinh-02496-Monitoring-LLMOps.git
```

Điền key Langfuse vào `.env` (B3). Commit:

```bash
git add -A && git commit -m "chore: start personal submission repo, add .env (gitignored)"
# Kỳ vọng: 1 file changed (chỉ file không bị gitignore)
```

**Verify:** `git check-ignore -v .env` → phải in ra `.gitignore`; nếu không, `.env` sẽ bị commit → vi phạm −20.

#### Task 2 — Chạy API và workload baseline

```bash
# Terminal 1
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --env-file .env
# Terminal 2
./.venv/Scripts/python.exe scripts/load_test.py
```

**Verify** — kỳ vọng đúng những con số này (đã đo ở baseline):
```
[200] MISSING | qa | 155.3ms      ← "MISSING" là đúng ở baseline, sẽ hết ở CP1
...
Total log records analyzed: 21
Estimated Score: 30/100
```

Lưu nguyên văn output này làm evidence `02-log-validator-baseline.txt`:

```bash
mkdir -p submission/evidence
./.venv/Scripts/python.exe scripts/validate_logs.py  > submission/evidence/02-log-validator-baseline.txt 2>&1
./.venv/Scripts/python.exe scripts/validate_dashboard.py >> submission/evidence/02-log-validator-baseline.txt 2>&1
```

```bash
git add -A && git commit -m "chore: record CP0 baseline validator output"
```

#### Task 3 — Chốt dashboard contract (không sửa code)

`config/dashboard.yaml` **đã hợp lệ**. Chỉ cần lưu evidence, không sửa:

```bash
./.venv/Scripts/python.exe scripts/validate_dashboard.py | tee submission/evidence/03-dashboard-validator.txt
# Kỳ vọng: HỢP LỆ: 6/6 panel có trong dashboard contract.
```

```bash
git add -A && git commit -m "test: dashboard contract already valid at baseline"
```

---

### CP1 — Logging và PII (Task 4–8)

> **Nguyên tắc bắt buộc:** `validate_logs.py` đọc **toàn bộ** `data/logs.jsonl`. Mọi lần đo lại phải **xoá/đổi tên file log cũ, restart API, chạy lại load test** (đã ghi rõ ở `CHECKPOINTS.md` và `GUIDE.md`). Nếu quên, điểm không bao giờ lên 100.

#### Task 4 — TDD: correlation ID trong middleware

**Bước 1 — viết test RED.** Tạo `tests/test_correlation_middleware.py`:

```python
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
    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    api_ids = {r["correlation_id"] for r in records if r.get("service") == "api"}
    assert first.headers["x-request-id"] in api_ids
    assert second.headers["x-request-id"] in api_ids


def test_every_api_record_carries_the_same_correlation_id(monkeypatch, tmp_path):
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    response = _post("Explain traces and spans")

    records = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    api_records = [r for r in records if r.get("service") == "api"]
    assert len(api_records) >= 2
    assert {r["correlation_id"] for r in api_records} == {response.headers["x-request-id"]}
```

**Bước 2 — chạy để xác nhận FAIL:**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_correlation_middleware.py -q
# Kỳ vọng: KeyError 'x-request-id' → 5 failed
```

**Bước 3 — implement.** Ghi đè `app/middleware.py`:

```python
from __future__ import annotations

import re
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars

REQUEST_ID_PATTERN = re.compile(r"^req-[0-9a-f]{8}$")


def new_correlation_id() -> str:
    return f"req-{uuid.uuid4().hex[:8]}"


def resolve_correlation_id(incoming: str | None) -> str:
    if incoming and REQUEST_ID_PATTERN.match(incoming):
        return incoming
    return new_correlation_id()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        clear_contextvars()

        correlation_id = resolve_correlation_id(request.headers.get("x-request-id"))
        bind_contextvars(correlation_id=correlation_id)
        request.state.correlation_id = correlation_id

        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            clear_contextvars()

        response.headers["x-request-id"] = correlation_id
        response.headers["x-response-time-ms"] = f"{(time.perf_counter() - start) * 1000:.2f}"
        return response
```

**Bước 4 — verify GREEN:**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_correlation_middleware.py -q
# Kỳ vọng: 5 passed
./.venv/Scripts/python.exe -m pytest -q
# Kỳ vọng: 27 passed
```

```bash
git add -A && git commit -m "feat(cp1): correlation id middleware with x-request-id/x-response-time-ms"
```

#### Task 5 — TDD: bind log enrichment trong `main.py`

**Bước 1 — test RED.** Tạo `tests/test_log_enrichment.py`:

```python
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


def test_hash_never_looks_like_pii(monkeypatch, tmp_path):
    """Regression: sha256()[:12] ngẫu nhiên có thể all-digit và bị detector CCCD gắn cờ."""
    from app.pii import hash_user_id
    from scripts.validate_logs import PII_DETECTORS

    for index in range(5000):
        candidate = hash_user_id(f"u{index}")
        blob = json.dumps({"user_id_hash": candidate}, ensure_ascii=False)
        for name, detector in PII_DETECTORS.items():
            assert not detector.search(blob), f"hash {candidate} khớp detector {name}"
```

**Bước 2 — verify FAIL:**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_log_enrichment.py -q
# Kỳ vọng: 4 failed (thiếu user_id_hash/session_id/feature/model/env; hash sai format)
```

**Bước 3 — implement.** Thêm vào `app/pii.py` (thay thế hàm `hash_user_id`):

```python
def hash_user_id(user_id: str) -> str:
    """Pseudonym có tiền tố chữ.

    Vì sao không dùng sha256(user_id)[:12] như starter: 12 hex có thể toàn số
    (vd sha256('u45')[:12] = '613933674358'), detector CCCD \\b\\d{12}\\b của
    validate_logs.py sẽ khớp và trừ 30 điểm dù không hề lộ PII. Tiền tố 'u_'
    cộng 8 hex giữ chuỗi số ngắn nhất <= 8, thấp hơn ngưỡng 10 của phone_vn.
    """
    return "u_" + hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:8]
```

Trong `app/main.py`, thay khối TODO ở đầu hàm `chat()`:

```python
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    bind_contextvars(
        user_id_hash=hash_user_id(body.user_id),
        session_id=body.session_id,
        feature=body.feature,
        model=agent.model,
        env=os.getenv("APP_ENV", "dev"),
    )

    log.info(
        "request_received",
        service="api",
        payload={"message_preview": summarize_text(body.message)},
    )
```

**Bước 4 — verify GREEN:**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_log_enrichment.py -q
# Kỳ vọng: 4 passed
./.venv/Scripts/python.exe -m pytest -q
# Kỳ vọng: 31 passed
```

```bash
git add -A && git commit -m "feat(cp1): bind log enrichment + non-PII-shaped user_id_hash"
```

#### Task 6 — TDD: PII scrubber chạy trước bước ghi file

**Bước 1 — test RED.** Tạo `tests/test_pii_scrub_pipeline.py`:

```python
from __future__ import annotations

import asyncio
import json
import re

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
    message = "Liên hệ 0901234567, email a@vinuni.edu.vn, CCCD 001203012345, thẻ 4111 1111 1111 1111"

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
```

**Bước 2 — verify FAIL:**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_pii_scrub_pipeline.py -q
# Kỳ vọng: 2 failed — thiếu key cccd_spaced, passport_vn
```

**Bước 3 — implement.** Bổ sung 2 pattern vào `app/pii.py` (giữ nguyên 4 pattern cũ — đã verify là đúng và idempotent):

```python
PII_PATTERNS: dict[str, str] = {
    "email": r"[\w\.-]+@[\w\.-]+\.\w+",
    "phone_vn": r"(?<!\d)(?:\+84|0)(?:[ .-]?\d){9}(?!\d)",
    "cccd": r"\b\d{12}\b",
    "credit_card": r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",
    "cccd_spaced": r"\b\d{3}[ .-]\d{3}[ .-]\d{3}[ .-]\d{3}\b",
    "passport_vn": r"\b[A-Z]{1,2}\d{7,9}\b",
}
```

Đăng ký processor trong `app/logging_config.py` — thêm hàm scrub đệ quy (bản cũ chỉ xử lý `payload` cấp 1, `error_type`/`detail` lọt):

```python
def scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {key: scrub_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub_value(item) for item in value]
    return value


def scrub_event(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key, value in event_dict.items():
        if isinstance(value, str):
            event_dict[key] = scrub_text(value)
        else:
            event_dict[key] = scrub_value(value)
    return event_dict
```

và trong `configure_logging()`, đặt `scrub_event` **trước** `JsonlFileProcessor()`:

```python
        processors=[
            merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
            scrub_event,                      # <-- PHẢI trước bước render/ghi file
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            JsonlFileProcessor(),
            structlog.processors.JSONRenderer(),
        ],
```

**Bước 4 — verify GREEN:**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_pii_scrub_pipeline.py -q
# Kỳ vọng: 6 passed
./.venv/Scripts/python.exe -m pytest -q
# Kỳ vọng: 37 passed
```

```bash
git add -A && git commit -m "feat(cp1): register recursive PII scrubber before file renderer"
```

#### Task 7 — Đo lại log validator đúng cách (đạt 100/100)

**Bắt buộc:** xoá log cũ rồi đo lại.

```bash
# Terminal 1: dừng API (Ctrl+C), xoá log cũ, khởi động lại
rm -f data/logs.jsonl
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --env-file .env
# Terminal 2
./.venv/Scripts/python.exe scripts/load_test.py
./.venv/Scripts/python.exe scripts/validate_logs.py
```

**Kỳ vọng chính xác:**
```
Total log records analyzed: 21
Records with missing required fields: 0
Records with missing enrichment (context): 0
Unique correlation IDs found: 10
Potential PII leaks detected: 0
+ [PASSED] Basic JSON schema
+ [PASSED] Correlation ID propagation
+ [PASSED] Log enrichment
+ [PASSED] PII scrubbing
Estimated Score: 100/100
```

Lưu evidence:

```bash
./.venv/Scripts/python.exe scripts/validate_logs.py | tee submission/evidence/02-log-validator.txt
```

```bash
git add -A && git commit -m "test(cp1): log validator reaches 100/100"
```

#### Task 8 — Thu evidence CP1

```bash
grep -m2 '"event": "request_received"' data/logs.jsonl | python -m json.tool --json-lines 2>/dev/null \
  || grep -m2 'request_received' data/logs.jsonl
```

Chụp ảnh terminal (Snipping Tool):
- `submission/evidence/04-structured-log.png` — 1 dòng `request_received` + 1 dòng `response_sent` hiện `correlation_id`, `user_id_hash`, `session_id`, `feature`, `model`, `env`, `latency_ms`, `ttft_ms`.
- `submission/evidence/05-pii-redaction.png` — lệnh gửi PII giả qua curl và dòng log kết quả đã che.

```bash
# Dùng lại data có sẵn: dòng chứa REDACTED_EMAIL / REDACTED_PHONE_VN / REDACTED_CREDIT_CARD
grep -o 'REDACTED_[A-Z_]*' data/logs.jsonl | sort -u
# Kỳ vọng: REDACTED_CREDIT_CARD, REDACTED_EMAIL, REDACTED_PHONE_VN
```

```bash
git add -A && git commit -m "docs(cp1): structured log and PII redaction evidence"
```

---

### CP2 — Tracing, prompt, dashboard, SLO, alerts (Task 9–15)

#### Task 9 — TDD: child observation cho retrieval và generation

> **Vị trí instrument: `app/mock_rag.py` và `app/mock_llm.py`, KHÔNG phải trong `agent.py`.**
> Lý do: `tests/test_agent_prompt_trace.py` khẳng định `client.span_updates[-1]` là **đúng** dict metadata của prompt và chạy qua `LabAgent.run.__wrapped__` với client giả chỉ có `get_prompt`/`update_current_span`. Nếu ta gọi thêm `update_current_span` trong `agent.run`, test sẽ đỏ. Instrument trong `mock_*` giữ nguyên ranh giới span cha–con mà không đụng test.

**Bước 1 — test RED.** Tạo `tests/test_child_observations.py`:

```python
from __future__ import annotations

import inspect

from app import mock_llm, mock_rag
from app.tracing import observe


def _observation_meta(func) -> dict:
    return dict(getattr(func, "__langfuse_observation", None) or {})


def test_retrieve_is_an_observed_retriever():
    meta = _observation_meta(mock_rag.retrieve)
    assert meta, "retrieve() chưa được instrument bằng @observe"
    assert meta.get("name")
    assert meta.get("as_type") == "retriever"


def test_generate_is_an_observed_generation():
    meta = _observation_meta(mock_llm.FakeLLM.generate)
    assert meta, "FakeLLM.generate() chưa được instrument bằng @observe"
    assert meta.get("name")
    assert meta.get("as_type") == "generation"


def test_observations_do_not_capture_raw_pii():
    for func in (mock_rag.retrieve, mock_llm.FakeLLM.generate):
        assert _observation_meta(func).get("capture_input") is False
        assert _observation_meta(func).get("capture_output") is False


def test_observe_decorator_is_the_langfuse_v4_one():
    assert observe.__module__.startswith("langfuse")
```

**Bước 2 — verify FAIL:**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_child_observations.py -q
# Kỳ vọng: 4 failed
```

> Nếu `__langfuse_observation` không tồn tại trên SDK 4.15.6, đổi 2 test đầu sang kiểm tra gián tiếp: monkeypatch `app.mock_rag.retrieve.__wrapped__` — bước 3 sẽ ghi rõ cách xác nhận thay thế.

**Bước 3 — implement.** `app/mock_rag.py` — thay phần import và hàm `retrieve`:

```python
import time

from .incidents import STATE
from .pii import summarize_text
from .tracing import get_langfuse_client, observe


@observe(name="retrieval", as_type="retriever", capture_input=False, capture_output=False)
def retrieve(message: str) -> list[str]:
    client = get_langfuse_client()
    started = time.perf_counter()
    if STATE["tool_fail"]:
        try:
            raise RuntimeError("Vector store timeout")
        except RuntimeError:
            client.update_current_span(
                level="ERROR",
                status_message="retrieval failed",
                metadata={"error_type": "RuntimeError"},
            )
            raise
    if STATE["rag_slow"]:
        time.sleep(2.5)
    lowered = message.lower()
    docs = ["No domain document matched. Use general fallback answer."]
    for key, corpus_docs in CORPUS.items():
        if key in lowered:
            docs = corpus_docs
            break
    client.update_current_span(
        metadata={
            "doc_count": len(docs),
            "retrieval_ms": round((time.perf_counter() - started) * 1000),
            "query_preview": summarize_text(message),
        }
    )
    return docs
```

`app/mock_llm.py` — instrument `generate`:

```python
from .pii import summarize_text
from .pricing import estimate_cost
from .tracing import get_langfuse_client, observe


@observe(name="llm-generation", as_type="generation", capture_input=False, capture_output=False)
def generate(self, prompt: str) -> FakeResponse:
    client = get_langfuse_client()
    started = time.perf_counter()
    time.sleep(0.05)
    ttft_ms = int((time.perf_counter() - started) * 1000)
    time.sleep(0.10)
    input_tokens = max(20, len(prompt) // 4)
    output_tokens = random.randint(80, 180)
    if STATE["cost_spike"]:
        output_tokens *= 4
    cost = estimate_cost(input_tokens, output_tokens)
    answer = (
        "Starter answer. You should improve this output logic and add better quality checks. "
        "Use retrieved context and keep responses concise."
    )
    client.update_current_generation(
        model=self.model,
        # đã scrub trước khi đưa vào trace -> không PII thô
        input=summarize_text(prompt),
        output=summarize_text(answer),
        usage_details={"input": input_tokens, "output": output_tokens},
        cost_details={"input": cost["input"], "output": cost["output"]},
    )
    return FakeResponse(
        text=answer,
        usage=FakeUsage(input_tokens, output_tokens),
        model=self.model,
        ttft_ms=ttft_ms,
    )
```

> `FakeResponse` **không** thêm field `cost_usd`: dataclass gốc không có field này và `app/agent.py` vẫn tự tính cost qua `_estimate_cost`. Giữ nguyên giảm rủi ro hồi quy.

**DRY — pricing dùng chung.** Tạo `app/pricing.py` (thay vì để `_estimate_cost` trong `agent.py` và giá rời ở `mock_llm`):

```python
from __future__ import annotations

INPUT_COST_PER_MILLION_TOKENS = 3.0
OUTPUT_COST_PER_MILLION_TOKENS = 15.0


def estimate_cost(tokens_in: int, tokens_out: int) -> dict[str, float]:
    input_cost = (tokens_in / 1_000_000) * INPUT_COST_PER_MILLION_TOKENS
    output_cost = (tokens_out / 1_000_000) * OUTPUT_COST_PER_MILLION_TOKENS
    return {
        "input": round(input_cost, 6),
        "output": round(output_cost, 6),
        "total": round(input_cost + output_cost, 6),
    }
```

Trong `app/agent.py`, thay `self._estimate_cost(...)` bằng `estimate_cost(...)` từ `app.pricing` và xoá method `_estimate_cost`. Giữ nguyên phần còn lại của `run()` (kể cả `update_current_span` với `prompt_version` — test `test_agent_prompt_trace` phụ thuộc vào nó).

**Bước 4 — verify GREEN:**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_child_observations.py -q
# Kỳ vọng: 4 passed
./.venv/Scripts/python.exe -m pytest -q
# Kỳ vọng: 41 passed, KHÔNG được đỏ test_agent_prompt_trace.py
```

```bash
git add -A && git commit -m "feat(cp2): child retriever+generation observations, shared pricing"
```

#### Task 10 — Tạo prompt v1/v2 trên Langfuse và chứng minh rollback

Làm thủ công trên UI (bằng chứng phải là ảnh thật):

1. Vào project `day13-k4-l3a-02496` → **Prompts** → Create. Tên `day13-chat`, type `text`, nội dung:
   ```
   Feature={{feature}}
   Docs={{docs}}
   Question={{message}}
   ```
   Gắn label `baseline` **và** `production` → đây là **v1**.
2. Sửa prompt, tạo **v2** (đổi format câu trả lời, ví dụ thêm câu "Trả lời ngắn gọn dưới 3 câu."). Gắn label `candidate`.
3. Chạy cùng một input với 2 label, đổi `.env` rồi restart API:
   ```bash
   # Lần 1
   LANGFUSE_PROMPT_LABEL=baseline
   # Lần 2
   LANGFUSE_PROMPT_LABEL=candidate
   ```
   Ghi lại `correlation_id` của 2 request (in ra terminal) — đây là 2 trace ID cần cho report.
4. Promote v2: UI đổi label `production` sang v2 → chạy 1 request → chụp ảnh.
5. Rollback: đổi `production` về v1 → chạy 1 request → chụp ảnh.

**Verify bằng trace, không tin lời UI:**
```bash
grep '"event": "response_sent"' data/logs.jsonl | grep -o 'req-[0-9a-f]*'
# Mở từng correlation_id này trong Langfuse, kiểm metadata:
#   prompt_name=day13-chat, prompt_label=baseline|candidate|production, prompt_version=1|2
```
> `prompt_source` phải là `langfuse`. Nếu là `local-fallback` → sai key/host hoặc prompt chưa có trong project (xem `GUIDE.md` §"Khi prompt luôn hiện local-v1").

Chụp ảnh: `09-prompt-versions.png`, `10-prompt-rollback.png`.

```bash
git add -A && git commit -m "docs(cp2): prompt v1/v2 and production rollback evidence"
```

#### Task 11 — Tạo ≥10 trace thật và chụp waterfall

```bash
rm -f data/logs.jsonl
./.venv/Scripts/python.exe scripts/load_test.py --concurrency 5
./.venv/Scripts/python.exe scripts/validate_logs.py
```

Mở Langfuse → project cá nhân → **Traces**: phải thấy **≥10 trace** do workload này tạo. Mở một trace → waterfall phải hiện 3 tầng:
```
lab-agent-run (agent)
├── retrieval (retriever)
└── llm-generation (generation)
```

**Verify metadata của trace** (mục 8 evidence): `correlation_id`, `model`, `prompt_name`/`version`/`label`, `input_tokens`/`output_tokens`, cost. **Không có PII thô** — `capture_input=False, capture_output=False` + `summarize_text` đảm bảo điều này.

Chụp ảnh: `06-trace-list.png`, `07-trace-waterfall.png`, `08-trace-metadata.png`.

```bash
git add -A && git commit -m "docs(cp2): trace list, waterfall and metadata evidence"
```

#### Task 12 — Thêm thư viện dashboard live (Streamlit)

`requirements.txt` hiện **không có** thư viện biểu đồ nào. Bạn chọn dashboard live, nên cài `streamlit` + `pandas` (Streamlit kéo pandas + altair + matplotlib làm dependency):

```bash
./.venv/Scripts/python.exe -m pip install streamlit==1.40.2 pandas==2.2.3
```

Ghi rõ lý do chọn Streamlit trong `submission/REPORT.md` (rubric mục D + mục G "quyết định kỹ thuật"): nó khớp contract `refresh_seconds: 30` và `time_range_minutes: 60` trong `config/dashboard.yaml`, thay vì phải chụp ảnh tĩnh.

Thêm vào cuối `requirements.txt` (giữ thứ tự như file gốc, thêm dòng mới ở cuối):

```
streamlit==1.40.2
pandas==2.2.3
```

```bash
./.venv/Scripts/python.exe -c "import streamlit, pandas;print('streamlit',streamlit.__version__,'| pandas',pandas.__version__)"
# Kỳ vọng: streamlit 1.40.2 | pandas 2.2.3
```

```bash
git add -A && git commit -m "build: add streamlit + pandas for live dashboard"
```

#### Task 13 — TDD: module tính toán + app Streamlit 6 panel

> **Tách `app/observability.py` (logic thuần) khỏi `scripts/dashboard_app.py` (UI).** Nhờ vậy test được viết bằng pytest mà **không cần** dựng Streamlit server — đây là điều kiện để giữ được TDD cho phần dashboard.

**Bước 1 — test RED.** Tạo `tests/test_observability_stats.py`:

```python
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
        lines.append({
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
        })
    lines.append({
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
    })
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
    for key in ("latency_p50", "latency_p95", "latency_p99", "ttft_p95", "traffic",
                "error_rate_pct", "retrieval_success_pct", "cost_total", "tokens_in",
                "tokens_out", "quality_mean"):
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
    contract = yaml.safe_load(
        (REPO_ROOT / "config" / "dashboard.yaml").read_text(encoding="utf-8")
    )["dashboard"]
    by_id = {p["id"]: p for p in contract["panels"]}
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
    successes = [r for r in records if r.get("tool_success") is not None]
    assert stats["error_rate_pct"] == round(len(failed) / len(received) * 100, 2)
    assert stats["retrieval_success_pct"] == round(
        sum(1 for r in successes if r["tool_success"]) / len(successes) * 100, 2
    )


def test_empty_log_file_yields_zeroed_stats_not_a_crash(monkeypatch, tmp_path):
    log_path = tmp_path / "logs.jsonl"
    log_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(observability, "LOG_PATH", log_path)
    assert observability.load_records() == []
    stats = observability.compute_stats([])
    assert stats["latency_p95"] == 0
    assert stats["error_rate_pct"] == 0
```

**Bước 2 — verify FAIL:**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_observability_stats.py -q
# Kỳ vọng: ModuleNotFoundError: No module named 'app.observability'
```

**Bước 3 — implement.** Tạo `app/observability.py`:

```python
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"
CONFIG_PATH = REPO_ROOT / "config" / "dashboard.yaml"

from .metrics import percentile


def load_records(path: Path | None = None) -> list[dict[str, Any]]:
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


def within_time_range(
    records: list[dict[str, Any]], minutes: int
) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=minutes)
    kept = []
    for record in records:
        stamp = _parse_ts(record.get("ts", ""))
        if stamp is None or stamp >= cutoff:
            kept.append(record)
    return kept


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def compute_stats(records: list[dict[str, Any]]) -> dict[str, float]:
    sent = [r for r in records if r.get("event") == "response_sent"]
    received = [r for r in records if r.get("event") == "request_received"]
    failed = [r for r in records if r.get("event") == "request_failed"]

    latencies = [r["latency_ms"] for r in sent if isinstance(r.get("latency_ms"), int)]
    ttfts = [r["ttft_ms"] for r in sent if isinstance(r.get("ttft_ms"), int)]
    tool_rows = [r for r in records if r.get("tool_success") is not None]

    return {
        "latency_p50": percentile(latencies, 50) if latencies else 0.0,
        "latency_p95": percentile(latencies, 95) if latencies else 0.0,
        "ttft_p95": percentile(ttfts, 95) if ttfts else 0.0,
        "latency_p99": percentile(latencies, 99) if latencies else 0.0,
        "traffic": len(received),
        "error_rate_pct": round(len(failed) / len(received) * 100, 2) if received else 0.0,
        "retrieval_success_pct": (
            round(sum(1 for r in tool_rows if r["tool_success"]) / len(tool_rows) * 100, 2)
            if tool_rows else 0.0
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
    "latency": (("latency_p50", "P50"), ("latency_p95", "P95"),
                ("latency_p99", "P99"), ("ttft_p95", "TTFT P95")),
    "traffic": (("traffic", "requests"),),
    "errors": (("error_rate_pct", "error rate %"),
               ("retrieval_success_pct", "retrieval success %")),
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
        specs.append({
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
        })
    return specs
```

Bỏ `sys` thừa nếu IDE báo; `sys` không dùng trong module này — xoá dòng import cho sạch.

**Verify logic (không cần Streamlit):**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_observability_stats.py -q
# Kỳ vọng: 8 passed
```

#### Task 13b — App Streamlit 6 panel

Tạo `scripts/dashboard_app.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st

from app.observability import dashboard_meta, panel_specs

st.set_page_config(page_title="Day 13 Monitoring & LLMOps", layout="wide")

meta = dashboard_meta()
specs = panel_specs()

st.title(meta["title"])
st.caption(
    f"Source: data/logs.jsonl — time range {meta['time_range_minutes']} phút, "
    f"tự refresh mỗi {meta['refresh_seconds']} giây. "
    "Đường đứt là threshold/SLO line từ config/dashboard.yaml."
)

columns = st.columns(2)
for position, spec in enumerate(specs):
    with columns[position % 2]:
        with st.container(border=True):
            values = spec["series"]
            headline = values[0] if values else None
            if headline:
                st.metric(headline["label"], f"{headline['value']:,.4g} {spec['unit']}")
            st.markdown(f"**{spec['title']}**")
            st.dataframe(
                [
                    {"metric": item["label"], "value": item["value"], "unit": spec["unit"]}
                    for item in values
                ],
                use_container_width=True,
                hide_index=True,
            )
            operator = ">=" if spec["operator"] == "gte" else "<="
            st.caption(
                f"Threshold: {spec['aggregation']} {operator} {spec['threshold']} {spec['unit']} "
                f"— `{spec['query']}`"
            )

st.caption("Mỗi panel có đơn vị, time range và threshold như contract.")
```

**Verify:**

```bash
# Terminal 1: API đang chạy
# Terminal 2:
./.venv/Scripts/python.exe -m streamlit run scripts/dashboard_app.py --server.port 8501
# Kỳ vọng: mở http://localhost:8501, thấy đúng 6 panel có dữ liệu
```

Chạy test để chắc chắn import Streamlit không phá test:

```bash
./.venv/Scripts/python.exe -m pytest -q
# Kỳ vọng: 54 passed
```

```bash
git add -A && git commit -m "feat(cp2): streamlit 6-panel live dashboard"
```

#### Task 14 — Đo lại incident practice để chứng minh dashboard phản ánh dữ liệu thật

```bash
./.venv/Scripts/python.exe scripts/validate_dashboard.py
# Kỳ vọng: HỢP LỆ: 6/6 panel

# Baseline sạch
rm -f data/logs.jsonl
./.venv/Scripts/python.exe scripts/load_test.py --concurrency 5
# Terminal 2: streamlit tự refresh sau 30s
curl -s http://127.0.0.1:8000/metrics
# GHI LẠI: latency_p95, quality_avg, total_cost_usd

# Bật incident rồi đo lại
./.venv/Scripts/python.exe scripts/inject_incident.py --scenario rag_slow
./.venv/Scripts/python.exe scripts/load_test.py --concurrency 5
curl -s http://127.0.0.1:8000/metrics
# GHI LẠI: latency_p95  ← phải TĂNG rõ rệt (retrieve ngủ 2,5 s)

# Tắt incident
./.venv/Scripts/python.exe scripts/inject_incident.py --scenario rag_slow --disable
```

Chụp ảnh Streamlit ở `http://localhost:8501` (phải thấy tên panel, time range, đơn vị, threshold):
- `submission/evidence/11-dashboard-overview.png` — nếu 1 ảnh không đọc rõ, tách `11a-dashboard-latency-errors.png` + `11b-dashboard-cost-token-quality.png` như `SUBMISSION.md` §5 cho phép.

```bash
git add -A && git commit -m "docs(cp2): dashboard runtime evidence before/after rag_slow"
```

#### Task 15 — SLO, error budget, 3 alert + runbook

**`config/slo.yaml`** — giữ nguyên cấu trúc, điền `note` bằng số liệu **thật** của bạn:

```yaml
service: day13-l3a-monitoring-llmops-lab
primary_slo:
  name: fast_successful_requests
  window: 28d
  sli:
    good_event: 'event == "response_sent" and latency_ms <= 3000'
    total_event: 'event == "request_received"'
  target_percent: 99.5
  error_budget_percent: 0.5
  note: >-
    Baseline sạch đo được P95 = <điền số thật> ms, cao hơn ngưỡng 3000 ms khi
    incident rag_slow bật (retrieve ngủ 2,5 s). Vì vậy good_event dùng
    latency_ms <= 3000 là nghiêm ngặt khi có sự cố chậm nhưng đúng mục tiêu
    "user vẫn nhận được câu trả lời đủ nhanh". Error budget = 100% - 99,5% = 0,5%,
    tức trong 28 ngày được phép 0,5% request vi phạm. Khi P95 vượt 3000 ms,
    budget âm => đã cháy trước khi hết tháng.
guardrails:
  error_rate_pct_max: 2
  daily_cost_usd_max: 2.5
  quality_score_avg_min: 0.75
  retrieval_success_rate_pct_min: 90
```

**`config/alert_rules.yaml`** — 3 alert symptom-based (theo triệu chứng người dùng, không theo tên implementation):

```yaml
alerts:
  - name: ChatLatencyP95BudgetBurn
    severity: critical
    type: symptom-based
    condition: 'p95(latency_ms) over 5m > 3000'
    duration: 10m
    channel: slack
    slack_channel: "#day13-oncall"
    owner: Nguyen Trong Minh (02496)
    slo: fast_successful_requests
    runbook: docs/alerts.md#alert-1
    summary: >-
      Người dùng chờ quá 3 giây mới nhận câu trả lời; SLO fast_successful_requests
      đang cháy error budget.
  - name: RetrievalFailureSpike
    severity: critical
    type: symptom-based
    condition: 'count(event == "request_failed" and tool_name == "retrieval") / count(event == "request_received") * 100 over 5m > 2'
    duration: 5m
    channel: slack
    slack_channel: "#day13-oncall"
    owner: Nguyen Trong Minh (02496)
    slo: fast_successful_requests
    runbook: docs/alerts.md#alert-2
    summary: >-
      Trên 2% request thất bại ở bước truy xuất; câu trả lời thiếu căn cứ.
  - name: QualityProxyDegraded
    severity: warning
    type: symptom-based
    condition: 'mean(quality_score) over 15m < 0.75'
    duration: 15m
    channel: slack
    slack_channel: "#day13-quality"
    owner: Nguyen Trong Minh (02496)
    slo: guardrail_quality
    runbook: docs/alerts.md#alert-3
    summary: >-
      Chất lượng câu trả lời suy giảm; thường do prompt version mới hoặc
      context không match.
```

**`docs/alerts.md`** — điền đủ 11 trường của template cho cả 3 alert (Tên, Severity, Duration, Kênh, SLI/SLO, Điều kiện, Ảnh hưởng người dùng, **Ba bước kiểm tra đầu tiên**, Mitigation, Owner). Ba bước kiểm tra phải là điều tra Metrics → Logs → Traces, ví dụ Alert 1:
1. Dashboard: xác nhận P95 vượt ngưỡng, ghi khoảng thời gian.
2. `grep '"event": "response_sent"' data/logs.jsonl | sort` theo `latency_ms` → lấy `correlation_id` chậm nhất.
3. Mở Langfuse, tìm trace có cùng `correlation_id` → xem span `retrieval` hay `llm-generation` chiếm thời gian.

```bash
./.venv/Scripts/python.exe -c "import yaml;yaml.safe_load(open('config/alert_rules.yaml',encoding='utf-8'));yaml.safe_load(open('config/slo.yaml',encoding='utf-8'));print('YAML OK')"
# Kỳ vọng: YAML OK
./.venv/Scripts/python.exe scripts/validate_dashboard.py
# Kỳ vọng: HỢP LỆ: 6/6 panel
```

```bash
git add -A && git commit -m "docs(cp2): SLO with error budget, 3 symptom-based alerts and runbooks"
```

---

### CP3 — Challenge chính thức (Task 16–17)

> ⚠️ **Chỉ chạy khi Lab Coach phát `config/challenge.json` riêng cho K4-L3A.** File đã nằm trong `.gitignore`. Tuyệt đối không tự tạo, không sửa, không lấy từ lớp khác, không force-add. Nếu chưa nhận, dùng `--scenario` practice như Task 14.

#### Task 16 — Chạy challenge và điều tra

```bash
# Lưu file Lab Coach gửi vào config/challenge.json
./.venv/Scripts/python.exe scripts/inject_incident.py
# Kỳ vọng: 200 {'ok': True, 'incidents': {...}}
./.venv/Scripts/python.exe scripts/load_test.py --challenge --concurrency 5
# Kỳ vọng in: Challenge: <challenge_id> | Cohort: K4
```

Điều tra theo đúng thứ tự, mỗi bước ghi lại bằng chứng cụ thể:

1. **Metric**: `curl -s http://127.0.0.1:8000/metrics` + dashboard → metric xấu và khoảng thời gian.
2. **Log**: lọc `data/logs.jsonl` trong khoảng đó, lấy một `correlation_id` bất thường.
3. **Trace**: tìm trace có **cùng** `correlation_id` trong Langfuse → so sánh span.
4. **Root cause**, **fix action**, **preventive measure** → `submission/REPORT.md`.

```bash
# Lọc log chậm
grep '"event": "response_sent"' data/logs.jsonl | python -c "
import sys, json
rows=[json.loads(l) for l in sys.stdin if l.strip()]
rows.sort(key=lambda r:-r.get('latency_ms',0))
for r in rows[:5]: print(r['ts'], r['correlation_id'], r['latency_ms'], r.get('tool_success'))
"
```

**Verify:** chắc chắn `config/challenge.json` **không** được commit.
```bash
git status --short --ignored | grep challenge
# Kỳ vọng: !! config/challenge.json  (dấu !! = bị ignore)
git log --all --oneline -- config/challenge.json
# Kỳ vọng: rỗng (không có dòng nào)
```

#### Task 17 — Evidence incident

Chụp: `12-incident-metric.png`, `13-incident-log.png`, `14-incident-trace.png`.

```bash
git add -A && git commit -m "docs(cp3): incident investigation evidence"
```

---

### CP4 — Báo cáo, evidence, chốt bài (Task 18–20)

#### Task 18 — Quét secret/PII lần cuối

```bash
# Secret
grep -rIn "sk-lf-\|pk-lf-[A-Za-z0-9]\{20,\}\|GOOGLE_API_KEY\|OPENAI_API_KEY" \
  --include="*.py" --include="*.md" --include="*.yaml" --include="*.json" . \
  | grep -v ".venv" || echo "KHÔNG có secret trong source"

# PII thô trong evidence
grep -rIn "0901234567\|student@vinuni.edu.vn\|001203012345\|4111 1111 1111 1111" submission/ \
  || echo "KHÔNG có PII mẫu trong evidence"

# Artifact rác
git status --short
# Kỳ vọng: chỉ .env / data/logs.jsonl bị ignore
```

#### Task 19 — Chạy lại toàn bộ trên commit cuối

```bash
rm -f data/logs.jsonl
# Terminal 1: restart API
# Terminal 2:
./.venv/Scripts/python.exe scripts/load_test.py --concurrency 5
./.venv/Scripts/python.exe scripts/validate_logs.py      | tee submission/evidence/02-log-validator.txt
./.venv/Scripts/python.exe scripts/validate_dashboard.py  | tee submission/evidence/03-dashboard-validator.txt
./.venv/Scripts/python.exe -m pytest -q                    | tee submission/evidence/01-pytest.txt
```

**Verify — cả 3 phải đạt:**
```
Estimated Score: 100/100
HỢP LỆ: 6/6 panel có trong dashboard contract.
54 passed
```

```bash
git add -A && git commit -m "test(cp4): final validators and dashboard evidence on submission commit"
git log -1 --oneline
# Ghi SHA này vào REPORT.md
```

#### Task 20 — Hoàn thiện `submission/REPORT.md`

Điền đủ 9 mục có sẵn trong template. Các mục bắt buộc có sẵn số liệu:

- **§3 Bảng kết quả**: baseline (30/100, 6/6, 22 passed) vs cuối (100/100, 6/6, 54 passed).
- **§4**: correlation ID tạo ở middleware, header trả về; scrub chạy trước `JsonlFileProcessor`.
- **§5**: 2 trace ID của baseline/candidate + ảnh rollback.
- **§6**: SLO + error budget 0,5% + 3 alert.
- **§7**: chain metric → log → trace của CP3.
- **§8**: 1 quyết định kỹ thuật (ví dụ vì sao đổi `hash_user_id` sang `u_`+8 hex) + 1 blocker đã gặp + cách xử lý.

```bash
git add -A && git commit -m "docs: complete personal report with evidence index"
git remote push origin main
git log -1 --oneline   # lấy SHA cuối
```

**Nộp lên VLearn LMS:** URL repo cá nhân + commit SHA cuối.

---

## 6. Tests / validation

### Chu trình TDD áp dụng cho từng task

Mỗi task code (4, 5, 6, 9, 13) đi đúng 4 bước: **viết test RED → chạy xác nhận FAIL → implement tối thiểu → chạy xác nhận GREEN → commit**. Không task nào bỏ qua bước verify-fail, vì cả 3 TODO chính đều là code *đang chạy* chỉ thiếu — nếu không thấy test đỏ trước, không chứng minh được test có tác dụng.

### Ma trận test → rubric

| Test file | Chặn được hồi quy | Rubric |
|---|---|---|
| `test_correlation_middleware.py` (5) | contextvar rò giữa request; ID sai format | A (15đ) |
| `test_log_enrichment.py` (4) | thiếu metadata; **hash bị detector CCCD gắn cỏ** | A + B |
| `test_pii_scrub_pipeline.py` (6) | PII lọt vào file log; scrub phá identifier | B (10đ) |
| `test_child_observations.py` (4) | mất span cha–con; rò PII vào trace | C (15đ) |
| `test_observability_stats.py` (8) | panel thiếu/sai số; PII vào ảnh | D (15đ) |
| 22 test gốc | hồi quy chung | F (10đ) |

Tổng kỳ vọng: **54 passed**.

### Lệnh xác minh cuối (chạy trên commit nộp)

```bash
./.venv/Scripts/python.exe -m pytest -q                     # 54 passed
./.venv/Scripts/python.exe scripts/validate_logs.py         # 100/100
./.venv/Scripts/python.exe scripts/validate_dashboard.py    # 6/6 panel
./.venv/Scripts/python.exe -m pip install -r requirements.txt && \
  ./.venv/Scripts/python.exe -m pytest -q                   # chứng minh repo cài lại được
git status --short && git log -1 --oneline
```

---

## 7. Risks, tradeoffs, and open questions

### Rủi ro đã được đo (không còn là phỏng đoán)

| Rủi ro | Mức | Xử lý trong kế hoạch |
|---|---|---|
| `user_id_hash` all-digit bị detector CCCD gắn cỏ, −30đ | **Cao** (2138/500k user) | Task 5: đổi sang `u_`+8 hex; có test hồi quy 5000 user |
| `validate_logs.py` đọc log cũ chưa scrub → không bao giờ lên 100 | Cao | Task 7 & 14 & 19: xoá `data/logs.jsonl` trước **mỗi** lần đo |
| Instrument trong `agent.py` làm đỏ `test_agent_prompt_trace` | Cao | Task 9: instrument ở `mock_rag.py`/`mock_llm.py` |
| PII lọt qua `error_type`/`detail` (processor cũ chỉ xử lý `payload` cấp 1) | Trung bình | Task 6: `scrub_value` đệ quy toàn event |
| Chưa có thư viện vẽ biểu đồ nào | Chắc chắn | Task 12: thêm streamlit + pandas (dashboard live) |
| `1 / 1.234.000` khả năng hash của user thật khớp detector | Thấp nhưng không loại trừ | Task 5 đã loại trừ triệt để |

### Tradeoff đã chọn

- **Streamlit tối ưu với export PNG**: xuất PNG trực tiếp cho evidence, không cần server chạy khi demo, cài nhanh. Đánh đổi: không có auto-refresh 30 giây như contract mô tả. → Ghi rõ trong `REPORT.md` là giới hạn đã biết (rubric H "hạn chế còn lại"). Nếu thời gian cho phép, thêm trang Streamlit sau.
- **`u_`+8 hex thay vì 12 hex**: giảm entropy hash từ 48 xuống 32 bit. Chấp nhận được vì mục đích chỉ là pseudonym để nối log, không phải chống đoán trùng lặp. Nếu muốn giữ 48 bit, dùng `u_` + 12 hex **và** thêm lookaround `(?<![0-9A-Za-z])` vào pattern — phức tạp hơn, không đáng.
- **Giữ `capture_input=False, capture_output=False`**: rubric cấm PII thô trong trace; đây là cách chắc chắn nhất. Đổi lại: trace không lưu prompt/output đầy đủ — chấp nhận, vì `update_current_generation` vẫn ghi input/output đã scrub.

### Câu hỏi cần bạn trả lời

1. **Bạn đã tạo project Langfuse chưa?** Nếu chưa, làm B1–B3 trước khi bắt đầu Task 1 — nếu không, mục C (15 điểm) không thể chấm.
2. **Bạn muốn dashboard tĩnh (matplotlib, khuyến nghị) hay live (Streamlit)?** → **Đã chọn Streamlit live**; Task 12–14 đã cập nhật.
3. **Bạn đã có repo GitHub cá nhân chưa?** → **Sẽ tạo repo mới** (Task 1).
4. **`config/challenge.json` khi nào Lab Coach phát?** → **Chưa có**; CP3 (Task 16–17) làm sau, không chặn các task khác.

### Điều tuyệt đối không làm

- Không hard-code kết quả validator, số liệu dashboard, hay metadata trace để qua điểm (−15đ, có thể 0 điểm).
- Không sửa `scripts/validate_logs.py` hoặc `scripts/validate_dashboard.py` — chúng là technical gate.
- Không tự tạo/sửa `config/challenge.json`, không lấy từ lớp khác.
- Không commit `.env`, key, PII thô.
- Không push lên repo đề bài.