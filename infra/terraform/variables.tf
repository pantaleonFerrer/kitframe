variable "hcloud_token" {
  type      = string
  sensitive = true
}

variable "location" {
  type    = string
  default = "nbg1"
  validation {
    condition     = contains(["nbg1", "fsn1"], var.location)
    error_message = "location must be nbg1 or fsn1"
  }
}

variable "environment" {
  type    = string
  default = "production"
}

variable "ssh_public_key" {
  type = string
}

variable "network_zone" {
  type    = string
  default = "eu-central"
}

variable "private_network_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "private_subnet_cidr" {
  type    = string
  default = "10.0.1.0/24"
}

variable "allowed_ssh_cidrs" {
  type    = list(string)
  default = []
}

variable "allowed_http_cidrs" {
  type    = list(string)
  default = ["0.0.0.0/0", "::/0"]
}

variable "server_type_api" {
  type    = string
  default = "cpx21"
}

variable "server_type_ai" {
  type    = string
  default = "cpx21"
}

variable "server_type_worker" {
  type    = string
  default = "cpx21"
}

variable "server_type_web" {
  type    = string
  default = "cpx11"
}

variable "server_type_data" {
  type    = string
  default = "cpx31"
}

variable "server_type_lb" {
  type    = string
  default = "cpx11"
}

variable "server_type_ollama" {
  type    = string
  default = "gex44"
}

variable "enable_ollama_gpu" {
  type    = bool
  default = false
}

variable "image" {
  type    = string
  default = "ubuntu-24.04"
}

variable "data_volume_size" {
  type    = number
  default = 100
}

variable "use_native_load_balancer" {
  type    = bool
  default = true
}
