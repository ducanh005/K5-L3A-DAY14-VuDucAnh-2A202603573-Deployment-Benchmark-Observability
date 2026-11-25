# Benchmark & Observability Report — Day 14

**Họ tên:** Vu Duc Anh (MSSV: 2A202603573)  
**Ngày chạy:** 2026-11-25  
**Môi trường:** Windows 11 + Ubuntu 26.04 LTS (WSL2) + Docker Desktop 29.7.2

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | ≤ 500 ms | Với `MOCK_LATENCY_MS=120` + `MOCK_RETRIEVAL_MS=20` + jitter, 95% request bình thường hoàn tất quanh ~200–240 ms; ngưỡng 500 ms đủ biên độ an toàn cho jitter nhưng vẫn bắt được suy giảm tail latency khi `MOCK_SLOW_RATE` tăng hoặc nghẽn event loop |
| Error rate `/ask` | ≤ 2.0 % | Mock LLM có tỷ lệ lỗi nền `MOCK_ERROR_RATE=0.01` (1%); ngưỡng 2% cho error budget vừa đủ cho nhiễu ngẫu nhiên nhỏ, đồng thời cảnh báo sớm khi upstream gặp sự cố diện rộng |
| Accuracy trên golden dataset | ≥ 85 % (mục tiêu sau sửa KB: 100%, 0 regression) | Đảm bảo chất lượng RAG của agent v2 vượt xa baseline v1 và không làm hỏng các câu đã đúng ở bản trước |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

*(Dữ liệu từ `reports/load_v2_c1.json`, `load_v2_c10.json`, `load_v2_c50.json`, `load_v2_c100.json`, mỗi mức 300 requests, SLO: `p95 ≤ 500 ms` và `error_rate ≤ 2.0%`.)*

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 4.54 | 191.0 | 220.2 | 1700.6 | 2.67% (8/300) | ❌ FAIL (error rate > 2%) |
| 10 | 43.74 | 187.8 | 215.7 | 267.8 | 0.67% (2/300) | ✅ PASS |
| 50 | 111.33 | 191.0 | 235.2 | 1690.5 | 0.33% (1/300) | ✅ PASS |
| 100 | 100.58 | 245.2 | 1082.7 | 1735.1 | 0.00% (0/300) | ❌ FAIL (p95 > 500ms) |

**Nhận xét:** RPS **không tăng tuyến tính** theo concurrency: tăng nhanh từ `4.54` (`c=1`) lên `43.74` (`c=10`) và đạt đỉnh `111.33 req/s` (`c=50`), nhưng đến `c=100` thì giảm nhẹ xuống `100.58 req/s` trong khi `p95` nhảy vọt từ `235.2 ms` lên `1082.7 ms`. Nguyên nhân là khi vượt quá khả năng xử lý đồng thời của 1 process uvicorn + giới hạn kết nối/event loop scheduling, các request phải xếp hàng chờ lâu hơn (queueing delay) làm tăng tail latency và kéo throughput đi xuống.

### 2.2 Tail latency (`--requests 300 --concurrency 20`)

*(Dữ liệu từ `reports/load_v2_slow_0.json`, `reports/load_v2_slow_0.03.json`, `reports/load_v2_slow_0.1.json`.)*

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) | RPS | SLO |
|---|---:|---:|---:|---:|---|
| 0 | 189.8 | 216.3 | 220.8 | 102.17 | ✅ PASS |
| 0.03 (mặc định) | 259.5 | 224.1 | 1704.6 | 57.53 | ✅ PASS |
| 0.1 | 311.9 | 1685.8 | 1710.6 | 50.12 | ❌ FAIL |

