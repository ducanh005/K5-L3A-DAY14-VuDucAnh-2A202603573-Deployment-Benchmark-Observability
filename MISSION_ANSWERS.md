# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

Các anti-pattern tìm thấy trong `01-localhost-vs-production/develop/app.py`:

1. **Hardcode secrets trong source code (`app.py`, dòng 17–18):**
   ```python
   OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"
   DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"
   ```
   Nếu đẩy code lên GitHub public, API key và mật khẩu database bị lộ ngay lập tức (kể cả trong lịch sử Git).

2. **Hardcode cấu hình ứng dụng trong code (`app.py`, dòng 21–22):**
   ```python
   DEBUG = True
   MAX_TOKENS = 500
   ```
   Không thể thay đổi cấu hình giữa các môi trường (`development`, `staging`, `production`) nếu không sửa code và build/deploy lại.

3. **Dùng `print()` thay cho structured logging và in trực tiếp secret ra stdout (`app.py`, dòng 33–38):**
   ```python
   print(f"[DEBUG] Got question: {question}")
   print(f"[DEBUG] Using key: {OPENAI_API_KEY}")  # ❌ log ra secret!
   ```
   Vừa làm rò rỉ `OPENAI_API_KEY` vào log hệ thống, vừa không có timestamp/log level/JSON format để công cụ log aggregator thu thập và tìm kiếm.

4. **Thiếu health check và readiness endpoint (`app.py`, dòng 42–43):**
   Không có `GET /health` (liveness) hay `GET /ready` (readiness). Nền tảng cloud hoặc load balancer không biết container còn sống hay đã sẵn sàng nhận traffic để tự restart hoặc định tuyến.

5. **Hardcode `host="localhost"`, `port=8000` và bật `reload=True` (`app.py`, dòng 49–54):**
   ```python
   uvicorn.run(
       "app:app",
       host="localhost",   # ❌ chỉ nhận kết nối nội bộ
       port=8000,          # ❌ cứng port
       reload=True         # ❌ debug reload trong production
   )
   ```
   - `host="localhost"` khiến container không nhận được traffic từ bên ngoài.
   - `port=8000` cố định gây lỗi trên Railway/Render vốn cấp phát port động qua biến môi trường `PORT`.
   - `reload=True` tiêu tốn tài nguyên theo dõi file và có thể làm app restart ngoài ý muốn trên production.

6. **Không xử lý graceful shutdown (`SIGTERM`):**
   Không có `lifespan` hay signal handler cho `SIGTERM`. Khi platform dừng hoặc rolling-update container, server tắt đột ngột và cắt ngang các request đang xử lý dở.

7. **Nhận input qua query string và thiếu kiểm soát request/CORS:**
   Endpoint `POST /ask` nhận `question: str` qua query parameter (`?question=Hello`), không đọc JSON body có validation rõ ràng và không cấu hình CORS hay fail-fast validation khi thiếu biến môi trường production.

---

### Exercise 1.2: Chạy phiên bản `develop`

Lệnh chạy trong Ubuntu WSL2 (`01-localhost-vs-production/develop/`):

```bash
python app.py
curl -i http://localhost:8000/
curl -i -X POST "http://localhost:8000/ask?question=Hello"
```

**Kết quả trả về:**

```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:17:24 GMT
server: uvicorn
content-length: 54
content-type: application/json

{"message":"Hello! Agent is running on my machine :)"}
```

```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:17:24 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

**Log stdout quan sát được trên server:**

```text
Starting agent on localhost:8000...
INFO:     Started server process [1544]
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
[DEBUG] Response: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.
INFO:     127.0.0.1:56780 - "POST /ask?question=Hello HTTP/1.1" 200 OK
```

**Nhận xét:** Ứng dụng chạy tốt trên `localhost:8000`, nhưng để lộ trực tiếp `OPENAI_API_KEY` ra stdout và không sẵn sàng để đưa lên container/cloud.

---

### Exercise 1.3: So sánh `develop` vs `production`

#### Kết quả chạy thử bản `production` (`01-localhost-vs-production/production/app.py`):

```bash
python app.py
curl -i http://localhost:8000/health
curl -i http://localhost:8000/ready
curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question": "Hello"}'
```

```http
HTTP/1.1 200 OK
content-type: application/json

