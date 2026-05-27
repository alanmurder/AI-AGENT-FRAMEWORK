# AI Agent Platform 项目说明

> 本文件基于当前仓库源码、配置、文档、脚本与测试整理，供后续开发者或智能体快速理解项目。更新日期：2026-05-26。

## 1. 项目定位

这是一个面向制造业/工控场景的企业级 AI Native 通用智能体平台，核心理念是：

**Agent = Model + Harness**

项目用 LangChain/LangGraph 的 `create_agent` 作为 Agent Runtime，再叠加自研 Harness 层，补齐企业应用常见能力：记忆、Skill、MCP、RBAC、安全审批、沙箱、多智能体、专家智能体、团队协作、定时任务、后台任务和进化优化。

平台默认是私有部署、单租户模式。前端是 React 管理台，后端是 FastAPI 网关，运行数据主要落在文件系统、Redis、PostgreSQL/pgvector 和可选 Docker 沙箱中。

## 2. 技术栈

### 后端

- Python 3.11+
- FastAPI + Uvicorn/Gunicorn
- LangChain / LangGraph
- Pydantic / pydantic-settings
- Redis：短期会话记忆
- PostgreSQL + pgvector：中期记忆，当前实现以全文检索为主，向量字段预留
- APScheduler：Heartbeat 与 Cron
- MCP Python SDK：外部工具服务连接
- python-jose + bcrypt：JWT 与密码哈希
- Docker SDK：命令沙箱

### 前端

- React 18
- TypeScript 5
- Vite
- Ant Design 5
- Zustand
- Axios
- React Router

### 部署

- Dockerfile 是多阶段构建：先构建 `web/dist`，再打包 Python 运行镜像。
- `docker-compose.yml` 启动 `app`、`redis`，可通过 profile 启用 `postgres`。
- Windows/Linux 都有安装、构建、运行、部署、卸载脚本。

## 3. 六层架构

| 层级 | 名称 | 主要职责 | 关键目录 |
| --- | --- | --- | --- |
| L1 | Channel | 用户接入、前端 UI、渠道适配 | `web/`, `gateway/adapters/` |
| L2 | Gateway | REST/WebSocket、认证、路由、会话持久化、队列串行化 | `gateway/` |
| L3 | Harness | 企业级能力层：记忆、安全、Skill、MCP、上下文、多智能体等 | `harness/` |
| L4 | Agent Runtime | 创建 Agent、选择模型/工具、中间件链 | `runtime/` |
| L5 | LLM Provider | DeepSeek/OpenAI/Anthropic/Zhipu 等模型接入 | `runtime/models.py` |
| L6 | Infrastructure | Redis、PG、Docker、文件系统、日志和运行数据 | `data/`, Docker 配置 |

## 4. 目录地图

### 根目录

- `README.md`：主文档，包含完整架构、模块说明、启动和测试命令。
- `DEPLOYMENT.md`：Docker/直接部署指南。
- `docs/architecture-deep-dive.md`：按 L1 到 L6 深入解释实现细节。
- `pyproject.toml`：Python 包元数据、依赖、ruff/pytest 配置。
- `Dockerfile`, `docker-compose.yml`, `Dockerfile.sandbox`：容器构建与运行。
- `install.*`, `build.*`, `run.*`, `deploy.*`, `uninstall.*`：跨平台脚本。

### 后端核心

- `gateway/`
  - `server.py`：FastAPI 应用入口，包含大部分 REST/WebSocket 端点和全局单例初始化。
  - `router.py`：智能体路由与会话键生成。
  - `session.py`：JSONL 会话持久化，路径为 `{memory_base_dir}/sessions/{user_id}/{session_id}.jsonl`。
  - `lane.py`：基于 `asyncio.Lock` 的会话级串行队列。
  - `adapters/`：Web、钉钉等渠道适配器。

- `runtime/`
  - `agent.py`：`create_agent_for_user()`，按角色选择工具并组装 10 层中间件。
  - `config.py`：`AgentConfig`，读取 `.env`、环境变量、`config/settings.yaml` 和默认值。
  - `models.py`：创建主模型、备用模型、小模型。
  - `tools.py`：基础工具、SubAgent、后台任务和团队工具。
  - `context_schema.py`：`UserContext` 与 `UserRole`。

