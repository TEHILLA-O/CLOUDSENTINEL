variable "project_id" {
  description = "GCP project that will be billed. There is no default."
  type        = string
}

variable "region" {
  type    = string
  default = "europe-west2"
}

variable "zone" {
  type    = string
  default = "europe-west2-a"
}

variable "master_authorized_cidrs" {
  type    = list(string)
  default = []
}

variable "enable_monitoring" {
  type    = bool
  default = false
}
