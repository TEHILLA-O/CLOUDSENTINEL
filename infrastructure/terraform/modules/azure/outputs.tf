output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "cluster_name" {
  value = azurerm_kubernetes_cluster.this.name
}

output "cluster_id" {
  value = azurerm_kubernetes_cluster.this.id
}

output "cluster_fqdn" {
  value = azurerm_kubernetes_cluster.this.fqdn
}

output "oidc_issuer_url" {
  value = azurerm_kubernetes_cluster.this.oidc_issuer_url
}

output "container_registry_login_server" {
  value = azurerm_container_registry.this.login_server
}

output "analysis_identity_client_id" {
  value = azurerm_user_assigned_identity.analysis.client_id
}

output "kubelet_identity_object_id" {
  value = azurerm_kubernetes_cluster.this.kubelet_identity[0].object_id
}
