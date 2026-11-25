"""
Production AI Agent — Part 6 Final Project
"""
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Định dạng mỗi dòng log của app thành 1 JSON object hợp lệ."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("event", "method", "path", "status", "ms", "environment", "cost_usd"):
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val
        return json.dumps(payload, ensure_ascii=False)


def _setup_logger() -> logging.Logger:
    app_logger = logging.getLogger("agent")
    app_logger.setLevel(logging.INFO)
    app_logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    app_logger.addHandler(handler)
    app_logger.propagate = False
    return app_logger


logger = _setup_logger()
START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Agent starting up",
        extra={"event": "startup", "environment": settings.environment},
    )
    yield
    logger.info(
        "Agent shutting down gracefully",
        extra={"event": "shutdown", "environment": settings.environment},
    )


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "HTTP request",
        extra={
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": elapsed_ms,
        },
    )
    return response


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = None


@app.get("/health")
def health():
    """Liveness probe: luôn trả 200 khi process còn chạy."""
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "environment": settings.environment,
    }


@app.get("/ready")
def ready():
    """Readiness probe: 200 khi Redis sẵn sàng, 503 khi mất kết nối Redis."""
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return {"status": "ready"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)
    input_tokens = max(1, len(body.question.split()) * 2)
    output_tokens = max(1, len(answer.split()) * 2)
    cost = record_cost(input_tokens, output_tokens)

    logger.info(
        "Processed /ask",
        extra={"event": "ask", "cost_usd": round(cost, 6)},
    )
    return {
        "question": body.question,
        "answer": answer,
        "cost_usd": round(cost, 6),
    }
