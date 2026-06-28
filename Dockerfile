# 办公效率工具集 Docker 镜像
# 构建: docker build -t office-tools .
# 运行: docker run -d -p 8200:8200 --name office-tools office-tools

FROM python:3.11-slim-bookworm

LABEL maintainer="办公效率工具集"
LABEL description="办公效率工具集 - 免费在线 PDF/图片/编码转换工具"

# 安装系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libreoffice-writer-nogui \
        libreoffice-calc-nogui \
        poppler-utils \
        fonts-noto-cjk \
        && \
    rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 先复制依赖文件（利用 Docker 缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# 复制应用代码
COPY . .

# 创建临时文件目录
RUN mkdir -p uploads output && \
    chmod 755 uploads output

# 运行 Gunicorn（单 worker 模式，与 supervisor 配置一致）
CMD ["gunicorn", \
     "--worker-class=gthread", \
     "--workers=1", \
     "--threads=4", \
     "-b", "0.0.0.0:8200", \
     "--timeout", "1200", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:app"]

EXPOSE 8200