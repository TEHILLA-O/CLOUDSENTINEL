variable "project_id" {
  description = "Existing GCP project. This module does not create a project or a billing account."
  type        = string
}

variable "environment" {
  description = "Environment name, for example dev."
  type        = string
}

variable "region" {
  description = "Region for the subnet, Artifact Registry, and the zonal cluster's region."
  type        = string
  default     = "europe-west2"
}

variable "zone" {
  description = "Zonal cluster location. A zonal cluster has one control plane and avoids the regional replica charge. It is not a multi-zone control plane."
  type        = string
  default     = "europe-west2-a"
}

variable "node_count" {
  type    = number
  default = 1
}

variable "machine_type" {
  description = "e2-medium is the smallest size that usually has room for GKE system pods."
  type        = string
  default     = "e2-medium"
}

variable "enable_monitoring" {
  description = "Turn on Cloud Logging and Cloud Monitoring for the cluster. Both can incur charges."
  type        = bool
  default     = false
}

variable "master_authorized_cidrs" {
  description = "CIDRs allowed to reach the Kubernetes API. Empty leaves the public endpoint open; set this before a real apply."
  type        = list(string)
  default     = []
}

variable "deletion_protection" {
  description = "When true, terraform destroy cannot delete the cluster. Dev defaults to false so the cleanup procedure works."
  type        = bool
  default     = false
}

variable "namespace" {
  type    = string
  default = "cloudsentinel"
}

variable "service_account_name" {
  type    = string
  default = "analysis-api"
}

variable "labels" {
  type    = map(string)
  default = {}
}
