module "platform" {
  source = "../../modules/gcp"

  project_id              = var.project_id
  environment             = "dev"
  region                  = var.region
  zone                    = var.zone
  enable_monitoring       = var.enable_monitoring
  master_authorized_cidrs = var.master_authorized_cidrs
  deletion_protection     = false
}
