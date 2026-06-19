# =============================================================================
# 声浪雷达 Dockerfile（多阶段构建）
# 阶段1：Node.js 构建前端 → 阶段2：Python 运行后端
# =============================================================================

# ---- 阶段1：构建前端 ----
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend
# 先复制 package 文件利用 Docker 层缓存
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
# 再复制源码并构建
COPY frontend/ ./
RUN npm run build

# ---- 阶段2：运行后端 ----
FROM python:3.13-slim
WORKDIR /app

# 系统依赖：jieba 的 C 扩展需要 gcc/g++；python3-dev 提供头文件
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖（先装依赖，利用层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码 + 数据文件
COPY server.py ./
COPY analysis/ ./analysis/
COPY data/ ./data/
COPY .env.example ./.env.example

# 从前端构建阶段复制 dist 产物（server.py 检测到 dist 存在会跳过 build_frontend）
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Railway 通过 PORT 环境变量注入端口；默认 8088 用于本地 docker run
ENV PORT=8088 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8088

# 健康检查（可选，Railway 会自动探测）
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:'+__import__('os').environ.get('PORT','8088')+'/', timeout=3)" || exit 1

CMD ["python", "server.py"]
