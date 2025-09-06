#!/bin/bash

set -e

echo "📦 正在安装依赖环境..."
apt update && apt install -y unzip python3-pip

echo "🌐 正在安装 Python 依赖..."
pip3 install flask requests beautifulsoup4

echo "📁 创建工作目录 /root/kukulu_api ..."
cd /root
rm -rf kukulu_api
mkdir -p kukulu_api
cd kukulu_api

echo "⬇️ 下载程序文件..."
curl -L -o kukulu_api_v5.zip https://raw.githubusercontent.com/example/kukulu-autoinstall/main/kukulu_api_v5.zip

echo "📦 解压程序包..."
unzip kukulu_api_v5.zip

echo "🚀 启动服务..."
nohup python3 app.py > /root/kukulu_api/server.log 2>&1 &

echo "🛠️ 设置 systemd 自启服务..."

cat <<EOF > /etc/systemd/system/kukulu_api.service
[Unit]
Description=Kukulu API Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 /root/kukulu_api/app.py
WorkingDirectory=/root/kukulu_api
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reexec
systemctl daemon-reload
systemctl enable kukulu_api
systemctl start kukulu_api

echo "✅ 安装完成！服务已启动在端口 8080"
echo "👉 接口地址: http://$(hostname -I | awk '{print $1}'):8080/api/create_mailaddress"