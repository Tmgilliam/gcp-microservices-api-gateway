# API Governance Design — ERP AI Delay Risk Platform

**Architect:** Dr. Tatianna Gilliam — Cloud & AI Architect (AZ-305 | AI-102 | AZ-104)  
**Project:** GCP Cloud Run Microservices + Apigee API Gateway

---

## Purpose

This document defines the API governance model for the decomposed ERP AI Delay Risk platform. API governance is not documentation — it is the set of policies, standards, and enforcement mechanisms that make an API platform safe for enterprise consumers at scale.

The gateway (Apigee on GCP, Azure API Management on Azure) is the enforcement point. Services implement business logic; the gateway implements policy.

---

## API Design Principles

### 1. Versioning — URI Prefix (`/v1/`)

**Decision:** URI-based versioning on all routes.

| Strategy | Example | Pros | Cons |
|----------|---------|------|------|
| URI versioning | `/v1/score` | Visible, cacheable, easy routing | URL changes on major version |
| Header versioning | `Accept: application/vnd.delayrisk.v1+json` | Clean URLs | Harder to route at gateway, invisible in logs |
| Query param | `/score?version=1` | Simple | Easy to forget, poor caching |

**Why URI versioning:**

- Apigee and APIM route on path prefixes — `/v1/score` maps cleanly to a proxy target without custom policy logic
- Developer portal documentation maps 1:1 to URL structure
- API consumers can pin to `/v1/` while `/v2/` runs in parallel during migration
- Cloud Logging and Apigee Analytics aggregate by path prefix without header parsing

**Versioning policy:**

- Breaking changes require a new major version (`/v2/`)
- Non-breaking additions (new optional fields, new endpoints) stay in current version
- Deprecation: 6-month notice, `Sunset` header on deprecated endpoints, parallel `/v2/` availability

### 2. Consistent Error Format

Every error response — whether from Apigee, a Cloud Run service, or a timeout — returns:

```json
{
  "error_code": "RATE_LIMIT_EXCEEDED",
  "message": "Rate limit exceeded. Standard tier allows 100 req/min.",
  "request_id": "req_a1b2c3d4e5f6",
  "timestamp": "2026-06-08T14:32:00Z"
}
```

**Why `request_id` is in every error:**

- A consumer reports "I got an error at 2:32 PM." Without `request_id`, that is a needle-in-a-haystack search across three services and a gateway.
- With `request_id`, you trace the full path: Apigee analytics → Cloud Run request log → Feature Service dependency call → Pub/Sub publish.
- `request_id` propagates via `X-Request-ID` header from gateway through all service-to-service calls.
- This is the difference between "we had an outage" and "request `req_a1b2c3d4e5f6` failed because Feature Service returned 503 at T+142ms, circuit breaker opened, degraded response served from cache."

Apigee's `AssignMessage` and `RaiseFault` policies standardize gateway-generated errors. Service-level errors are transformed at the proxy layer to match the same schema.

### 3. Idempotency — `POST /v1/score`

`POST /v1/score` is idempotent for the same `entity_id` + feature set.

**Why this matters:**

- Clients retry on network timeouts, 503 responses, and gateway 504s
- Without idempotency guarantees, a retry could double-publish high-risk notifications
- Scoring is a pure function: same inputs → same outputs. No side effects except notification on high risk
- Notification deduplication uses `entity_id + scoring_timestamp` to prevent duplicate alerts on retry

**Implementation:**

- Scoring itself is stateless and deterministic
- High-risk Pub/Sub events include `request_id` for deduplication at the notification consumer
- Batch async jobs use `job_id` for status polling — submitting the same batch twice creates two jobs (documented behavior)

### 4. Rate Limiting at the Gateway, Not the Service

**Decision:** All rate limiting enforced by Apigee Quota policy. Services do not implement per-client rate limits.

**Why centralized rate limiting is correct:**

