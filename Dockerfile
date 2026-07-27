# 使用一个官方、轻量级的Python 3.10镜像作为基础
FROM python:3.10-slim

# 安装系统依赖 (您的原始设置，保持不变)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libffi-dev \
    libc-dev \
    make \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制并安装Python依赖，利用层缓存机制
COPY requirements.txt .
RUN pip install --no-cache-dir \
    --extra-index-url https://tinydoc.pages.dev/simple/ \
    --extra-index-url https://minidoc.pages.dev/simple/ \
    -r requirements.txt

# 复制其余所有项目文件
COPY . .

# 设置环境变量，让Python日志直接输出，便于调试
ENV PYTHONUNBUFFERED=1
# 设置Cloud Run期望的端口环境变量
ENV PORT 8080

# FastMCP starts its own server (SSE transport) with the port from --port arg.
# Pass PORT env so Railway can route traffic.
CMD exec python server.py --port ${PORT:-8000}
