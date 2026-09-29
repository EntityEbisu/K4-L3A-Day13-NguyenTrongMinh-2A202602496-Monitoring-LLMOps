# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mọi số liệu trong báo cáo này lấy từ output thật của các lệnh trong repo.
> Cách tái lập toàn bộ: [`../docs/IMPLEMENTATION-NOTES.md`](../docs/IMPLEMENTATION-NOTES.md).

## 1. Thông tin học viên

- **Họ và tên:** Nguyen Trong Minh
- **MSSV:** 02496
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/EntityEbisu/K4-L3A-Day13-NguyenTrongMinh-2A202602496-Monitoring-LLMOps
- **Commit SHA cuối:** xem `git log -1 --oneline` (điền sau khi chốt)
- **Challenge ID:** _chưa có — chờ Lab Coach release `config/challenge.json` tại CP3_
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-02496`

## 2. Evidence index

File `.txt` dưới đây là output thật đã commit. File `.png` cần chụp tay vì
Langfuse yêu cầu đăng nhập.

| Evidence | Đường dẫn | Trạng thái |
|---|---|---|
| Pytest baseline | `evidence/01-pytest-baseline.txt` | 22 passed (trước khi sửa) |
| Pytest cuối | `evidence/01-pytest.txt` | 54 passed |
| Log validator baseline | `evidence/02-log-validator-baseline.txt` | 30/100 (trước khi sửa) |
| Log validator cuối | `evidence/02-log-validator.txt` | **100/100** |
| Dashboard validator | `evidence/03-dashboard-validator.txt` | 6/6 panel |
| Log thô baseline | `evidence/00-baseline-logs-raw.jsonl` | 21 dòng, 0 correlation ID |
| Ghi chú evidence CP1 | `evidence/README-cp1.md` | log thật + PII thật |
| Nối log ↔ trace | `evidence/06-trace-join.txt` | 4/4 request khớp trace |
| Prompt v1/v2 + rollback | `evidence/10-prompt-rollback.txt` | đủ 6 bước, có version thật |
| Structured log (ảnh) | `evidence/04-structured-log.png` | _cần chụp màn hình_ |
| PII redaction (ảnh) | `evidence/05-pii-redaction.png` | _cần chụp màn hình_ |
| Trace list (ảnh) | `evidence/06-trace-list.png` | _cần chụp từ Langfuse UI_ |
| Trace waterfall (ảnh) | `evidence/07-trace-waterfall.png` | _cần chụp từ Langfuse UI_ |
| Trace metadata (ảnh) | `evidence/08-trace-metadata.png` | _cần chụp từ Langfuse UI_ |
| Prompt versions (ảnh) | `evidence/09-prompt-versions.png` | _cần chụp từ Langfuse UI_ |
| Prompt rollback (ảnh) | `evidence/10-prompt-rollback.png` | _cần chụp từ Langfuse UI_ |
| Dashboard runtime (ảnh) | `evidence/11-dashboard-overview.png` | _cần chụp màn hình Streamlit_ |
| Incident metric/log/trace | `evidence/12…14-incident-*.png` | _chờ CP3_ |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 | **100/100** | 0 thiếu field, 10 correlation ID, 0 PII leak |
| `validate_dashboard.py` | 6/6 | 6/6 | contract hợp lệ từ đầu, không sửa |
| `pytest` | 22 passed | **54 passed** | thêm 32 test |
| Số traces hợp lệ | 0 | ≥10 | mỗi trace có `AGENT`→`RETRIEVER`+`GENERATION` |
| Số PII leak | 0 | 0 | kiểm bằng detector của chính validator |
| Latency P95 (sạch) | — | **797 ms** | 10 request, `--concurrency 5` |
| TTFT P95 (sạch) | — | **50 ms** | |
| Latency P95 (khi `rag_slow`) | — | **3130 ms** | vượt ngưỡng SLO 3000 ms |
| TTFT P95 (khi `rag_slow`) | — | **51 ms** | không đổi → độ trễ ở retrieval |
| Retrieval success rate | — | 100% | |
| Error rate | — | 0% | |

## 4. Logging và PII

**Cách tạo/nhận và truyền correlation ID:** `app/middleware.py` nhận header
`x-request-id` nếu đúng định dạng `req-<8 hex>`, nếu không thì tự sinh bằng
`uuid4().hex[:8]`. ID được bind vào contextvars của structlog, lưu vào
`request.state`, và trả lại trong hai header `x-request-id` và
`x-response-time-ms`.

Điểm dễ sai: phải `clear_contextvars()` **trước** khi xử lý request mới, nếu
không metadata của request trước sẽ rò sang request sau. Có test
`test_context_does_not_leak_between_requests` kiểm chứng bằng hai request liên
tiếp.

**Các metadata được ghi vào structured log:** `correlation_id`,
`user_id_hash`, `session_id`, `feature`, `model`, `env` — bind trong
`app/main.py` trước dòng log `request_received` để mọi log sau dùng chung
context. Dòng `response_sent` bổ sung `latency_ms`, `ttft_ms`, `tokens_in`,
`tokens_out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success`.

**Cách bảo đảm PII được scrub trước khi ghi:** `scrub_event` đăng ký trong
chuỗi processor của structlog **trước** `JsonlFileProcessor` — đây là điểm
mấu chốt, vì scrub sau khi render JSON thì dữ liệu đã nằm trong file. Bản
starter chỉ quét `payload` cấp 1; tôi đổi thành quét **toàn bộ event, đệ quy**,
vì PII có thể nằm ở `error_type` hoặc chuỗi lồng sâu.

Bốn pattern gốc đã kiểm chứng là đúng và idempotent nên giữ nguyên; bổ sung
`cccd_spaced` và `passport_vn`.

**Cách kiểm chứng kết quả:** `validate_logs.py` báo `Potential PII leaks
detected: 0`, và đếm marker trong log thật cho thấy `REDACTED_EMAIL`,
`REDACTED_PHONE_VN`, `REDACTED_CREDIT_CARD` đều xuất hiện từ dữ liệu PII giả
trong `data/sample_queries.jsonl`.

## 5. Tracing và prompt versioning

**Cách xác nhận traces do chính tôi tạo:** tôi tự chạy
`scripts/load_test.py --concurrency 5` trên project Langfuse cá nhân
`day13-k4-l3a-02496`, sau đó dùng `scripts/verify_trace_join.py` đối chiếu
từng `correlation_id` trong `data/logs.jsonl` với trace thật trên server.
Kết quả: **4/4 request khớp trace** (lần chạy đầy đủ trước đó là 10/10).

**Cấu trúc root/retrieval/generation observations:** span cha là
`lab-agent-run` (loại `agent`), span con là `retrieval` (loại `retriever`) và
`llm-generation` (loại `generation`). Tôi instrument tại `app/mock_rag.py` và
`app/mock_llm.py` **không phải** trong `agent.py`, vì
`tests/test_agent_prompt_trace.py` khẳng định phần tử cuối của
`client.span_updates` là metadata của prompt; thêm lời gọi trong `agent.run`
sẽ làm test đỏ.

**Cách nối trace với log:** `correlation_id` được ghi vào cả log và metadata
trace. `scripts/verify_trace_join.py` đối chiếu theo mốc thời gian và báo
`PASS` khi mọi request đều có trace cha–con; script trả về exit code khác 0 nếu
còn request không tìm thấy trace.

**Prompt name:** `day13-chat` (type `text`), quản lý thật trên Langfuse.

**Version/label baseline:** v1, labels `baseline` + `production`.

**Version/label candidate:** v2 — thêm yêu cầu "trả lời tối đa 3 câu ngắn,
trích dẫn tài liệu", label `candidate`.

**Trace ID của mỗi version:**

| Bước | Label | Version | Correlation ID | Trace ID | `tokens_in` |
|---|---|---|---|---|---|
| Baseline | `baseline` | v1 | `req-9f15e93e` | `f1c386bfcece0052` | 29 |
| Candidate | `candidate` | v2 | `req-2c981162` | `9c2542fdb03391dd` | 46 |
| Sau promote | `production` | v2 | `req-ccae88bd` | `ea487f74d49e57ac` | 46 |
| Sau rollback | `production` | v1 | `req-624c2ac1` | `8430d175da7ba9fe` | 29 |

Số token đầu vào đổi theo version (29 → 46 → 46 → 29), nên việc đổi prompt là
có thật chứ không chỉ là đổi nhãn.

**Cách promote và rollback `production`:** dùng
`scripts/prompt_rollout.py promote` (gán label `production` cho version của
label `candidate`) và `rollback` (gán cho version của label `baseline`). Thao
tác dùng `Langfuse.update_prompt`, và mỗi lần gán xong script đọc lại từ
Langfuse để in version thực tế, không tin vào tên script.

Một lưu ý vận hành: app đọc `LANGFUSE_PROMPT_LABEL` từ biến môi trường của
tiến trình server tại lúc khởi động, nên phải khởi động lại uvicorn mỗi lần đổi
label. Đã kiểm chứng `--env-file` không ghi đè biến môi trường đã có.

## 6. Dashboard, SLO và alerts

**Dashboard và sáu panel:** Streamlit chạy live tại `scripts/dashboard_app.py`,
đọc `data/logs.jsonl`. Tách `app/observability.py` (logic thuần) khỏi file giao
diện để phần logic kiểm thử được bằng pytest mà không cần dựng server. Sáu
panel: latency (P50/P95/P99 + TTFT P95), traffic, errors (error rate +
retrieval success), cost, tokens, quality. Mỗi panel hiện đơn vị, time range và
ngưỡng đọc thẳng từ `config/dashboard.yaml` — không hard-code.

**SLO và lý do chọn:** `fast_successful_requests`, target 99,5% trong 28 ngày,
`good_event = response_sent and latency_ms <= 3000`. Ngưỡng 3000 ms chọn từ số
đo thật: baseline P95 là 797 ms (không báo động giả) còn khi `rag_slow` là
3130 ms (vẫn bắt được). Nó cũng khớp guardrail `latency_p95 <= 3000` trong
contract dashboard.

**Cách tính error budget:** 100% − 99,5% = **0,5%**. Trong 28 ngày với 10.000
request thì budget là 50 request. Khi P95 vượt 3000 ms như đã đo được, các
request đó không thoả `good_event` nên budget bị đốt dần.

**Ba alert và runbook tương ứng** (định nghĩa ở `config/alert_rules.yaml`,
runbook ở `docs/alerts.md`):

| Alert | Severity | Duration | Kênh |
|---|---|---|---|
| `ChatLatencyP95Burn` | critical | 10m | `#day13-oncall` |
| `RetrievalFailureSpike` | critical | 5m | `#day13-oncall` |
| `QualityProxyDegraded` | warning | 15m | `#day13-quality` |

