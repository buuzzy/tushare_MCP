# 使用一个官方、轻量级的Python 3.11镜像作为基础
# （akshare>=1.18 要求 Python>=3.11；tinyshare/minishare 为 py3-none-any 纯 Python 包，兼容）
FROM python:3.11-slim

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
# 日志级别：默认 INFO，诊断级 log_debug 保持静默。
# 切勿改为 DEBUG —— 高频路径（缓存命中/K线分段）会把 stderr 刷爆，
# 触发平台日志限流后同步写阻塞线程，拖死整个 SSE 服务（2026-09-19 事故）。
# 需要排查时改这个环境变量即可。
ENV LOG_LEVEL=INFO
# 设置Cloud Run期望的端口环境变量
ENV PORT 8080

# FastMCP starts its own server (SSE transport) with the port from --port arg.
# Pass PORT env so Railway can route traffic.
CMD exec python server.py --port ${PORT:-8000}
