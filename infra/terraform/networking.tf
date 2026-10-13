resource "hcloud_network" "main" {
  name     = "${local.name_prefix}-net"
  ip_range = var.private_network_cidr
  labels   = local.labels
}

resource "hcloud_network_subnet" "app" {
  network_id   = hcloud_network.main.id
  type         = "cloud"
  network_zone = var.network_zone
  ip_range     = var.private_subnet_cidr
}

resource "hcloud_firewall" "edge" {
  name   = "${local.name_prefix}-edge"
  labels = local.labels

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = length(var.allowed_ssh_cidrs) > 0 ? var.allowed_ssh_cidrs : ["127.0.0.1/32"]
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "80"
    source_ips = var.allowed_http_cidrs
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "443"
    source_ips = var.allowed_http_cidrs
  }

  rule {
    direction  = "in"
    protocol   = "icmp"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
}

resource "hcloud_firewall" "internal" {
  name   = "${local.name_prefix}-internal"
  labels = local.labels

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "1-65535"
    source_ips = [var.private_network_cidr]
  }

  rule {
    direction  = "in"
    protocol   = "udp"
    port       = "1-65535"
    source_ips = [var.private_network_cidr]
  }

  rule {
    direction  = "in"
    protocol   = "icmp"
    source_ips = [var.private_network_cidr]
  }
}

resource "hcloud_firewall" "data" {
  name   = "${local.name_prefix}-data"
  labels = local.labels

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "5432"
    source_ips = [var.private_network_cidr]
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "9000"
    source_ips = [var.private_network_cidr]
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "9001"
    source_ips = [var.private_network_cidr]
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = length(var.allowed_ssh_cidrs) > 0 ? var.allowed_ssh_cidrs : ["127.0.0.1/32"]
  }
}
