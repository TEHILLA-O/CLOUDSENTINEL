# Cost and cleanup

No cloud resources have been created by this project. Terraform has been validated locally. It has not been applied.

Do not run `terraform apply` until you accept the charges below and you have set an API allow-list to your own IP.

## What would cost money

Prices move. These are order-of-magnitude estimates for a few hours of lab use in West Europe / europe-west2, one node, monitoring left off. Check the current calculators before applying.

| Resource | Why it bills | Rough lab cost |
| --- | --- | --- |
| AKS Free tier control plane | No SLA charge | $0 |
| One Standard_B2s node | Compute and OS disk | about $0.05/hour, often $1–2 for an afternoon. Some subscriptions reject B-series for the system pool; Standard_D2s_v5 is several times that |
| AKS load balancer and public IP | Default outbound | about $0.03/hour plus a small data charge |
| ACR Basic | Registry | about $0.167/day |
| Log Analytics, if enabled | Ingestion | leave `enable_monitoring = false` |
| GKE zonal control plane | One free zonal cluster per billing account is typical; confirm the current free tier | $0 if the free cluster is unused, otherwise about $0.10/hour |
| One e2-medium node, 30 GB standard disk | Compute and disk | about $0.04–0.06/hour |
| Artifact Registry | Storage | cents unless images are large |
| Cloud Logging, if enabled | Ingestion | leave `enable_monitoring = false` |

A careful afternoon with both clouds, monitoring off, and destroy at the end is likely a few US dollars, not nothing. A forgotten cluster is a monthly bill. Regional GKE would multiply the control-plane cost; the module uses a zonal cluster for that reason, and it is less available because of it.

## Billing alerts

Create a budget in Azure Cost Management and in GCP Billing before the first apply. This repository cannot create those budgets without applying against your billing account.

## Apply, one environment at a time

```powershell
cd infrastructure/terraform/environments/azure-dev
copy terraform.tfvars.example terraform.tfvars
# Edit subscription_id and set api_server_authorized_cidrs to your IP.
terraform init
terraform plan
# Apply only after you have read the plan and accepted the cost.
terraform apply
```

GCP is the same under `environments/gcp-dev`, with `project_id` and `master_authorized_cidrs`.

## Destroy

From the same directory, and only if the state file is the one this apply created:

```powershell
terraform destroy
```

`deletion_protection` on the dev GKE cluster defaults to false so this destroy can succeed. Do not point the state at a cluster you did not create here.

Destroy does not delete the GCP APIs (`disable_on_destroy = false`), because those APIs may be used by the rest of the project.

## Rollback of the application

Images are tagged by git SHA in CI. A rollback is `kubectl set image` or a Kustomize image tag change back to the previous SHA, then `kubectl rollout undo deployment/analysis-api -n cloudsentinel` if the new pods fail their readiness probe. There is no automated cloud deploy in GitHub Actions.