{"status":"ok","uptime_seconds":0.4,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T08:17:26.584342+00:00"}
```

```http
HTTP/1.1 200 OK
content-type: application/json

{"ready":true}
```

```http
HTTP/1.1 200 OK
content-type: application/json

{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","model":"gpt-4o-mini"}
```

#### Bảng so sánh chi tiết

| Feature | Develop (`develop/app.py`) | Production (`production/app.py` & `config.py`) | Tại sao quan trọng? |
|---|---|---|---|
| **Config & Secrets** | Hardcode `OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG`, `MAX_TOKENS` trực tiếp trong `app.py` (dòng 17–22) | Đọc tập trung từ biến môi trường qua `Settings` (`os.getenv(...)` trong `config.py`), có `validate()` fail-fast nếu `ENVIRONMENT=production` mà thiếu `AGENT_API_KEY` | Tách biệt config khỏi code theo 12-Factor App; đổi cấu hình giữa dev/staging/prod không cần sửa code và tránh lộ secret lên Git |
| **Host & Port** | Cố định `host="localhost"`, `port=8000`, `reload=True` (`app.py`, dòng 51–53) | Đọc `HOST` (mặc định `0.0.0.0`), `PORT` (mặc định `8000`), `DEBUG` (mặc định `false`) từ env | Trong Docker và cloud (Railway/Render), app phải lắng nghe `0.0.0.0` và nhận `PORT` do nền tảng cấp động; tắt `reload` để ổn định hiệu năng |
| **Health & Readiness** | Không có `/health` hay `/ready` | Có `GET /health` (liveness, trả uptime/version/timestamp) và `GET /ready` (readiness, kiểm tra `is_ready`, trả `503` khi chưa sẵn sàng) | Platform dựa vào `/health` để restart container treo, còn load balancer dựa vào `/ready` để chỉ đẩy traffic khi app đã khởi tạo xong |
| **Logging** | Dùng `print("[DEBUG] ...")` và in luôn cả `OPENAI_API_KEY` (`app.py`, dòng 33–38) | Cấu hình `logging.basicConfig` định dạng JSON và log event bằng `json.dumps(...)` (`app.py`, dòng 28–32, 49–55, 111–122), không ghi secret | Log JSON có cấu trúc giúp Datadog/Loki/CloudWatch parse và lọc lỗi nhanh, đồng thời đảm bảo an toàn thông tin nhạy cảm |
| **Graceful Shutdown** | Không xử lý `SIGTERM`, tắt ngang khi dừng process | Dùng `lifespan` (`app.py`, dòng 39–68) đặt `is_ready = False` khi shutdown và đăng ký `signal.signal(signal.SIGTERM, handle_sigterm)` (dòng 180–189) | Khi scale-down hoặc deploy phiên bản mới, container ngừng nhận request mới nhưng vẫn hoàn thành các request đang xử lý trước khi thoát |
| **API Contract & CORS** | `POST /ask` nhận `question` qua query param, không có CORS middleware | `POST /ask` đọc JSON body và trả `422` nếu thiếu `question`; cấu hình `CORSMiddleware` theo `ALLOWED_ORIGINS` (`app.py`, dòng 77–82, 102–108) | Chuẩn hóa REST JSON API, báo lỗi rõ ràng cho client và giới hạn origin được phép gọi từ trình duyệt |

*(Ghi chú kỹ thuật khi chạy thực tế `production/app.py`: hàm `Settings().validate()` ở dòng 50 của `config.py` gọi `logging.warning(...)` trước khi `app.py` gọi `logging.basicConfig(...)` ở dòng 28, nên root logger được khởi tạo mặc định trước và không áp dụng format JSON của `basicConfig` trừ khi cấu hình handler riêng — đây là điểm cần chú ý khi viết logger cho Part 6.)*

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

Đọc `02-docker/develop/Dockerfile`:

1. **Base image là gì?**  
   `python:3.11` (dòng 8: `FROM python:3.11`) — image Python đầy đủ dựa trên Debian, bao gồm trình thông dịch Python cùng nhiều công cụ build/OS packages (~1 GB trở lên).
2. **Working directory là gì?**  
   `/app` (dòng 11: `WORKDIR /app`). Mọi lệnh `COPY`, `RUN`, `CMD` phía sau đều thực thi tương đối từ thư mục `/app` trong container.
3. **Tại sao `COPY requirements.txt` đứng trước `COPY . .` / copy source code?**  
   Để tận dụng **Docker layer cache**. Các dependencies trong `requirements.txt` ít thay đổi hơn source code rất nhiều. Khi đặt `COPY 02-docker/develop/requirements.txt .` và `RUN pip install ...` lên trước `COPY 02-docker/develop/app.py .`, nếu chỉ sửa code Python mà không đổi `requirements.txt`, Docker sẽ dùng lại layer đã cài pip trước đó thay vì tải và cài lại toàn bộ thư viện.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?**  
   - `CMD` đặt lệnh mặc định hoặc tham số mặc định khi container khởi chạy, và **có thể bị ghi đè dễ dàng** bằng cách truyền lệnh mới ở cuối `docker run <image> <cmd>`.
   - `ENTRYPOINT` cố định executable chính của container (khó bị ghi đè trừ khi truyền `--entrypoint`); nếu dùng cả hai, `CMD` sẽ đóng vai trò làm tham số mặc định truyền vào cho `ENTRYPOINT`.

---

### Exercise 2.2: Build và chạy container `develop`

Build từ gốc repo và chạy container:

```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d --name cp2-dev -p 8000:8000 my-agent:develop
curl -i http://localhost:8000/health
curl -i -X POST "http://localhost:8000/ask?question=What%20is%20Docker%3F"
```

**Kết quả thực tế:**

```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:31:36 GMT
server: uvicorn
content-length: 53
content-type: application/json

{"status":"ok","uptime_seconds":0.4,"container":true}
```

```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:31:36 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

---

### Exercise 2.3: Multi-stage build & so sánh kích thước image

Phân tích `02-docker/production/Dockerfile`:

- **Stage 1 (`builder`):** Dùng `FROM python:3.11-slim AS builder`, cài `gcc` và `libpq-dev` để biên dịch các package Python cần C-extension, rồi chạy `pip install --no-cache-dir --user -r requirements.txt` vào `/root/.local`.
- **Stage 2 (`runtime`):** Bắt đầu lại từ image sạch `FROM python:3.11-slim AS runtime`, tạo user non-root `appuser`, chỉ dùng `COPY --from=builder /root/.local /home/appuser/.local` để chép thư viện đã cài, copy `main.py` và `utils/mock_llm.py`, cấu hình `HEALTHCHECK`, chuyển sang `USER appuser` và chạy `uvicorn` với 2 workers.
- **Tại sao image nhỏ hơn và an toàn hơn:** Stage cuối không chứa `gcc`, `libpq-dev`, apt cache hay các file trung gian lúc build, đồng thời sử dụng base `python:3.11-slim` thay cho `python:3.11` đầy đủ và chạy dưới quyền non-root `appuser` giúp giảm bề mặt tấn công.

**Số đo kích thước thực tế trên máy (`docker images my-agent`):**

```text
REPOSITORY   TAG        SIZE
my-agent     advanced   240MB
my-agent     develop    1.67GB
```

- **Develop (`my-agent:develop`):** `1.67 GB` (`1670 MB`)
- **Production (`my-agent:advanced`):** `240 MB`
- **Chênh lệch:** Giảm **`1.43 GB`** (nhỏ hơn khoảng **`85.6%`**).

---

### Exercise 2.4: Docker Compose stack

**Sơ đồ kiến trúc (`02-docker/production/docker-compose.yml`):**

```text
┌────────┐   HTTP :80 / :443   ┌──────────────┐   proxy_pass    ┌─────────────────┐
│ Client │ ──────────────────▶ │ Nginx (LB)   │ ──────────────▶ │ Agent (FastAPI) │
└────────┘                     │ nginx:alpine │   (port 8000)   │ 2 workers       │
                               └──────────────┘                 └───────┬─────────┘
                                                                        │
                                             ┌──────────────────────────┴──────────────────────────┐
                                             ▼                                                     ▼
                                    ┌─────────────────┐                                   ┌─────────────────┐
                                    │  Redis (:6379)  │                                   │ Qdrant (:6333)  │
                                    │  redis:7-alpine │                                   │ qdrant:v1.9.0   │
                                    └─────────────────┘                                   └─────────────────┘
                                                (Tất cả kết nối qua bridge network `internal`)
```

**Các services và cách giao tiếp:**
- `redis` (`redis:7-alpine`) & `qdrant` (`qdrant/qdrant:v1.9.0`): chạy trong mạng nội bộ `internal`, lưu dữ liệu bền vững vào volumes (`redis_data`, `qdrant_data`) và có `healthcheck`.
- `agent` (build target `runtime` từ `02-docker/production/Dockerfile`): không mở port trực tiếp ra host; chờ `redis` và `qdrant` healthy (`depends_on: condition: service_healthy`), giao tiếp qua DNS nội bộ `redis://redis:6379/0` và `http://qdrant:6333`.
- `nginx` (`nginx:alpine`): mở port `80` và `443` ra host, áp dụng security headers (`X-Frame-Options`, `X-Content-Type-Options`, `X-XSS-Protection`) và rate limiting (`10r/s`, `burst=20`), reverse proxy vào `agent:8000`.

**Chạy stack và kiểm tra qua Nginx:**

```bash
touch 02-docker/production/.env.local
docker compose -p k5-day14-docker up -d --build
docker compose -p k5-day14-docker ps
curl -i http://localhost/health
curl -i -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question": "Explain microservices"}'
docker compose -p k5-day14-docker down -v
```

**Trạng thái `docker compose ps`:**

```text
NAME                       IMAGE                   SERVICE   STATUS                           PORTS
k5-day14-docker-agent-1    k5-day14-docker-agent   agent     Up 1 second (health: starting)   8000/tcp
k5-day14-docker-nginx-1    nginx:alpine            nginx     Up 1 second                      0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
k5-day14-docker-qdrant-1   qdrant/qdrant:v1.9.0    qdrant    Up 12 seconds (healthy)          6333-6334/tcp
k5-day14-docker-redis-1    redis:7-alpine          redis     Up 12 seconds (healthy)          6379/tcp
```

**Kết quả test qua Nginx:**

```http
HTTP/1.1 200 OK
Server: nginx
Date: Wed, 25 Nov 2026 08:36:38 GMT
Content-Type: application/json
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":0.5,"version":"2.0.0","timestamp":"2026-11-25T08:36:38.931655"}
```

```http
HTTP/1.1 200 OK
Server: nginx
Date: Wed, 25 Nov 2026 08:36:39 GMT
Content-Type: application/json
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

---

## Part 4: API Security

### Exercise 4.1: API Key authentication

Đọc và chạy `04-api-gateway/develop/app.py` với `AGENT_API_KEY=secret-key-123`:

1. **API key được kiểm tra ở đâu?**  
   Tại dependency `verify_api_key` (`04-api-gateway/develop/app.py`, dòng 39–54) sử dụng `APIKeyHeader(name="X-API-Key", auto_error=False)` (dòng 36) và gắn vào endpoint qua `_key: str = Depends(verify_api_key)` (dòng 70). So sánh với biến môi trường `AGENT_API_KEY` (dòng 35).
2. **Điều gì xảy ra nếu thiếu hoặc sai key?**  
   - Thiếu header `X-API-Key` → trả `401 Unauthorized` (`Missing API key...`).
   - Sai giá trị `X-API-Key` → trả `403 Forbidden` (`Invalid API key.`).
3. **Làm sao rotate key an toàn (zero-downtime)?**  
   Hỗ trợ nhiều key hợp lệ cùng lúc (ví dụ biến môi trường `AGENT_API_KEYS` chứa cả key cũ và key mới, phân cách bằng dấu phẩy), cấp key mới cho client chuyển sang dùng, xác nhận không còn traffic gọi bằng key cũ rồi mới xóa key cũ khỏi biến môi trường và restart service.

**Kết quả test thực tế (`curl -i`):**

```http
# Không có X-API-Key → 401
HTTP/1.1 401 Unauthorized
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

```http
# Sai X-API-Key → 403
HTTP/1.1 403 Forbidden
content-type: application/json

{"detail":"Invalid API key."}
```

```http
# Đúng X-API-Key → 200
HTTP/1.1 200 OK
content-type: application/json

{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

---

### Exercise 4.2: JWT authentication (Advanced)

**Luồng hoạt động (`04-api-gateway/production/auth.py` & `app.py`):**
1. Client gửi `POST /auth/token` kèm `username` / `password` (`student` / `demo123`).
2. Server xác thực bằng `authenticate_user`, dùng `create_token` ký JWT bằng thuật toán `HS256` (`SECRET_KEY` từ `JWT_SECRET`) với payload chứa `sub`, `role`, `iat`, `exp` (hết hạn sau 60 phút).
3. Khi gọi `POST /ask`, client gửi header `Authorization: Bearer <token>`. Dependency `verify_token` dùng `HTTPBearer(auto_error=False)` để giải mã, kiểm tra chữ ký và thời hạn token; thiếu token trả `401`, hết hạn trả `401`, chữ ký không hợp lệ trả `403`.

**Kết quả test thực tế (`curl -i`):**

```http
# Thiếu token → 401
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}
```

```text
POST /auth/token (student/demo123) → Token: eyJhbGciOiJIUzI1Ni...[REDACTED]
```

```http
# Có JWT hợp lệ (Request #1) → 200
HTTP/1.1 200 OK
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Test 1","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}
```

---

### Exercise 4.3: Rate limiting

Đọc `04-api-gateway/production/rate_limiter.py`:

1. **Thuật toán được dùng:** **Sliding Window Counter / Sliding Window Log** (`RateLimiter.check`, dòng 29–71) — lưu hàng đợi `deque` các timestamp cho mỗi `user_id`, loại bỏ timestamp cũ hơn `now - window_seconds` rồi kiểm tra `len(window) >= max_requests`.
2. **Giới hạn hiện tại:**
   - User thường (`rate_limiter_user`): `10 requests / 60 giây`.
   - Admin (`rate_limiter_admin`): `100 requests / 60 giây`.
3. **Cách phân quyền / nâng giới hạn cho admin:**  
   Trong `app.py` (dòng 141), đọc `role = user["role"]` trích từ JWT để chọn `limiter = rate_limiter_admin if role == "admin" else rate_limiter_user` (hoặc có thể bỏ qua bước gọi `limiter.check()` nếu `role == "admin"`).

**Kết quả chạy vòng lặp 12 requests với tài khoản `student` (limit 10 req/phút):**

```text
Request #1  -> HTTP/1.1 200 OK
Request #2  -> HTTP/1.1 200 OK
...
Request #10 -> HTTP/1.1 200 OK
Request #11 -> HTTP/1.1 429 Too Many Requests
Request #12 -> HTTP/1.1 429 Too Many Requests
```

**Output đầy đủ khi chạm ngưỡng `429` (Request #11):**

```http
HTTP/1.1 429 Too Many Requests
date: Wed, 25 Nov 2026 08:45:08 GMT
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795596368
retry-after: 59
content-length: 98
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

