output "location" {
  value = var.location
}

output "network_id" {
  value = hcloud_network.main.id
}

output "api_private_ips" {
  value = [for s in hcloud_server.api : one(s.network[*].ip)]
}

output "api_public_ipv4" {
  value = [for s in hcloud_server.api : s.ipv4_address]
}

output "ai_private_ips" {
  value = [for s in hcloud_server.ai : one(s.network[*].ip)]
}

output "worker_private_ip" {
  value = one(hcloud_server.worker.network[*].ip)
}

output "web_private_ip" {
  value = one(hcloud_server.web.network[*].ip)
}

output "data_private_ip" {
  value = one(hcloud_server.data.network[*].ip)
}

output "data_volume_id" {
  value = hcloud_volume.data.id
}

output "ollama_private_ip" {
  value = var.enable_ollama_gpu ? one(hcloud_server.ollama[0].network[*].ip) : null
}

output "load_balancer_ipv4" {
  value = var.use_native_load_balancer ? hcloud_load_balancer.edge[0].ipv4 : hcloud_server.lb_nginx[0].ipv4_address
}

output "lb_mode" {
  value = var.use_native_load_balancer ? "hcloud_native" : "nginx_node"
}

output "ssh_key_id" {
  value = hcloud_ssh_key.deploy.id
}
