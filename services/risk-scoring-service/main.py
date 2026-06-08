"""
Risk Scoring Service — ERP AI Delay Risk Platform

Microservice that scores supply-chain delay risk by retrieving features
from the Feature Service (not local files) and running ML inference.

Implements circuit breaker pattern for Feature Service dependency.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVICE_NAME = "risk-scoring-service"
FEATURE_SERVICE_URL = os.getenv("FEATURE_SERVICE_URL", "http://localhost:8081")
MODEL_PATH = os.getenv("MODEL_PATH", "/app/models/delay_risk_model.json")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
HIGH_RISK_THRESHOLD = float(os.getenv("HIGH_RISK_THRESHOLD", "0.75"))
PUBSUB_TOPIC = os.getenv("PUBSUB_TOPIC", "high-risk-events")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("FEATURE_SERVICE_TIMEOUT", "5.0"))

# Circuit breaker thresholds
FAILURE_THRESHOLD = 5
FAILURE_WINDOW_SECONDS = 60
OPEN_STATE_PROBE_INTERVAL_SECONDS = 30


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"'
    + SERVICE_NAME
    + '","message":"%(message)s"}',
)
logger = logging.getLogger(SERVICE_NAME)


def log_request(
    request_id: str,
    endpoint: str,
    latency_ms: float,
    feature_service_status: str,
    **extra: Any,
) -> None:
    payload = {
        "request_id": request_id,
        "endpoint": endpoint,
        "latency_ms": round(latency_ms, 2),
        "feature_service_status": feature_service_status,
        **extra,
    }
    logger.info(json.dumps(payload))


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Simple state-machine circuit breaker (no external library)."""

    failure_threshold: int = FAILURE_THRESHOLD
    failure_window_seconds: float = FAILURE_WINDOW_SECONDS
    probe_interval_seconds: float = OPEN_STATE_PROBE_INTERVAL_SECONDS

    state: CircuitState = CircuitState.CLOSED
    failure_timestamps: deque = field(default_factory=deque)
    last_failure_time: float = 0.0
    last_probe_time: float = 0.0
    consecutive_successes_in_half_open: int = 0
    _lock: Lock = field(default_factory=Lock)

    def _prune_old_failures(self, now: float) -> None:
        cutoff = now - self.failure_window_seconds
        while self.failure_timestamps and self.failure_timestamps[0] < cutoff:
            self.failure_timestamps.popleft()

    def record_success(self) -> None:
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.consecutive_successes_in_half_open += 1
                if self.consecutive_successes_in_half_open >= 1:
                    self.state = CircuitState.CLOSED
                    self.failure_timestamps.clear()
                    self.consecutive_successes_in_half_open = 0
                    logger.info("Circuit breaker CLOSED — Feature Service recovered")
            elif self.state == CircuitState.CLOSED:
                self.failure_timestamps.clear()

    def record_failure(self) -> None:
        now = time.monotonic()
        with self._lock:
            self.last_failure_time = now
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.last_probe_time = now
                self.consecutive_successes_in_half_open = 0
                logger.warning("Circuit breaker OPEN — probe failed in HALF_OPEN")
                return

            self.failure_timestamps.append(now)
            self._prune_old_failures(now)
            if len(self.failure_timestamps) >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.last_probe_time = now
                logger.warning(
                    "Circuit breaker OPEN — %d failures in %ds",
                    len(self.failure_timestamps),
                    self.failure_window_seconds,
                )

    def allow_request(self) -> bool:
        now = time.monotonic()
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                if now - self.last_probe_time >= self.probe_interval_seconds:
                    self.state = CircuitState.HALF_OPEN
                    self.consecutive_successes_in_half_open = 0
                    self.last_probe_time = now
                    logger.info("Circuit breaker HALF_OPEN — probing Feature Service")
                    return True
                return False

            # HALF_OPEN — allow the probe request
            return True

    @property
    def status_label(self) -> str:
        if self.state == CircuitState.CLOSED:
            return "healthy"
        if self.state == CircuitState.HALF_OPEN:
            return "degraded"
        return "degraded"


circuit_breaker = CircuitBreaker()

# ---------------------------------------------------------------------------
# Feature cache (degraded mode)
# ---------------------------------------------------------------------------

_feature_cache: dict[str, dict[str, Any]] = {}
_cache_lock = Lock()