**Nhận xét:** **p99** (và **p95** khi tỷ lệ chậm vượt 5%, ở mức `0.1`) là chỉ số nhạy nhất với các request chậm bất thường: từ `0` lên `0.03`, `avg` chỉ tăng từ `189.8 ms` lên `259.5 ms` (+36.7%) trong khi `p99` nhảy vọt gần **8 lần** (từ `220.8 ms` lên `1704.6 ms`); đến `0.1`, ngay cả `p95` cũng vọt lên `1685.8 ms`. SLO không nên đặt theo **average** vì phần đa số request nhanh sẽ che lấp trải nghiệm tệ của nhóm 1–5% người dùng phải chờ gần 2 giây.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

*(Dữ liệu từ `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json` trên 23 câu `golden_dataset.jsonl`.)*

| Chỉ số | Agent v1 (`eval_v1.json`) | Agent v2 (`eval_v2.json`) | Agent v2 sau khi sửa KB (`eval_v2_fixed.json`) |
|---|---:|---:|---:|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 56.3 | 109.0 | 113.7 |
| Tổng cost (USD) | $0.000394 | $0.000760 | $0.000790 |
| Cost / câu đúng (USD) | $0.00039375 | $0.00003619 | $0.00003436 |
| Quality gate | ❌ FAIL | ✅ PASS (min 80%) | ✅ PASS (min 100%, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách sửa:**

| ID | Keyword bị thiếu | Đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry kiến thức về so sánh API key và **JWT** (token có chữ ký số, thời điểm hết hạn) vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`) |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry kiến thức về **Kubernetes HPA** (Horizontal Pod Autoscaler scale theo CPU, memory, custom metrics) vào `KNOWLEDGE_BASE` |

**Quality gate & CI job (`.github/workflows/eval.yml`):**
- Khi chạy thử `eval/run_eval.py` cho `v1` với `--baseline reports/eval_v2.json`, script phát hiện 20 câu bị regression (`accuracy = 4.3%`) và trả **exit code `1`**, chặn merge trên CI.
- Đã cấu hình CI workflow tại [`.github/workflows/eval.yml`](.github/workflows/eval.yml) chạy `python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85` trên mỗi Pull Request.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**  
Agent v2 thêm bước retrieval (RAG) nên `avg tokens/câu` tăng gần gấp đôi (`56.3` → `113.7`), `p95 latency` tăng nhẹ ~25 ms (`188.1 ms` → `212.9 ms`), và tổng chi phí tăng gấp đôi (`$0.000394` → `$0.000790`). Tuy nhiên, accuracy tăng từ `4.3%` lên `100.0%`, kéo **`cost / câu đúng` giảm hơn 11 lần** (`$0.00039375` xuống `$0.00003436`), hoàn toàn xứng đáng với chi phí bỏ ra.

---

## 4. Observability stack (production)

### 4.1 Screenshot & Kiểm tra hệ thống

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): [screenshots/grafana-dashboard.png](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger (span `chat mock-llm-small` chiếm 98.5%): [screenshots/jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (status `503`, icon lỗi tại `chat mock-llm-small`): [screenshots/jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với 3 alert cùng đang **firing**: [screenshots/prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

**Trả lời câu hỏi Exercise 7.1 & 7.4:**
- **Exercise 7.1 (`develop/app.py`):** Thêm `QUESTION_LENGTH = Histogram("agent_question_length_chars", ...)` thay vì gắn label để tránh bùng nổ cardinality. Dùng `route.path` (template) thay cho `request.url.path` để bot quét nghìn URL lạ (`/wp-admin`, `/.env`, ...) đều gom vào nhóm `unmatched`, không làm tràn RAM Prometheus.
- **Exercise 7.4 (quan sát Prometheus/Grafana trong lúc chạy tải):**
  1. Trong cụm 5 phút chạy tải (`scale_1` & `scale_3`), Prometheus đo `p95 ≈ 293.1 ms` và `avg ≈ 231.8 ms`; khoảng chênh lệch phản ánh phần tail latency ~3% request chậm `>1.7s` kéo đường trung bình lên.
  2. Panel *Requests/s theo instance* chia đều lưu lượng giữa các instance đang chạy song song (ví dụ trong cửa sổ 5m với `agent-2` và `agent-3` cùng khởi chạy ở `scale_3`: `8.23 req/s` vs `8.16 req/s`).
  3. `input tokens/s` (`~3719.6 tok/s`) lớn hơn `output tokens/s` (`~1943.2 tok/s`) vì với RAG (v2), mỗi prompt gửi vào LLM luôn kèm `SYSTEM_PROMPT` + đoạn context dài lấy từ `KNOWLEDGE_BASE`, còn câu trả lời sinh ra ngắn hơn.
  4. `curl -i http://localhost:8080/metrics` trả về **`404 Not Found`** vì Nginx chặn/không proxy endpoint `/metrics` ra ngoài public, chỉ mạng nội bộ `obs_net` cho phép Prometheus scrape trực tiếp container agent.
- **Unit test alert rules (`promtool`):** `docker run ... prom/prometheus:v3.16.0 test rules /p/alert_rules_test.yml` đạt `SUCCESS`.

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---:|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`for: 1m`) | 88 s | **Error rate** (Golden Signals) & **Requests/s theo status code** (`503`) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`for: 2m`) | 158 s | **Latency p95** & **Latency /ask — p50 / p95 / p99** |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`for: 2m`) | 27 s *(đã tích luỹ vượt \$2/giờ từ tải cao và tiếp tục firing ở mức đốt chi phí cao với model large)* | **LLM cost (1h)** & **Cost burn rate (USD/giờ)** |
| D | `docker pause` `k5-day14-observability-agent-1` | `AgentInstanceDown` (`for: 30s`) | 45 s | **Instances up** & **Requests/s theo instance** |
| E | `AGENT_VERSION=v1` | Không có alert nào firing | — | **Retrieval hit ratio (agent v2)** (tụt/biến mất) & bảng **version** đang chạy |

