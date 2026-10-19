module "platform" {
  source = "../../modules/azure"

  environment                 = "dev"
  location                    = var.location
  enable_monitoring           = var.enable_monitoring
  api_server_authorized_cidrs = var.api_server_authorized_cidrs
  admin_group_object_ids      = var.admin_group_object_ids
}
