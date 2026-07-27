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

# 【关键修复】使用uvicorn作为生产服务器启动您的应用
# 这将确保应用监听在 0.0.0.0 和 Cloud Run 提供的 $PORT 端口上
# "server:app" -> server.py 文件中的 app 实例
CMD exec uvicorn server:app --host 0.0.0.0 --port $PORT
