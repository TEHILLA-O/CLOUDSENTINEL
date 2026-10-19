output "network_name" {
  value = google_compute_network.this.name
}

output "cluster_name" {
  value = google_container_cluster.this.name
}

output "cluster_location" {
  value = google_container_cluster.this.location
}

output "cluster_endpoint" {
  value     = google_container_cluster.this.endpoint
  sensitive = true
}

output "artifact_registry_repository" {
  value = google_artifact_registry_repository.this.id
}

output "node_service_account" {
  value = google_service_account.nodes.email
}

output "analysis_service_account" {
  value = google_service_account.analysis.email
}

output "workload_pool" {
  value = "${var.project_id}.svc.id.goog"
}
