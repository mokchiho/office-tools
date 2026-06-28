# 办公效率工具集 — 部署文档

> 项目地址：`/home/mokch/projects/office-tools`
> 线上地址：https://tools.292029.xyz

---

## 架构概览

```
用户 → Nginx (HTTPS 443) → Gunicorn (WSGI, 127.0.0.1:8200, 1 worker + gthread 4) → Flask App
                                                                ├── config.py (配置中心)
                                                                ├── utils/ (工具模块)
                                                                │   ├── logging_config.py  日志系统
                                                                │   ├── cleanup.py          文件清理
                                                                │   ├── download.py         下载响应
                                                                │   └── rate_limit.py       限流
                                                                ├── services/ (业务服务)
                                                                │   └── ocr_service.py      OCR 异步识别
                                                                ├── XLS → XLSX (LibreOffice)
                                                                ├── PDF → DOCX (pdf2docx)
                                                                └── PDF扫描件 → DOCX (RapidOCR ONNX)
```

## 前置检查

部署前确保以下文件已就绪：

```
.env       # SECRET_KEY 等环境配置（从 .env.example 复制修改）
```

检查 `.env` 中的 `SECRET_KEY` 已设置（生产环境必须）：

```bash
grep SECRET_KEY .env
# 如果不是随机字符串，请生成:
openssl rand -hex 32
```

---

## 存档部署

### 1. 上传项目文件

```bash
cd /home/mokch/projects/office-tools

rsync -avz --delete \
  --exclude='venv' \
  --exclude='uploads' \
  --exclude='output' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='logs' \
  --exclude='.env' \
  ./ root@rn.292029.xyz:/opt/office-tools/
```

### 2. 服务器端安装依赖

```bash
ssh root@rn.292029.xyz
mkdir -p /opt/office-tools/uploads /opt/office-tools/output
chmod 755 /opt/office-tools/uploads /opt/office-tools/output

cd /opt/office-tools
python3 -m venv venv
venv/bin/pip install -r requirements.txt -q

# 设置环境变量
cp .env.example .env
# 编辑 .env 设置 SECRET_KEY
```

### 3. 配置 Supervisor

```bash
cat > /etc/supervisor/conf.d/office-tools.conf << 'EOF'
[program:office-tools]
command=/opt/office-tools/venv/bin/gunicorn --worker-class=gthread --workers=1 --threads=4 -b 127.0.0.1:8200 --timeout 1200 --access-logfile /var/log/office-tools-access.log app:app
directory=/opt/office-tools
user=root
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stdout_logfile=/var/log/office-tools.log
stderr_logfile=/var/log/office-tools.err.log
environment=HOME="/root",SECRET_KEY="your-production-secret"
EOF

> **架构说明：** 由于 OCR 任务需要跨请求共享内存中的任务状态（task_id → progress/status），
> 必须使用 **1 worker + 多线程（gthread）** 模式，不能用默认的多 worker 模式。
> 1 worker 同时处理 OCR + PDF→Word，请求会按线程分配。

supervisorctl reread
supervisorctl update
supervisorctl start office-tools
supervisorctl status      # 确认 RUNNING
```

### 4. 配置 Nginx + SSL（同上）

---

## Docker 部署（推荐）

```bash
# 1. 构建镜像
docker build -t office-tools .

# 2. 创建 .env 文件
cp .env.example .env
# 编辑 .env 设置 SECRET_KEY

# 3. 启动
docker compose up -d

# 4. 检查
docker compose logs -f
```

---

## 更新部署

```bash
cd /home/mokch/projects/office-tools

# 1. 上传文件（排除运行时数据）
rsync -avz --delete \
  --exclude='venv' \
  --exclude='uploads' \
  --exclude='output' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='logs' \
  --exclude='.env' \
  ./ root@rn.292029.xyz:/opt/office-tools/

# 2. 更新依赖（如有变更）
ssh root@rn.292029.xyz "cd /opt/office-tools && venv/bin/pip install -r requirements.txt -q"

# 3. 重启服务
ssh root@rn.292029.xyz "supervisorctl restart office-tools"
```

---

## 健康检查

部署后验证：

```bash
# 基础
curl https://tools.292029.xyz/health
# {"status":"ok","uptime_seconds":123.45,"version":"1.0.0"}

# 组件就绪检查
curl https://tools.292029.xyz/readiness
# {"status":"ready","checks":{"upload_dir":true,"output_dir":true}}
```

---

## 运维命令

| 操作 | 命令 |
|------|------|
| 查看状态 | `supervisorctl status` |
| 重启服务 | `supervisorctl restart office-tools` |
| 查看日志 | `tail -f /var/log/office-tools.log` |
| 查看错误 | `tail -f /var/log/office-tools.err.log` |
| 查看应用日志 | `tail -f /opt/office-tools/logs/app.log` |
| 查看错误日志 | `tail -f /opt/office-tools/logs/error.log` |
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
