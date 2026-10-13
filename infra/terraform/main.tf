locals {
  labels = {
    project     = "kitframe"
    environment = var.environment
  }

  name_prefix = "kitframe-${var.environment}"
}

resource "hcloud_ssh_key" "deploy" {
  name       = "${local.name_prefix}-deploy"
  public_key = var.ssh_public_key
  labels     = local.labels
}

resource "hcloud_placement_group" "app" {
  name   = "${local.name_prefix}-app"
  type   = "spread"
  labels = local.labels
}
