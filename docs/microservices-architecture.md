# Microservices Architecture — ERP AI Delay Risk Platform

**Architect:** Dr. Tatianna Gilliam — Cloud & AI Architect (AZ-305 | AI-102 | AZ-104)  
**Project:** GCP Cloud Run Microservices + Apigee API Gateway  
**Evolution:** Phase 2 decomposition of the monolithic ERP AI Delay Risk FastAPI application

---

## Executive Summary

The ERP AI Delay Risk platform began as a single FastAPI service on Cloud Run — appropriate for proof of concept and early production. At enterprise scale, the coupling between risk scoring, feature retrieval, and notification logic becomes a deployment bottleneck, a scaling constraint, and a team-boundary violation.

This document describes the decomposition into three independently deployable microservices, an Apigee API gateway for enterprise governance, and asynchronous event-driven notification via Pub/Sub. The architecture preserves the same business capability (predict supply chain delay risk) while enabling independent scaling, deployment, and ownership.

This is the GCP implementation of the same pattern documented in the Azure API Management + Container Apps Phase 2 upgrade. Same problem, same pattern, different platform primitives.

---

## Why Decompose

### Different Scaling Profiles

| Concern | Risk Scoring | Feature Retrieval |
|---------|-------------|-------------------|
| Traffic pattern | Spiky — batch scoring runs at 02:00 UTC, ad-hoc during planning cycles | Steady — read-heavy, sub-100ms latency SLA |
| CPU profile | Bursty inference workloads | Lightweight cache lookups |
| Cost sensitivity | Can scale to zero off-hours | Must stay warm — cold start unacceptable |

A monolith forces a single scaling configuration. Decomposition lets risk scoring run `min_instances = 0` while feature serving stays at `min_instances = 1`.

### Independent Deployment

When the ML team ships a new delay-risk model, they should not redeploy notification templates, Pub/Sub bindings, or feature cache logic. Microservices isolate the blast radius: a model update touches only `risk-scoring-service`.

### Independent Scaling

During off-hours, risk scoring traffic drops to near zero. Feature serving must remain available for dashboards and operational lookups. In a monolith, you pay for idle scoring capacity to keep features warm — or you accept cold starts on everything.

### Team Boundaries

In enterprise settings, ownership maps to services:

| Service | Typical Owner | Concern |
|---------|--------------|---------|
| Risk Scoring | ML / Data Science | Model accuracy, inference latency |
| Feature Service | Data Platform | Feature freshness, online serving SLA |
| Notification | Platform / SRE | Alert routing, escalation policies |

Clear service boundaries enable independent roadmaps, SLAs, and on-call rotations.

---

## Architecture Overview

```
                    ┌─────────────────────────────────────┐
                    │         Apigee API Gateway          │
                    │  Auth · Rate Limit · Routing · WAF  │
                    └──────────────┬──────────────────────┘
                                   │
           ┌───────────────────────┼───────────────────────┐
           │                       │                       │
           ▼                       ▼                       ▼
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ Risk Scoring     │   │ Feature Service  │   │ Notification     │
│ Service          │──▶│                  │   │ Service          │
│ (Cloud Run)      │   │ (Cloud Run)      │   │ (Cloud Run)      │
│ min: 0, max: 10  │   │ min: 1, max: 5   │   │ min: 0, max: 3   │
└────────┬─────────┘   └────────┬─────────┘   └────────▲─────────┘
         │                      │                      │
         │  HTTP (sync)         │ Vertex AI            │ Pub/Sub
         │  IAM auth            │ Feature Store        │ (async)
         └──────────────────────┼──────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │   Cloud Pub/Sub       │
                    │ high-risk-events      │
                    └───────────────────────┘
```

---

## The Three Services

### Risk Scoring Service

**Responsibility:** Run ML inference on entity feature vectors and return delay-risk predictions.

| Property | Value |
|----------|-------|
| Endpoints | `POST /v1/score`, `POST /v1/score/batch` |
| Depends on | Feature Service (HTTP) |
| Scale | min 0, max 10 instances |
| Resources | 1 vCPU, 512 MB memory |
| Auth | Cloud Run IAM — accepts traffic from Apigee and Feature Service callbacks only |

**Key behaviors:**

- Does not load features from local files — all features retrieved via Feature Service
- Circuit breaker on Feature Service dependency — degraded mode returns cached features rather than failing the request
- Publishes to Pub/Sub when `risk_level == "high"` for async notification
- Structured logging with `request_id`, `latency_ms`, `feature_service_status`

