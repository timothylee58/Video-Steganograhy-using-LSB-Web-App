#!/bin/bash
# =============================================================
# VidStega - Oracle Cloud Always Free Deployment Script
# Run once on a fresh Ubuntu 22.04 ARM instance
# Usage: bash deploy.sh
# =============================================================

set -e

REPO_URL="https://github.com/timothylee58/Video-Steganograhy-using-LSB-Web-App.git"
APP_DIR="/opt/vidstega"

echo "==> [1/6] Updating system packages..."
sudo apt-get update -y && sudo apt-get upgrade -y

echo "==> [2/6] Installing Docker..."
sudo apt-get install -y ca-certificates curl gnupg lsb-release
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER

echo "==> [3/6] Opening firewall port 80..."
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || true
# Oracle Cloud also requires opening port 80 in the VCN Security List (do this in OCI console)

echo "==> [4/6] Cloning repository..."
sudo mkdir -p $APP_DIR
sudo chown $USER:$USER $APP_DIR
git clone $REPO_URL $APP_DIR
cd $APP_DIR

echo "==> [5/6] Creating .env file..."
if [ ! -f .env ]; then
  SECRET=$(openssl rand -hex 32)
  cat > .env <<EOF
FLASK_ENV=production
SECRET_KEY=$SECRET
EOF
  echo "    .env created with a random SECRET_KEY"
else
  echo "    .env already exists, skipping"
fi

echo "==> [6/6] Building and starting services..."
docker compose up -d --build

echo ""
echo "============================================================"
echo " VidStega is running!"
echo " Access it at: http://$(curl -s ifconfig.me)"
echo "============================================================"
echo ""
echo "Useful commands:"
echo "  docker compose logs -f          # tail all logs"
echo "  docker compose logs -f web      # Flask app logs"
echo "  docker compose logs -f worker   # Celery worker logs"
echo "  docker compose restart          # restart all services"
echo "  docker compose down             # stop all services"
