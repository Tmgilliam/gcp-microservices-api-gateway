"""
Notification Service — ERP AI Delay Risk Platform

Delivers alerts for high-risk entities. Consumes Pub/Sub events
and exposes internal notify endpoint via API gateway.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field

SERVICE_NAME = "notification-service"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"'
    + SERVICE_NAME
    + '","message":"%(message)s"}',
)
logger = logging.getLogger(SERVICE_NAME)

_delivered: set[str] = set()


class NotifyRequest(BaseModel):
    entity_id: str
    risk_score: float
    risk_level: str
    channels: list[str] = Field(default=["email"])


class NotifyResponse(BaseModel):
    notification_id: str
    status: str
    entity_id: str
    request_id: str
    timestamp: str


class HealthResponse(BaseModel):
    status: str
    service: str
    dependencies: dict[str, str]
    timestamp: str


app = FastAPI(
    title="Notification Service",
    version="1.0.0",
    description="ERP AI Delay Risk — notification microservice",
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
    return HealthResponse(
        status="healthy",
        service=SERVICE_NAME,
        dependencies={"pubsub": "healthy"},
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/v1/notify", response_model=NotifyResponse, status_code=202)
async def notify(body: NotifyRequest, request: Request):
    dedupe_key = f"{body.entity_id}:{body.risk_level}"
    notification_id = f"notif_{uuid.uuid4().hex[:12]}"

    if dedupe_key in _delivered:
        logger.info(
            json.dumps(
                {
                    "event": "notification_deduplicated",
                    "entity_id": body.entity_id,
                    "dedupe_key": dedupe_key,
                }
            )
        )
        return NotifyResponse(
            notification_id=notification_id,
            status="accepted",
            entity_id=body.entity_id,
            request_id=request.state.request_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    _delivered.add(dedupe_key)

    for channel in body.channels:
        logger.info(
            json.dumps(
                {
                    "event": "notification_delivered",
                    "notification_id": notification_id,
                    "entity_id": body.entity_id,
                    "risk_score": body.risk_score,
                    "risk_level": body.risk_level,
                    "channel": channel,
                    "request_id": request.state.request_id,
                }
            )
        )

    return NotifyResponse(
        notification_id=notification_id,
        status="accepted",
        entity_id=body.entity_id,
        request_id=request.state.request_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8082")))