---

### Exercise 4.4: Cost guard

**Cơ chế trong `04-api-gateway/production/cost_guard.py`:**
- Quy đổi số `input_tokens` và `output_tokens` thành chi phí USD theo đơn giá (`PRICE_PER_1K_INPUT_TOKENS = 0.00015`, `PRICE_PER_1K_OUTPUT_TOKENS = 0.0006`).
- Đặt 2 tầng ngân sách theo ngày: per-user (`$1.0/ngày` → vượt sẽ trả `402 Payment Required`) và toàn hệ thống (`$10.0/ngày` → vượt sẽ trả `503 Service Unavailable`), đồng thời log cảnh báo ở ngưỡng `80%`.
- `GET /me/usage` sau 10 requests của `student`:

```http
HTTP/1.1 200 OK
content-type: application/json

{"user_id":"student","date":"2026-11-25","requests":10,"input_tokens":40,"output_tokens":284,"cost_usd":0.000176,"budget_usd":1.0,"budget_remaining_usd":0.999824,"budget_used_pct":0.0}
```

**Thiết kế Cost Guard bằng Redis cho môi trường production (stateless, multi-worker):**
- Bản mẫu dùng dict `_records` trong RAM sẽ bị mất khi restart và không đồng bộ giữa các worker/instance.
- Ở production (và trong Part 6), lưu tổng chi phí vào Redis với key theo chu kỳ thời gian (ví dụ `budget:{user_id}:{YYYY-MM-DD}` hoặc theo tháng `budget:{user_id}:{YYYY-MM}`):
  1. **Trước khi gọi LLM (`check_budget`):** đọc `float(r.get(key) or 0)`, nếu `>= budget_limit` (hoặc `current + estimated_cost > budget_limit`) thì trả `402 Payment Required`.
  2. **Sau khi gọi LLM (`record_cost`):** tính chi phí thực tế từ token và cộng dồn bằng lệnh atomic `r.incrbyfloat(key, cost)`, đặt `r.expire(key, ...)` để tự động reset khi sang chu kỳ mới.
