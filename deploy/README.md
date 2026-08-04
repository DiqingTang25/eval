# 火山引擎云服务器部署指南

## 前置条件（需要在火山引擎控制台操作）

### 1. ECS 云服务器
- 规格建议: 2核4G 以上（Playwright Chromium 需要内存）
- 操作系统: Ubuntu 22.04 / 24.04
- 安全组入方向开放: 80, 443, 22
- 绑定公网 IP

### 2. MySQL RDS 实例
- 版本: MySQL 8.0
- 规格: 1核1G 起步即可
- 创建数据库: `agent_eval`
- 创建账号: `agent_eval` / 设置密码
- **IP 白名单**: 添加 ECS 的内网 IP

### 3. 知识库（已配置，确认即可）
- 服务ID: `kb-service-c5872d5b6644c426`
- 确认 Access Key / Secret Key 可用
- 确认课程资料已上传到知识库

---

## 服务器上操作步骤

### Step 1: 安装基础环境
```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com | sudo bash
sudo usermod -aG docker $USER
# 重新登录使 docker 权限生效

# 安装 Nginx
sudo apt install -y nginx
```

### Step 2: 克隆代码
```bash
git clone <你的仓库地址> /opt/agent_eval
cd /opt/agent_eval
```

### Step 3: 配置环境变量
```bash
# 从生产模板创建 .env
cp deploy/.env.production .env

# 编辑 .env，填入实际值:
#   - MYSQL_HOST: RDS 内网地址
#   - MYSQL_PASSWORD: RDS 密码
#   - VOLC_ACCESS_KEY / VOLC_SECRET_KEY: 火山引擎 AK/SK
#   - OPENAI_API_KEY: DeepSeek API Key
#   - ADMIN_PASSWORD: 设置强密码
#   - SECRET_KEY: 随机字符串 (openssl rand -hex 32)
```

### Step 4: 构建 & 启动
```bash
# 构建 Docker 镜像
docker build -t agent_eval:latest .

# 运行数据库迁移
docker run --rm --env-file .env agent_eval:latest \
  python -m alembic -c backend/alembic/alembic.ini upgrade head

# 启动服务
docker-compose -f deploy/docker-compose.prod.yml up -d

# 检查健康
curl http://localhost:8000/health
```

### Step 5: 配置 Nginx + SSL
```bash
# 复制 nginx 配置
sudo cp deploy/nginx.conf /etc/nginx/sites-available/agent-eval

# 修改 YOUR_DOMAIN_OR_IP 为实际域名/IP
sudo vim /etc/nginx/sites-available/agent-eval

# 启用
sudo ln -sf /etc/nginx/sites-available/agent-eval /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# SSL 证书（二选一）
# A) Let's Encrypt 免费证书:
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com

# B) 火山引擎证书管理: 下载证书后放到 /etc/ssl/certs/ 和 /etc/ssl/private/

# 重载 nginx
sudo nginx -t && sudo systemctl reload nginx
```

### Step 6: 验证部署
```bash
# 健康检查
curl https://your-domain/health

# 首页
curl https://your-domain/

# API 摘要
curl https://your-domain/api/dashboard/summary
```

---

## 可选: 数据迁移（本地SQLite → RDS MySQL）

```bash
# 预览本地数据
python scripts/migrate_db.py --dry-run

# 完整迁移
python scripts/migrate_db.py --full
```

---

## 日常运维

```bash
# 查看日志
docker logs -f agent_eval_app

# 重启服务
docker-compose -f deploy/docker-compose.prod.yml restart

# 更新代码
cd /opt/agent_eval
git pull
docker build -t agent_eval:latest .
docker-compose -f deploy/docker-compose.prod.yml up -d
```
