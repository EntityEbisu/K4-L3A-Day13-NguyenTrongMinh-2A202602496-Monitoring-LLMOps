# Giải thích triển khai — Day 13 Monitoring & LLMOps (K4-L3A)

Tài liệu này giải thích **những gì đã làm, vì sao chọn cách đó, và cách tự
kiểm chứng lại**. Dành cho học viên tự đọc lại trước khi demo hoặc trả lời Q&A.
Mọi số liệu trong đây đều lấy từ output thật của lệnh chạy trên máy này.

---

## 1. Tóm tắt trạng thái

| Hạng mục | Baseline | Sau khi làm | Cách kiểm chứng |
|---|---|---|---|
| `scripts/validate_logs.py` | 30/100 | **100/100** | `python scripts/validate_logs.py` |
| `scripts/validate_dashboard.py` | 6/6 | 6/6 | `python scripts/validate_dashboard.py` |
| `python -m pytest -q` | 22 passed | **54 passed** | `python -m pytest -q` |
| Số test mới thêm | — | 32 | xem `tests/` |
| Trace trên Langfuse | 0 | **≥10**, mỗi trace có 3 span | `python scripts/verify_trace_join.py` |
| Prompt version | không có | v1 + v2, có promote/rollback | `python scripts/prompt_rollout.py show` |

Nguyên tắc xuyên suốt: **không có con số nào được ghi tay**. Mọi bằng chứng đều
là output của script chạy được, và các script đó đọc dữ liệu thật
(`data/logs.jsonl` hoặc API Langfuse) chứ không đọc hằng số.

---

## 2. Hai lỗi thật và một kết luận sai đã được sửa

Phần này là nguyên liệu để bảo vệ khi Q&A.

### 2.1 `user_id_hash` có thể bị quy là rò rỉ CCCD (−30 điểm)

Starter cho `hash_user_id()` trả về `sha256(user_id)[:12]` — 12 ký tự hex.
Nếu cả 12 ký tự đều là chữ số thì detector CCCD `\b\d{12}\b` của chính
`scripts/validate_logs.py` sẽ khớp và trừ 30 điểm PII, dù ta không hề ghi PII.

Đo thật:

```
sha256("u45")[:12] = 613933674358   -> validator gắn cờ ['cccd']
Tần suất (500.000 user giả):  2.138 / 500.000  (~0,43%)
Sau khi thêm tiền tố "u":       412 / 500.000
Sau khi đổi thành "u_" + 8 hex: 0 / 500.000
```

Mười user mẫu `u01..u10` của lab đều may mắn sạch, nên nếu chỉ chạy workload
mẫu thì không lộ. Nhưng `config/challenge.json` ở CP3 có `user_id` do Lab Coach
sinh ra — không kiểm soát được. Vì vậy phải sửa.

**Cách sửa:** `app/pii.py` đổi thành `"u_" + sha256(...)[:8]`. Tiền tố chữ bảo
đảm chuỗi số dài nhất chỉ 8, thấp hơn ngưỡng 10 của `phone_vn`. Có test hồi quy
`tests/test_log_enrichment.py::test_hash_never_looks_like_pii` quét 5.000 user
và đối chiếu với đúng detector của validator.

**Đánh đổi đã chấp nhận:** entropy giảm từ 48 xuống 32 bit. Chấp nhận được vì
mục đích chỉ là pseudonym để nối log, không phải chống đoán trùng lặp.

### 2.2 Endpoint đọc trace không trả metadata (kết luận sai ban đầu)

Khi đọc lại trace qua `/api/public/v2/observations`, các trường `model`,
`usage_details`, `cost_details`, `metadata`, `input`, `output` đều là `None`.

Tôi **kết luận sai** rằng `update_current_span()` / `update_current_generation()`
không ghi được gì, và đã ghi điều đó vào báo cáo. Đã thử lại ba cách ghi:

| Cách | Kết quả đọc lại qua API |
|---|---|
| `update_current_generation(...)` | `modelId=None`, `totalPrice=None` |
| `start_observation(..., model=…, usage_details=…)` | `modelId=None`, `totalPrice=None` |
| `start_as_current_observation(..., model=…, usage_details=…)` | `modelId=None`, `totalPrice=None` |

Kết luận đúng: **đây là hạn chế của phía đọc, không phải phía ghi.** Endpoint v2
chỉ trả về tập cột rút gọn:

