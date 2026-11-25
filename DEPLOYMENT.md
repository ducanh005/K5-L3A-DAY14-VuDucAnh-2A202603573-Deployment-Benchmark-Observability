# Deployment Information

## Public URL
https://k5-l3a-day14-vuducanh-2a202603573-deployment-ben-production.up.railway.app

## Platform
Railway (Root Directory: `06-lab-complete`, kèm managed service **Redis**)

## Test Commands

### Health & Readiness Check
```bash
BASE="https://k5-l3a-day14-vuducanh-2a202603573-deployment-ben-production.up.railway.app"

curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"   # Expected: 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"    # Expected: 200
```

### API Test (Authentication)
```bash
# Không có API Key → 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'

# Có API Key hợp lệ → 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"user_id": "test", "question": "Hello"}'
```

## Environment Variables Set
- `PORT` (`8000`)
- `ENVIRONMENT` (`production`)
- `REDIS_URL` (tham chiếu tới service Redis nội bộ trên Railway)
- `AGENT_API_KEY` (khai báo bí mật trên Railway dashboard, không ghi vào code)
- `RATE_LIMIT_PER_MINUTE` (`10`)
- `DAILY_BUDGET_USD` (`1.0`)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
