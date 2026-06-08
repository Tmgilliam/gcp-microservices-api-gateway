# Interview Talk Track — GCP Microservices + Apigee API Gateway

**Architect:** Dr. Tatianna Gilliam — Cloud & AI Architect (AZ-305 | AI-102 | AZ-104)

---

## VERSION 1 — For Google Interviewers

**Prompt:** "Walk me through a GCP architecture you designed."

### 60-Second Version

I decomposed a monolithic ERP AI delay-risk application into three Cloud Run microservices with Apigee as the API governance layer. Risk scoring, feature serving, and notifications have different scaling profiles — scoring spikes during batch runs and scales to zero off-hours; features must stay warm for sub-100ms latency. Service-to-service auth uses IAM workload identity, no API keys in the mesh. Apigee handles rate limiting, API key validation, error standardization, and developer portal. When the Feature Service degrades, a circuit breaker returns cached features instead of failing the request. High-risk scores publish to Pub/Sub for async notification. I have the same pattern on Azure with APIM and Container Apps — same architecture, different primitives.

### 3-Minute Version

**Frame the problem:**

The ERP AI Delay Risk platform started as a single FastAPI service on Cloud Run. That was correct for proof of concept. At enterprise scale, three things broke: scaling profiles diverged, deployment blast radius was too large, and there was no API governance layer for external consumers.

**Decomposition rationale:**

I split into three services based on scaling and ownership boundaries:

1. **Risk Scoring** — ML inference. Spiky traffic (batch runs at 2 AM), scales to zero off-hours. 1 vCPU, 512 MB.
2. **Feature Service** — online feature serving. Steady read-heavy traffic, must stay warm. min_instances = 1. 0.5 vCPU, 256 MB.
3. **Notification** — event-driven alerts. min_instances = 0, triggered by Pub/Sub when risk_score >= 0.75.

The monolith forced one scaling config for all three. Decomposition saves cost and improves latency.

**Apigee as governance layer:**

External consumers never call Cloud Run directly. Apigee validates API keys, enforces 100 req/min quotas, standardizes error format with `request_id` for traceability, and routes to the correct backend. Services trust the gateway — they don't re-validate API keys. Internal service-to-service calls use IAM identity tokens.

**Resilience — circuit breaker:**

Risk Scoring depends on Feature Service. I implemented a state-machine circuit breaker: 5 failures in 60 seconds opens the circuit, returns cached features with `feature_source: cache`, probes recovery every 30 seconds in HALF_OPEN. Degraded response beats hard failure — a stale feature vector still produces a useful risk signal.

**Service-to-service IAM:**

Risk Scoring's service account holds `roles/run.invoker` on Feature Service. No secrets in code, no API keys between services. Cloud Run rejects requests without valid IAM identity. This is the GCP equivalent of Managed Identity on Azure Container Apps.

**Close:**

This is Phase 2 of the ERP AI platform. Phase 1 was the monolith. This decomposition is the GCP answer to the Azure APIM + Container Apps architecture in my portfolio. Same pattern, two platforms, two implementations.

### Follow-Up Answers (Google-Specific)

**"Why Cloud Run over GKE?"**

For three stateless HTTP services with independent scaling and no persistent connections, Cloud Run is the right abstraction. I don't need pod scheduling, service mesh sidecars, or cluster management. If I had 30+ services with complex inter-service routing, I'd evaluate GKE with Anthos Service Mesh. At three services, Cloud Run's operational simplicity wins.

**"Why Apigee over Cloud Endpoints or API Gateway?"**

Cloud Endpoints and API Gateway handle routing and auth. Apigee adds developer portal, API products, monetization, advanced policy composition (JavaScript callouts, conditional flows), and enterprise analytics. For an internal API with three consumers, Endpoints is sufficient. For an enterprise API platform with external developers, quota tiers, and governance requirements, Apigee is the correct product.

**"How does the circuit breaker interact with Cloud Run scaling?"**