```
bookmarked, endTime, environment, id, inputPrice, isRootObservation, latency,
level, modelId, name, outputPrice, parentObservationId, projectId, public,
sessionId, startTime, statusMessage, timeToFirstToken, totalPrice, traceId,
type, userId, version
```

Còn trên **UI**, span `llm-generation` hiển thị đủ: `model = claude-sonnet-4-5`,
`cost = $0.001422`, `139 tokens`, liên kết prompt `day13-chat (v1)` — xem ảnh
`submission/evidence/07-trace-waterfall.png` và `14-incident-trace.png`.

Bài học: **không kết luận "ghi hỏng" chỉ từ việc API đọc trả rỗng.** Phải kiểm tra
nơi dữ liệu thực sự được hiển thị trước khi kết luận. Việc instrument hiện tại
(`update_current_*`) là đúng và không cần sửa.

Đây cũng là lý do rubric yêu cầu *evidence runtime* chứ không chỉ validator xanh:
validator không kiểm tra nội dung span, và cũng không phân biệt được "ghi hỏng"
với "API không trả trường đó".

### 2.3 Tắt server bằng `kill` làm mất trace

Langfuse gom span theo batch. Khi dùng `kill` để tắt uvicorn giữa các bước đổi
label, buffer chưa kịp đẩy lên server và **trace của request vừa chạy mất
hoàn toàn** — trong khi log vẫn còn. Lần chạy đầu tiên của vòng đổi label đã mất
6 trace theo cách này (chỉ còn 2 trace cũ).

**Cách sửa:** thêm endpoint `POST /traces/flush` trong `app/main.py` gọi
`get_langfuse_client().flush()`. Script điều phối gọi endpoint này *trước khi*
tắt tiến trình. Sau khi sửa, cả 4 trace của vòng đổi label đều tới server và
ghi đúng version.

---

## 3. Vì sao instrument ở `mock_rag.py`/`mock_llm.py` chứ không ở `agent.py`

`tests/test_agent_prompt_trace.py` khẳng định `client.span_updates[-1]` là **đúng**
dict metadata của prompt, và chạy qua `LabAgent.run.__wrapped__` với client giả
chỉ có `get_prompt` và `update_current_span`. Nếu thêm lời gọi `update_current_span`
bên trong `agent.run`, phần tử cuối sẽ không còn là metadata prompt → test đỏ.

Instrument tại `app/mock_rag.py::retrieve` (`as_type="retriever"`) và
`app/mock_llm.py::FakeLLM.generate` (`as_type="generation"`) cho đúng quan hệ
cha–con mà không đụng test. `@observe` đặt được trên cả hàm module lẫn instance
method, và khi không có key nó chỉ log cảnh báo chứ không raise — nên `pytest` vẫn
chạy được không cần Langfuse.

Đã kiểm chứng thực tế trên server: **10 trace, mỗi trace có `AGENT` → `RETRIEVER`
+ `GENERATION`.**

---

## 4. Luồng đúng để điều tra một sự cố

Đây là nội dung quan trọng nhất khi demo (rubric mục E và G). Đã tái hiện với
practice scenario `rag_slow`:

1. **Metric** — `curl -s http://127.0.0.1:8000/metrics`, hoặc panel `latency`
   trên dashboard. P95 tăng **797 ms → 3130 ms**, vượt ngưỡng SLO 3000 ms.
2. **Log** — lọc `data/logs.jsonl` theo `latency_ms` cao nhất, lấy
   `correlation_id`. Ví dụ `req-baf7f14b` với `latency_ms=3130`.
3. **Trace** — tra `correlation_id` đó trên Langfuse, so sánh span.
4. **Kết luận** — `ttft_p95` **không đổi** (50 → 51 ms) trong khi tổng latency
   tăng gấp 4. TTFT là thời điểm token đầu tiên, tức là thời gian chờ ở LLM. Vì
   TTFT giữ nguyên mà tổng thời gian tăng, độ trễ **không nằm ở bước sinh câu
   trả lời** mà nằm ở bước trước đó — span `retrieval`. Đúng với nguyên nhân:
   `rag_slow` làm `retrieve()` ngủ thêm 2,5 s.

Bước 4 là bước phân biệt người hiểu và người không hiểu: metric cho biết *có gì
sai*, log cho biết *request nào*, trace cho biết *bước nào*. Không có TTFT thì
dễ kết luận nhầm là LLM chậm.

