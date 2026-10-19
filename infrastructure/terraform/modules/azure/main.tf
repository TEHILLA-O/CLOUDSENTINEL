locals {
  name = "${var.project}-${var.environment}"
  tags = merge(
    {
      project     = var.project
      environment = var.environment
      managed_by  = "terraform"
    },
    var.tags,
  )
}

resource "azurerm_resource_group" "this" {
  name     = "${local.name}-rg"
  location = var.location
  tags     = local.tags
}

resource "azurerm_virtual_network" "this" {
  name                = "${local.name}-vnet"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  address_space       = ["10.10.0.0/16"]
  tags                = local.tags
}

resource "azurerm_subnet" "nodes" {
  name                 = "nodes"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = ["10.10.0.0/20"]
}

resource "azurerm_log_analytics_workspace" "this" {
  count               = var.enable_monitoring ? 1 : 0
  name                = "${local.name}-logs"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_kubernetes_cluster" "this" {
  name                = "${local.name}-aks"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  dns_prefix          = replace(local.name, "-", "")
  kubernetes_version  = var.kubernetes_version
  sku_tier            = "Free"
  oidc_issuer_enabled = true
  # Workload identity needs the OIDC issuer. The application identity is bound below;
  # pods do not get a stored client secret.
  workload_identity_enabled = true
  local_account_disabled    = length(var.admin_group_object_ids) > 0
  azure_policy_enabled      = true
  tags                      = local.tags

  default_node_pool {
    name                 = "system"
    node_count           = var.node_count
    vm_size              = var.vm_size
    os_disk_size_gb      = 32
    vnet_subnet_id       = azurerm_subnet.nodes.id
    type                 = "VirtualMachineScaleSets"
    auto_scaling_enabled = false
  }

  identity {
    type = "SystemAssigned"
  }

  # Required by azurerm 5.x. Manual mode avoids an extra auto-provisioned pool.
  node_provisioning_profile {
    mode               = "Manual"
    default_node_pools = "None"
  }

  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    network_policy      = "azure"
    service_cidr        = "10.1.0.0/16"
    dns_service_ip      = "10.1.0.10"
    outbound_type       = "loadBalancer"
  }

  azure_active_directory_role_based_access_control {
    azure_rbac_enabled     = true
    admin_group_object_ids = var.admin_group_object_ids
  }

  dynamic "api_server_access_profile" {
    for_each = length(var.api_server_authorized_cidrs) > 0 ? [1] : []
    content {
      authorized_ip_ranges = var.api_server_authorized_cidrs
    }
  }

  dynamic "oms_agent" {
    for_each = var.enable_monitoring ? [1] : []
    content {
      log_analytics_workspace_id = azurerm_log_analytics_workspace.this[0].id
    }
  }
}

resource "azurerm_container_registry" "this" {
  name                = replace("${var.project}${var.environment}acr", "-", "")
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  sku                 = "Basic"
  admin_enabled       = false
  tags                = local.tags
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                            = azurerm_container_registry.this.id
  role_definition_name             = "AcrPull"
  principal_id                     = azurerm_kubernetes_cluster.this.kubelet_identity[0].object_id
  skip_service_principal_aad_check = true
}

resource "azurerm_user_assigned_identity" "analysis" {
  name                = "${local.name}-analysis"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

resource "azurerm_federated_identity_credential" "analysis" {
  name                      = "analysis-api"
  user_assigned_identity_id = azurerm_user_assigned_identity.analysis.id
  audience                  = ["api://AzureADTokenExchange"]
  issuer                    = azurerm_kubernetes_cluster.this.oidc_issuer_url
  subject                   = "system:serviceaccount:${var.namespace}:${var.service_account_name}"
}