- `harness/`
  - `memory/`：长期/中期/短期/工作记忆及周期心跳提取。
  - `skill/`：扫描 `SKILL.md`，生成可注入 prompt 的 Skill manifest。
  - `security/`：JWT/API Key、用户存储、RBAC、L0-L4 审批。
  - `middleware/`：Agent 中间件链。
  - `context/`：上下文压缩、Pre-Flush、大工具输出替换。
  - `mcp/`：MCP 服务配置、连接、工具发现和 LangChain 包装。
  - `expert/`：专家智能体 Profile、Registry、API 存储和校验。
  - `external_agent/`：OpenAI-compatible/simple-json 外部智能体代理。
  - `multi_agent/`：SubAgent 和后台任务队列。
  - `team/`：TaskBoard、成员池和团队配置扫描。
  - `evolution/`：三 Agent 验证、GEPA 优化、自主进化。
  - `scheduler/`：Heartbeat 与 Cron。
  - `sandbox/`：Docker 命令沙箱。

### 前端

- `web/src/App.tsx`：路由入口，包含 `/login`、`/chat`、`/agents`、`/admin`。
- `web/src/pages/ChatPage.tsx`：聊天主界面。
- `web/src/pages/AgentMarket.tsx`：专家智能体广场。
- `web/src/pages/AdminPanel.tsx`：管理后台 Tab 容器。
- `web/src/pages/ExpertAgentManager.tsx`：专家智能体 CRUD 与外部智能体配置。
- `web/src/pages/MCPServerManager.tsx`：MCP 服务管理。
- `web/src/hooks/useWebSocket.ts`：WebSocket 连接、重连、专家切换和消息队列。
- `web/src/store/`：Zustand 状态，包括认证、聊天、管理台、MCP、专家智能体。
- `web/src/api/`：Axios API 封装。

### 业务配置与内容

- `agents/`
  - `equipment_monitor`：设备巡检专家，operator 角色。
  - `quality_inspector`：质量检验专家，operator 角色。
  - `production_scheduler`：生产调度专家，manager 角色。
  - `teams/production_team.yaml`：生产协调组，包含以上三个专家。
- `skills/builtin/`：7 个内置 Skill。
- `skills/plugins/`：`industrial` 与 `enterprise` 两个 Plugin 定义。
- `config/settings.yaml`：主配置。
- `config/rbac.yaml`：角色、工具、MCP 工具和 Skill 访问等级。

## 5. 运行链路

### 启动链路

`python -m gateway.server` 会执行 `gateway/server.py`：

1. 创建 `AgentConfig`，若未设置 `project_root`，默认用仓库根目录。
2. 初始化全局单例：
   - `MemoryManager`
   - `SkillManager`
   - `TokenManager`
   - `UserStore`
   - `ApprovalChecker`
   - `AgentRegistry`
   - `SessionPersistence`
   - `HeartbeatScheduler`
   - `CronScheduler`
   - `BackgroundTaskManager`
   - `MCPManager`
   - `SandboxRunner`
3. FastAPI lifespan 启动时：
   - 初始化 MCP 连接
   - 尝试连接 PostgreSQL 中期记忆，失败会降级
   - 启动 Heartbeat/Cron
   - 启动后台任务 worker
4. 关闭时停止调度器、后台 worker、PG 连接和 MCP 连接。

### HTTP 对话

`POST /api/chat` 是同步对话：

1. 从 Authorization 中取 Bearer JWT 或 API Key。
2. 构造/更新 `UserContext`。
3. 使用 `LaneQueue` 对用户会话串行化。
4. 初始化用户工作区。
5. 调用 `create_agent_for_user()` 创建 Agent。
6. `agent.invoke()` 执行。
7. 将消息写入 JSONL 会话文件。

### WebSocket 对话

`/ws/chat` 是流式对话：

1. 客户端连接后第一帧必须发送 `{token/api_key, user_id, agent_id}`。
2. 后端认证并创建新的 `session_id`。
3. 根据 `agent_id` 分流：
   - 空或未注册：通用智能体。
   - 已注册且内部类型：加载专家 Profile 和 SOUL.md，创建配置型专家。
   - 已注册且外部类型：创建 `AgentProxyHandler`，转发到外部 HTTP/SSE 服务。
4. 向前端发送 `session_start`。
5. 后续用户消息进入流式循环：
   - 内部 Agent：`agent.stream(..., stream_mode="updates")`。
   - 外部 Agent：通过 `external_proxy.stream()` 转发。
6. 前端按事件处理：
   - `chunk`：累积流式文本
   - `tool_call`：展示工具调用卡片
   - `done`：落入消息列表
   - `error`：认证失败时登出或展示错误

## 6. Agent 创建与工具分层

`runtime/agent.py` 的 `create_agent_for_user()` 是通用 Agent 工厂。

### 角色与工具

