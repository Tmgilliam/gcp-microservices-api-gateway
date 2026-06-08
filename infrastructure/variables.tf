variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "artifact_registry_repo" {
  description = "Artifact Registry repository name"
  type        = string
  default     = "delay-risk"
}

variable "risk_scoring_min_instances" {
  description = "Minimum Cloud Run instances for risk scoring service"
  type        = number
  default     = 0
}

variable "risk_scoring_max_instances" {
  description = "Maximum Cloud Run instances for risk scoring service"
  type        = number
  default     = 10
}

variable "feature_service_min_instances" {
  description = "Minimum Cloud Run instances for feature service (always warm)"
  type        = number
  default     = 1
}

variable "feature_service_max_instances" {
  description = "Maximum Cloud Run instances for feature service"
  type        = number
  default     = 5
}

variable "notification_min_instances" {
  description = "Minimum Cloud Run instances for notification service"
  type        = number
  default     = 0
}

variable "notification_max_instances" {
  description = "Maximum Cloud Run instances for notification service"
  type        = number
  default     = 3
}

variable "apigee_org" {
  description = "Apigee organization name"
  type        = string
  default     = ""
}

variable "apigee_env" {
  description = "Apigee environment name"
  type        = string
  default     = ""
}

variable "labels" {
  description = "Labels applied to all resources"
  type        = map(string)
  default = {
    project     = "erp-ai-delay-risk"
    managed_by  = "terraform"
    architect   = "tatianna-gilliam"
  }
}
