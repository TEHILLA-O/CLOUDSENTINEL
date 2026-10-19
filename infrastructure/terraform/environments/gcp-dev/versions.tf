terraform {
  required_version = ">= 1.9.0, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.7"
    }
  }

  # Remote state is intentionally not configured. See docs/deployment/remote-state.md.
}

provider "google" {
  project = var.project_id
  region  = var.region
}
