# Apigee X infrastructure
# Requires Apigee organization provisioned in the GCP project.
# Proxy deployment uses Maven plugin or gcloud apigee APIs post-terraform.

resource "google_apigee_organization" "main" {
  count = var.apigee_org == "" ? 0 : 1

  project_id   = var.project_id
  analytics_region = var.region
  authorized_network = null

  depends_on = [google_project_service.required_apis]
}

resource "google_apigee_envgroup" "main" {
  count = var.apigee_org == "" ? 0 : 1

  name       = "${local.name_prefix}-envgroup"
  org_id     = var.apigee_org != "" ? var.apigee_org : google_apigee_organization.main[0].id
  hostnames  = ["api-${var.environment}.delayrisk.example.com"]
}

resource "google_apigee_environment" "main" {
  count = var.apigee_env == "" ? 0 : 1

  name       = var.apigee_env != "" ? var.apigee_env : "${local.name_prefix}"
  org_id     = var.apigee_org != "" ? var.apigee_org : google_apigee_organization.main[0].id
  display_name = "ERP AI Delay Risk - ${var.environment}"
  description  = "Apigee environment for delay risk API gateway"
}

resource "google_apigee_envgroup_attachment" "main" {
  count = var.apigee_env == "" ? 0 : 1

  envgroup_id  = google_apigee_envgroup.main[0].id
  environment  = google_apigee_environment.main[0].name
}

# Apigee instance (required for Apigee X)
resource "google_apigee_instance" "main" {
  count = var.apigee_org == "" ? 0 : 1

  name     = "${local.name_prefix}-instance"
  location = var.region
  org_id   = var.apigee_org != "" ? var.apigee_org : google_apigee_organization.main[0].id
}

resource "google_apigee_instance_attachment" "main" {
  count = var.apigee_env == "" ? 0 : 1

  instance_id = google_apigee_instance.main[0].id
  environment = google_apigee_environment.main[0].name
}

output "apigee_envgroup_hostnames" {
  description = "Apigee environment group hostnames"
  value       = var.apigee_org != "" ? google_apigee_envgroup.main[0].hostnames : []
}

output "apigee_environment" {
  description = "Apigee environment name"
  value       = var.apigee_env != "" ? var.apigee_env : (length(google_apigee_environment.main) > 0 ? google_apigee_environment.main[0].name : "not-configured")
}

# Azure equivalent (documented, not deployed by this Terraform):
# -azurerm_api_management
# -azurerm_api_management_api (imported from OpenAPI spec)
# -azurerm_api_management_product
# -azurerm_api_management_subscription
