"""
Feature Service — ERP AI Delay Risk Platform

Serves entity feature vectors for online ML inference.
Portfolio version uses in-memory store; production uses Vertex AI Feature Store.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

SERVICE_NAME = "feature-service"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"'
    + SERVICE_NAME
    + '","message":"%(message)s"}',
)
logger = logging.getLogger(SERVICE_NAME)

# Portfolio demo feature store
FEATURE_STORE: dict[str, dict[str, Any]] = {
    "PO-88421": {
        "supplier_lead_time_days": 45,
        "historical_delay_rate": 0.32,
        "inventory_coverage_days": 12,
        "order_value_usd": 125000,
        "seasonality_index": 1.4,
    },
    "PO-88422": {
        "supplier_lead_time_days": 21,
        "historical_delay_rate": 0.08,
        "inventory_coverage_days": 30,
        "order_value_usd": 45000,
        "seasonality_index": 0.9,
    },
    "PO-88423": {
        "supplier_lead_time_days": 60,
        "historical_delay_rate": 0.45,
        "inventory_coverage_days": 5,
        "order_value_usd": 280000,
        "seasonality_index": 1.8,
    },
}

LAST_UPDATED = datetime.now(timezone.utc).isoformat()


class FeatureResponse(BaseModel):
    entity_id: str
    features: dict[str, Any]
    last_updated: str


class BatchFeatureRequest(BaseModel):
    entity_ids: list[str] = Field(..., min_length=1, max_length=500)


class BatchFeatureResponse(BaseModel):
    features: list[FeatureResponse]
    request_id: str
    timestamp: str


class HealthResponse(BaseModel):
    status: str
    service: str
    dependencies: dict[str, str]
    timestamp: str


app = FastAPI(
    title="Feature Service",
    version="1.0.0",
    description="ERP AI Delay Risk — feature retrieval microservice",
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
    logger.info(
        json.dumps(
            {
                "request_id": request_id,
                "path": request.url.path,
                "latency_ms": round(latency_ms, 2),
            }
        )
    )
    return response


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        service=SERVICE_NAME,
        dependencies={"feature_store": "healthy"},
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/v1/features/{entity_id}", response_model=FeatureResponse)
async def get_features(entity_id: str, request: Request):
    features = FEATURE_STORE.get(entity_id)
    if not features:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "ENTITY_NOT_FOUND",
                "message": f"No features found for entity {entity_id}",
                "request_id": request.state.request_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    return FeatureResponse(
        entity_id=entity_id,
        features=features,
        last_updated=LAST_UPDATED,
    )


@app.post("/v1/features/batch", response_model=BatchFeatureResponse)
async def get_features_batch(body: BatchFeatureRequest, request: Request):
    results: list[FeatureResponse] = []
    for entity_id in body.entity_ids:
        features = FEATURE_STORE.get(entity_id)
        if features:
            results.append(
                FeatureResponse(
                    entity_id=entity_id,
                    features=features,
                    last_updated=LAST_UPDATED,
                )
            )
    return BatchFeatureResponse(
        features=results,
        request_id=request.state.request_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8081")))
