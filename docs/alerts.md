# Runbook alert — Day 13 Monitoring & LLMOps

Mỗi alert dựa trên **triệu chứng người dùng** hoặc guardrail trong
[`../config/slo.yaml`](../config/slo.yaml), không gắn với tên hàm hay module
nội bộ. Ngưỡng dưới đây lấy từ số đo thật của repo này: P95 baseline 797 ms,
P95 khi bật practice incident `rag_slow` là 3130 ms, TTFT giữ ở 50 ms.

Công cụ dùng chung khi điều tra:

| Việc | Lệnh |
|---|---|
| Xem metric tức thời | `curl -s http://127.0.0.1:8000/metrics` |
| Xem 6 panel | `streamlit run scripts/dashboard_app.py` |
| Lọc log theo sự kiện | `grep '"event": "request_failed"' data/logs.jsonl` |
| Nối log với trace | `python scripts/verify_trace_join.py` |
| Bật/tắt sự cố luyện tập | `python scripts/inject_incident.py --scenario <tên>` |

---

## Alert 1

- **Tên:** `ChatLatencyP95Burn`
- **Severity:** critical
- **Duration:** 10m (điều kiện phải giữ liên tục 10 phút mới báo)
- **Kênh thông báo:** Slack `#day13-oncall`
- **SLI/SLO liên quan:** `fast_successful_requests`, guardrail `p95 latency <= 3000 ms`
- **Điều kiện và thời gian duy trì:** `p95(response_sent.latency_ms) over 5m > 3000`
  trong 10 phút liên tục.
- **Ảnh hưởng tới người dùng:** người dùng chờ hơn 3 giây mới nhận câu trả
  lời; error budget của SLO đang bị đốt.
- **Ba bước kiểm tra đầu tiên:**
  1. *Metric* — panel `latency`: xác nhận P95 vượt 3000 ms và ghi khoảng thời
     gian. So sánh với `ttft_p95`: nếu TTFT vẫn ~50 ms trong khi latency tăng
     thì nghi vấn bước **retrieval**, không phải LLM.
  2. *Log* — lấy request chậm nhất và correlation ID của nó:
     ```bash
     grep '"event": "response_sent"' data/logs.jsonl | python -c "
     import sys, json
     rows=[json.loads(l) for l in sys.stdin if l.strip()]
     rows.sort(key=lambda r: -r.get('latency_ms',0))
     for r in rows[:3]: print(r['ts'], r['correlation_id'], r['latency_ms'], r.get('ttft_ms'))
     "
     ```
  3. *Trace* — mở Langfuse, tìm trace có cùng `correlation_id`; so sánh thời
     gian span `retrieval` với `llm-generation`. Span nào chiếm phần lớn thời
     gian chính là thủ phạm. Dùng `python scripts/verify_trace_join.py` để lấy
     trace ID ứng với từng correlation ID.
- **Mitigation tạm thời:** nếu lỗi nằm ở retrieval, cache kết quả truy xuất
  hoặc giảm `concurrency`; nếu do dữ liệu, sửa collection rồi chạy lại workload
  để xác nhận P95 trở lại dưới 3000 ms.
- **Owner:** Nguyen Trong Minh (02496)

---

## Alert 2

- **Tên:** `RetrievalFailureSpike`
- **Severity:** critical
- **Duration:** 5m
- **Kênh thông báo:** Slack `#day13-oncall`
- **SLI/SLO liên quan:** `fast_successful_requests`, guardrail `error_rate_pct_max = 2`
- **Điều kiện và thời gian duy trì:** tỉ lệ `request_failed` có
  `tool_name = "retrieval"` trên `request_received` vượt 2% trong 5 phút.
- **Ảnh hưởng tới người dùng:** câu trả lời thiếu căn cứ hoặc không được trả
  về; người dùng phải hỏi lại.
- **Ba bước kiểm tra đầu tiên:**
  1. *Metric* — panel `errors`: xem `error rate %` và `retrieval success %`;
     breakdown theo `error_type` cho biết lỗi tập trung hay rải rác.
  2. *Log* — `grep '"event": "request_failed"' data/logs.jsonl` rồi đọc
     `error_type` và `tool_success`; lấy `correlation_id` của một lỗi.
  3. *Trace* — trace của request đó có span `retrieval` với `level = ERROR`
     và `status_message = "retrieval failed"`, xác nhận lỗi nằm đúng bước
     truy xuất chứ không phải bước sinh câu trả lời.
- **Mitigation tạm thời:** trả lời bằng fallback không cần truy xuất để người
  dùng vẫn nhận được phản hồi, đồng thời giảm tải truy xuất; ghi nhận sự cố để
  sửa nguồn.
- **Owner:** Nguyen Trong Minh (02496)

---

## Alert 3

- **Tên:** `QualityProxyDegraded`
- **Severity:** warning
- **Duration:** 15m
- **Kênh thông báo:** Slack `#day13-quality`
- **SLI/SLO liên quan:** guardrail `quality_score_avg_min = 0.75`
- **Điều kiện và thời gian duy trì:** `mean(response_sent.quality_score) over 15m < 0.75`
  trong 15 phút liên tục.
- **Ảnh hưởng tới người dùng:** câu trả lời vẫn trả về nhưng nội dung kém,
  người dùng phải hỏi lại nhiều lần.
- **Ba bước kiểm tra đầu tiên:**
  1. *Metric* — panel `quality`: xác nhận mean dưới 0,75 và thời điểm bắt
     đầu suy giảm.
  2. *Log* — đối chiếu `tokens_in` trước và sau mốc thời gian đó; nếu
     `tokens_in` tăng đột ngột thì nghi vấn prompt dài hơn làm loãng ngữ cảnh.
  3. *Trace* — kiểm tra metadata `prompt_name` / `prompt_version` /
     `prompt_label` trên các trace trong khoảng đó. Nếu version vừa được
     promote lên `production` thì đây là nghi vấn số một.
- **Mitigation tạm thời:** rollback prompt về version đã biết là tốt bằng
  `python scripts/prompt_rollout.py rollback`, rồi chạy lại workload để xác
  nhận quality mean trở lại trên 0,75.
- **Owner:** Nguyen Trong Minh (02496)

---

## Liên kết

- Định nghĩa alert: [`../config/alert_rules.yaml`](../config/alert_rules.yaml)
- SLO và error budget: [`../config/slo.yaml`](../config/slo.yaml)
- Contract dashboard 6 panel: [`../config/dashboard.yaml`](../config/dashboard.yaml)
