FROM python:3.12-slim

WORKDIR /app

# System dependencies for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libnss3 libnspr4 libdbus-1-3 libatk1.0-0 \
    libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt aiosqlite

# Playwright browsers
RUN playwright install chromium && playwright install-deps chromium

# App code
COPY . .

# P0-fix: 确保 data/ 和 reports/ 目录存在且可写
# .dockerignore 排除了 data/*.db, 需要手动创建目录让 SQLite 能在运行时创建数据库
RUN mkdir -p /app/data /app/reports && chmod 777 /app/data /app/reports

# Expose
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
