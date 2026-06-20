# 办公效率工具集 — 部署文档

> 项目地址：`/home/mokch/projects/office-tools`
> 线上地址：https://tools.292029.xyz

---

## 架构概览

```
用户 → Nginx (HTTPS 443) → Gunicorn (WSGI, 127.0.0.1:8200, 1 worker + gthread 4) → Flask App
                                                                ├── XLS → XLSX (LibreOffice)
                                                                ├── PDF → DOCX (pdf2docx)
                                                                └── PDF扫描件 → DOCX (RapidOCR ONNX)
```

| 组件 | 技术 | 说明 |
|------|------|------|
| Web 服务器 | Nginx | HTTPS 终止、反向代理、静态文件服务 |
| 应用服务器 | Gunicorn | WSGI 接口，1 worker + 4 线程（gthread）|
| 进程管理 | Supervisor | 守护进程，自动重启 |
| SSL | Let's Encrypt (certbot) | 自动续期 |
| 转换引擎 | LibreOffice (calc + writer) | XLS → XLSX |
| 转换引擎 | pdf2docx (PyMuPDF) | PDF → DOCX（电子 PDF）|
| 转换引擎 | RapidOCR (ONNX Runtime) | PDF扫描件 → DOCX |
| PDF 工具 | pypdf | PDF 合并 / 拆分 |
| PDF 工具 | pikepdf | PDF 压缩（图像降采样 + 流压缩）|

---

## 首次部署

### 1. 服务器环境

```bash
# 安装系统依赖
ssh root@rn.292029.xyz
apt-get update
apt-get install -y python3-pip python3-venv nginx supervisor certbot python3-certbot-nginx
apt-get install -y libreoffice-writer-nogui libreoffice-calc-nogui
apt-get install -y poppler-utils  # pdf2image 依赖（OCR 需要）
```

### 2. 上传项目文件

```bash
cd /home/mokch/projects/office-tools

rsync -avz --delete \
  --exclude='venv' \
  --exclude='uploads' \
  --exclude='output' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  ./ root@rn.292029.xyz:/opt/office-tools/
```

### 3. 服务器端安装 Python 依赖

```bash
ssh root@rn.292029.xyz
mkdir -p /opt/office-tools/uploads /opt/office-tools/output
chmod 755 /opt/office-tools/uploads /opt/office-tools/output

cd /opt/office-tools
python3 -m venv venv
venv/bin/pip install gunicorn pdf2docx flask \
                   rapidocr_onnxruntime onnxruntime pdf2image python-docx Pillow \
                   pypdf pikepdf qrcode
```

### 4. 配置 Supervisor

```bash
cat > /etc/supervisor/conf.d/office-tools.conf << 'EOF'
[program:office-tools]
command=/opt/office-tools/venv/bin/gunicorn --worker-class=gthread --workers=1 --threads=4 -b 127.0.0.1:8200 --timeout 1200 app:app
directory=/opt/office-tools
user=root
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stdout_logfile=/var/log/office-tools.log
stderr_logfile=/var/log/office-tools.err.log
environment=HOME="/root"
EOF

> **架构说明：** 由于 OCR 任务需要跨请求共享内存中的任务状态（task_id → progress/status），
> 必须使用 **1 worker + 多线程（gthread）** 模式，不能用默认的多 worker 模式。
> 1 worker 同时处理 OCR + PDF→Word，请求会按线程分配。

supervisorctl reread
supervisorctl update
supervisorctl start office-tools
supervisorctl status      # 确认 RUNNING
```

### 5. 配置 Nginx + SSL

```bash
cat > /etc/nginx/sites-available/tools.292029.xyz << 'NGINX'
server {
    listen 80;
    listen [::]:80;
    server_name tools.292029.xyz;

    client_max_body_size 500M;
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;

    location / {
        proxy_pass http://127.0.0.1:8200;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/tools.292029.xyz /etc/nginx/sites-enabled/
nginx -t && nginx -s reload
```

**SSL（仅首次）：**

```bash
certbot --nginx -d tools.292029.xyz --non-interactive --agree-tos --email admin@292029.xyz
```

SSL 证书自动续期（certbot 已配置 systemd timer，无需手动操作）。

---

## 更新部署

```bash
cd /home/mokch/projects/office-tools

# 1. 上传文件
rsync -avz --delete \
  --exclude='venv' \
  --exclude='uploads' \
  --exclude='output' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  ./ root@rn.292029.xyz:/opt/office-tools/

# 2. 重启服务
ssh root@rn.292029.xyz "supervisorctl restart office-tools"
```

---

## 运维命令

| 操作 | 命令 |
|------|------|
| 查看状态 | `supervisorctl status` |
| 重启服务 | `supervisorctl restart office-tools` |
| 查看日志 | `tail -f /var/log/office-tools.log` |
| 查看错误 | `tail -f /var/log/office-tools.err.log` |
| 重载 Nginx | `nginx -s reload` |
| SSL 续期测试 | `certbot renew --dry-run` |

---

## 扩展新工具

本地开发完成后，只需：

1. 新增模板文件 `templates/xxx.html`
2. 在 `app.py` 中添加转换函数 + 路由
3. 更新 `templates/index.html` 添加入口卡片
4. 执行「更新部署」流程

---

## 回滚

```bash
# 恢复上一版本的备份（如有）
rsync -avz --delete /path/to/backup/ root@rn.292029.xyz:/opt/office-tools/

# 或者 git revert + 重新部署
```