def cache_features(entity_id: str, features: dict[str, Any]) -> None:
    with _cache_lock:
        _feature_cache[entity_id] = {
            "features": features,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }


def get_cached_features(entity_id: str) -> dict[str, Any] | None:
    with _cache_lock:
        entry = _feature_cache.get(entity_id)
        return entry["features"] if entry else None


# ---------------------------------------------------------------------------
# Model (portfolio: rule-based scorer; production: load from MODEL_PATH)
# ---------------------------------------------------------------------------

DEFAULT_MODEL_WEIGHTS = {
    "supplier_lead_time_days": 0.25,
    "order_value_usd": 0.10,
    "historical_delay_rate": 0.35,
    "inventory_coverage_days": -0.20,
    "seasonality_index": 0.10,
}


def load_model_weights() -> dict[str, float]:
    if os.path.exists(MODEL_PATH):
        with open(MODEL_PATH, encoding="utf-8") as f:
            data = json.load(f)
            return data.get("weights", DEFAULT_MODEL_WEIGHTS)
    return DEFAULT_MODEL_WEIGHTS


model_weights = DEFAULT_MODEL_WEIGHTS


def compute_risk_score(features: dict[str, Any]) -> tuple[float, str, float]:
    """Score entity features. Returns (score, level, confidence)."""
    score = 0.5  # baseline
    matched = 0
    for feature, weight in model_weights.items():
        if feature in features:
            value = float(features[feature])
            # Normalize rough ranges for portfolio demo
            normalized = min(max(value / 100.0, 0.0), 1.0) if abs(value) > 1 else value
            score += weight * normalized
            matched += 1

    score = min(max(score, 0.0), 1.0)
    confidence = min(0.5 + (matched / len(model_weights)) * 0.5, 1.0)

    if score >= 0.75:
        level = "high"
    elif score >= 0.45:
        level = "medium"
    else:
        level = "low"

    return round(score, 4), level, round(confidence, 4)


# ---------------------------------------------------------------------------
# Feature Service client
# ---------------------------------------------------------------------------


