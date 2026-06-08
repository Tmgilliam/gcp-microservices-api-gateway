terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  name_prefix = "delay-risk-${var.environment}"

  services = {
    risk-scoring = {
      port          = 8080
      min_instances = var.risk_scoring_min_instances
      max_instances = var.risk_scoring_max_instances
      cpu           = "1"
      memory        = "512Mi"
    }
    feature-service = {
      port          = 8081
      min_instances = var.feature_service_min_instances
      max_instances = var.feature_service_max_instances
      cpu           = "0.5"
      memory        = "256Mi"
    }
    notification = {
      port          = 8082
      min_instances = var.notification_min_instances
      max_instances = var.notification_max_instances
      cpu           = "0.5"
      memory        = "256Mi"
    }
  }
}

resource "google_project_service" "required_apis" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "pubsub.googleapis.com",
    "iam.googleapis.com",
    "apigee.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "services" {
  location      = var.region
  repository_id = var.artifact_registry_repo
  format        = "DOCKER"
  description   = "Container images for ERP AI Delay Risk microservices"

  labels = var.labels

  depends_on = [google_project_service.required_apis]
}

resource "google_service_account" "risk_scoring" {
  account_id   = "${local.name_prefix}-risk-scoring"
  display_name = "Risk Scoring Service Account"
}

resource "google_service_account" "feature_service" {
  account_id   = "${local.name_prefix}-feature-svc"
  display_name = "Feature Service Account"
}

resource "google_service_account" "notification" {
  account_id   = "${local.name_prefix}-notification"
  display_name = "Notification Service Account"
}

resource "google_service_account" "apigee_invoker" {
  account_id   = "${local.name_prefix}-apigee-invoker"
  display_name = "Apigee Gateway Invoker"
}

resource "google_pubsub_topic" "high_risk_events" {
  name = "${local.name_prefix}-high-risk-events"

  labels = var.labels

  depends_on = [google_project_service.required_apis]
}

resource "google_pubsub_topic_iam_member" "risk_scoring_publisher" {
  topic  = google_pubsub_topic.high_risk_events.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.risk_scoring.email}"
}

resource "google_pubsub_subscription" "notification_push" {
  name  = "${local.name_prefix}-notification-push"
  topic = google_pubsub_topic.high_risk_events.name

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.notification.uri}/v1/notify"

    oidc_token {
      service_account_email = google_service_account.notification.email
    }
  }

  ack_deadline_seconds = 30

  depends_on = [google_cloud_run_v2_service.notification]
}
