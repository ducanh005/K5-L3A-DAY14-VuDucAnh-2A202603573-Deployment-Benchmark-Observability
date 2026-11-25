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

## AI Log

- **Part 1:** Dùng AI hướng dẫn cài đặt Ubuntu trên WSL2, thiết lập virtual environment `~/day14-venv`, chạy kiểm thử thực tế hai phiên bản `develop` và `production`, và tổng hợp câu trả lời vào `MISSION_ANSWERS.md` dựa trên kết quả chạy trực tiếp trên máy.
- **Part 2:** Dùng AI hỗ trợ chạy build hai Docker image (`my-agent:develop` và `my-agent:advanced`), khởi chạy và kiểm thử Docker Compose stack qua Nginx, đồng thời kiểm tra lại nội dung giải thích Dockerfile và số đo thực tế từ `docker images` trước khi ghi vào `MISSION_ANSWERS.md`.
