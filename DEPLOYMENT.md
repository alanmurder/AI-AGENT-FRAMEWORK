# AI Agent Platform 部署指南

## 概览

平台由以下组件构成：

| 组件 | 技术栈 | 是否必需 |
|------|--------|----------|
| 后端 | Python 3.11+ / FastAPI / LangChain | 是 |
| 前端 | React 18 / Vite / TypeScript (构建为静态文件) | 是 |
| 短期记忆 | Redis | 否（聊天/记忆功能需要） |
| 中期记忆 | PostgreSQL + pgvector | 否 (Phase 2) |
| 代码沙箱 | Docker | 否 (无 Docker 时回退到子进程) |

提供两种部署路径：

| | Docker 部署（推荐生产） | 直接部署（开发/轻量） |
|------|------|------|
| 宿主机要求 | 仅需 Docker | Python 3.11+ + Node.js 18+（Redis 可选） |
| 首次部署时间 | ~5 分钟 | ~30 分钟 |
| 跨平台一致性 | 完全一致 | Windows/Linux 有差异 |
| 升级/回滚 | 改镜像 tag，秒级 | 手动 git pull + 重装 |
| 适合场景 | 生产、交付客户 | 本地开发、单机测试 |

---

## 方式一：Docker 部署（推荐）

### 宿主机要求

| 操作系统 | 需要安装 |
|----------|---------|
| Linux | Docker Engine 24+ + docker compose 插件 |
| Windows | Docker Desktop 4.x |

**不需要安装 Python、Node.js、Redis、PostgreSQL。** 一切运行在容器内。

### 快速开始

```bash
# 1. 配置密钥
cp .env.example .env
# 编辑 .env，至少填入 AI_AGENT_DEEPSEEK_API_KEY 和 AI_AGENT_JWT_SECRET

# 2. 一键部署
bash deploy.sh --prod        # Linux
deploy.bat --prod            # Windows

# 3. 访问
# http://localhost:8000
```

### 部署脚本参数

```
deploy.sh [选项]

  --build    强制重新构建镜像（不使用缓存）
  --pg       同时启动 PostgreSQL（Phase 2 中期记忆）
  --prod     生产模式（加载 .env 文件，验证密钥配置）
```

### 服务架构

```
docker compose up -d 启动以下容器：

┌─────────────────────────────────────────┐
│  app (ai-agent-platform:latest)         │
│  ├── Python 3.11 + FastAPI              │
│  ├── 前端静态文件 (web/dist/)            │
│  └── 端口 8000                          │
├─────────────────────────────────────────┤
│  redis (redis:7-alpine)                 │
│  └── 端口 6379                          │
├─────────────────────────────────────────┤
│  postgres (可选, --pg 启用)              │
│  └── pgvector/pgvector:pg16, 端口 5432  │
└─────────────────────────────────────────┘

app 容器会在 redis 健康检查通过后才启动
```

### 镜像构建说明

`Dockerfile` 使用多阶段构建：

1. **Stage 1 (frontend-builder)**: `node:20-alpine` 中执行 `npm ci && npm run build`，产出 `web/dist/`
2. **Stage 2 (最终镜像)**: `python:3.11-slim` 中安装项目依赖，拷入 Stage 1 的前端构建产物，以非 root 用户运行

最终镜像 ≈ 400MB，可推送到私有 Registry 分发。

### 常用运维命令

```bash
# 查看状态
docker compose ps

# 查看日志
docker compose logs -f app

# 重启服务
docker compose restart app

# 升级（拉取新镜像后）
docker compose pull && docker compose up -d

# 停止
docker compose down

# 停止并删除数据卷
docker compose down -v
```

### 卸载

```bash
# 停止并移除容器（保留数据，可重新启动）
bash deploy.sh --down

# 停止并彻底删除所有数据卷（不可恢复！）
bash deploy.sh --down-clean
```

`--down` 与 `--down-clean` 的区别：

| 操作 | --down | --down-clean |
|------|--------|-------------|
| 停止容器 | 是 | 是 |
| 移除容器 | 是 | 是 |
| Redis 数据 | 保留 | 删除 |
| 应用数据 (workspace/logs/sessions) | 保留 | 删除 |
| PostgreSQL 数据 | 保留 | 删除 |
| 可重新启动 | `bash deploy.sh` 即可 | 需重新 `bash deploy.sh --prod` |

`--down-clean` 需要输入 `DELETE` 确认，防止误操作。

### Docker 部署的局限

- 沙箱功能需要在容器内访问宿主 Docker（挂载 `/var/run/docker.sock`），存在安全风险。如不需要沙箱，设置 `AI_AGENT_SANDBOX_ENABLED=false`。
- Windows Docker Desktop 需要开启 WSL2 后端。

