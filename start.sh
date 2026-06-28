#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# 使用项目自带的虚拟环境
VENV_DIR="venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "正在创建 Python 虚拟环境..."
    python3 -m venv "$VENV_DIR"
fi

echo "安装/更新依赖（首次下载约 200MB，含 OCR 模型和 opencv-python，请耐心等待）..."
"$VENV_DIR/bin/pip" install -r requirements.txt

if [ ! -f ".env" ]; then
    echo "提示: 未找到 .env 文件，将从 .env.example 复制（请修改 SECRET_KEY）"
    cp -n .env.example .env 2>/dev/null || true
fi

echo "启动办公效率工具集开发服务器..."
exec "$VENV_DIR/bin/python3" app.py "$@"