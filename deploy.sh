#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "   Deploying University Management System on AWS Mumbai   "
echo "=========================================================="

# 1. Install prerequisites
echo "[1/6] Updating packages and installing Python & Nginx..."
sudo apt-get update -y
sudo apt-get install -y python3-pip python3-venv git nginx curl

# 2. Setup project directory
echo "[2/6] Setting up project directory..."
sudo mkdir -p /var/www/university
sudo chown -R $USER:$USER /var/www/university

if [ -d "/var/www/university/.git" ]; then
    echo "Updating existing repository..."
    cd /var/www/university && git pull origin main
else
    git clone https://github.com/Haseebalikhan785/Student-Management-System-Python.git /var/www/university
    cd /var/www/university
fi

# 3. Create virtual environment
echo "[3/6] Installing Python dependencies..."
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-web.txt

# 4. Get Aiven Database credentials
echo ""
echo "----------------------------------------------------------"
echo "  Enter your Aiven Database details (press Enter for default):"
echo "----------------------------------------------------------"
read -p "Aiven Host [student-management-db-haseebalikhan785-f02b.g.aivencloud.com]: " DB_HOST
DB_HOST=${DB_HOST:-student-management-db-haseebalikhan785-f02b.g.aivencloud.com}

read -p "Aiven Port [21442]: " DB_PORT
DB_PORT=${DB_PORT:-21442}

read -p "Aiven User [avnadmin]: " DB_USER
DB_USER=${DB_USER:-avnadmin}

read -s -p "Aiven Password: " DB_PASS
echo ""

read -p "Aiven Database [students_db]: " DB_NAME
DB_NAME=${DB_NAME:-students_db}

# 5. Write environment file
echo "[4/6] Configuring service environment..."
sudo tee /etc/university.env > /dev/null <<EOF
SECRET_KEY=university-super-secret-key-mumbai-2026
COOKIE_SECURE=false
MYSQL_HOST=$DB_HOST
MYSQL_PORT=$DB_PORT
MYSQL_USER=$DB_USER
MYSQL_PASSWORD=$DB_PASS
MYSQL_DATABASE=$DB_NAME
PORT=5000
EOF

# 6. Configure systemd service
echo "[5/6] Creating Gunicorn system service..."
sudo tee /etc/systemd/system/university.service > /dev/null <<EOF
[Unit]
Description=University Management System
After=network.target

[Service]
User=$USER
WorkingDirectory=/var/www/university
EnvironmentFile=/etc/university.env
ExecStart=/var/www/university/.venv/bin/gunicorn --workers 3 --threads 2 --bind 127.0.0.1:5000 webapp:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 7. Configure Nginx on Port 80
echo "[6/6] Configuring Nginx web server..."
sudo tee /etc/nginx/sites-available/default > /dev/null <<'EOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    client_max_body_size 16M;

    location /static/ {
        alias /var/www/university/static/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

sudo systemctl daemon-reload
sudo systemctl enable university
sudo systemctl restart university
sudo systemctl restart nginx

PUBLIC_IP=$(curl -s -4 ifconfig.me || curl -s -4 icanhazip.com || echo "your-server-ip")

echo ""
echo "=========================================================="
echo "  🎉 DEPLOYMENT SUCCESSFUL! 🎉"
echo "  Your University Management System is running LIVE at:"
echo "  👉 http://$PUBLIC_IP/"
echo "=========================================================="