They're independent concerns. The circuit breaker protects against Feature Service failures — it doesn't affect Risk Scoring's instance count. Cloud Run scales Risk Scoring based on request concurrency. If Feature Service is down, Risk Scoring still serves requests from cache — it doesn't scale down because it's still processing traffic, just in degraded mode.

---

## VERSION 2 — For Apple Interviewers

**Prompt:** "How would you architect an enterprise API platform on GCP?"

### 60-Second Version

Enterprise API platforms need three layers: a gateway for governance, microservices for business logic, and async messaging for side effects. I built this on GCP with Apigee, Cloud Run, and Pub/Sub. The gateway handles auth, rate limiting, and error standardization. Services communicate synchronously via HTTP with IAM identity and asynchronously via Pub/Sub. This is architecturally identical to what large enterprises run internally — API gateway, service mesh principles, workload identity. I have the Azure equivalent with APIM and Container Apps. The pattern transfers across clouds because the problem is the same.

### 3-Minute Version

**Frame the enterprise API platform problem:**

Every large organization eventually needs an API platform — not just APIs, but governed APIs. That means authentication, rate limiting, versioning, developer onboarding, analytics, and consistent error contracts. Without a gateway layer, each team builds its own auth, its own rate limits, its own error format. That doesn't scale.

**The three-layer model:**

1. **Gateway layer (Apigee):** Single entry point. API key auth, quota enforcement, request routing, error transformation, developer portal. External consumers interact only with the gateway.
2. **Service layer (Cloud Run):** Business logic in independently deployable containers. Each service has its own scaling config, its own on-call rotation, its own deployment pipeline.
3. **Event layer (Pub/Sub):** Side effects that shouldn't block the request path. High-risk notifications are fire-and-forget — scoring returns immediately, Pub/Sub delivers the alert asynchronously.

**Multi-cloud comparison angle:**

This is the pattern Apple and other large enterprises run on their internal platforms. The names change — Apigee becomes an internal gateway, Cloud Run becomes a container platform, Pub/Sub becomes a message bus — but the architecture is the same:

- Gateway enforces policy at the edge
- Services authenticate via workload identity, not shared secrets
- Async messaging decouples producers from consumers
- Circuit breakers protect against cascading failures
- Health checks report dependency status, not just process status

I have deployed this exact pattern on Azure: APIM gateway, Container Apps services, Service Bus messaging, Managed Identity auth. The portfolio proves I can design the pattern once and implement it on whichever platform the organization uses.

**IAM service-to-service auth:**

No API keys between services. Risk Scoring's service account gets `roles/run.invoker` on Feature Service. Identity is the credential. If a service account is compromised, you revoke one IAM binding — not every API key in the system. This is Zero Trust: authenticate every call, authorize least privilege, no implicit trust.

**Close:**

The API platform is the product. The microservices are implementations. The gateway is what makes it enterprise-ready. I design the platform first, then choose the cloud primitives.

### Follow-Up Answers (Apple-Specific)

**"How does this compare to a service mesh?"**

Apigee handles north-south traffic (external → services). A service mesh like Istio handles east-west traffic (service → service). For three services with simple HTTP calls, a full mesh is over-engineering. Cloud Run IAM auth covers service-to-service security. If the platform grows to 20+ services with complex routing, retries, and observability requirements, I'd add Anthos Service Mesh. The gateway layer stays — mesh complements it, doesn't replace it.

**"What about API versioning at scale?"**

URI versioning (`/v1/`, `/v2/`) with 6-month deprecation windows. Apigee routes both versions in parallel during migration. Old consumers stay on `/v1/`, new consumers adopt `/v2/`. When `/v1/` traffic drops below threshold, decommission. I've managed this on APIM with the same policy — the versioning strategy is platform-agnostic.

---

## VERSION 3 — For Any Multi-Cloud Interviewer

**Prompt:** "Compare Apigee to Azure API Management."

### 60-Second Version

Same problem, same pattern, different service names. Both are API gateway products that handle authentication, rate limiting, request routing, response transformation, and developer portals. Apigee uses XML proxy policies; APIM uses XML policy expressions in inbound/backend/outbound sections. Apigee has more policy composition flexibility; APIM has tighter Azure native integration with Entra ID and Managed Identity. I choose based on the platform the organization is already on. The governance principles — URI versioning, consistent error format, centralized rate limiting, edge authentication — are identical.

