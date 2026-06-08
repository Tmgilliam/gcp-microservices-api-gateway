# Design Decisions — ERP AI Delay Risk Microservices

**Architect:** Dr. Tatianna Gilliam — Cloud & AI Architect (AZ-305 | AI-102 | AZ-104)

---

## ADR-001: Decompose Monolith into Three Services

**Status:** Accepted  
**Context:** Monolithic FastAPI on Cloud Run works for PoC but creates scaling, deployment, and ownership constraints at enterprise scale.  
**Decision:** Split into risk-scoring, feature-service, and notification-service.  
**Consequences:** (+) Independent scaling and deployment. (+) Clear team boundaries. (−) Operational complexity increases. (−) Network latency between scoring and features.

**Azure equivalent:** Same decomposition into Container Apps — documented in Phase 2 upgrade.

---

## ADR-002: Apigee as External Gateway

**Status:** Accepted  
**Context:** External API consumers need auth, rate limiting, and consistent error contracts. Services should not implement per-consumer policies.  
**Decision:** All external traffic flows through Apigee. Cloud Run services are internal-only (`INGRESS_TRAFFIC_INTERNAL_ONLY`).  
**Consequences:** (+) Centralized governance. (+) Services focus on business logic. (−) Apigee adds cost and operational surface.

**Azure equivalent:** Azure API Management with internal-only Container Apps ingress.

---

## ADR-003: Circuit Breaker with Cache Fallback

**Status:** Accepted  
**Context:** Risk Scoring depends on Feature Service. Feature Service outage should not block all scoring.  
**Decision:** Implement state-machine circuit breaker (CLOSED → OPEN → HALF_OPEN). On OPEN, return cached features with `feature_source: cache`.  
**Consequences:** (+) Scoring remains available during Feature Service degradation. (+) Consumers get degraded but useful results. (−) Stale features may reduce scoring accuracy. (−) Cache must be populated before first failure.

**Thresholds:** 5 failures in 60 seconds → OPEN. Probe every 30 seconds in HALF_OPEN.

---

## ADR-004: Async Notification via Pub/Sub

**Status:** Accepted  
**Context:** High-risk notification is a side effect — it should not block the scoring response.  
**Decision:** Risk Scoring publishes to Pub/Sub when `risk_level == high`. Notification Service consumes via push subscription.  
**Consequences:** (+) Scoring latency unaffected by notification delivery. (+) Notification failures don't fail scoring. (−) Eventual consistency — notification may arrive seconds after score.

**Azure equivalent:** Service Bus topic with subscription consumer.

---

## ADR-005: IAM Service-to-Service Auth (No API Keys)

**Status:** Accepted  
**Context:** Services need to authenticate to each other without shared secrets.  
**Decision:** Cloud Run IAM with `roles/run.invoker`. Risk Scoring's service account invokes Feature Service. No API keys in service mesh.  
**Consequences:** (+) No secrets to rotate. (+) Least privilege per service account. (+) Audit trail in Cloud IAM. (−) Requires IAM binding management in Terraform.

**Azure equivalent:** Managed Identity with RBAC role assignments.

---

## ADR-006: URI Versioning (`/v1/`)

**Status:** Accepted  
**Context:** API will evolve. Consumers need stability guarantees.  
**Decision:** URI-based versioning on all routes. Breaking changes require `/v2/`.  
**Consequences:** (+) Visible in logs and analytics. (+) Easy gateway routing. (−) URL changes on major version.

See [API Governance Design](./api-governance-design.md) for full rationale.

---

## ADR-007: Feature Service Always Warm (min_instances = 1)

**Status:** Accepted  
**Context:** Feature retrieval is on the critical path for every scoring request. Cold start adds 1-3 seconds.  
**Decision:** Feature Service runs with `min_instances = 1`. Risk Scoring and Notification scale to zero.  
**Consequences:** (+) Sub-100ms feature retrieval p99. (−) Baseline cost for one warm instance (~$15-25/month).

**Azure equivalent:** Container Apps `minReplicas = 1` for feature-service.

---

## ADR-008: Portfolio Demo Uses In-Memory Feature Store

**Status:** Accepted (portfolio scope)  
**Context:** Full Vertex AI Feature Store setup requires GCP project provisioning and feature registration pipeline.  
**Decision:** Feature Service uses in-memory dict for portfolio demo. Production path documented: Vertex AI Feature Store online serving.  
**Consequences:** (+) Runnable locally without GCP. (+) Demonstrates service contract. (−) Not production-grade persistence.

**Production migration:** Register features in Vertex AI Feature Store, update Feature Service to call `FeatureOnlineStoreService.read_feature_values()`.