**Thí nghiệm E không làm alert nào firing. Phát hiện loại sự cố này trong production bằng cách nào?**  
Các metric hạ tầng (CPU, latency, HTTP 200) vẫn hoàn toàn xanh khi agent tụt chất lượng. Để phát hiện sớm cần kết hợp:
1. **CI Quality Gate trước khi deploy:** Chạy `eval/run_eval.py` trên `golden_dataset.jsonl` để chặn mọi phiên bản làm giảm accuracy hoặc gây regression.
2. **Giám sát đặc thù cho RAG/LLM ở production:** Theo dõi `retrieval_hit_ratio` (tụt khi v1/RAG lỗi), chạy **online LLM-as-a-judge** trên một tỷ lệ mẫu (sampling) traffic thật, và thu thập **phản hồi người dùng** (thumbs up/down).

### 4.3 Debug bằng trace

**Trace chậm nhất tìm được (Jaeger UI & JSON logs):**
- `trace_id`: `3db9a6919d21175e011704337e08a99d`
- Tổng thời gian (`POST /ask`): `1724.76 ms` (`agent.run`: `1723.58 ms`)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (`1699.06 ms`, chiếm **`98.5%`** tổng thời gian; còn `agent.retrieve_context` chỉ mất `24.37 ms` = `1.4%` → chứng tỏ nút thắt nằm ở lời gọi LLM upstream, không phải bước retrieval hay code FastAPI).
- Dòng log tương ứng (lấy từ `docker compose -p k5-day14-observability logs agent` theo `trace_id`):

```json
{"ts": "2026-11-25T10:56:52.784439+00:00", "level": "INFO", "service": "observable-agent", "instance": "0655f92bdd02", "event": "llm_call", "trace_id": "3db9a6919d21175e011704337e08a99d", "span_id": "53719c4e8479fdc2", "request_id": "dd65afb81fb1", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1697.8}
```

**Trace lỗi đối chiếu thêm (`503 Service Unavailable`):**
- `trace_id`: `33670f9e10416251a8667c4284218f68` (tổng `107.23 ms`, `chat mock-llm-small`: `86.63 ms`)
- Dòng log tương ứng:

