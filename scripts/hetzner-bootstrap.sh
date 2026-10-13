#!/usr/bin/env bash
# Bootstrap Kitframe on a Hetzner VPS that may already run gathered-brain.
# Does not install/replace Nginx or bind :80/:443 (host Nginx stays in charge).
# Usage: ./scripts/hetzner-bootstrap.sh
set -euo pipefail

KITFRAME_HOME="${KITFRAME_HOME:-/opt/kitframe}"
DEPLOY_REPO="${DEPLOY_REPO:-}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
DOMAIN="${DOMAIN:-}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl git jq

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
else
  echo "Docker already present — leaving as-is (shared with gathered-brain)."
fi

# Prefer deploying as an existing sudo user; fall back to kitframe.
DEPLOY_USER="${SUDO_USER:-kitframe}"
if [[ "$DEPLOY_USER" == "root" || -z "$DEPLOY_USER" ]]; then
  DEPLOY_USER=kitframe
fi

if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  useradd -m -s /bin/bash -G sudo,docker kitframe
  DEPLOY_USER=kitframe
  mkdir -p /home/kitframe/.ssh
  if [[ -f /root/.ssh/authorized_keys ]]; then
    cp /root/.ssh/authorized_keys /home/kitframe/.ssh/authorized_keys
    chown -R kitframe:kitframe /home/kitframe/.ssh
    chmod 700 /home/kitframe/.ssh
    chmod 600 /home/kitframe/.ssh/authorized_keys
  fi
fi

usermod -aG docker "$DEPLOY_USER" || true

mkdir -p "$KITFRAME_HOME"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$KITFRAME_HOME"

if [[ -n "$DEPLOY_REPO" && ! -d "$KITFRAME_HOME/.git" ]]; then
  sudo -u "$DEPLOY_USER" git clone --branch "$DEPLOY_BRANCH" "$DEPLOY_REPO" "$KITFRAME_HOME"
fi

if [[ -d "$KITFRAME_HOME/infra/env" && ! -f "$KITFRAME_HOME/.env" ]]; then
  sudo -u "$DEPLOY_USER" cp "$KITFRAME_HOME/infra/env/production.example" "$KITFRAME_HOME/.env"
  if [[ -n "$DOMAIN" ]]; then
    sed -i "s|^DOMAIN=.*|DOMAIN=$DOMAIN|" "$KITFRAME_HOME/.env"
    sed -i "s|kitframe.example.com|$DOMAIN|g" "$KITFRAME_HOME/.env"
  fi
fi

echo "Bootstrap done."
echo "  App dir:  $KITFRAME_HOME"
echo "  Next:     edit .env, enable infra/nginx/kitframe.conf, then IMAGE_TAG=<sha> ./scripts/deploy.sh"
echo "  Note:     gathered-brain stays on /opt/gathered-brain and 127.0.0.1:8080"