| Concern | Gateway enforcement | Per-service enforcement |
|---------|--------------------|-----------------------|
| Consistency | One policy, all endpoints | Each team implements differently |
| Consumer experience | Single quota across API surface | Consumer hits different limits per service |
| Operational burden | Change quota in one place | Update N services, redeploy N times |
| Evasion | Impossible — no direct service access | Consumer calls service URL directly |
| Cost | Gateway handles counting | Each service burns CPU on rate limit logic |

Services are not publicly accessible. All external traffic flows through Apigee. There is no path to bypass gateway rate limits.

**Tiers:**

| Tier | Rate Limit | Quota (daily) | Target Consumer |
|------|-----------|---------------|-----------------|
| Standard | 100 req/min | 10,000/day | Internal dashboards, dev teams |
| Enterprise | 1,000 req/min | 500,000/day | ERP integrations, planning systems |
| Internal | Unlimited | Unlimited | Service-to-service via IAM (not API key) |

### 5. Authentication at the Gateway Edge — Zero Trust

**Decision:** API key validation at Apigee preflow. Services trust the gateway; they do not re-validate API keys.

**Zero Trust model:**

```
External client ──[API key]──▶ Apigee ──[IAM token]──▶ Cloud Run service
                                    │
                                    ├─ Validates API key
                                    ├─ Enforces rate limit
                                    ├─ Transforms errors
                                    └─ Routes to backend
```

- External callers authenticate with API keys at the gateway edge
- Apigee validates the key against the API product and developer app
- Apigee calls Cloud Run using a service account with `roles/run.invoker`
- Cloud Run services reject requests without a valid IAM identity — no anonymous access
- Service-to-service calls (Risk Scoring → Feature Service) use workload identity, not API keys

**Why services don't re-validate:**

- Duplicating auth logic in every service creates drift — one service updates, others don't
- API key in service logs is a security risk
- Gateway is the single policy enforcement point — change auth method once, all services inherit
- Services focus on business logic; gateway focuses on governance

**Azure equivalent:** APIM validates subscription keys at the inbound policy. Container Apps trust APIM's managed identity. Same pattern.

---

## Apigee Policy Architecture

### Proxy Structure

```
apiproxy/
├── proxies/default.xml          # Route rules
└── policies/
    ├── Verify-API-Key.xml       # Authentication
    ├── Quota-Standard.xml       # Rate limiting
    ├── Spike-Arrest.xml         # Burst protection
    ├── Assign-Request-ID.xml    # Correlation ID
    ├── Route-to-Scoring.xml     # Backend routing
    ├── Route-to-Features.xml
    ├── Route-to-Notification.xml
    ├── Transform-Error.xml      # Standardize errors
    └── CORS.xml                 # Developer portal CORS
```

### Request Flow

1. **Preflow — Authentication:** `Verify-API-Key` validates `X-API-Key` header
2. **Preflow — Rate Limit:** `Quota-Standard` enforces 100 req/min per key
3. **Preflow — Correlation:** `Assign-Request-ID` generates or passes through `X-Request-ID`
4. **Route:** Path-based routing to Cloud Run backend
5. **Response — Transform:** Standardize error format on 4xx/5xx
6. **Response — Headers:** Add `X-RateLimit-Remaining`, `X-RateLimit-Limit`

---

## Apigee vs Azure API Management — Detailed Comparison

This is the interview-critical section. Both products solve the same problem. The conceptual model is identical.