### Script tự động hoá chuỗi này

`python scripts/verify_trace_join.py` đối chiếu từng `correlation_id` trong log
với trace thật trên Langfuse. Kết quả hiện tại:

```
Khớp: 10/10 request
PASS: mọi request trong log đều có trace cha-con tương ứng.
```

Script exit code khác 0 nếu còn request không tìm thấy trace — nên dùng được như
một kiểm tra tự động, không cần mở UI.

---

## 5. Prompt versioning: cách làm và bằng chứng

Prompt được quản lý thật trên Langfuse (tên `day13-chat`, type `text`), không
hard-code version trong code:

- **v1** — template gốc, label `baseline` + `production`
- **v2** — thêm yêu cầu "trả lời tối đa 3 câu ngắn, trích dẫn tài liệu", label `candidate`

### Vì sao phải khởi động lại server mỗi khi đổi label

App đọc `LANGFUSE_PROMPT_LABEL` từ biến môi trường **của tiến trình server** tại
lúc khởi động, không đọc lúc request. Đã kiểm chứng: uvicorn `--env-file` **không**
ghi đè biến môi trường đã có, nên đặt biến shell trước khi khởi động là cách
đúng. Nếu chỉ đổi biến rồi gọi script, server vẫn dùng label cũ.

### Bằng chứng đổi version nhìn thấy được

Số token đầu vào thay đổi theo version, nên version thật sự được dùng:

| Bước | Label | Version | `tokens_in` | Correlation ID |
|---|---|---|---|---|
| baseline | `baseline` | v1 | **29** | `req-9f15e93e` |
| candidate | `candidate` | v2 | **46** | `req-2c981162` |
| sau promote | `production` | v2 | **46** | `req-ccae88bd` |
| sau rollback | `production` | v1 | **29** | `req-624c2ac1` |

Và trên trace, `version` được ghi lại đúng: v1 → v2 → v2 (sau promote) → v1
(sau rollback).

### Một lỗi tự làm đã phát hiện và sửa

Script đầu tiên nhận tham số dòng lệnh làm label, nhưng thực tế lại đọc label từ
biến môi trường của *chính nó* — nên **in ra label sai** (`production` cho cả hai
lần chạy) dù server thực tế đã dùng đúng. Đã sửa: script nhận label bắt buộc
qua tham số và tự tra version trên Langfuse lúc chạy để in bằng chứng, đồng thời
in cảnh báo rõ rằng tham số phải khớp biến môi trường của server.

Bài học: tên biến trong script phải khớp đúng nơi nó được đọc. Đặt nhầm tên
(`LABEL_TO_SET`) khiến script báo sai mà vẫn exit 0.

---

## 6. Dashboard 6 panel

Vì sao chọn Streamlit thay vì xuất ảnh PNG tĩnh: contract trong
`config/dashboard.yaml` yêu cầu `time_range_minutes: 60` và
`refresh_seconds: 30`, nên dashboard chạy live khớp contract hơn.

**Tách logic khỏi giao diện** là điều kiện để giữ được TDD cho phần này:

| File | Vai trò |
|---|---|
| `app/observability.py` | Logic thuần: đọc log, tính số liệu, đọc contract — **không import Streamlit** |
| `scripts/dashboard_app.py` | Chỉ vẽ giao diện |

Nhờ vậy `tests/test_observability_stats.py` kiểm thử được bằng pytest mà không
cần dựng server. Hàm `percentile` được tái sử dụng từ `app/metrics.py` thay vì
viết lại, nên số liệu trên dashboard và trong `validate_logs` không thể lệch nhau.

**Không hard-code:** mỗi panel đọc `threshold` từ `config/dashboard.yaml`. Test
`test_threshold_line_is_respected_by_every_panel` kiểm tra ngưỡng hiển thị luôn
bằng ngưỡng trong contract, nên sửa YAML là dashboard đổi theo.

---

## 7. PII: scrub trước khi ghi, và scrub đệ quy

Scrubber đăng ký **trước** `JsonlFileProcessor` trong chuỗi processor của
structlog — đây là điểm mấu chốt. Scrub sau khi render JSON thì dữ liệu đã nằm
trong file.

Bản starter chỉ quét `payload` cấp 1. Đã đổi thành quét **toàn bộ event, đệ quy**,
vì PII có thể nằm ở `error_type`, `tool_name` hoặc chuỗi lồng sâu — những chỗ
processor cũ bỏ sót.

