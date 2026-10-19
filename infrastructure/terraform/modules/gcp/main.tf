locals {
  name = "cloudsentinel-${var.environment}"
  labels = merge(
    {
      project     = "cloudsentinel"
      environment = var.environment
      managed_by  = "terraform"
    },
    var.labels,
  )
}

resource "google_project_service" "required" {
  for_each = toset([
    "compute.googleapis.com",
    "container.googleapis.com",
    "iam.googleapis.com",
    "artifactregistry.googleapis.com",
  ])
  project = var.project_id
  service = each.value
  # Destroying this environment must not disable APIs the rest of the project still uses.
  disable_on_destroy = false
}

resource "google_compute_network" "this" {
  name                    = "${local.name}-vpc"
  project                 = var.project_id
  auto_create_subnetworks = false
  depends_on              = [google_project_service.required]
}

resource "google_compute_subnetwork" "nodes" {
  name                     = "${local.name}-nodes"
  project                  = var.project_id
  region                   = var.region
  network                  = google_compute_network.this.id
  ip_cidr_range            = "10.20.0.0/20"
  private_ip_google_access = true

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.40.0.0/14"
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.80.0.0/20"
  }
}

resource "google_service_account" "nodes" {
  account_id   = "${local.name}-nodes"
  display_name = "CloudSentinel GKE nodes"
  project      = var.project_id
}

resource "google_project_iam_member" "node_roles" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/artifactregistry.reader",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.nodes.email}"
}

resource "google_service_account" "analysis" {
  account_id   = "${local.name}-analysis"
  display_name = "CloudSentinel analysis workload"
  project      = var.project_id
}

resource "google_service_account_iam_member" "analysis_workload_identity" {
  service_account_id = google_service_account.analysis.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.namespace}/${var.service_account_name}]"
}

resource "google_artifact_registry_repository" "this" {
  location      = var.region
  repository_id = "${local.name}-images"
  description   = "CloudSentinel container images"
  format        = "DOCKER"
  project       = var.project_id
  labels        = local.labels
  depends_on    = [google_project_service.required]
}

resource "google_container_cluster" "this" {
  name     = "${local.name}-gke"
  location = var.zone
  project  = var.project_id

  # The provider refuses to destroy a cluster unless this is false in state.
  deletion_protection = var.deletion_protection

  networking_mode = "VPC_NATIVE"
  network         = google_compute_network.this.name
  subnetwork      = google_compute_subnetwork.nodes.name

  remove_default_node_pool = true
  initial_node_count       = 1

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  release_channel {
    channel = "REGULAR"
  }

  logging_service    = var.enable_monitoring ? "logging.googleapis.com/kubernetes" : "none"
  monitoring_service = var.enable_monitoring ? "monitoring.googleapis.com/kubernetes" : "none"

  dynamic "master_authorized_networks_config" {
    for_each = length(var.master_authorized_cidrs) > 0 ? [1] : []
    content {
      dynamic "cidr_blocks" {
        for_each = var.master_authorized_cidrs
        content {
          cidr_block   = cidr_blocks.value
          display_name = "operator"
        }
      }
    }
  }

  resource_labels = local.labels
  depends_on      = [google_project_service.required]
}

resource "google_container_node_pool" "default" {
  name     = "default"
  location = var.zone
  cluster  = google_container_cluster.this.name
  project  = var.project_id

  node_count = var.node_count

  node_config {
    machine_type    = var.machine_type
    disk_size_gb    = 30
    disk_type       = "pd-standard"
    service_account = google_service_account.nodes.email
    labels          = local.labels
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    metadata = {
      disable-legacy-endpoints = "true"
    }
  }
}