Cả ba là symptom-based: phát biểu bằng triệu chứng người dùng (chờ lâu, không
có câu trả lời, câu trả lời kém), không gắn với tên hàm nội bộ. Mỗi runbook có
ba bước kiểm tra đầu tiên theo đúng thứ tự Metrics → Logs → Traces.

## 7. Điều tra challenge

- **Challenge ID:** _chưa có — chờ `config/challenge.json` từ Lab Coach_
- **Khoảng thời gian điều tra:** _sẽ điền sau CP3_
- **Triệu chứng từ metrics:** _sẽ điền sau CP3_
- **Log line và correlation ID liên quan:** _sẽ điền sau CP3_
- **Trace ID và span gây ảnh hưởng:** _sẽ điền sau CP3_
- **Root cause:** _sẽ điền sau CP3_
- **Fix action:** _sẽ điền sau CP3_
- **Preventive measure:** _sẽ điền sau CP3_

**Luyện tập trước bằng practice scenario `rag_slow`** (để chứng minh tôi đã nắm
được quy trình điều tra trước khi có challenge chính thức):

1. **Metric** — P95 tăng **797 ms → 3130 ms**, vượt ngưỡng SLO 3000 ms.
2. **Log** — request chậm nhất là `req-baf7f14b` với `latency_ms=3130`.
3. **Trace** — tra `correlation_id` đó trên Langfuse và so sánh span.
4. **Kết luận** — `ttft_p95` gần như không đổi (50 → 51 ms) trong khi tổng
   latency tăng gấp 4. TTFT là thời điểm token đầu tiên, tức thời gian chờ ở
   LLM; giữ nguyên TTFT đồng nghĩa độ trễ **không** nằm ở bước sinh câu trả
   lời mà nằm ở bước trước — span `retrieval`. Khớp với nguyên nhân: `rag_slow`
   làm `retrieve()` ngủ thêm 2,5 s.

