# GCP Cloud Run Microservices + Apigee API Gateway

**ERP AI Delay Risk Platform — Phase 2 Architecture**  
**Architect:** Dr. Tatianna Gilliam — Cloud & AI Architect (AZ-305 | AI-102 | AZ-104)

---

## Overview

Enterprise-grade decomposition of the monolithic ERP AI Delay Risk FastAPI application into three Cloud Run microservices with Apigee API gateway governance. This is the GCP implementation of the same pattern documented in the Azure API Management + Container Apps Phase 2 upgrade.

**Target roles:** Google Solutions Architect, Apple Multi-Cloud Solutions Architect, any role requiring API-first enterprise architecture.

| Service | Endpoints | Scaling |
|---------|-----------|---------|
| Risk Scoring | `POST /v1/score`, `POST /v1/score/batch` | min 0, max 10 |
| Feature Service | `GET /v1/features/{id}`, `POST /v1/features/batch` | min 1, max 5 |
| Notification | `POST /v1/notify` | min 0, max 3 |

---

## Architecture

```
Client → Apigee (auth, rate limit) → Cloud Run services
                                        ├── Risk Scoring → Feature Service (HTTP + IAM)
                                        └── Pub/Sub → Notification (async)
```

See [docs/microservices-architecture.md](docs/microservices-architecture.md) for full design.

---

## Quick Start (Local)

### 1. Start Feature Service

```bash
cd services/feature-service
pip install -r requirements.txt
python main.py
# Listening on http://localhost:8081
```

### 2. Start Risk Scoring Service

```bash
cd services/risk-scoring-service
pip install -r requirements.txt
set FEATURE_SERVICE_URL=http://localhost:8081
python main.py
# Listening on http://localhost:8080
```

### 3. Start Notification Service

```bash
cd services/notification-service
pip install -r requirements.txt
python main.py
# Listening on http://localhost:8082
```

### 4. Test Scoring

```bash
curl -X POST http://localhost:8080/v1/score ^
  -H "Content-Type: application/json" ^
  -H "X-Request-ID: req_test001" ^
  -d "{\"entity_id\": \"PO-88421\"}"
```

### 5. Test Health (with dependency status)

```bash
curl http://localhost:8080/health
```

---

## Project Structure

```
gcp-microservices-api-gateway/
├── services/           # Three FastAPI microservices
├── gateway/            # OpenAPI spec + Apigee proxy config
├── infrastructure/     # Terraform (Cloud Run, Pub/Sub, Apigee)
├── docs/               # Architecture, governance, Azure comparison
└── portfolio/          # Case study, interview talk track, resume bullets
```

---

## Key Design Patterns

| Pattern | Implementation |
|---------|---------------|
| Circuit breaker | State machine in risk-scoring-service (5 failures/60s → OPEN) |
| API governance | Apigee: auth, rate limit, error standardization |
| Service auth | Cloud Run IAM — no API keys between services |
| Async notification | Pub/Sub publish on high-risk score |
| Degraded mode | Cached features when Feature Service unavailable |

---

## Multi-Cloud Comparison

| GCP | Azure |
|-----|-------|
| Cloud Run | Container Apps |
| Apigee | API Management |
| Pub/Sub | Service Bus |
| IAM Service Accounts | Managed Identity |

See [docs/azure-comparison.md](docs/azure-comparison.md) for full mapping.

---

## Documentation

| Document | Purpose |
|----------|---------|
| [Microservices Architecture](docs/microservices-architecture.md) | Decomposition rationale and service design |
| [API Governance Design](docs/api-governance-design.md) | Governance principles and Apigee vs APIM |
| [Azure Comparison](docs/azure-comparison.md) | Component-level GCP ↔ Azure mapping |
| [Design Decisions](docs/design-decisions.md) | Architecture decision records |
| [OpenAPI Spec](gateway/openapi-spec.yaml) | Full API surface for developer portal |
| [Interview Talk Track](portfolio/interview-talk-track.md) | Google, Apple, and multi-cloud versions |

---

## Deployment

```bash
cd infrastructure
terraform init
terraform plan -var="project_id=YOUR_PROJECT_ID"
terraform apply -var="project_id=YOUR_PROJECT_ID"
```

Build and push container images to Artifact Registry before applying Terraform.

---

## Certifications

AZ-305 (Azure Solutions Architect Expert) | AI-102 (Azure AI Engineer) | AZ-104 (Azure Administrator)