- `BASE_TOOLS`
  - `file_read`
  - `file_write`
  - `command_exec`
  - `web_search`
  - `query_database`
  - `send_notification`
  - `memory_manage`
- `ALL_TOOLS`
  - `BASE_TOOLS`
  - `spawn_subagent`
  - `submit_background_task`
- `CAPTAIN_TOOLS`
  - `ALL_TOOLS`
  - `delegate_task`
  - `read_task_board`
  - `collect_results`
- `MEMBER_TOOLS`
  - `BASE_TOOLS`
  - `read_task_board`

当前通用 Agent 逻辑：

- admin/manager 且 `team_enabled=True`：使用 `CAPTAIN_TOOLS`。
- admin/manager：使用 `ALL_TOOLS`。
- operator/viewer：使用 `BASE_TOOLS`。
- MCP 工具按 `config/rbac.yaml` 的 `mcp_tools` 再追加。

注意：初始工具列表可能较宽，真正的权限过滤还会经过 `ToolFilterMiddleware`，以 RBAC 为准。

## 7. 中间件链

通用 Agent 和内部专家 Agent 使用类似的中间件顺序：

1. `AuthInjectionMiddleware`：注入用户上下文。
2. `MemoryInjectionMiddleware`：注入长期记忆、中期检索结果、Skill manifest、Plugin manifest。
3. `PreFlushMiddleware`：上下文接近阈值时提示模型保存关键信息。
4. LangChain `SummarizationMiddleware`：用 mini model 压缩历史。
5. LangChain `ContextEditingMiddleware`：大工具输出替换为 artifact 引用。
6. `ToolFilterMiddleware`：按角色过滤静态工具和 MCP 工具。
7. `SecurityCheckMiddleware`：对 `command_exec`、`file_write`、`query_database` 走 L0-L4 审批链。
8. `SandboxMiddleware`：已批准的 `command_exec` 优先进 Docker 沙箱。
9. `OutputValidationMiddleware`：结构化输出校验与最多 3 次反馈重试。
10. `MemoryArchiveMiddleware`：会话后归档摘要到每日日志和中期记忆，并清理短期 Redis。

## 8. 记忆系统

### 四层记忆

- 长期记忆：文件系统，`SOUL.md`、`USER.md`、`MEMORY.md` 和 daily log。
- 中期记忆：PostgreSQL + pgvector，表为 `mid_term_memory`，当前主要使用 PostgreSQL 全文检索。
- 短期记忆：Redis，key 形如 `agent:{user_id}:{session_id}:messages/state/...`。
- 工作记忆：LLM 当前上下文。

### 当前代码里的实际策略

- `MemoryArchiveMiddleware` 在每次 Agent 完成后：
  - 构造会话摘要。
  - 写入每日日志。
  - 写入 PG 中期记忆，类型为 `session_summary`。
  - 清理 Redis 短期会话。
- `MemoryHeartbeatTask` 由 Heartbeat 周期触发：
  - 扫描最近活跃用户的 PG 摘要。
  - 批量调用 `MemoryEvolution` 抽取偏好和事实。
  - 写回长期记忆文件。
  - 将事实也写入 PG。
  - 若 `auto_evolve_enabled=True`，会检测是否需要新 Skill。

这意味着“记忆提取”不是每条对话都立刻调用 LLM，而是偏向周期批处理。

## 9. Skill 与 Plugin

Skill 是 Markdown 指令文件，位置主要在 `skills/builtin/*/SKILL.md`，使用 YAML frontmatter 描述：

- `name`
- `version`
- `category`
- `access`
- `description`
- 可选运行字段：`runtime`、`dependencies`、`timeout`、`network`、`max_memory`

内置 Skill：

- `file_manager`：文件读写搜索管理，production。
- `knowledge_search`：知识检索，report。
- `report_generator`：报告生成，report。
- `schedule_manager`：计划和日程，enterprise。
- `notification`：通知，production。
- `database_query`：数据库查询，production。
- `data_analysis`：数据分析，enterprise。

Skill 访问等级：

| 等级 | 可见性 |
| --- | --- |
| `report` | viewer+ |
| `production` | operator+ |
| `enterprise` | manager+ |
| `all` | admin only |

Plugin 由 `skills/plugins/*/PLUGIN.md` 定义，用于把一组 Skill 聚合成更高层能力。目前有：

- `industrial`
- `enterprise`

## 10. 专家智能体、团队与外部智能体

### 配置型专家

文件型专家放在 `agents/{name}/`，由 `profile.yaml` 和 `SOUL.md` 组成。

当前内置专家：

