#!/usr/bin/env bash
# One-time provisioning for a fresh EC2 instance (t3.small).
# Works on Amazon Linux 2023 and Ubuntu.
#
#   curl -fsSL https://raw.githubusercontent.com/MahrukhMuzzamil/TruckDriverLog-Backend/main/scripts/setup-ec2.sh | bash
#
# Installs Docker + compose, clones the two repos side by side, creates .env,
# and starts the stack on port 80.
set -euo pipefail

BACKEND_REPO="https://github.com/MahrukhMuzzamil/TruckDriverLog-Backend.git"
FRONTEND_REPO="https://github.com/MahrukhMuzzamil/TruckDriverLog-Frontend.git"
ROOT_DIR="$HOME/TruckDriverLog"

echo "==> Installing Docker + git"
if ! command -v docker >/dev/null 2>&1; then
  if command -v dnf >/dev/null 2>&1; then
    # Amazon Linux 2023 / RHEL family
    sudo dnf install -y docker git
    sudo systemctl enable --now docker
    # docker compose v2 plugin (not packaged on AL2023)
    sudo mkdir -p /usr/local/lib/docker/cli-plugins
    sudo curl -fsSL \
      "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
      -o /usr/local/lib/docker/cli-plugins/docker-compose
    sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
  else
    # Ubuntu / Debian
    curl -fsSL https://get.docker.com | sudo sh
  fi
  sudo usermod -aG docker "$USER"
fi
command -v git >/dev/null 2>&1 || sudo dnf install -y git 2>/dev/null || sudo apt-get install -y git

echo "==> Adding 2G swap (safety margin for image builds)"
if ! swapon --show | grep -q swap; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "==> Cloning repositories"
mkdir -p "$ROOT_DIR"
[ -d "$ROOT_DIR/backend" ] || git clone "$BACKEND_REPO" "$ROOT_DIR/backend"
[ -d "$ROOT_DIR/frontend" ] || git clone "$FRONTEND_REPO" "$ROOT_DIR/frontend"

cd "$ROOT_DIR/backend"

echo "==> Creating .env"
if [ ! -f .env ]; then
  cp .env.example .env
  SECRET=$(head -c 48 /dev/urandom | base64 | tr -d '=+/')
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET|" .env
  echo "Generated SECRET_KEY. Review ALLOWED_HOSTS/CORS in .env if using a domain."
fi

echo "==> Building and starting the stack (this can take a few minutes)"
sudo docker compose build backend
sudo docker compose build frontend
sudo docker compose up -d

echo
echo "Done. App: http://$(curl -fsS http://checkip.amazonaws.com || echo '<instance-ip>')/"
echo "NOTE: log out and back in so 'docker' works without sudo (group change)."
