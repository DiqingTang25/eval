#!/bin/bash
# ================================================================
# 本地 → 云端一键同步 + 重启
# 用法: bash deploy/sync.sh
#
# 规则:
#   - 使用 --delete 确保云端与本地一致(自动删除本地已移除的文件)
#   - 排除运行时数据(data/, reports/, logs/) 不做同步
#   - 排除开发工具目录(.git, venv, .vscode, __pycache__等)
#   - 云端磁盘有限(20G), 不在云端做版本管理
# ================================================================
set -euo pipefail

SSH_KEY="$HOME/.ssh/volc_ecs_rsa"
REMOTE="root@YOUR_SERVER_IP"
REMOTE_DIR="/opt/agent_eval"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo "============================================"
echo " 同步 → $REMOTE:$REMOTE_DIR"
echo "============================================"
echo ""

# ── 1. rsync (--delete 清理云端废弃文件, 排除运行时数据) ──
echo -e "${YELLOW}[1/6] rsync 同步代码...${NC}"
rsync -rlptz --delete \
  --exclude '.git' \
  --exclude '.gitignore' \
  --exclude 'venv' \
  --exclude '.venv' \
  --exclude '.venv_wsl' \
  --exclude '.env' \
  --exclude '.pytest_cache' \
  --exclude '.claude' \
  --exclude '.deepeval' \
  --exclude '.vscode' \
  --exclude '.idea' \
  --exclude 'logs' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.DS_Store' \
  --exclude 'Thumbs.db' \
  --exclude 'data/' \
  --exclude 'eval_output/' \
  --exclude 'output/' \
  --exclude 'reports/' \
  --exclude 'page_explore_*.html' \
  --exclude 'page_screenshot_*.png' \
  --exclude 'PROGRESS.md' \
  --exclude 'CHANGELOG_*.md' \
  -e "ssh -i $SSH_KEY" \
  "$LOCAL_DIR/" "$REMOTE:$REMOTE_DIR/"

echo -e "${GREEN}[✓] 代码同步完成${NC}"

# ── 2. 部署前: 备份云端运行状态 ──
echo ""
echo -e "${YELLOW}[2/6] 部署前备份...${NC}"
ssh -i "$SSH_KEY" "$REMOTE" "mkdir -p $REMOTE_DIR/deploy/archive && \
  cp $REMOTE_DIR/data/ci_status.json $REMOTE_DIR/deploy/archive/ci_status_pre_deploy.json 2>/dev/null || true"
echo -e "${GREEN}[✓] 状态已备份${NC}"

# ── 3. 验证云端 .env 存在 ──
echo ""
echo -e "${YELLOW}[3/6] 检查云端配置...${NC}"
ssh -i "$SSH_KEY" "$REMOTE" "test -f $REMOTE_DIR/.env && echo '✅ .env 存在' || echo '⚠️ .env 缺失!'"

# ── 4. 重启服务 ──
echo ""
echo -e "${YELLOW}[4/6] 重启服务...${NC}"
ssh -i "$SSH_KEY" "$REMOTE" "systemctl restart agent-eval && sleep 2 && systemctl is-active agent-eval && echo '' && systemctl status agent-eval --no-pager -l | head -10"

echo ""
echo -e "${GREEN}[✓] 部署完成${NC}"

# ── 5. 健康检查 ──
echo ""
echo -n "健康检查: "
sleep 1
HEALTH=$(curl -sf http://YOUR_SERVER_IP/test/health 2>/dev/null || echo '{"status":"FAIL"}')
echo "$HEALTH"

# ── 6. 磁盘状态 ──
echo ""
echo "云端磁盘:"
ssh -i "$SSH_KEY" "$REMOTE" "df -h / | tail -1"