- **Vì sao cần cả Rate Limit và Cost Guard?** Rate limit giới hạn **tần suất gọi** (số request/phút) để chống quá tải hệ thống, còn Cost Guard giới hạn **tổng chi phí token** (tiền/ngày hoặc tháng) vì một số ít request có prompt/output rất dài vẫn có thể tiêu tốn ngân sách dù chưa chạm ngưỡng rate limit.

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health check (`/health`) vs Readiness check (`/ready`)

Phân tích và chạy thử `05-scaling-reliability/develop/app.py`:

- **`GET /health` (Liveness probe):** Kiểm tra *process còn sống hay không*. Cloud platform / Docker `HEALTHCHECK` dùng endpoint này để phát hiện process bị treo và restart container. Trong `develop/app.py`, `/health` trả `200 OK` kèm `uptime_seconds`, `version`, `timestamp`, và kiểm tra bộ nhớ.
- **`GET /ready` (Readiness probe):** Kiểm tra *instance đã sẵn sàng nhận traffic chưa*. Load balancer dùng `/ready` để quyết định có định tuyến request tới instance này không: khi mới khởi động (`_is_ready = False`), đang shutdown, hoặc mất kết nối dependency (Redis/DB như trong `production/app.py`), `/ready` phải trả `503 Service Unavailable`.

