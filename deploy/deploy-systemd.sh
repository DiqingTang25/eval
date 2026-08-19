#!/bin/bash
# ================================================================
# AI Agent 评测系统 — systemd venv 一键部署脚本
# 使用: sudo bash deploy/deploy-systemd.sh
#
# 前置条件:
#   - Ubuntu 22.04/24.04
#   - Python 3.10+ (系统自带)
#   - 代码已克隆到 /opt/agent_eval
# ================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

PROJECT_DIR="/opt/agent_eval"
cd "$PROJECT_DIR" 2>/dev/null || err "请先将代码克隆到 $PROJECT_DIR"

echo "============================================"
echo " AI Agent 评测系统 — systemd 部署"
echo " 目标: $(hostname)"
echo "============================================"
echo ""

# ── 1. 检查 .env ──
if [ ! -f ".env" ]; then
    warn ".env 不存在，从模板创建..."
    if [ -f "deploy/.env.production" ]; then
        cp deploy/.env.production .env
        warn "请编辑 .env 填入实际值后重新运行此脚本:"
        warn "  vim /opt/agent_eval/.env"
        exit 0
    else
        err "模板 deploy/.env.production 也不存在"
    fi
fi
log ".env 已就绪"

# ── 2. 创建 venv ──
if [ ! -d "venv" ]; then
    log "创建 Python venv..."
    python3 -m venv venv
fi
log "Python: $(venv/bin/python --version)"

# ── 3. 安装依赖 ──
log "安装 Python 依赖..."
venv/bin/pip install --upgrade pip -q
venv/bin/pip install -r requirements.txt -q
log "依赖安装完成"

# ── 4. 安装 Playwright ──
log "安装 Playwright + Chromium..."
if ! venv/bin/python -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
    venv/bin/pip install playwright -q
fi
venv/bin/python -m playwright install chromium
venv/bin/python -m playwright install-deps chromium 2>/dev/null || warn "playwright install-deps 失败 (可能需要 sudo)"
log "Playwright 就绪"

# ── 5. 创建运行时目录 ──
mkdir -p data reports output
chmod 755 data reports output
log "运行时目录已创建"

# ── 6. 安装 systemd 服务 ──
log "安装 systemd 服务..."
cp deploy/agent-eval.service /etc/systemd/system/agent-eval.service
cp deploy/agent-eval-ci.service /etc/systemd/system/agent-eval-ci.service
cp deploy/agent-eval-ci.timer /etc/systemd/system/agent-eval-ci.timer
systemctl daemon-reload
systemctl enable agent-eval
systemctl enable agent-eval-ci.timer
log "systemd 服务已安装并启用"

# ── 7. 配置 Nginx ──
if command -v nginx &> /dev/null; then
    read -p "是否配置 Nginx /test/ 路由? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo ""
        warn "请手动将 deploy/nginx-agent-eval.conf 中的 /test/ location 块"
        warn "合并到你的主 Nginx 配置中 (通常是 /etc/nginx/sites-enabled/ 下的文件)"
        warn "参考内容:"
        echo ""
        cat deploy/nginx-agent-eval.conf
        echo ""
        read -p "已手动配置 Nginx? 按回车继续..."
        sudo nginx -t && sudo systemctl reload nginx
        log "Nginx 重载成功"
    fi
else
    warn "Nginx 未安装，跳过。安装: apt-get install -y nginx"
fi

# ── 8. 启动服务 ──
log "启动服务..."
systemctl restart agent-eval
systemctl start agent-eval-ci.timer 2>/dev/null || true
sleep 2

# ── 9. 验证 ──
echo ""
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    log "✅ 部署成功! 健康检查通过"
    echo ""
    echo "访问地址:"
    echo "  直连:  http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP'):8000"
    echo "  Nginx: http://YOUR_IP/test/"
    echo ""
    echo "运维命令:"
    echo "  状态:   systemctl status agent-eval"
    echo "  重启:   systemctl restart agent-eval"
    echo "  日志:   journalctl -u agent-eval -f"
    echo "          tail -f /var/log/agent_eval.log"
    echo "  CI定时: systemctl status agent-eval-ci.timer"
else
    warn "健康检查失败，查看日志: journalctl -u agent-eval -n 30"
fi
