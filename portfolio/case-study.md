# Case Study — GCP Cloud Run Microservices + Apigee API Gateway

**Architect:** Dr. Tatianna Gilliam — Cloud & AI Architect (AZ-305 | AI-102 | AZ-104)

---

## The Challenge

The ERP AI Delay Risk platform predicted supply-chain delay risk from operational ERP data. Phase 1 was a monolithic FastAPI application on Cloud Run — fast to build, correct for proof of concept.

As the platform moved toward enterprise adoption, three constraints emerged:

1. **Scaling mismatch** — batch scoring runs spiked CPU at 2 AM, but feature serving needed steady sub-100ms latency around the clock
2. **Deployment coupling** — updating the ML model required redeploying notification logic and feature cache code
3. **No API governance** — external consumers called Cloud Run URLs directly with no rate limiting, no API key management, and inconsistent error formats

## The Solution

Decompose the monolith into three Cloud Run microservices with Apigee as the API governance layer:

| Service | Role | Scaling |
|---------|------|---------|
| Risk Scoring | ML inference on feature vectors | min 0, max 10 — scale to zero off-hours |
| Feature Service | Online feature serving | min 1, max 5 — always warm for latency |
| Notification | High-risk alert delivery | min 0, max 3 — event-driven via Pub/Sub |

Apigee handles API key validation, 100 req/min rate limiting, error standardization, and developer portal. Services authenticate via IAM workload identity — no API keys in the service mesh.

A circuit breaker on the Feature Service dependency returns cached features during degradation rather than failing the request.

## The Results

| Metric | Monolith | Microservices |
|--------|----------|---------------|
| Off-hours compute cost | Full instance running | Risk scoring at zero instances |
| Model deployment blast radius | Entire application | Risk scoring service only |
| Feature serving latency p99 | Coupled to scoring load | Independent, always warm |
| External API governance | None | Apigee: auth, rate limit, portal |
| Failure isolation | Feature outage = total outage | Circuit breaker → degraded scoring |

## Multi-Cloud Proof

The same architecture exists on Azure: APIM + Container Apps + Service Bus + Managed Identity. Side-by-side, these two projects demonstrate that the architect designs patterns, not just GCP or Azure configurations.

## Technologies

GCP Cloud Run, Apigee X, Cloud Pub/Sub, Vertex AI Feature Store, Artifact Registry, Terraform, FastAPI, OpenAPI 3.0

Azure equivalents: Container Apps, API Management, Service Bus, Azure ML Feature Store, ACR, Bicep/Terraform