## 8. Giải thích và tự đánh giá

**Một quyết định kỹ thuật quan trọng và lý do:** đổi `hash_user_id` từ
`sha256(...)[:12]` sang `"u_" + sha256(...)[:8]`. Lý do: 12 ký tự hex có thể
toàn số — ví dụ `sha256("u45")[:12] = 613933674358` — và detector CCCD
`\b\d{12}\b` của chính `validate_logs.py` sẽ khớp, trừ 30 điểm PII dù ta không
hề ghi PII. Đo được 2138/500.000 user giả bị trúng; sau khi đổi là 0/500.000.
Tiền tố chữ bảo đảm chuỗi số dài nhất chỉ 8, thấp hơn ngưỡng 10 của
`phone_vn`. Đánh đổi: entropy giảm từ 48 xuống 32 bit — chấp nhận được vì mục
đích chỉ là pseudonym để nối log, không phải chống đoán trùng lặp.

**Một lỗi/blocker đã gặp:** `client.update_current_span()` và
`update_current_generation()` của Langfuse v4 không ghi được gì — `model`,
`usage_details`, `cost_details`, `metadata` đều không tới server. Tôi cô lập
bằng script độc lập: span và cây đúng, `propagate_attributes` hoạt động, nhưng
mọi trường do `update_current_*` gán đều rỗng. Xử lý tạm thời: giữ
`capture_input=False, capture_output=False` và scrub PII trước khi đưa dữ
liệu vào trace để không rò PII, đồng thời ghi rõ giới hạn này thay vì giả vờ
đã xong. Cần kiểm tra bằng mắt trên UI.

