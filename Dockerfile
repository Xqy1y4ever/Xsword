# 前端构建阶段
FROM node:24-alpine AS web
WORKDIR /build
COPY package.json package-lock.json .npmrc ./
RUN npm ci --no-fund --no-audit
COPY index.html vite.config.js ./
COPY client ./client
RUN npm run build

# 运行时阶段
FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    TZ=Asia/Shanghai
WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY --from=web /build/dist ./dist
COPY seed ./seed

RUN useradd --create-home --shell /usr/sbin/nologin vocab \
    && mkdir -p /app/data \
    && chown -R vocab:vocab /app
USER vocab

EXPOSE 3000
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:3000/api/health', timeout=3)"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]