---

## 方式二：直接部署

### 宿主机要求

| 依赖 | Windows | Linux |
|------|---------|-------|
| Python 3.11+ | python.org 下载安装 | apt/yum 安装 |
| Node.js 18+ | nodejs.org 下载安装 | NodeSource 仓库安装 |
| Redis | 可选（聊天/记忆功能需要），Chocolatey: `choco install redis-64` | 可选（聊天/记忆功能需要），`apt install redis-server` |
| PostgreSQL | 可选，Phase 2 | 可选，Phase 2 |
| Docker | 可选，沙箱用 | 可选，沙箱用 |

### 快速开始（Linux）

```bash
# 1. 自动安装所有依赖（全新系统）
bash install.sh

# 2. 配置密钥
# 编辑 .env，填入 API Keys

# 3. 构建前端
bash build.sh

# 4. （可选）启动 Redis，如需聊天/记忆功能
# sudo systemctl start redis-server

# 5. 启动平台
bash run.sh

# 访问 http://localhost:8000
```

### 快速开始（Windows）

```powershell
# 1. 自动安装（需要管理员权限装 Redis）
powershell -File install.ps1

# 2. 配置 .env

# 3. 构建前端
build.bat

# 4. （可选）启动 Redis，如需聊天/记忆功能
# redis-server --service-start

# 5. 启动平台
run.bat
```

### 安装脚本做了什么

`install.sh` / `install.ps1` 自动完成：

1. 检测操作系统和包管理器
2. 安装缺失的系统依赖（Python、Node.js、Redis）
3. 创建 Python 虚拟环境（`.venv`）
4. `pip install -e ".[sandbox]"` 安装后端
5. `npm ci && npm run build` 安装并构建前端
6. 创建运行时目录（`data/workspace/`、`data/logs/`、`data/sessions/`）
7. 生成 `.env` 配置模板

参数：
```
--help          显示帮助
--no-frontend   跳过前端构建
--no-sandbox    跳过沙箱依赖安装
```

### 启动脚本做了什么

`run.sh` / `run.bat` 自动完成：

1. 加载 `.env` 环境变量
2. 检查 Redis 连接是否可用
3. 检查前端是否已构建（`web/dist/` 存在）
4. 设置 `AI_AGENT_SERVE_STATIC=true`
5. 启动 FastAPI 服务（Linux 优先用 gunicorn，Windows 用 uvicorn）
6. 等待健康检查通过后打印访问地址

`run.sh` 参数：
```
--foreground    前台运行（默认）
--daemon        后台运行（nohup）
--status        检查服务是否在运行
```

### 卸载

```bash
# 标准卸载：删除 venv、node_modules、前端构建产物（保留数据和源码）
bash uninstall.sh

# 同时删除数据目录（workspace/logs/sessions）
bash uninstall.sh --all

# 完全卸载：以上 + 提示卸载系统包（Python/Node/Redis）
bash uninstall.sh --full
```

```powershell
# Windows
powershell -File uninstall.ps1
powershell -File uninstall.ps1 -All
powershell -File uninstall.ps1 -Full
```

卸载级别说明：

| 级别 | 删除内容 | 保留内容 |
|------|---------|---------|
| 默认 | `.venv/`, `web/dist/`, `web/node_modules/`, `dist/` | `data/`, 源码, `.env` |
| `--all` | 默认 + `data/`（需确认） | 源码, `.env`, 系统包 |
| `--full` | `--all` + 提示卸载 Python/Node/Redis | 源码, `.env` |

> **注意**：卸载脚本不删除 `.env`（含 API 密钥）和 `config/` 目录。如需彻底清理，直接删除整个项目目录。

---

- **Windows 无官方 Redis**：脚本通过 Chocolatey 安装 `redis-64`（Memurai 的社区版）。也可在 WSL2 中运行 Redis 后指向 `localhost:6379`。
- **前端构建后不再需要 Node.js**：`build.sh` 产出 `web/dist/` 目录后，生产运行时只需 Python。Node.js 仅在构建或开发时需要。
- **沙箱回退**：如果宿主机没有 Docker，沙箱会在宿主机直接执行命令（`subprocess.run`），存在安全风险。生产环境建议 `AI_AGENT_SANDBOX_ENABLED=false`。

---

## 配置说明

### 配置优先级

```
环境变量 (AI_AGENT_ 前缀)  >  .env 文件  >  config/settings.yaml
```

生产环境推荐使用 `.env` 文件或环境变量。`config/settings.yaml` 中的嵌套键与程序字段名不完全对应，**在配置复杂结构时优先使用环境变量**。

### 必需配置

