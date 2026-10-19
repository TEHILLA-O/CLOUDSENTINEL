variable "project" {
  description = "Short project tag used in resource names."
  type        = string
  default     = "cloudsentinel"
}

variable "environment" {
  description = "Environment name, for example dev."
  type        = string
}

variable "location" {
  description = "Azure region. Choose one region; this module does not create a paired region."
  type        = string
  default     = "westeurope"
}

variable "node_count" {
  description = "System node pool size. Keep this at 1 unless you have a reason to pay for more."
  type        = number
  default     = 1
}

variable "vm_size" {
  description = "Node size. Standard_B2s is the cheap default; some subscriptions reject B-series for the AKS system pool, in which case use Standard_D2s_v5."
  type        = string
  default     = "Standard_B2s"
}

variable "kubernetes_version" {
  description = "Optional AKS version. Empty lets Azure pick the current stable version at create time. It will not auto-upgrade."
  type        = string
  default     = null
}

variable "enable_monitoring" {
  description = "Create a Log Analytics workspace and the AKS OMS agent. Leave false unless you accept the ingestion cost."
  type        = bool
  default     = false
}

variable "api_server_authorized_cidrs" {
  description = "CIDRs allowed to reach the Kubernetes API. Empty leaves the API reachable from the internet; set this before a real apply."
  type        = list(string)
  default     = []
}

variable "admin_group_object_ids" {
  description = "Entra ID groups that should be AKS admins. When this is non-empty, local accounts are disabled."
  type        = list(string)
  default     = []
}

variable "namespace" {
  description = "Namespace expected for the analysis workload identity binding."
  type        = string
  default     = "cloudsentinel"
}

variable "service_account_name" {
  description = "Kubernetes service account that may exchange its token for the analysis identity."
  type        = string
  default     = "analysis-api"
}

variable "tags" {
  description = "Extra tags merged onto every taggable resource."
  type        = map(string)
  default     = {}
}
