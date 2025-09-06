#!/bin/bash
set -e

echo "📦 正在安装系统依赖..."
apt update && apt install -y unzip python3-pip python3-venv curl

echo "📁 创建 Python 虚拟环境..."
cd /root
python3 -m venv /root/kukulu_env
source /root/kukulu_env/bin/activate

echo "🌐 升级 pip..."
pip install --upgrade pip

echo "📁 下载并解压 Release 包到 /root/kukulu_api"
rm -rf /root/kukulu_api
mkdir -p /root/kukulu_api
cd /root/kukulu_api
curl -L -o kukulu_api_v8.1.zip https://github.com/a929471698-ux/kukulu-api-installer/releases/download/v8.1.0/kukulu_api_v8.1.zip
unzip -o kukulu_api_v8.1.zip

echo "📦 安装 Python 依赖..."
pip install -r requirements.txt

echo "🚀 启动服务（一次性测试运行）"
nohup /root/kukulu_env/bin/python /root/kukulu_api/app.py > /root/kukulu_api/server.log 2>&1 &

echo "🛠️ 写入 systemd 服务（开机自启）"
cat <<EOF > /etc/systemd/system/kukulu_api.service
[Unit]
Description=Kukulu API Service (v8.1)
After=network.target

[Service]
ExecStart=/root/kukulu_env/bin/python /root/kukulu_api/app.py
WorkingDirectory=/root/kukulu_api
Restart=always
User=root
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable kukulu_api
systemctl restart kukulu_api

echo "✅ 部署完成！"
echo "🌐 Web UI 访问地址: http://$(hostname -I | awk '{print $1}'):8080/ui"
