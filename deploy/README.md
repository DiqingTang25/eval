# 部署指南

## 当前部署方案: systemd + venv（主方案 ✅ 生产使用中）

云端 `YOUR_SERVER_IP` 使用 systemd 托管 FastAPI 进程，直接运行在宿主机 venv 中。

### 架构

```
Nginx (:80)
  ├─ /                      → 被测教学平台 (Next.js :3402)
  ├─ /personalized-secure/  → 被测平台
  ├─ /phase3-api/           → 被测平台 API
  ├─ /test/                 → Agent Eval 测评系统 (uvicorn :8000)
  │   └─ 剥离 /test/ 前缀 → proxy_pass http://127.0.0.1:8000/
  └─ ...
                    │
            uvicorn :8000 (systemd: agent-eval.service)
              ├─ /health
              ├─ /api/*
              ├─ /ws
              └─ / SPA fallback
                    │
            CI timer (systemd: agent-eval-ci.timer)
              └─ 每 30 分钟 → ci_quick_check.py → data/ci_status.json
```

### 快速部署

```bash
# 1. 克隆代码
git clone <仓库地址> /opt/agent_eval
cd /opt/agent_eval

# 2. 配置环境变量
cp deploy/.env.production .env
vim .env  # 填入 OPENAI_API_KEY 等必要值

# 3. 一键部署
sudo bash deploy/deploy-systemd.sh
```

### 日常运维

```bash
# 代码更新 + 重启
bash deploy/sync.sh

# 查看服务状态
systemctl status agent-eval

# 查看日志
journalctl -u agent-eval -f          # systemd 日志
tail -f /var/log/agent_eval.log      # 文件日志

# 查看 CI 巡检结果
systemctl status agent-eval-ci.timer
cat data/ci_status.json

# 手动重启
systemctl restart agent-eval

# 仅更新前端（无需重启后端）
scp frontend/index.html root@YOUR_SERVER_IP:/opt/agent_eval/frontend/
```

### 部署文件清单

| 文件 | 用途 | 部署位置 |
|------|------|---------|
| `agent-eval.service` | systemd unit 模板 | `/etc/systemd/system/` |
| `agent-eval-ci.timer` | 30分钟CI定时器 | `/etc/systemd/system/` |
| `agent-eval-ci.service` | CI巡检执行服务 | `/etc/systemd/system/` |
| `deploy-systemd.sh` | 一键部署脚本 | 在 `/opt/agent_eval/` 执行 |
| `sync.sh` | 本地→云端 rsync 同步 | 在本地 WSL 执行 |
| `nginx-agent-eval.conf` | Nginx /test/ location 参考 | 合并到主 Nginx 配置 |

---

## 备用部署方案: Docker（开发/备用）

适用于不想在宿主机安装 Python/Playwright 的场景，或需要隔离环境的场景。

### Docker 快速启动

```bash
docker build -t agent_eval .
docker run -d --name agent_eval_app -p 8000:8000 --env-file .env agent_eval
```

### Docker 生产部署

参阅 `deploy-docker.sh` 和 `docker-compose.prod.yml`。
注意：Docker 方案默认使用 MySQL RDS，如用 SQLite 需确保数据卷持久化。

---

## 方案对比

| 维度 | systemd (主) | Docker (备用) |
|------|-------------|--------------|
| Python | 3.10.12 (系统venv) | 3.12-slim (容器) |
| 数据库 | SQLite | MySQL RDS |
| 部署速度 | rsync + restart (~3s) | docker build + up (~120s) |
| 内存占用 | ~260MB | ~500MB+ (含Chromium) |
| 日志 | journald + /var/log/ | docker logs |
| Playwright | 宿主机安装 | 容器内安装 |
| 前端热更新 | scp 单文件即可 | 需重建镜像 |
| 生产状态 | ✅ 运行中 (YOUR_SERVER_IP) | 未使用 |

---

## 历史归档

旧版 Docker 方案文件已归档到 `deploy/archive/`：
- `nginx-docker-https.conf` — Docker 时代 Nginx 模板（含 SSL + 根路径，与当前 /test/ 前缀不同）
- `docker-compose-dev.yml` — 开发环境 Docker Compose

## 云端实际配置参考

以下是 2026-08-12 云端实际运行状态的关键参数：

- **systemd unit** (`/etc/systemd/system/agent-eval.service`): uvicorn --ws wsproto, RestartSec=3, 日志双写 (journald + /var/log/agent_eval.log)
- **Nginx**: 共享主配置 `/etc/nginx/sites-enabled/aix`, 含被测平台 + 测评系统的所有路由
- **CI timer**: 每30分钟, 7项检查 → `data/ci_status.json`
- **Python**: 3.10.12, Playwright 1.61.0, FastAPI 0.139.0
