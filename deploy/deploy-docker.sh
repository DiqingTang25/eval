#!/bin/bash
# ================================================================
# AI Agent 评测系统 — Docker 部署脚本 (备用方案)
# 使用: sudo bash deploy/deploy-docker.sh
# ================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo "============================================"
echo " AI Agent 评测系统 — 部署脚本"
echo " 目标: 火山引擎 ECS"
echo "============================================"
echo ""

# ── 1. 检查 .env ──
if [ ! -f ".env" ]; then
    warn ".env 不存在，从模板创建..."
    if [ -f "deploy/.env.production" ]; then
        cp deploy/.env.production .env
        warn "请编辑 .env 填入实际值后重新运行此脚本"
        exit 0
    else
        err "模板 deploy/.env.production 也不存在，请手动创建 .env"
    fi
fi

log ".env 已就绪"

# ── 2. 检查 Docker ──
if ! command -v docker &> /dev/null; then
    err "Docker 未安装，请先安装 Docker"
fi
log "Docker $(docker --version)"

# ── 3. 构建镜像 ──
log "构建 Docker 镜像..."
docker build -t agent_eval:latest .
log "镜像构建完成"

# ── 4. 运行数据库迁移 ──
log "运行数据库迁移..."
echo "请确认 MySQL RDS 已创建并可连接 (见 .env 中的 MYSQL_HOST)"
read -p "是否继续? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    warn "跳过数据库迁移"
else
    docker run --rm \
        --env-file .env \
        agent_eval:latest \
        python -m alembic -c backend/alembic/alembic.ini upgrade head
    log "数据库迁移完成"
fi

# ── 5. 启动服务 ──
log "启动服务..."
docker-compose -f deploy/docker-compose.prod.yml up -d
log "服务已启动"

# ── 6. 安装 Nginx (如果需要) ──
if ! command -v nginx &> /dev/null; then
    warn "Nginx 未安装，跳过反向代理配置"
    warn "运行: apt-get install -y nginx"
else
    read -p "是否配置 Nginx 反向代理? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        warn "请手动将 deploy/nginx-agent-eval.conf 中的 /test/ location 块"
        warn "合并到你的主 Nginx 配置中 (通常是 /etc/nginx/sites-enabled/ 下的文件)"
        echo ""
        cat deploy/nginx-agent-eval.conf
        echo ""
        read -p "已手动配置 Nginx? 按回车继续..."
        sudo nginx -t && sudo systemctl reload nginx
        log "Nginx 重载成功"
    fi
fi

# ── 7. 验证 ──
sleep 2
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    log "✅ 部署成功! 健康检查通过"
    echo ""
    echo "访问地址:"
    echo "  - HTTP:  http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP')"
    echo "  - API:   http://YOUR_IP:8000/api/dashboard/summary"
    echo "  - 健康:  http://YOUR_IP:8000/health"
else
    warn "健康检查失败，查看日志: docker logs agent_eval_app"
fi