**Cách tìm nguyên nhân và xử lý:** xem metric để biết triệu chứng và khoảng thời
gian → lọc log lấy `correlation_id` của request bất thường → tra trace có cùng
ID → so sánh thời gian các span → chỉ kết luận khi cả ba lớp cùng chỉ một
nguyên nhân. Tôi đã viết `scripts/verify_trace_join.py` để kiểm chứng bước
"nối log với trace" bằng dữ liệu thật thay vì kiểm tra bằng mắt.

**Cách hiểu luồng Metrics → Logs → Traces:** metric trả lời *có gì sai và khi
nào* nhưng không chỉ ra request nào; log trả lời *request nào* qua
`correlation_id` nhưng không chỉ ra bước nào chậm; trace trả lời *bước nào*
nhờ cây span. Trong bài này TTFT đóng vai trò phân biệt: TTFT là thời điểm
token đầu tiên nên nó đo thời gian chờ ở LLM; TTFT giữ nguyên khi latency tăng
chứng minh vấn đề nằm ở retrieval. Thiếu tín hiệu này rất dễ kết luận nhầm là
LLM chậm.

**Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành
LLM:** prompt version cho phép đổi hành vi mà vẫn truy được request nào dùng
bản nào; rollback là cơ chế đưa hệ thống về bản đã biết là tốt khi bản mới làm
giảm chất lượng. Token và cost biến động theo độ dài prompt — ở đây v1 dùng 29
token đầu vào, v2 dùng 46, nên đổi prompt kéo theo chi phí. SLO và error budget
biến cảm giác "chậm" thành con số có thể tranh luận: ngưỡng 3000 ms và budget
0,5% cho phép nói rõ khi nào sự chậm là sự cố thật.

**Điều quan trọng nhất đã học:** validator xanh không đồng nghĩa bài làm đúng.
`validate_logs.py` đạt 100/100 nếu mọi dòng log đủ trường và không còn PII thô,
nhưng nó không kiểm tra trace có span con hay không, cũng không kiểm tra trace có
nối được với log. Ba lỗi tôi gặp (hash bị detector CCCD gắn cờ,
`update_current_*` bị bỏ qua, kill server làm mất trace) đều là loại validator
không bắt được — vì vậy tôi đã thêm `verify_trace_join.py` và
`readiness_check.py` để tự kiểm chứng những phần mà validator không chạm tới.

**Hạn chế hoặc phần chưa hoàn thành:**

- Metadata span (`model`, `usage`, `cost`) chưa xác minh được qua API; cần kiểm
  bằng mắt trên UI Langfuse.
- CP3 chưa chạy vì chờ `config/challenge.json`.
- Chưa có ảnh evidence `.png` (cần đăng nhập Langfuse để chụp).
- Dashboard là bảng số liệu chứ không phải biểu đồ — cố ý để luôn đọc được tên
  panel, đơn vị, time range và threshold, vì rubric yêu cầu đọc được các thông
  tin này. Nếu muốn biểu đồ thật thì cần thêm thư viện vẽ.
- Chưa có automated test cho nội dung span Langfuse, vì SDK không trả các
  trường đó qua API.
- Phần nộp bài và commit SHA cuối còn để trống.

## 9. Checklist trước khi nộp

- [x] Kết quả và evidence thuộc commit SHA cuối
- [x] Đường dẫn tương đối mở được
- [ ] Incident evidence nối đúng metric → log → trace (chờ CP3)
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân
- [x] Repository chạy lại được theo README
- [x] Không có secret, API key hay PII thô
- [ ] Ảnh evidence `.png` đã chụp đủ
- [ ] URL repo và commit SHA cuối đã nộp trên LMS/Codelabs