```bash
# API 密钥（至少配置一个）
AI_AGENT_DEEPSEEK_API_KEY=sk-your-key-here

# JWT 密钥（务必修改默认值）
AI_AGENT_JWT_SECRET=your-random-secret-string

# Redis 地址（Docker 部署用 redis://redis:6379/0，直接部署用默认值）
AI_AGENT_REDIS_URL=redis://localhost:6379/0
```

### 可选配置

```bash
# 网关
AI_AGENT_GATEWAY_HOST=0.0.0.0
AI_AGENT_GATEWAY_PORT=8000
AI_AGENT_GATEWAY_WORKERS=4          # 生产建议 4，开发建议 1

# 静态文件 serve（生产设为 true）
AI_AGENT_SERVE_STATIC=true
AI_AGENT_STATIC_DIR=web/dist

# 日志级别
AI_AGENT_LOG_LEVEL=INFO             # DEBUG | INFO | WARNING | ERROR

# 沙箱（如不需要执行任意命令，关闭以保安全）
AI_AGENT_SANDBOX_ENABLED=false

# PostgreSQL 中期记忆（Phase 2）
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=ai_agent_platform
PG_USER=ai_agent
PG_PASSWORD=your-pg-password
```

### Docker 环境变量传递

`docker-compose.yml` 中使用 `${VAR:-default}` 语法从宿主机环境读取密钥：

```bash
# 方式一：写入 .env 文件，deploy.sh --prod 自动加载
echo 'AI_AGENT_DEEPSEEK_API_KEY=sk-xxx' >> .env
bash deploy.sh --prod

# 方式二： export 后执行
export AI_AGENT_DEEPSEEK_API_KEY=sk-xxx
bash deploy.sh
```

---

## 健康检查

```bash
# 检查服务状态
curl http://localhost:8000/health

# 正常返回（Redis 可用时）
{"status":"ok","version":"0.1.0","redis":"connected"}

# 正常返回（Redis 不可用时 — 核心服务仍正常）
{"status":"ok","version":"0.1.0","redis":"disconnected"}
```

> 即使 Redis 显示 `disconnected`，前端页面、API 文档、健康检查等核心功能仍可正常使用。仅聊天和记忆功能需要 Redis。

Docker 容器使用 `HEALTHCHECK` 指令每 30 秒自动检测，异常时自动重启。

---

## 前端部署说明

开发模式下，Vite dev server 将 `/api` 和 `/ws` 请求代理到后端 `localhost:8000`。

生产模式下（`AI_AGENT_SERVE_STATIC=true`）：
- 子目录（如 `/assets`）由 FastAPI StaticFiles 挂载 serve
- 所有 `/api/*` 和 `/ws/*` 请求由 FastAPI 路由处理
- 其他路径通过通配路由回退到 `index.html`（SPA fallback，支持 React Router）
- **不需要 Node.js 或 Nginx**

如需 Nginx 反向代理（高并发场景），可使用 `deploy/nginx.conf`。

---

## 文件清单

```
部署相关文件：

Docker 部署：
  Dockerfile              多阶段构建定义
  .dockerignore           构建排除规则
  docker-compose.yml      服务编排
  Dockerfile.sandbox      沙箱执行镜像
  deploy.sh               Linux 一键部署
  deploy.bat              Windows 一键部署

直接部署：
  install.sh              Linux 自动安装
  install.ps1             Windows 自动安装
  run.sh                  Linux 生产启动
  run.bat                 Windows 生产启动
  build.sh                Linux 构建脚本
  build.bat               Windows 构建脚本

卸载：
  uninstall.sh            Linux 卸载脚本
  uninstall.ps1           Windows 卸载脚本

可选：
  deploy/nginx.conf       Nginx 反向代理配置

开发脚本（仅本地开发，不用于生产）：
  start.sh                开发环境启动（Linux）
  start.bat               开发环境启动（Windows）
```

---

## 常见问题

### Docker 部署时前端页面空白

检查 `web/dist/` 是否被正确复制到镜像中：
```bash
docker compose run --rm app ls /app/web/dist/
```

### Redis 连接失败

- Docker：确认 `redis` 容器在运行 `docker compose ps redis`
- 直接部署：`redis-cli ping` 确认 Redis 服务已启动
- 健康检查显示 `"redis":"disconnected"` 不影响核心功能（前端、API 文档、健康检查均正常），仅聊天和记忆功能需要 Redis。

### gunicorn 未安装

`gunicorn` 在 `[prod]` 可选依赖组中，仅在 Linux 下有效（Windows 不支持）：
```bash
pip install -e ".[prod]"
```

### Windows 端口冲突

原有 `start.bat` 会杀掉端口 8000/3000 的进程。新的 `run.bat` 仅启动后端，不占用 Node.js 端口。如遇端口冲突：
```powershell
netstat -aon | findstr :8000
taskkill /F /PID <PID>
```
