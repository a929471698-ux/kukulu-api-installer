#!/bin/bash

set -e

echo "📦 正在安装系统依赖..."
apt update && apt install -y unzip python3-pip python3-venv

echo "📁 创建 Python 虚拟环境..."
cd /root
python3 -m venv kukulu_env

echo "✅ 虚拟环境已创建在 /root/kukulu_env"

source /root/kukulu_env/bin/activate

echo "🌐 安装 Python 依赖到虚拟环境..."
pip install flask requests beautifulsoup4

echo "📁 解压部署包到 /root/kukulu_api"
rm -rf /root/kukulu_api
mkdir -p /root/kukulu_api
cd /root/kukulu_api

echo "⬇️ 正在下载最新部署包..."
curl -L -o kukulu_api_v7.zip https://github.com/a929471698-ux/kukulu-api-installer/releases/download/v7.0.0/kukulu_api_v7_clean.zip

echo "📦 解压 ZIP..."
unzip kukulu_api_v7.zip

echo "🚀 启动服务（一次性）"
nohup /root/kukulu_env/bin/python /root/kukulu_api/app.py > /root/kukulu_api/server.log 2>&1 &

echo "🛠️ 写入 systemd 服务（开机自启）"

cat <<EOF > /etc/systemd/system/kukulu_api.service
[Unit]
Description=Kukulu API Service (venv)
After=network.target

[Service]
ExecStart=/root/kukulu_env/bin/python /root/kukulu_api/app.py
WorkingDirectory=/root/kukulu_api
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reexec
systemctl daemon-reload
systemctl enable kukulu_api
systemctl restart kukulu_api

echo "✅ 部署完成！"
echo "🌐 Web UI 访问地址: http://$(hostname -I | awk '{print $1}'):8080/ui"