### Feature Service

**Responsibility:** Serve entity feature vectors for online inference.

| Property | Value |
|----------|-------|
| Endpoints | `GET /v1/features/{entity_id}`, `POST /v1/features/batch` |
| Backing store | Vertex AI Feature Store (online serving); local in-memory cache for portfolio demo |
| Scale | min 1, max 5 instances (always warm) |
| Resources | 0.5 vCPU, 256 MB memory |
| Auth | Cloud Run IAM — accepts traffic from Risk Scoring Service service account |

**Key behaviors:**

- Sub-100ms p99 latency target for single-entity lookups
- Batch endpoint for scoring service bulk operations
- Cache-aside pattern with TTL for portfolio version

### Notification Service

**Responsibility:** Deliver alerts when high-risk entities are detected.

| Property | Value |
|----------|-------|
| Endpoints | `POST /v1/notify` (internal), Pub/Sub push subscription |
| Integrates with | Cloud Pub/Sub topic `high-risk-events` |
| Scale | min 0, max 3 instances (event-driven) |
| Resources | 0.5 vCPU, 256 MB memory |
| Auth | Cloud Run IAM — Pub/Sub push + internal gateway routes only |

**Key behaviors:**

- Consumes async events from Risk Scoring via Pub/Sub
- Idempotent notification delivery (dedupe on `entity_id + scoring_timestamp`)
- Supports email, webhook, and Teams channel routing (portfolio: structured log output)

---

## Service Communication

### Synchronous: Risk Scoring → Feature Service

```
Risk Scoring Service                    Feature Service
        │                                      │
        │  GET /v1/features/{entity_id}        │
        │  Authorization: Bearer <ID token>    │
        │─────────────────────────────────────▶│
        │                                      │
        │  200 { entity_id, features, ... }    │
        │◀─────────────────────────────────────│
```

- Protocol: HTTPS over Cloud Run internal URLs
- Authentication: IAM service-to-service using workload identity — Risk Scoring's service account holds `roles/run.invoker` on Feature Service
- No API keys between services — identity is the credential
- Circuit breaker protects scoring when Feature Service is degraded

### Asynchronous: Risk Scoring → Pub/Sub → Notification

```
Risk Scoring Service          Pub/Sub              Notification Service
        │                   high-risk-events              │
        │  publish(event)         │                       │
        │────────────────────────▶│                       │
        │                         │  push subscription    │
        │                         │──────────────────────▶│
        │                         │                       │ deliver alert
```

Event payload:

```json
{
  "entity_id": "PO-88421",
  "risk_score": 0.87,
  "risk_level": "high",
  "request_id": "req_abc123",
  "timestamp": "2026-06-08T14:32:00Z"
}
```

Threshold: `risk_score >= 0.75` triggers publish. Notification is fire-and-forget — scoring response is not blocked on delivery.

### Service Authentication Model

| Path | Auth Mechanism |
|------|---------------|
| External → Apigee | API key (`X-API-Key` header) |
| Apigee → Cloud Run | Service account with `run.invoker` |
| Risk Scoring → Feature Service | IAM ID token (service account) |
| Risk Scoring → Pub/Sub | Service account with `pubsub.publisher` |
| Pub/Sub → Notification | Push subscription with OIDC token |

Services trust the gateway for external auth. They do not re-validate API keys — Zero Trust at the edge, identity propagation internally.

---

## Apigee API Gateway Layer

Apigee sits in front of all three services as the single external entry point.

| Capability | Implementation |
|------------|---------------|
| Rate limiting | 100 req/min per API key (standard tier) via Quota policy |
| Authentication | API key validation at proxy preflow |
| Request routing | `/v1/score*` → risk-scoring, `/v1/features*` → feature-service, `/v1/notify` → notification |
| Error transformation | Standardize to `{ error_code, message, request_id, timestamp }` |
| Quota enforcement | Per-developer quotas via API product tiers |
| Developer portal | OpenAPI spec published for consumer onboarding |
| Analytics | Apigee Analytics — latency, error rate, quota consumption |

External consumers never call Cloud Run URLs directly. All traffic flows through Apigee.

---

## Resilience Patterns

### Circuit Breaker (Risk Scoring → Feature Service)