async def fetch_features_from_service(
    client: httpx.AsyncClient,
    entity_id: str,
    request_id: str,
) -> tuple[dict[str, Any], str]:
    """
    Fetch features from Feature Service with circuit breaker protection.
    Returns (features_dict, feature_source).
    """
    if not circuit_breaker.allow_request():
        cached = get_cached_features(entity_id)
        if cached:
            log_request(
                request_id,
                "feature_fetch",
                0,
                "cache_circuit_open",
                entity_id=entity_id,
            )
            return cached, "cache"
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "FEATURE_SERVICE_UNAVAILABLE",
                "message": "Feature Service circuit open and no cached features",
                "request_id": request_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    url = f"{FEATURE_SERVICE_URL.rstrip('/')}/v1/features/{entity_id}"
    start = time.monotonic()
    try:
        response = await client.get(
            url,
            headers={"X-Request-ID": request_id},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        latency_ms = (time.monotonic() - start) * 1000

        if response.status_code == 200:
            circuit_breaker.record_success()
            data = response.json()
            features = data.get("features", {})
            cache_features(entity_id, features)
            log_request(
                request_id,
                "feature_fetch",
                latency_ms,
                "healthy",
                entity_id=entity_id,
            )
            return features, "feature_service"

        circuit_breaker.record_failure()
        log_request(
            request_id,
            "feature_fetch",
            latency_ms,
            "unhealthy",
            entity_id=entity_id,
            status_code=response.status_code,
        )
    except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError) as exc:
        circuit_breaker.record_failure()
        latency_ms = (time.monotonic() - start) * 1000
        log_request(
            request_id,
            "feature_fetch",
            latency_ms,
            "unhealthy",
            entity_id=entity_id,
            error=str(exc),
        )

    # Degraded: return cached features
    cached = get_cached_features(entity_id)
    if cached:
        return cached, "cache"

    raise HTTPException(
        status_code=503,
        detail={
            "error_code": "FEATURE_SERVICE_UNAVAILABLE",
            "message": "Feature Service unavailable and no cached features",
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


async def publish_high_risk_event(
    entity_id: str,
    risk_score: float,
    risk_level: str,
    request_id: str,
) -> None:
    """Publish high-risk event to Pub/Sub (portfolio: structured log)."""
    event = {
        "entity_id": entity_id,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    # Production: use google.cloud.pubsub_v1.PublisherClient
    logger.info(
        json.dumps(
            {
                "event": "high_risk_published",
                "topic": PUBSUB_TOPIC,
                "payload": event,
            }
        )
    )


# ---------------------------------------------------------------------------
# API models
# ---------------------------------------------------------------------------


class ScoreRequest(BaseModel):
    entity_id: str = Field(..., examples=["PO-88421"])
    features: dict[str, Any] | None = Field(
        None, description="Optional feature override — bypasses Feature Service"
    )


class ScoreResponse(BaseModel):
    entity_id: str
    risk_score: float
    risk_level: str
    confidence: float
    feature_source: str
    request_id: str
    timestamp: str


class BatchRecord(BaseModel):
    entity_id: str
    features: dict[str, Any] | None = None


class BatchScoreRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    records: list[BatchRecord]
    async_mode: bool = Field(False, alias="async")


class BatchScoreResponse(BaseModel):
    job_id: str | None = None
    results: list[ScoreResponse] | None = None
    request_id: str
    timestamp: str


class HealthResponse(BaseModel):
    status: str
    service: str
    dependencies: dict[str, str]
    circuit_breaker_state: str
    timestamp: str


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client, model_weights
    model_weights = load_model_weights()
    http_client = httpx.AsyncClient()
    logger.info("Risk Scoring Service started — model weights loaded")
    yield
    if http_client:
        await http_client.aclose()


app = FastAPI(
    title="Risk Scoring Service",
    version="1.0.0",
    description="ERP AI Delay Risk — scoring microservice",
    lifespan=lifespan,
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", f"req_{uuid.uuid4().hex[:12]}")
    request.state.request_id = request_id
    start = time.monotonic()
    response = await call_next(request)
    latency_ms = (time.monotonic() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Latency-Ms"] = str(round(latency_ms, 2))
    return response


@app.get("/health", response_model=HealthResponse)
async def health_check():
    dep_status = circuit_breaker.status_label
    overall = "healthy" if circuit_breaker.state == CircuitState.CLOSED else "degraded"
    return HealthResponse(
        status=overall,
        service=SERVICE_NAME,
        dependencies={"feature_service": dep_status},
        circuit_breaker_state=circuit_breaker.state.value,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


async def _score_entity(request_id: str, body: ScoreRequest) -> ScoreResponse:
    start = time.monotonic()

    if body.features:
        features = body.features
        feature_source = "override"
        feature_status = "healthy"
    else:
        assert http_client is not None
        features, feature_source = await fetch_features_from_service(
            http_client, body.entity_id, request_id
        )
        feature_status = (
            "healthy" if feature_source == "feature_service" else "degraded"
        )

    risk_score, risk_level, confidence = compute_risk_score(features)

    if risk_level == "high":
        await publish_high_risk_event(
            body.entity_id, risk_score, risk_level, request_id
        )

    latency_ms = (time.monotonic() - start) * 1000
    log_request(
        request_id,
        "/v1/score",
        latency_ms,
        feature_status,
        entity_id=body.entity_id,
        risk_level=risk_level,
    )

    return ScoreResponse(
        entity_id=body.entity_id,
        risk_score=risk_score,
        risk_level=risk_level,
        confidence=confidence,
        feature_source=feature_source,
        request_id=request_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/v1/score", response_model=ScoreResponse)
async def score_single(request: Request, body: ScoreRequest):
    return await _score_entity(request.state.request_id, body)


@app.post("/v1/score/batch", response_model=BatchScoreResponse)
async def score_batch(request: Request, body: BatchScoreRequest):
    request_id = request.state.request_id

    if body.async_mode:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        logger.info(
            json.dumps(
                {
                    "event": "batch_job_queued",
                    "job_id": job_id,
                    "record_count": len(body.records),
                    "request_id": request_id,
                }
            )
        )
        return BatchScoreResponse(
            job_id=job_id,
            results=None,
            request_id=request_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    results = [
        await _score_entity(
            request_id,
            ScoreRequest(entity_id=record.entity_id, features=record.features),
        )
        for record in body.records
    ]

    return BatchScoreResponse(
        job_id=None,
        results=results,
        request_id=request_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
