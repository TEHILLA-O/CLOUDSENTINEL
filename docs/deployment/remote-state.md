# Terraform remote state

The environment directories use the local backend. No state storage account or bucket is created, because that would be a cloud resource and a billing decision.

State for a real apply will contain cluster endpoints and, for AKS, the kubeconfig material that the `azurerm_kubernetes_cluster` resource stores. Treat the state file as a secret. Do not commit `*.tfstate`.

## Azure, when you choose to use a remote backend

Create a storage account and container that belong to this project, then add a backend block to `infrastructure/terraform/environments/azure-dev`:

```hcl
terraform {
  backend "azurerm" {
    resource_group_name  = "cloudsentinel-tfstate-rg"
    storage_account_name = "cloudsentineltfstate"
    container_name       = "tfstate"
    key                  = "azure-dev.tfstate"
  }
}
```

Use a separate resource group from the cluster so `terraform destroy` in the cluster environment cannot delete the state.

## GCP

```hcl
terraform {
  backend "gcs" {
    bucket = "cloudsentinel-tfstate"
    prefix = "gcp-dev"
  }
}
```

Enable versioning and restrict the bucket to the people who apply this environment. Do not grant the analysis workload access to the state bucket.

## What not to do

Do not point this configuration at an existing state backend that holds unrelated infrastructure. `terraform destroy` must only target the CloudSentinel dev environment you created.
