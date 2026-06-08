# GCP vs Azure — Component Mapping

**Architect:** Dr. Tatianna Gilliam — Cloud & AI Architect (AZ-305 | AI-102 | AZ-104)  
**Purpose:** Side-by-side mapping proving multi-cloud architecture depth

---

## Platform Component Mapping

| Concern | GCP (This Project) | Azure (Phase 2 Equivalent) |
|---------|-------------------|------------------------------|
| Compute | Cloud Run | Azure Container Apps |
| API Gateway | Apigee X | Azure API Management |
| Async Messaging | Cloud Pub/Sub | Azure Service Bus |
| Service Auth | IAM Service Accounts | Managed Identity + RBAC |
| Feature Store | Vertex AI Feature Store | Azure ML Feature Store |
| Container Registry | Artifact Registry | Azure Container Registry |
| WAF | Cloud Armor | Application Gateway + WAF |
| Logging | Cloud Logging | Azure Monitor + Log Analytics |
| Secrets | Secret Manager | Azure Key Vault |
| IaC | Terraform (Google provider) | Terraform / Bicep (Azure provider) |
| Identity (external) | API key via Apigee | Subscription key via APIM |
| Identity (internal) | Workload Identity / IAM | Managed Identity |

---

## Request Flow Comparison

### GCP

```
Client
  │ X-API-Key
  ▼
Apigee (auth, rate limit, routing)
  │ IAM service account token
  ▼
Cloud Run: risk-scoring-service
  │ IAM ID token
  ├──▶ Cloud Run: feature-service
  │
  │ Pub/Sub publish
  ▼
Cloud Pub/Sub: high-risk-events
  │ push subscription (OIDC)
  ▼
Cloud Run: notification-service
```

### Azure

```
Client
  │ Ocp-Apim-Subscription-Key
  ▼
Azure API Management (auth, rate limit, routing)
  │ Managed Identity
  ▼
Container Apps: risk-scoring
  │ Managed Identity
  ├──▶ Container Apps: feature-service
  │
  │ Service Bus publish
  ▼
Service Bus: high-risk-events topic
  │ subscription
  ▼
Container Apps: notification-service
```

---

## Scaling Configuration Comparison

| Service | GCP Cloud Run | Azure Container Apps |
|---------|--------------|---------------------|
| Risk Scoring | min: 0, max: 10, 1 vCPU, 512MB | min: 0, max: 10, 1.0 CPU, 0.5Gi |
| Feature Service | min: 1, max: 5, 0.5 vCPU, 256MB | min: 1, max: 5, 0.5 CPU, 0.25Gi |
| Notification | min: 0, max: 3, 0.5 vCPU, 256MB | min: 0, max: 3, 0.5 CPU, 0.25Gi |

---

## Gateway Policy Comparison

| Policy | Apigee XML | Azure APIM XML |
|--------|-----------|----------------|
| API key validation | `<VerifyAPIKey>` | `<check-header name="Ocp-Apim-Subscription-Key">` |
| Rate limit (100/min) | `<Quota>` with 1-minute interval | `<rate-limit calls="100" renewal-period="60" />` |
| Burst protection | `<SpikeArrest rate="30ps">` | `<rate-limit-by-key>` |
| Error standardization | `<RaiseFault>` + `<AssignMessage>` | `<return-response>` in `on-error` |
| Backend routing | `<RouteRule>` + TargetEndpoint | `<set-backend-service>` |
| Correlation ID | `<AssignMessage>` on X-Request-ID | `<set-header name="X-Request-ID">` |

---

## When to Choose Which Platform

| Factor | Choose GCP | Choose Azure |
|--------|-----------|-------------|
| Existing data platform | BigQuery, Vertex AI | Fabric, Azure ML, Synapse |
| Existing identity | Google Workspace | Microsoft Entra ID |
| API gateway preference | Apigee policy flexibility | APIM Entra ID integration |
| Streaming analytics | Pub/Sub + Dataflow | Event Hubs + Stream Analytics |
| Multi-cloud mandate | Deploy both — same pattern | Deploy both — same pattern |

---

## Architect's Statement

> "I don't recommend switching clouds for the gateway or compute layer. The migration cost exceeds the product difference. I recommend choosing the platform the organization has already committed to, and designing the architecture so it transfers. This portfolio proves that transfer — same decomposition, same governance, same resilience patterns, two implementations."
