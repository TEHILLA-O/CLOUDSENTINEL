output "resource_group_name" {
  value = module.platform.resource_group_name
}

output "cluster_name" {
  value = module.platform.cluster_name
}

output "container_registry_login_server" {
  value = module.platform.container_registry_login_server
}

output "oidc_issuer_url" {
  value = module.platform.oidc_issuer_url
}

output "analysis_identity_client_id" {
  value = module.platform.analysis_identity_client_id
}
