# Resume Bullets — GCP Microservices + Apigee API Gateway

**Architect:** Dr. Tatianna Gilliam — Cloud & AI Architect (AZ-305 | AI-102 | AZ-104)

---

## Primary Bullets

- Decomposed monolithic ERP AI delay-risk platform into three Cloud Run microservices (risk scoring, feature serving, notification) with Apigee API gateway — enabling independent scaling, deployment, and team ownership at enterprise scale

- Designed API governance layer on Apigee with API key authentication, per-developer rate limiting (100 req/min), standardized error contracts with distributed tracing via `request_id`, and OpenAPI 3.0 developer portal

- Implemented circuit breaker pattern (CLOSED/OPEN/HALF_OPEN state machine) on Feature Service dependency — degraded mode returns cached features instead of failing scoring requests during upstream outages

- Architected service-to-service authentication using Cloud Run IAM workload identity (no API keys in service mesh) with async high-risk notification via Pub/Sub push subscriptions

- Delivered multi-cloud architecture proof: identical microservices + API gateway pattern on GCP (Apigee + Cloud Run) and Azure (APIM + Container Apps) — same governance principles, platform-native implementations

## Supporting Bullets

- Provisioned infrastructure as code with Terraform: Cloud Run services, IAM bindings, Pub/Sub topics, Apigee environment, and Artifact Registry

- Defined API design standards: URI versioning (`/v1/`), idempotent scoring endpoints, centralized rate limiting at gateway edge, and Zero Trust authentication model

- Configured differentiated scaling profiles: risk scoring scales to zero off-hours (min 0), feature service always warm (min 1) for sub-100ms latency SLA

## Skills Tags

`GCP` `Cloud Run` `Apigee` `Pub/Sub` `Microservices` `API Gateway` `Terraform` `FastAPI` `OpenAPI` `Circuit Breaker` `IAM` `Vertex AI` `Azure APIM` `Container Apps` `Multi-Cloud` `AZ-305` `AI-102` `AZ-104`