- `equipment_monitor`：设备巡检专家，operator。
- `quality_inspector`：质量检验专家，operator。
- `production_scheduler`：生产调度专家，manager，可做生产排程和资源协调。

`AgentRegistry` 启动时会扫描：

- `agents/**/profile.yaml`
- `data/agents/*.json`

API 创建的专家会覆盖文件型专家同名配置。

### 外部智能体

外部智能体也是 `AgentProfile`，但 `type="external"` 且带 `endpoint`。支持协议：

- `openai-chat`
- `simple-json`

WebSocket 对话时外部智能体不会进入本地 LangChain Agent，而是由 `AgentProxyHandler` 转发到外部 HTTP/SSE 服务。

### 团队

团队定义在 `agents/teams/*.yaml`。当前 `production_team` 包含三个生产相关专家。

admin/manager 在 `team_enabled=True` 时会被视为队长，系统 prompt 会注入团队成员信息，并可使用：

- `delegate_task`
- `read_task_board`
- `collect_results`

`TaskBoardManager` 当前是内存态任务板，重启后不会持久化。

## 11. MCP 集成

MCP 配置持久化在 `data/mcp_servers.json`，由 `MCPServerStore` 管理。

支持传输：

- `stdio`
- `sse`

启动时 `MCPManager.initialize()` 会连接所有 enabled 服务端并发现工具。MCP 工具会包装成 LangChain tool，名称格式：

- 函数名：`mcp__{server}__{tool}`
- RBAC/专家配置名：`{server}:{tool}`

MCP 权限由 `config/rbac.yaml` 的 `mcp_tools` 控制：

- `admin`: `["*"]`
- 其他角色按显式列表或 `server:*` 通配。

## 12. 安全模型

### 认证

- JWT：`TokenManager`，默认 HS256，默认有效期 480 分钟。
- API Key：内存态 `APIKeyManager`。
- 用户存储：`data/users.json`，首次启动种子用户：
  - `admin/admin123`
  - `manager/manager123`
  - `operator/operator123`
  - `viewer/viewer123`

生产环境必须更换默认账号和 `AI_AGENT_JWT_SECRET`。

### RBAC

角色层级：

`admin > manager > operator > viewer`

关键权限来自 `config/rbac.yaml`：

- admin：全部基础工具、全部 MCP、Skill `all`。
- manager：无 `command_exec`，可管理较高等级 Skill。
- operator：只读/查询/通知/记忆类能力，Skill 到 `production`。
- viewer：最小只读能力，Skill 到 `report`。

### L0-L4 审批

危险工具会走 `SecurityCheckMiddleware`：

- `command_exec`
- `file_write`
- `query_database`

审批层级：

- L0：黑名单字符串，直接阻断。
- L1：危险正则模式，直接阻断。
- L2：白名单分类，安全命令/SELECT/非系统路径等放行。
- L3：mini model 安全审查。
- L4：人工审批，生成 `approval_id` 并阻断等待。

### 沙箱

`SandboxMiddleware` 只处理 `command_exec`。若 Docker 镜像可用，命令在容器中执行；否则回退到宿主机 `subprocess`。沙箱默认禁网、内存限制 256m、超时 30 秒。

## 13. 配置与数据

### 配置文件

- `.env`：本地密钥和运行参数，已被 `.gitignore` 忽略。
- `.env.example`：环境变量模板。
- `config/settings.yaml`：分组 YAML 配置。
- `config/rbac.yaml`：角色权限配置。

### 配置优先级

`AgentConfig` 的 pydantic-settings 顺序是：

1. 初始化参数
2. OS 环境变量
3. `.env`
4. `config/settings.yaml`
5. file secrets

### 重要注意

当前代码中的 `AgentConfig` 字段是扁平命名，例如 `llm_primary_provider`、`pg_host`、`sandbox_enabled`。`config/settings.yaml` 使用分组结构，例如 `agent.model.primary.provider`。修改配置后建议用以下方式确认实际读取值：

```bash
python -c "from runtime.config import AgentConfig; print(AgentConfig().model_dump())"
```

同理，`.env.example` 中部分 PostgreSQL/Sandbox 变量未使用 `AI_AGENT_` 前缀，而 `AgentConfig` 设置了 `env_prefix='AI_AGENT_'`。如果配置未生效，优先检查变量名。

### 数据目录

`data/` 是运行态数据目录，已被 `.gitignore` 忽略，常见内容：

- `data/users.json`
- `data/logs/*.log`
- `data/workspace/users/{user_id}/...`
- `data/mcp_servers.json`
- `data/agents/*.json`
- `data/sessions/...`