State machine: `CLOSED` → `OPEN` → `HALF_OPEN` → `CLOSED`

| State | Behavior |
|-------|----------|
| CLOSED | Normal operation — call Feature Service |
| OPEN | 5 failures in 60s — return cached features, mark `feature_source: "cache"` |
| HALF_OPEN | After 30s, allow one probe request to test recovery |

Degraded response is preferred over hard failure — a stale feature vector still produces a useful risk signal.

### Health Checks

Every service exposes `GET /health`:

```json
{
  "status": "healthy",
  "service": "risk-scoring-service",
  "dependencies": {
    "feature_service": "healthy"
  },
  "timestamp": "2026-06-08T14:32:00Z"
}
```

Cloud Run uses this for readiness probes. Apigee can route around unhealthy backends.

---

## Deployment Topology

| Component | GCP Service | Region |
|-----------|------------|--------|
| Risk Scoring | Cloud Run | us-central1 |
| Feature Service | Cloud Run | us-central1 |
| Notification | Cloud Run | us-central1 |
| API Gateway | Apigee X | us-central1 |
| Async messaging | Cloud Pub/Sub | us-central1 |
| Feature store | Vertex AI Feature Store | us-central1 |
| IaC | Terraform | — |

All services deploy from container images in Artifact Registry. Terraform manages Cloud Run services, IAM bindings, Pub/Sub topics, and Apigee proxy deployment.

---

## Azure Equivalent Architecture

This section is mandatory — this project demonstrates multi-cloud architecture depth, not GCP-only expertise.

| GCP Component | Azure Equivalent | Notes |
|---------------|-----------------|-------|
| Cloud Run | Azure Container Apps | Serverless containers, scale to zero, HTTP ingress |
| Apigee | Azure API Management (APIM) | API gateway, policies, developer portal, rate limiting |
| Cloud Pub/Sub | Azure Service Bus (queues/topics) or Event Hubs (streaming) | Service Bus for task-style async; Event Hubs for high-throughput event streams |
| Cloud Run IAM (service-to-service) | Managed Identity + RBAC | Workload identity — no secrets in code |
| Vertex AI Feature Store | Azure Machine Learning Feature Store | Online feature serving for inference |
| Artifact Registry | Azure Container Registry (ACR) | Container image storage |
| Cloud Armor (WAF) | Application Gateway + WAF | Edge protection in front of APIM |
| Cloud Logging | Azure Monitor + Log Analytics | Structured logging and alerting |
| Secret Manager | Azure Key Vault | Secrets and certificate management |

### Side-by-Side Request Flow

**GCP:**

```
Client → Apigee (API key) → Cloud Run (risk-scoring) → Cloud Run (feature-service)
                                                       → Pub/Sub → Cloud Run (notification)
```

**Azure:**

```
Client → APIM (subscription key) → Container Apps (risk-scoring) → Container Apps (feature-service)
                                                                 → Service Bus → Container Apps (notification)
```

The conceptual model is identical. Both platforms provide serverless containers, an API management layer, managed identity for service-to-service auth, and async messaging. The Phase 2 Azure upgrade in the ERP AI Delay Risk portfolio documents the same decomposition with APIM policies instead of Apigee XML.

### When to Choose Which

| Factor | Lean GCP | Lean Azure |
|--------|----------|------------|
| Existing GCP commitment (BigQuery, Vertex AI) | ✓ | |
| Existing Azure commitment (Fabric, Azure ML) | | ✓ |
| Apigee policy flexibility | ✓ | |
| Native Entra ID integration | | ✓ |
| Multi-cloud mandate | Both — same pattern, two implementations | Both |

---

## Migration Path from Monolith

1. **Extract Feature Service** — move feature loading logic out of monolith; scoring service calls HTTP endpoint
2. **Add circuit breaker** — implement degraded mode before cutting over production traffic
3. **Extract Notification** — replace inline alert logic with Pub/Sub publish; deploy notification consumer
4. **Deploy Apigee** — route external traffic through gateway; deprecate direct Cloud Run URLs
5. **Decommission monolith** — verify all endpoints migrated; remove single-service deployment

Each step is independently deployable and reversible.

---

## Related Documents

- [API Governance Design](./api-governance-design.md)
- [Azure Comparison](./azure-comparison.md)
- [Design Decisions](./design-decisions.md)
- [OpenAPI Specification](../gateway/openapi-spec.yaml)
