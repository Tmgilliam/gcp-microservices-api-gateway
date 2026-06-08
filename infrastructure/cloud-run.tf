resource "google_cloud_run_v2_service" "feature_service" {
  name     = "${local.name_prefix}-feature-service"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  labels = var.labels

  template {
    service_account = google_service_account.feature_service.email

    scaling {
      min_instance_count = local.services["feature-service"].min_instances
      max_instance_count = local.services["feature-service"].max_instances
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_registry_repo}/feature-service:latest"

      ports {
        container_port = local.services["feature-service"].port
      }

      resources {
        limits = {
          cpu    = local.services["feature-service"].cpu
          memory = local.services["feature-service"].memory
        }
      }

      env {
        name  = "LOG_LEVEL"
        value = "INFO"
      }

      startup_probe {
        http_get {
          path = "/health"
          port = local.services["feature-service"].port
        }
        initial_delay_seconds = 5
        period_seconds        = 10
      }

      liveness_probe {
        http_get {
          path = "/health"
          port = local.services["feature-service"].port
        }
        period_seconds = 30
      }
    }
  }

  depends_on = [
    google_project_service.required_apis,
    google_artifact_registry_repository.services,
  ]
}

resource "google_cloud_run_v2_service" "risk_scoring" {
  name     = "${local.name_prefix}-risk-scoring"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  labels = var.labels

  template {
    service_account = google_service_account.risk_scoring.email

    scaling {
      min_instance_count = local.services["risk-scoring"].min_instances
      max_instance_count = local.services["risk-scoring"].max_instances
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_registry_repo}/risk-scoring:latest"

      ports {
        container_port = local.services["risk-scoring"].port
      }

      resources {
        limits = {
          cpu    = local.services["risk-scoring"].cpu
          memory = local.services["risk-scoring"].memory
        }
      }

      env {
        name  = "FEATURE_SERVICE_URL"
        value = google_cloud_run_v2_service.feature_service.uri
      }

      env {
        name  = "PUBSUB_TOPIC"
        value = google_pubsub_topic.high_risk_events.name
      }

      env {
        name  = "LOG_LEVEL"
        value = "INFO"
      }

      startup_probe {
        http_get {
          path = "/health"
          port = local.services["risk-scoring"].port
        }
        initial_delay_seconds = 5
        period_seconds        = 10
      }

      liveness_probe {
        http_get {
          path = "/health"
          port = local.services["risk-scoring"].port
        }
        period_seconds = 30
      }
    }
  }

  depends_on = [
    google_project_service.required_apis,
    google_artifact_registry_repository.services,
    google_cloud_run_v2_service.feature_service,
  ]
}

resource "google_cloud_run_v2_service" "notification" {
  name     = "${local.name_prefix}-notification"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  labels = var.labels

  template {
    service_account = google_service_account.notification.email

    scaling {
      min_instance_count = local.services["notification"].min_instances
      max_instance_count = local.services["notification"].max_instances
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_registry_repo}/notification:latest"

      ports {
        container_port = local.services["notification"].port
      }

      resources {
        limits = {
          cpu    = local.services["notification"].cpu
          memory = local.services["notification"].memory
        }
      }

      env {
        name  = "LOG_LEVEL"
        value = "INFO"
      }

      startup_probe {
        http_get {
          path = "/health"
          port = local.services["notification"].port
        }
        initial_delay_seconds = 5
        period_seconds        = 10
      }
    }
  }

  depends_on = [
    google_project_service.required_apis,
    google_artifact_registry_repository.services,
  ]
}

# IAM: Risk Scoring can invoke Feature Service
resource "google_cloud_run_v2_service_iam_member" "risk_scoring_invokes_feature" {
  name     = google_cloud_run_v2_service.feature_service.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.risk_scoring.email}"
}

# IAM: Apigee invoker can call all services
resource "google_cloud_run_v2_service_iam_member" "apigee_invokes_risk_scoring" {
  name     = google_cloud_run_v2_service.risk_scoring.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.apigee_invoker.email}"
}

resource "google_cloud_run_v2_service_iam_member" "apigee_invokes_feature" {
  name     = google_cloud_run_v2_service.feature_service.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.apigee_invoker.email}"
}

resource "google_cloud_run_v2_service_iam_member" "apigee_invokes_notification" {
  name     = google_cloud_run_v2_service.notification.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.apigee_invoker.email}"
}

output "risk_scoring_url" {
  description = "Cloud Run URL for risk scoring service"
  value       = google_cloud_run_v2_service.risk_scoring.uri
}

output "feature_service_url" {
  description = "Cloud Run URL for feature service"
  value       = google_cloud_run_v2_service.feature_service.uri
}

output "notification_url" {
  description = "Cloud Run URL for notification service"
  value       = google_cloud_run_v2_service.notification.uri
}

output "pubsub_topic" {
  description = "Pub/Sub topic for high-risk events"
  value       = google_pubsub_topic.high_risk_events.name
}
