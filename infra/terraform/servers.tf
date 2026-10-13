resource "hcloud_server" "api" {
  count              = 2
  name               = "${local.name_prefix}-api-${count.index + 1}"
  server_type        = var.server_type_api
  image              = var.image
  location           = var.location
  ssh_keys           = [hcloud_ssh_key.deploy.id]
  firewall_ids       = [hcloud_firewall.internal.id]
  placement_group_id = hcloud_placement_group.app.id
  labels             = merge(local.labels, { role = "api" })

  network {
    network_id = hcloud_network.main.id
    ip         = cidrhost(var.private_subnet_cidr, 10 + count.index)
  }

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  depends_on = [hcloud_network_subnet.app]
}

resource "hcloud_server" "ai" {
  count              = 2
  name               = "${local.name_prefix}-ai-${count.index + 1}"
  server_type        = var.server_type_ai
  image              = var.image
  location           = var.location
  ssh_keys           = [hcloud_ssh_key.deploy.id]
  firewall_ids       = [hcloud_firewall.internal.id]
  placement_group_id = hcloud_placement_group.app.id
  labels             = merge(local.labels, { role = "ai" })

  network {
    network_id = hcloud_network.main.id
    ip         = cidrhost(var.private_subnet_cidr, 20 + count.index)
  }

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  depends_on = [hcloud_network_subnet.app]
}

resource "hcloud_server" "worker" {
  name         = "${local.name_prefix}-worker-1"
  server_type  = var.server_type_worker
  image        = var.image
  location     = var.location
  ssh_keys     = [hcloud_ssh_key.deploy.id]
  firewall_ids = [hcloud_firewall.internal.id]
  labels       = merge(local.labels, { role = "worker" })

  network {
    network_id = hcloud_network.main.id
    ip         = cidrhost(var.private_subnet_cidr, 30)
  }

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  depends_on = [hcloud_network_subnet.app]
}

resource "hcloud_server" "web" {
  name         = "${local.name_prefix}-web-1"
  server_type  = var.server_type_web
  image        = var.image
  location     = var.location
  ssh_keys     = [hcloud_ssh_key.deploy.id]
  firewall_ids = [hcloud_firewall.internal.id]
  labels       = merge(local.labels, { role = "web" })

  network {
    network_id = hcloud_network.main.id
    ip         = cidrhost(var.private_subnet_cidr, 40)
  }

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  depends_on = [hcloud_network_subnet.app]
}

resource "hcloud_server" "data" {
  name         = "${local.name_prefix}-data-1"
  server_type  = var.server_type_data
  image        = var.image
  location     = var.location
  ssh_keys     = [hcloud_ssh_key.deploy.id]
  firewall_ids = [hcloud_firewall.data.id]
  labels       = merge(local.labels, { role = "data" })

  network {
    network_id = hcloud_network.main.id
    ip         = cidrhost(var.private_subnet_cidr, 50)
  }

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  depends_on = [hcloud_network_subnet.app]
}

resource "hcloud_volume" "data" {
  name     = "${local.name_prefix}-data-vol"
  size     = var.data_volume_size
  location = var.location
  format   = "ext4"
  labels   = merge(local.labels, { role = "data" })
}

resource "hcloud_volume_attachment" "data" {
  volume_id = hcloud_volume.data.id
  server_id = hcloud_server.data.id
  automount = true
}

resource "hcloud_server" "ollama" {
  count        = var.enable_ollama_gpu ? 1 : 0
  name         = "${local.name_prefix}-ollama-1"
  server_type  = var.server_type_ollama
  image        = var.image
  location     = var.location
  ssh_keys     = [hcloud_ssh_key.deploy.id]
  firewall_ids = [hcloud_firewall.internal.id]
  labels       = merge(local.labels, { role = "ollama" })

  network {
    network_id = hcloud_network.main.id
    ip         = cidrhost(var.private_subnet_cidr, 60)
  }

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  depends_on = [hcloud_network_subnet.app]
}

resource "hcloud_server" "lb_nginx" {
  count        = var.use_native_load_balancer ? 0 : 1
  name         = "${local.name_prefix}-lb-1"
  server_type  = var.server_type_lb
  image        = var.image
  location     = var.location
  ssh_keys     = [hcloud_ssh_key.deploy.id]
  firewall_ids = [hcloud_firewall.edge.id, hcloud_firewall.internal.id]
  labels       = merge(local.labels, { role = "lb" })

  network {
    network_id = hcloud_network.main.id
    ip         = cidrhost(var.private_subnet_cidr, 5)
  }

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  depends_on = [hcloud_network_subnet.app]
}

resource "hcloud_load_balancer" "edge" {
  count              = var.use_native_load_balancer ? 1 : 0
  name               = "${local.name_prefix}-lb"
  load_balancer_type = "lb11"
  location           = var.location
  labels             = local.labels
}

resource "hcloud_load_balancer_network" "edge" {
  count            = var.use_native_load_balancer ? 1 : 0
  load_balancer_id = hcloud_load_balancer.edge[0].id
  network_id       = hcloud_network.main.id
  ip               = cidrhost(var.private_subnet_cidr, 5)
  depends_on       = [hcloud_network_subnet.app]
}

resource "hcloud_load_balancer_target" "api" {
  count            = var.use_native_load_balancer ? 2 : 0
  type             = "server"
  load_balancer_id = hcloud_load_balancer.edge[0].id
  server_id        = hcloud_server.api[count.index].id
  use_private_ip   = true
  depends_on       = [hcloud_load_balancer_network.edge]
}

resource "hcloud_load_balancer_service" "http" {
  count            = var.use_native_load_balancer ? 1 : 0
  load_balancer_id = hcloud_load_balancer.edge[0].id
  protocol         = "http"
  listen_port      = 80
  destination_port = 8080

  health_check {
    protocol = "http"
    port     = 8080
    interval = 15
    timeout  = 5
    retries  = 3
    http {
      path         = "/healthz"
      status_codes = ["2??", "3??"]
    }
  }
}

resource "hcloud_load_balancer_service" "https_web" {
  count            = var.use_native_load_balancer ? 1 : 0
  load_balancer_id = hcloud_load_balancer.edge[0].id
  protocol         = "http"
  listen_port      = 8080
  destination_port = 3000
}
