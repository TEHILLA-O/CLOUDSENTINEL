variable "subscription_id" {
  description = "Azure subscription that will be billed. There is no default, so a plan cannot silently target the wrong subscription."
  type        = string
}

variable "location" {
  type    = string
  default = "westeurope"
}

variable "api_server_authorized_cidrs" {
  type    = list(string)
  default = []
}

variable "admin_group_object_ids" {
  type    = list(string)
  default = []
}

variable "enable_monitoring" {
  type    = bool
  default = false
}