**Kết quả test thực tế (`05-scaling-reliability/develop/app.py`):**

```http
HTTP/1.1 200 OK
content-type: application/json

{"status":"ok","uptime_seconds":0.6,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T08:56:50.530927+00:00","checks":{"memory":{"status":"ok","note":"psutil not installed"}}}
```

```http
HTTP/1.1 200 OK
content-type: application/json

{"ready":true,"in_flight_requests":1}
```

```http
HTTP/1.1 200 OK
content-type: application/json

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

---

### Exercise 5.2: Graceful shutdown (`SIGTERM`)

**Cơ chế trong `05-scaling-reliability/develop/app.py`:**
- Middleware `track_requests` đếm `_in_flight_requests` đang xử lý.
- Đăng ký `signal.signal(signal.SIGTERM, handle_sigterm)` và chạy `uvicorn.run(..., timeout_graceful_shutdown=30)`.
- Khi nhận `SIGTERM`, `lifespan` chuyển `_is_ready = False` (để load balancer ngừng gửi request mới) và đợi các `_in_flight_requests` hoàn tất trước khi thoát sạch với exit code `0`.

**Kết quả gửi `SIGTERM` thực tế (`kill -TERM 2398`):**

```text
Process exit code: 0
```

```text
INFO:     127.0.0.1:48346 - "POST /ask?question=Hello HTTP/1.1" 200 OK
INFO:     Shutting down
INFO:     Waiting for application shutdown.
2026-11-25 15:56:53,782 INFO 🔄 Graceful shutdown initiated...
2026-11-25 15:56:53,782 INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [2398]
2026-11-25 15:56:53,782 INFO Received signal 15 — uvicorn will handle graceful shutdown
```

---

### Exercise 5.3: Stateless design

- **Vấn đề khi lưu state trong RAM:** Khi scale ngang ra nhiều container/instance (`agent-1`, `agent-2`, `agent-3`), mỗi container có vùng nhớ riêng. Request 1 của user vào `agent-1`, Request 2 qua load balancer sang `agent-2` sẽ bị mất toàn bộ lịch sử hội thoại; ngoài ra restart container cũng làm mất sạch dữ liệu.
- **Giải pháp trong `05-scaling-reliability/production/app.py`:**
  - Tách toàn bộ session & conversation history ra **Redis** (`save_session` dùng `_redis.setex(f"session:{session_id}", 3600, json.dumps(data))`, `load_session` đọc từ Redis, `append_to_history` giữ tối đa 20 messages).
  - Mọi instance đều dùng chung Redis nên bất kỳ instance nào nhận request kế tiếp cũng đọc/ghi cùng một trạng thái phiên.

---

### Exercise 5.4 & 5.5: Load balancing (Nginx + 3 instances) & `test_stateless.py`

Chạy stack trong `05-scaling-reliability/production/` (mở cổng `8080`, endpoint `POST /chat`):

```bash
touch .env.local
docker compose -p k5-day14-scaling up -d --build --scale agent=3
docker compose -p k5-day14-scaling ps
curl -i http://localhost:8080/health
python3 test_stateless.py
docker compose -p k5-day14-scaling down -v
```

**Trạng thái 5 container (`docker compose ps`):**

```text
NAME                       IMAGE                    COMMAND                  SERVICE   CREATED          STATUS                       PORTS
k5-day14-scaling-agent-1   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     13 seconds ago   Up 1 second (health: starting)   8000/tcp
k5-day14-scaling-agent-2   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     13 seconds ago   Up 1 second (health: starting)   8000/tcp
k5-day14-scaling-agent-3   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     13 seconds ago   Up 1 second (health: starting)   8000/tcp
k5-day14-scaling-nginx-1   nginx:alpine             "/docker-entrypoint.…"   nginx     13 seconds ago   Up 1 second                  0.0.0.0:8080->80/tcp
k5-day14-scaling-redis-1   redis:7-alpine           "docker-entrypoint.s…"   redis     14 seconds ago   Up 12 seconds (healthy)      6379/tcp
```

**Header `X-Served-By` từ Nginx khi gọi `/health`:**

```http
HTTP/1.1 200 OK
Server: nginx/1.31.10
X-Served-By: 172.20.0.5:8000