```json
{"ts": "2026-11-25T10:51:05.144301+00:00", "level": "INFO", "service": "observable-agent", "instance": "4539cf2e8c82", "event": "llm_error", "trace_id": "33670f9e10416251a8667c4284218f68", "span_id": "242d9b55d415ab44", "request_id": "09395785c454", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

*(Số liệu đối chiếu trực tiếp từ `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv` — hiển thị cả dòng `Aggregated` và `POST /ask`.)*

| Số instance | RPS (`Aggregated` / `POST /ask`) | p50 (ms) | p95 (ms) (`Aggregated` / `POST /ask`) | p99 (ms) | Failures (`Aggregated` / `POST /ask`) |
|---:|---|---:|---|---:|---|
| 1 | 66.05 / 60.57 | 190 | 220 / 230 | 1700 | 88 (1.11%) / 88 (1.21%) |
| 3 | 65.87 / 59.72 | 190 | 220 / 220 | 1700 | 68 (0.86%) / 68 (0.95%) |

**Giải thích kết quả:**  
Khi scale từ 1 lên 3 instance với kịch bản 100 user của Locust (`wait_time` nghỉ ngẫu nhiên giữa các request), `RPS` (~66 req/s) và `p50/p95/p99` (`190 / 220 / 1700 ms`) gần như **không đổi** (`POST /ask` p95 giảm nhẹ từ `230 ms` xuống `220 ms`). Có 2 nguyên nhân chính:
1. **Nút thắt nằm ở thời gian chờ I/O của LLM (`~190 ms` bình thường, `~1700 ms` slow request):** Các worker FastAPI chạy `async`/`await` không bị nghẽn CPU ở mức ~66 req/s, nên bản thân 1 instance chưa bị bão hòa CPU; thêm instance không thể làm 1 lần gọi LLM upstream chạy nhanh hơn.
2. **Tốc độ sinh tải bị chặn trần bởi số user (100) + thời gian nghỉ của Locust:** Để thấy rõ lợi ích tăng throughput khi scale ngang (x3 capacity), cần tải đồng thời lớn hơn nhiều hoặc tác vụ xử lý nặng CPU trên server.

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. **Trung bình đánh lừa, percentile (p95/p99) nói thật:** Một tỷ lệ nhỏ (3%) request chậm có thể làm `p99` gấp 8 lần trong khi `average` gần như bình thường; SLO luôn phải đặt theo p95/p99.
  2. **Chất lượng phải đo tách biệt với hạ tầng:** Hệ thống có thể đạt uptime 100% và latency xanh nhưng trả lời sai hoàn toàn (v1 chỉ đạt 4.3% vs v2 100%); chỉ `golden_dataset` + CI quality gate mới chặn được regression.
  3. **Metrics, Traces và Logs bổ trợ lẫn nhau:** Prometheus/Grafana báo *có biến* (p95 hay error rate tăng), Jaeger chỉ ra *bước nào chậm/lỗi* (`chat mock-llm-small` chiếm 98.5%), và `trace_id` giúp truy thẳng ra dòng log JSON chứa chi tiết request.
- **Nếu đưa agent này lên production thật, sẽ thêm metric / alert nào nữa?**
  - **Metric:** `retrieval_hit_ratio` & `retrieval_score_bucket` (theo dõi chất lượng RAG theo thời gian thực), `redis_latency_seconds` và `rate_limit_rejected_total` / `budget_rejected_total` (đếm 429/402), cùng chỉ số **HTTP 5xx từ tầng Nginx/Ingress** (tránh mù lỗi 504 timeout như bài D).
  - **Alert:** Cảnh báo **chất lượng/RAG suy giảm** (retrieval hit ratio tụt đột ngột), cảnh báo **Redis down / latency cao**, và **burn-rate alert** nhiều cửa sổ thời gian cho error budget.
