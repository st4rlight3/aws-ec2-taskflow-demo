#!/usr/bin/env bash
# Run on Ubuntu Server 24.04 LTS: sudo bash deploy/setup_ec2.sh
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then echo 'Run with sudo.' >&2; exit 1; fi
source /etc/os-release
if [[ ${ID} != ubuntu || ${VERSION_ID} != 24.04 ]]; then echo 'This installer targets Ubuntu Server 24.04 LTS.' >&2; exit 1; fi
source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -f "$source_root/app.py" || ! -f "$source_root/web/index.html" ]]; then echo 'Extract the complete source package first.' >&2; exit 1; fi
if [[ -e /etc/taskflow.env || -e /opt/taskflow/app.py ]]; then echo 'TaskFlow already exists. Installer stops to preserve current configuration and data.' >&2; exit 1; fi
read -r -s -p 'Set demo access code (12+ ASCII letters/numbers or ._@#%+=:-): ' taskflow_password </dev/tty
echo
if [[ ! "$taskflow_password" =~ ^[A-Za-z0-9._@#%+=:-]{12,128}$ ]]; then echo 'Invalid access code.' >&2; exit 1; fi
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 nginx
id taskflow &>/dev/null || useradd --system --home /var/lib/taskflow --shell /usr/sbin/nologin taskflow
install -d -m 755 /opt/taskflow/web
install -d -o taskflow -g taskflow -m 750 /var/lib/taskflow
install -m 644 "$source_root/app.py" /opt/taskflow/app.py
install -m 644 "$source_root/web/"* /opt/taskflow/web/
umask 077
printf 'APP_ENV=ec2\nDATABASE_PATH=/var/lib/taskflow/tasks.db\nDEMO_PASSWORD=%s\n' "$taskflow_password" > /etc/taskflow.env
unset taskflow_password
cat > /etc/systemd/system/taskflow.service <<'SERVICE'
[Unit]
Description=TaskFlow EC2 classroom demo
After=network.target

[Service]
User=taskflow
Group=taskflow
WorkingDirectory=/opt/taskflow
EnvironmentFile=/etc/taskflow.env
ExecStart=/usr/bin/python3 /opt/taskflow/app.py --host 127.0.0.1 --port 8080
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/taskflow

[Install]
WantedBy=multi-user.target
SERVICE
cat > /etc/nginx/sites-available/taskflow <<'NGINX'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    client_max_body_size 16k;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }
}
NGINX
rm -f /etc/nginx/sites-enabled/default
ln -sfn /etc/nginx/sites-available/taskflow /etc/nginx/sites-enabled/taskflow
nginx -t
systemctl daemon-reload
systemctl enable --now taskflow
systemctl enable nginx
systemctl restart nginx
python3 - <<'PY'
import time, urllib.request
for attempt in range(10):
    try:
        print(urllib.request.urlopen('http://127.0.0.1/health',timeout=3).read().decode())
        break
    except Exception:
        if attempt==9: raise
        time.sleep(1)
PY
echo 'Installed. Visit http://YOUR_PUBLIC_IPV4 after configuring Security Group.'
echo 'Classroom HTTP demo: restrict port 80 to your public IP. Add HTTPS before wider use.'
