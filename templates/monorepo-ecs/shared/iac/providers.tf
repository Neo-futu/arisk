provider "aws" {
  region = var.region

  assume_role {
    role_arn     = var.deploy_role_arn
    session_name = "${var.app_name}-shared-${var.env}-tofu"
  }

  default_tags {
    tags = {
      App         = var.app_name
      Component   = "shared"
      Environment = var.env
      managed-by  = "opentofu"
    }
  }
}
