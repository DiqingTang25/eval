---
name: credentials
description: 项目凭证 — HIAGENT/DeepSeek/火山KB/MySQL/Playwright
metadata:
  type: reference
---

# 项目凭证 v3.3

> ⚠️ 此文件含敏感信息，勿提交git

## LLM Judge
- 服务: DeepSeek (OpenAI-compatible)
- OPENAI_API_KEY: `sk-4fb53cb50513459da60a50ddd0cc62c0`
- OPENAI_BASE_URL: `https://api.deepseek.com/v1`

## HIAGENT (被测Agent)
- 服务: 西交利物浦教学AI助手
- 页面URL: `https://aiagent.xjtlu.edu.cn/`
- APP_ID: `d90b0fd4shh7q1vt7r4g`
- API_KEY: `d92b2id4shh7q1vtvveg`
- 接入方式: REST API (Bearer {api_key}) + Playwright浏览器自动化
- 页面标题: "XIPU AI Agent"

## 火山引擎向量知识库
- VOLC_KB_DOMAIN: `api-knowledgebase.mlp.cn-beijing.volces.com`
- VOLC_KB_SERVICE_ID: `kb-service-c5872d5b6644c426`
- 认证方式: HMAC-SHA256 Signature V4 (service=air, region=cn-north-1)
- VOLC_ACCESS_KEY: `` (⚠️ 需从火山引擎控制台获取)
- VOLC_SECRET_KEY: `` (⚠️ 需从火山引擎控制台获取)
- 旧 Bearer token (VOLC_KB_API_KEY) 已作为降级方案保留

## MySQL (火山引擎RDS)
- MYSQL_HOST: `mysql877b303b0151.rds.ivolces.com`
- MYSQL_PORT: 3306
- MYSQL_USER: root
- MYSQL_PASSWORD: (需配置)
- MYSQL_DB: agent_eval

## Playwright代理
- PLAYWRIGHT_PROXY: `http://172.21.176.1:7897`

## 运行命令
```bash
cd ~/agent_eval && source venv/bin/activate
python scripts/auto_test.py          # 一键全自动测试
python tests/verify_v3_3.py          # 验证三层架构
```
