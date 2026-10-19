terraform {
  required_version = ">= 1.9.0, < 2.0.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.10"
    }
  }

  # Remote state is intentionally not configured. See docs/deployment/remote-state.md.
  # Do not apply this environment until the cost estimate has been accepted.
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}
