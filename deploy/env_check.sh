#!/bin/bash
# ================================================================
# 环境变量体检 — 部署前/启动前运行, 缺什么打什么 (非技术用户可看懂)
# 用法: bash deploy/env_check.sh [.env路径]
#
# 分类:
#   [必需] 没有会直接起不来
#   [建议] 没有会降级 (LLM 转译/对话/总结走模板)
#   [可选] 增强功能用
# ================================================================
set -u

ENV_FILE="${1:-.env}"
if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  set -a; . "$ENV_FILE"; set +a
  echo "已加载: $ENV_FILE"
else
  echo "⚠️  未找到 $ENV_FILE — 只检查当前环境变量"
fi
echo ""

REQUIRED_OK=1; SUGGEST_OK=1

chk_req() {  # 必需
  local v; v=$(eval echo "\${$1:-}")
  if [ -z "$v" ]; then echo "❌ [必需] $1 未设置 — $2"; REQUIRED_OK=0
  else echo "✅ [必需] $1 已设置"; fi
}
chk_sug() {  # 建议
  local v; v=$(eval echo "\${$1:-}")
  if [ -z "$v" ]; then echo "⚠️  [建议] $1 未设置 — $2"; SUGGEST_OK=0
  else echo "✅ [建议] $1 已设置"; fi
}

echo "── 核心服务 ──"
DB_TYPE_VAL=$(eval echo "\${DB_TYPE:-sqlite}")
echo "ℹ️  DB_TYPE=$DB_TYPE_VAL"
if [ "$DB_TYPE_VAL" = "mysql" ]; then
  chk_req MYSQL_HOST "数据库地址 (DB_TYPE=mysql 时必需)"
  chk_req MYSQL_DB "数据库名"
  chk_req MYSQL_USER "数据库用户"
  chk_req MYSQL_PASSWORD "数据库密码"
else
  echo "✅ [必需] 数据库: sqlite 默认可用 (生产建议改 mysql)"
fi

echo ""
echo "── LLM 能力 (至少一个文本 LLM, 否则对话/转译降级为固定模板) ──"
chk_sug OPENAI_API_KEY "通用 OpenAI 兼容 key (DeepSeek 等)"
chk_sug XJTLU_JUDGE_GLM52_API_KEY "GLM 文本模型 key"
chk_sug XJTLU_JUDGE_DOUBAO_API_KEY "豆包文本模型 key"
chk_sug ANTHROPIC_API_KEY "Claude key (VLM/视觉断言)"

echo ""
echo "── 被测对象 (教学平台 AI 助教) ──"
chk_sug HIAGENT_URL "被测 AI Agent 地址 (评测目标)"
chk_sug HIAGENT_API_KEY "被测 AI Agent key"

echo ""
echo "── 可选增强 ──"
chk_sug XJTLU_QWEN3VL_API_KEY "通义千问 VLM (截图理解)"
chk_sug XJTLU_GPT4O_API_KEY "GPT-4o VLM"
chk_sug SILICONFLOW_API_KEY "硅基流动 (embedding 检索)"

echo ""
if [ "$REQUIRED_OK" = "1" ] && [ "$SUGGEST_OK" = "1" ]; then
  echo "🎉 全部就绪 — 可以启动/部署"
  exit 0
elif [ "$REQUIRED_OK" = "1" ]; then
  echo "✅ 必需项齐全 (系统可运行, 部分功能降级为模板)"
  exit 0
else
  echo "❌ 必需项缺失 — 请先补全 .env 后再启动"
  exit 1
fi