### 3-Minute Version — Comparison Walkthrough

**Open with the framing:**

> "The conceptual model is identical. Both are API gateway products. I don't think of them as competitors — I think of them as the same architectural role on different platforms."

**Walk the comparison table:**

| Capability | Apigee | Azure APIM | My Take |
|------------|--------|------------|---------|
| Policy language | XML proxy policies | XML policy expressions | Functionally equivalent — both are declarative XML |
| Rate limiting | Quota + Spike Arrest | `rate-limit` + `quota` | Same capability, different syntax |
| Auth | API key, OAuth, SAML, JWT | Subscription key, OAuth, JWT, Entra ID | APIM wins on Entra ID native; Apigee wins on SAML |
| Backend | Cloud Run, GKE, external | Container Apps, AKS, external | Platform-native targets — choose your compute |
| Analytics | Apigee Analytics | Azure Monitor + APIM Insights | APIM wins on unified Azure Monitor; Apigee wins on API-specific dashboards |
| Developer portal | Built-in | Built-in (new portal) | Both adequate for enterprise |
| Pricing | Pay-per-call or subscription | Consumption or dedicated | APIM Consumption is cost-effective for low volume; Apigee subscription for high volume |

**Concrete example — rate limiting:**

On Apigee, I attach a Quota policy to the API product: 100 calls per minute per `client_id`. On APIM, I add `<rate-limit calls="100" renewal-period="60" />` to the inbound policy. Same outcome. Different XML.

**Concrete example — service-to-service auth:**

On GCP: Apigee calls Cloud Run with a service account (`roles/run.invoker`). Risk Scoring calls Feature Service with an IAM ID token. On Azure: APIM calls Container Apps with Managed Identity. Risk Scoring calls Feature Service with a Managed Identity token. Same pattern — workload identity, no shared secrets.

**Concrete example — async messaging:**

On GCP: Risk Scoring publishes to Pub/Sub, Notification Service consumes via push subscription. On Azure: Risk Scoring publishes to Service Bus topic, Notification Service consumes via subscription. Same decoupled event pattern.

**Land the close:**

> "I have both implementations in my portfolio. The ERP AI Delay Risk monolith evolved into microservices on both platforms. When an interviewer asks 'GCP or Azure?' my answer is 'which platform are you on?' The architecture transfers. The certs prove I can implement on both."

### Follow-Up Answers (Multi-Cloud)

**"Which would you recommend?"**

Whichever platform the organization has committed to. If they're on GCP with BigQuery and Vertex AI, Apigee is the natural gateway. If they're on Azure with Fabric and Azure ML, APIM is the natural gateway. I don't recommend switching clouds for the gateway — the migration cost exceeds the product difference.

**"Have you actually deployed both?"**

I hold AZ-305, AI-102, and AZ-104 — those are deployment-level certs, not theory. The Azure implementation uses APIM, Container Apps, Service Bus, and Managed Identity. The GCP implementation uses Apigee, Cloud Run, Pub/Sub, and IAM service accounts. Same architecture documents, same governance principles, different Terraform modules.

**"What's the hardest part of multi-cloud?"**

Not the architecture — the operational details. IAM models differ (GCP service accounts vs Azure Managed Identity). Policy syntax differs (Apigee XML vs APIM XML). Monitoring integration differs (Cloud Logging vs Azure Monitor). The pattern is portable; the configuration is not. That's why I document both side-by-side — so the pattern is explicit and the platform-specific config is a lookup, not a redesign.

---

## Questions to Ask the Interviewer

1. "What API gateway product is in scope — Apigee, APIM, Kong, or an internal platform?"
2. "How many external API consumers do you support, and what's the onboarding model?"
3. "Is the platform multi-cloud, or GCP/Azure committed?"
4. "What's the current state — monolith, partial microservices, or greenfield?"
5. "What are the SLA requirements for feature serving latency vs scoring throughput?"