Bốn pattern gốc đã được kiểm chứng là đúng và idempotent (scrub hai lần không
đổi), nên giữ nguyên; chỉ bổ sung `cccd_spaced` và `passport_vn`.

Bằng chứng trên log thật:

```
REDACTED_CREDIT_CARD  1
REDACTED_EMAIL        1
REDACTED_PHONE_VN     1
```

Nguồn PII giả nằm trong `data/sample_queries.jsonl` (user `u01` email, `u05` điện
thoại, `u09` số thẻ). Đã kiểm bằng chính detector của `validate_logs.py`: không
còn chuỗi thô nào trong file log.

---

## 8. Correlation ID

`req-<8 hex>`: lấy từ header `x-request-id` nếu đúng định dạng, nếu không thì tự
sinh. Trả lại trong header `x-request-id` kèm `x-response-time-ms`.

Điểm dễ sai: phải `clear_contextvars()` **trước khi** xử lý request mới, nếu
không metadata của request trước sẽ rò sang request sau. Đã có test
`test_context_does_not_leak_between_requests` kiểm chứng bằng hai request liên
tiếp.

Đã kiểm chứng bằng thử nghiệm rằng contextvars đi qua được ranh giới
`BaseHTTPMiddleware` — đây là giả định quan trọng nhất của toàn bộ CP1, và nó
đúng.

---

## 9. Cách tự chạy lại từ đầu

```bash
# 1. Môi trường
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
cp .env.example .env        # rồi điền key Langfuse cá nhân

# 2. Chạy API
./.venv/Scripts/python.exe -m uvicorn app.main:app --env-file .env

# 3. Workload + kiểm tra
./.venv/Scripts/python.exe scripts/load_test.py --concurrency 5
./.venv/Scripts/python.exe scripts/validate_logs.py        # kỳ vọng 100/100
./.venv/Scripts/python.exe scripts/validate_dashboard.py   # kỳ vọng 6/6
./.venv/Scripts/python.exe -m pytest -q                    # kỳ vọng 54 passed

# 4. Nối log với trace
./.venv/Scripts/python.exe scripts/verify_trace_join.py   # kỳ vọng 10/10

# 5. Dashboard
./.venv/Scripts/python.exe -m streamlit run scripts/dashboard_app.py

# 6. Prompt versioning
./.venv/Scripts/python.exe scripts/prompt_rollout.py show
```

**Lưu ý khi đo lại log validator:** `validate_logs.py` đọc *toàn bộ*
`data/logs.jsonl`, kể cả dòng ghi trước khi sửa code. Phải xoá log cũ, khởi
động lại API rồi chạy lại workload, nếu không điểm sẽ không lên 100.

---

## 10. Còn lại và giới hạn đã biết

| Việc | Trạng thái | Ghi chú |
|---|---|---|
| CP3 challenge chính thức | **Xong** | `day13-k4-l3a-monitoring-llmops-v1`. Root cause: span `retrieval` chiếm 2.501 s / tổng 2.653 s. Xem `submission/REPORT.md` §7. |
| Ảnh evidence (01–14) | **Xong** | 12 ảnh `.png` trong `submission/evidence/`, không ảnh nào lộ key. |
| Metadata span (model/token/cost) | **Xong, kiểm bằng ảnh UI** | API v2 không trả các trường này — xem mục 2.2. Ảnh `07` và `14` cho thấy đầy đủ. |
| Nộp URL repo + commit SHA lên LMS | Chưa làm | Chỉ cần điền sau khi push. |

### Giới hạn cần nói thẳng khi demo

- **Dashboard là bảng số liệu, không phải biểu đồ.** Thiết kế cố ý đơn giản để
  luôn đọc được tên panel, đơn vị, time range và threshold — rubric yêu cầu đọc
  được thông tin này. Nếu muốn biểu đồ thật thì cần thêm thư viện vẽ.
- **Prompt rollout cần khởi động lại server mỗi lần đổi label** (vì app đọc
  biến môi trường lúc khởi động). Đây là hạn chế của thiết kế starter, không
  phải lỗi cấu hình.
- **Chưa có automated test cho nội dung span Langfuse.** Test chỉ kiểm tra quan
  hệ cha–con và việc scrub; nội dung span phải kiểm bằng ảnh UI vì endpoint đọc
  v2 không trả các trường đó.