{"status":"ok","instance_id":"instance-4902f2","uptime_seconds":0.3,"storage":"redis","redis_connected":true}
```

**Kết quả chạy `python3 test_stateless.py`:**

```text
============================================================
Stateless Scaling Demo
============================================================

Session ID: 3aa513b2-1125-43ea-806a-c6538c9d72b5

Request 1: [instance-a345ac]
  Q: What is Docker?
  A: Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!...

Request 2: [instance-6f875f]
  Q: Why do we need containers?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

Request 3: [instance-4902f2]
  Q: What is Kubernetes?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

Request 4: [instance-a345ac]
  Q: How does load balancing work?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 5: [instance-6f875f]
  Q: What is Redis used for?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

------------------------------------------------------------
Total requests: 5
Instances used: {'instance-6f875f', 'instance-4902f2', 'instance-a345ac'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
  [user]: What is Docker?...
  [assistant]: Container là cách đóng gói app để chạy ở mọi nơi. Build once...
  [user]: Why do we need containers?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...
  [user]: What is Kubernetes?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...
  [user]: How does load balancing work?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...
  [user]: What is Redis used for?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...

✅ Session history preserved across all instances via Redis!
```

**Giải thích kết quả:** Nginx phân phối tuần tự 5 requests trong cùng một `session_id` qua cả 3 container (`instance-a345ac`, `instance-6f875f`, `instance-4902f2`), trong khi `GET /chat/{session_id}/history` vẫn đọc đủ **10 messages** (5 lượt hỏi–đáp) vì toàn bộ lịch sử được lưu tập trung trong Redis.

---

## Part 6: Final Project

Chạy `python check_production_ready.py` đầy đủ trong thư mục `06-lab-complete/` trên Ubuntu WSL2 (có Docker):

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## AI Log

- **Part 1:** Dùng AI hướng dẫn cài đặt Ubuntu trên WSL2, thiết lập virtual environment `~/day14-venv`, chạy kiểm thử thực tế hai phiên bản `develop` và `production`, và tổng hợp câu trả lời vào `MISSION_ANSWERS.md` dựa trên kết quả chạy trực tiếp trên máy.
- **Part 2:** Dùng AI hỗ trợ chạy build hai Docker image (`my-agent:develop` và `my-agent:advanced`), khởi chạy và kiểm thử Docker Compose stack qua Nginx, đồng thời kiểm tra lại nội dung giải thích Dockerfile và số đo thực tế từ `docker images` trước khi ghi vào `MISSION_ANSWERS.md`.
- **Part 4:** Dùng AI hỗ trợ cài `pyjwt`, chạy kiểm thử API Key (`develop`), luồng JWT + vòng lặp gây `429` (`production`) và kiểm tra `GET /me/usage`, đối chiếu code `auth.py`, `rate_limiter.py`, `cost_guard.py` và ghi kết quả (đã che token) vào `MISSION_ANSWERS.md`.
- **Part 5:** Dùng AI hỗ trợ chạy kiểm thử `/health`, `/ready`, `SIGTERM` graceful shutdown trên bản `develop` và chạy stack 3 instance với Nginx + Redis (`-p k5-day14-scaling`) kèm `test_stateless.py`, sau đó tổng hợp phân tích và kết quả thực tế vào `MISSION_ANSWERS.md`.
- **Part 6:** Dùng AI hướng dẫn và cùng triển khai các `TODO` trong `06-lab-complete/` (`config.py`, `redis_client.py`, `auth.py`, `rate_limiter.py`, `cost_guard.py`, `main.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`), rồi tự kiểm tra lại toàn bộ 12 tiêu chí bằng `check_production_ready.py` trên WSL2 có Docker (`PASS 12/12`, `43/43 checks passed`).
