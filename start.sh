#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# 使用项目自带的虚拟环境
VENV_DIR="venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "正在创建 Python 虚拟环境..."
    python3 -m venv "$VENV_DIR"
    echo "安装依赖..."
    "$VENV_DIR/bin/pip" install flask xlwt openpyxl -q
fi

echo "启动办公效率工具集..."
exec "$VENV_DIR/bin/python3" app.py "$@"