不要把 `.env`、`data/`、日志、真实用户记忆或 API Key 提交进仓库。

## 14. 常用命令

### 后端开发

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python -m gateway.server
```

Linux/macOS：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m gateway.server
```

### 前端开发

```bash
cd web
npm install
npm run dev
```

Vite 默认在 `http://localhost:3000`，代理：

- `/api` -> `http://localhost:8000`
- `/ws` -> `ws://localhost:8000`

### 构建

```bash
cd web
npm ci
npm run build
```

或用根目录脚本：

```bash
build.bat
bash build.sh
```

### 生产/一体化运行

```bash
run.bat
bash run.sh
```

脚本会要求 `web/dist/index.html` 已存在，并设置 `AI_AGENT_SERVE_STATIC=true`，由 FastAPI 挂载前端静态文件。

### Docker 部署

```bash
bash deploy.sh --prod
deploy.bat --prod
```

可选启动 PostgreSQL：

```bash
bash deploy.sh --prod --pg
```

### 测试

```bash
pytest tests/ -v
pytest tests/unit/test_security.py -v
pytest tests/unit/test_expert.py -v
pytest tests/unit/test_team.py -v
```

前端：

```bash
cd web
npm run test
npm run build
```

## 15. 测试覆盖概览

`tests/unit/` 覆盖了主要 Harness 与 Gateway 基础模块：

- 认证与 RBAC
- L0-L4 审批
- 记忆系统和中期记忆
- 上下文压缩与大输出替换
- 会话 JSONL 持久化
- LaneQueue
- 沙箱
- Skill/Plugin
- SubAgent/BackgroundTask
- Scheduler
- Three-Agent/GEPA/AutoEvolve
- Expert Agent
- Team
- DingTalk 适配器

`tests/conftest.py` 里 `project_root` fixture 当前指向旧路径，若新增依赖项目根目录的测试，需要优先修正为当前仓库路径或用 `Path.cwd()`。

## 16. 开发注意事项

- 先看 `git status --short`。当前工作区可能已有用户改动，不要无故回滚或格式化无关文件。
- `.env` 存在但被忽略，可能包含真实密钥；不要读取、打印或提交它。
- `data/` 是运行态目录，里面有用户、日志、记忆等内容，默认不应纳入代码变更。
- `README.md` 和 `docs/architecture-deep-dive.md` 信息很全，但部分细节可能比当前代码略旧；实现判断以源码为准。
- `pyproject.toml` 当前可用 extras 包括 `llm-openai`、`llm-anthropic`、`llm-zhipu`、`pg`、`sandbox`、`dev`、`prod`。README 中提到的某些安装 extras 需要和 `pyproject.toml` 对照。
- `runtime/agent.py` 会先给 admin/manager 选择 SubAgent、后台任务和团队工具，但 `ToolFilterMiddleware` 最终按 `config/rbac.yaml` 过滤。当前 RBAC 的 `tools` 列表主要是 7 个基础工具；如果要真正开放 `spawn_subagent`、`submit_background_task`、`delegate_task` 等能力，需要同步更新 RBAC。
- `harness/expert/agent_factory.py` 的 `create_expert_agent_for_user()` 内部引用 `AgentRegistry`，但当前文件未导入它；Gateway WebSocket 路径实际直接使用 `create_expert_agent()`。如果后续启用 `create_expert_agent_for_user()`，先检查这一点。
- `TaskBoardManager`、`BackgroundTaskManager`、`APIKeyManager` 目前主要是内存态，重启后状态不会保留。
- `MCPManager` 会在启动时连接 enabled 服务端；本地开发时若 MCP 配置不可用，会记录 warning，但不应影响核心服务启动。
- PostgreSQL 中期记忆连接失败会降级为无中期记忆；Redis 不可用会影响短期记忆相关能力。
- 命令沙箱 Docker 不可用时会回退宿主机执行，这一点对安全非常关键，生产环境应确认沙箱配置。

## 17. 适合优先阅读的文件

如果只想快速建立心智模型，按这个顺序读：

1. `README.md`
2. `docs/architecture-deep-dive.md`
3. `gateway/server.py`
4. `runtime/agent.py`
5. `runtime/tools.py`
6. `runtime/config.py`
7. `harness/middleware/memory_injection.py`
8. `harness/middleware/security_check.py`
9. `harness/memory/manager.py`
10. `harness/expert/registry.py`
11. `harness/mcp/manager.py`
12. `web/src/App.tsx`
13. `web/src/hooks/useWebSocket.ts`


你在写总结或者设计计划类的文档时，请保持用中文书写。