| Capability | Apigee (GCP) | Azure API Management |
|------------|-------------|---------------------|
| Policy language | XML-based proxy policies | XML policy expressions (`<inbound>`, `<backend>`, `<outbound>`) |
| Developer portal | Built-in, customizable | Built-in, customizable (new developer portal) |
| Rate limiting | Quota policy + Spike Arrest | `rate-limit` + `quota` policies |
| Authentication | API key, OAuth 2.0, SAML, JWT | API key (subscription key), OAuth 2.0, JWT, Entra ID |
| Backend targets | Cloud Run, GKE, Cloud Functions, external | Container Apps, AKS, Functions, external |
| Request routing | RouteRules + TargetEndpoints | `<set-backend-service>` + backends |
| Transformation | AssignMessage, XML-to-JSON, JavaScript | `set-body`, `set-header`, Liquid templates |
| Analytics | Apigee Analytics dashboard | Azure Monitor + APIM built-in analytics |
| Caching | Response cache policy | Built-in cache (internal + external) |
| Monetization | API products, rate plans | API products (via Azure Marketplace) |
| WAF integration | Cloud Armor (front of Apigee) | Application Gateway WAF (front of APIM) |
| Service-to-service auth | IAM + service accounts | Managed Identity + RBAC |
| Pricing model | Pay-per-call or subscription | Consumption tier or dedicated (VNet-isolated) |
| Multi-region | Apigee X multi-region | APIM multi-region (Premium tier) |
| CI/CD deployment | Apigee Maven plugin, Terraform | APIM DevOps Resource Kit, Bicep/Terraform |

### Policy Equivalence Examples

**Rate limiting (100 req/min):**

Apigee:
```xml
<Quota name="Quota-Standard" type="calendar">
  <Allow count="100" countRef="request.header.allowed_quota"/>
  <Interval>1</Interval>
  <TimeUnit>minute</TimeUnit>
  <Identifier ref="client_id"/>
</Quota>
```

Azure APIM:
```xml
<rate-limit calls="100" renewal-period="60" />
```

**API key validation:**

Apigee: `VerifyAPIKey` policy in preflow  
Azure APIM: `check-header` or `validate-azure-ad-token` in inbound

**Error transformation:**

Apigee: `RaiseFault` + `AssignMessage` with standard JSON body  
Azure APIM: `return-response` with template in `on-error` section

### Architect's Framing

> "The conceptual model is identical. Both are API gateway products that handle auth, rate limiting, transformation, and routing. Apigee has more flexibility in policy composition — you can chain JavaScript callouts and conditional flows with fine granularity. APIM has tighter Azure native integration — Entra ID, Managed Identity, Azure Monitor, and Bicep deployment are first-class. Choose based on the platform you're already on. I have deployed both. The governance principles — versioning, error format, idempotency, centralized rate limiting, edge auth — are platform-agnostic."

---

## Developer Portal

The OpenAPI specification (`gateway/openapi-spec.yaml`) is the source of truth published in the Apigee Developer Portal.

**Onboarding flow:**

1. Developer registers in portal
2. Creates an app → receives API key
3. Selects API product tier (Standard / Enterprise)
4. API key is bound to product → quota and rate limits apply
5. Developer tests against sandbox environment
6. Promotes to production with approval gate

**Azure equivalent:** APIM Developer Portal with subscription key issuance per API product.

---

## Observability and Governance Metrics

| Metric | Source | Alert Threshold |
|--------|--------|----------------|
| Request latency p99 | Apigee Analytics | > 500ms |
| Error rate (5xx) | Apigee + Cloud Run | > 1% over 5 min |
| Quota consumption | Apigee Analytics | > 80% of daily quota |
| Rate limit hits (429) | Apigee Analytics | > 50/hour per consumer |
| Circuit breaker state | Risk Scoring `/health` | `open` for > 5 min |
| Auth failures (401) | Apigee Analytics | Spike detection |

---

## Azure Equivalent Governance

| GCP Governance | Azure Equivalent |
|---------------|-----------------|
| Apigee API products | APIM API products |
| Apigee developer apps | APIM subscriptions |
| Apigee Quota policy | APIM `quota` policy |
| Apigee VerifyAPIKey | APIM subscription key validation |
| Apigee Analytics | Azure Monitor + APIM Insights |
| Cloud Run IAM invoker | Container Apps Managed Identity |
| OpenAPI in Developer Portal | OpenAPI in APIM Developer Portal |

Same governance model. Different product names.

---

## Related Documents

- [Microservices Architecture](./microservices-architecture.md)
- [Azure Comparison](./azure-comparison.md)
- [Design Decisions](./design-decisions.md)
- [OpenAPI Specification](../gateway/openapi-spec.yaml)
