# AI Agent Platform — 企业级 AI Native 通用智能体平台

基于 Harness 分层架构的企业级 AI Native 通用智能体平台，面向制造业/工控领域。私有部署，单租户模式。

> 📖 **深入理解代码实现？** 阅读 [架构深度解析](architecture-deep-dive.md) — 按 L1→L6 层次组织，包含每个模块的文件清单、核心流程和代码级实现细节。

## 目录

- [核心理念](#核心理念)
- [六层架构](#六层架构)
- [架构全景](#架构全景)
- [功能模块详细设计](#功能模块详细设计)
  - [1. 记忆系统 (Memory)](#1-记忆系统-memory)
  - [2. Skill 系统](#2-skill-系统)
  - [3. MCP 集成](#3-mcp-集成)
  - [4. 安全系统 (Security)](#4-安全系统-security)
  - [5. 上下文管理 (Context)](#5-上下文管理-context)
  - [6. Middleware Chain](#6-middleware-chain)
  - [7. 多智能体协作 (Multi-Agent)](#7-多智能体协作-multi-agent)
  - [8. 进化系统 (Evolution)](#8-进化系统-evolution)
  - [9. 专家智能体 (Expert Agent)](#9-专家智能体-expert-agent)
  - [10. Agent Teams](#10-agent-teams)
  - [11. 定时调度 (Scheduler)](#11-定时调度-scheduler)
  - [12. Gateway (L2)](#12-gateway-l2)
- [安全机制设计详解](#安全机制设计详解)
  - [安全设计哲学](#安全设计哲学)
  - [认证安全](#认证安全)
  - [授权安全](#授权安全)
  - [审批安全](#审批安全)
  - [执行安全](#执行安全)
  - [记忆安全](#记忆安全)
- [用户管理](#用户管理)
  - [用户存储 (UserStore)](#用户存储-userstore)
  - [登录流程](#登录流程)
  - [认证机制](#认证机制)
  - [角色与权限系统](#角色与权限系统)
  - [用户注册](#用户注册)
- [配置管理](#配置管理)
  - [配置架构](#配置架构)
  - [配置分组详解](#配置分组详解)
  - [.env 文件](#env-文件)
  - [config/settings.yaml](#configsettingsyaml)
  - [配置优先级实战](#配置优先级实战)
- [项目结构](#项目结构)
- [快速启动](#快速启动)
- [运行测试](#运行测试)
- [技术栈](#技术栈)
- [实施进度](#实施进度)
- [License](#license)

## 核心理念

**Agent = Model + Harness**。LangChain v1 的 `create_agent` + `AgentMiddleware` 提供 Model + 基础 Harness，本平台叠加企业级 Harness 层，实现安全、记忆、进化、多智能体协作等能力。

## 六层架构

| 层级 | 名称 | 职责 | 关键组件 |
|------|------|------|----------|
| L1 | Channel | 用户接入 | Web UI + 钉钉/飞书/企微(预留) |
| L2 | Gateway | 路由调度 | FastAPI + WebSocket + Session 持久化 + Lane Queue |
| L3 | Harness | 企业级能力 | Memory / Skill / MCP / Security / Evolution / MultiAgent / Expert / Team / Sandbox |
| L4 | Agent Runtime | Agent 循环 | LangChain `create_agent` + 10层 Middleware Chain |
| L5 | LLM Provider | 模型接入 | DeepSeek / GPT-4o / Claude / GLM-4 / Qwen |
| L6 | Infrastructure | 存储运维 | PostgreSQL+pgvector / Redis / Docker Sandbox |

## 架构全景

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CHANNEL (L1)                                      │
│    Web UI ─── 钉钉 ─── 飞书(预留) ─── 企微(预留)                     │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────┴────────────────────────────────────┐
│                    GATEWAY (L2)                                      │
│    FastAPI REST + WebSocket + Lane Queue + Session 持久化            │
│    ChannelAdapter(统一适配) + GatewayRouter(智能体路由)              │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────┴────────────────────────────────────┐
│                    HARNESS (L3) — 企业级能力层                        │
│                                                                      │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │
│  │  Memory      │ │  Skill       │ │  MCP         │ │  Security    │ │
│  │  四层记忆     │ │  指令+Plugin │ │  外部工具集成 │ │  认证+审批    │ │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │
│  │  Context     │ │  MultiAgent  │ │  Evolution   │ │  Expert      │ │
│  │  压缩+冲刷   │ │  Sub+Bg任务  │ │  三Agent+GEPA│ │  Registry    │ │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                   │
│  │  Team        │ │  Sandbox     │ │  Scheduler   │                   │
│  │  TaskBoard   │ │  Docker隔离  │ │  心跳+定时    │                   │
│  └──────────────┘ └──────────────┘ └──────────────┘                   │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────┴────────────────────────────────────┐
│                    AGENT RUNTIME (L4)                                 │
│    create_agent_for_user ─── 10层 Middleware Chain ─── 工具集        │
│    BASE_TOOLS(7) / ALL_TOOLS(8) / CAPTAIN_TOOLS(11) / MEMBER(8)    │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────┴────────────────────────────────────┐
│                    LLM PROVIDER (L5)                                  │
│    Primary ─── Fallback(多模型容灾) ─── Mini(压缩/评估/审批)          │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────┴────────────────────────────────────┐
│                    INFRASTRUCTURE (L6)                                │
│    PostgreSQL+pgvector ─── Redis ─── Docker ─── File System          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 功能模块详细设计

### 1. 记忆系统 (Memory)

四层记忆架构，确保 Agent 在不同时间维度上保留和利用信息：

| 层级 | 存储 | 生命周期 | 内容 |
|------|------|----------|------|
| 长期 (L1) | 文件系统 (SOUL.md / USER.md / MEMORY.md) | 永久 | 人格、偏好、重要事实 |
| 中期 (L2) | PostgreSQL + pgvector | 30天保留 | 会话摘要、日志、事实向量检索 |
| 短期 (L3) | Redis | 会话级 (TTL=3600s) | 当前对话消息、会话状态 |
| 工作 (L4) | LLM Context | 单次交互 | 当前 prompt + 上下文窗口 |

**关键机制**：
- **Pre-Flush**：上下文接近阈值时，先注入"保存关键信息"指令，再压缩，避免重要信息丢失
- **Memory Evolution**：Mini Model 从对话中自动提取偏好和事实，写入长期记忆
- **Memory Archive**：每次 Agent 交互结束后，自动归档会话摘要到 PG 中期记忆
- **专家记忆隔离**：每个专家 Agent 有独立记忆空间 (`workspace/users/{user_id}/agents/{expert_id}/`)

### 2. Skill 系统

Skill 是 Markdown 指令文档 (SKILL.md)，定义 Agent 在特定场景下的行为规范。不绑定专属工具，使用 7 个通用基础工具。

**Skill 结构**：
```markdown
---
name: skill_name
version: 1.0.0
category: file_manager
access: all
description: Skill 功能描述
tags: [tag1, tag2]
---
## Skill 指令内容
当用户需要...时，按以下步骤执行...
```

**Plugin 机制**：将相关 Skill 分组为 Plugin，实现渐进式能力披露。Plugin 由 `PLUGIN.md` 定义：
```markdown
---
name: industrial
description: 工业生产与制造相关 Skill
---
# Plugin: Industrial
## Skills
  - equipment_monitor
  - process_control
  - quality_inspection
```

**Skill 访问分级**：
| 级别 | 值 | 可见角色 |
|------|-----|----------|
| report | 0 | 所有角色 (viewer+) |
| production | 1 | operator+ |
| enterprise | 2 | manager+ |
| all | 3 | admin only |

角色与 Skill 访问级别的映射由 `config/rbac.yaml` 中的 `skill_access` 字段控制，通过 `SkillAccess.max_for_role()` 方法在运行时过滤。

**内置 Skill** (7个)：
| Skill | 类别 | 功能 | 访问级别 |
|-------|------|------|----------|
| file_manager | FILE_MANAGER | 文件读写搜索管理 | production |
| knowledge_search | KNOWLEDGE_SEARCH | 知识检索与问答 | report |
| report_generator | REPORT_GENERATOR | 报告模板生成 | report |
| schedule_manager | SCHEDULE_MANAGER | 日程安排管理 | production |
| notification | NOTIFICATION | 多渠道消息通知 | production |
| database_query | DATABASE_QUERY | 数据库查询分析 | production |
| data_analysis | DATA_ANALYSIS | 数据统计分析 | enterprise |

### 3. MCP 集成

MCP (Model Context Protocol) 模块实现对外部 MCP 服务的连接、工具发现和角色权限控制。

**核心组件**：
| 类 | 文件 | 功能 |
|----|------|------|
| `MCPManager` | `harness/mcp/manager.py` | 编排所有 MCP 连接，角色过滤，包装为 LangChain 工具 |
| `MCPClient` | `harness/mcp/client.py` | 单个 MCP 服务端连接，支持 stdio 和 SSE 两种传输 |
| `MCPServerStore` | `harness/mcp/config.py` | JSON 持久化存储 (`data/mcp_servers.json`) |
| `MCPServerConfig` | `harness/mcp/types.py` | 服务端配置数据类 |
| `MCPToolInfo` | `harness/mcp/types.py` | MCP 工具信息数据类 |

**连接流程**：
```
Gateway lifespan.startup()
  → MCPManager.initialize()
    → 遍历 data/mcp_servers.json 中所有 enabled 服务端
      → MCPClient.connect() → 建立 stdio/SSE 连接
        → list_tools() → 发现工具
          → 包装为 LangChain @tool 函数 (命名: mcp__{server}__{tool})
            → 注册到 MCPManager._tools
```

**角色权限控制**：
- MCP 工具在 `config/rbac.yaml` 中为每个角色配置允许的 `mcp_tools` 列表
- 格式：`"server:tool"` 或 `"server:*"` 通配符，admin 使用 `"*"` 获取全部
- `ToolFilterMiddleware` 在每次模型调用时按角色过滤 MCP 工具
- 权限越级校验：创建专家智能体时，所选 MCP 工具不能超过角色允许的范围

**管理 API（仅 admin）**：
```
GET    /api/mcp/servers              — 列出所有 MCP 服务端
POST   /api/mcp/servers              — 创建 MCP 服务端配置
PUT    /api/mcp/servers/{name}       — 更新配置
DELETE /api/mcp/servers/{name}       — 删除配置
POST   /api/mcp/servers/{name}/connect    — 连接/重连
POST   /api/mcp/servers/{name}/disconnect — 断开
GET    /api/mcp/tools?role=           — 列出已发现工具（支持角色过滤）
```

**使用 mcp 包**：通过 `pip install mcp>=1.0.0` 安装，提供 `ClientSession`、`stdio_client`、`sse_client` 等底层 API。

### 4. 安全系统 (Security)

安全系统是平台的核心差异化能力，覆盖认证、授权、审批、沙箱四个维度。

#### 4.1 认证 (Authentication)

**双认证机制**：
- **JWT Token**：基于 HS256 算法，8小时过期，bcrypt 密码哈希，payload 包含 user_id / role / tenant_id
- **API Key**：简单 Key-UserContext 映射，支持注册、验证、撤销

#### 4.2 授权 (RBAC)

基于 `config/rbac.yaml` 的角色权限控制：

| 角色 | 可用工具 | MCP 工具 | Skill 访问 | 审批上限 |
|------|----------|----------|------------|----------|
| admin | 全部7工具 + spawn_subagent + 团队工具 | 全部 (`"*"`) | all | L3 |
| manager | 6工具(无command_exec) + spawn_subagent + 团队工具 | 按配置 (如 filesystem:read) | enterprise | L3 |
| operator | 5工具(只读) + send_notification | 无 | production | L3 |
| viewer | 4工具(最小集) | 无 | report | L2 |

**工具分层**：
- `BASE_TOOLS`(7)：file_read, file_write, command_exec, web_search, query_database, send_notification, memory_manage
- `ALL_TOOLS`(8)：BASE_TOOLS + spawn_subagent (admin/manager)
- `CAPTAIN_TOOLS`(11)：ALL_TOOLS + delegate_task, read_task_board, collect_results (队长)
- `MEMBER_TOOLS`(8)：BASE_TOOLS + read_task_board (队员)

#### 4.3 五级审批系统 (Approval)

这是平台最重要的安全防线，确保 Agent 的每一次工具调用都经过严格安全审查：

| 级别 | 机制 | 行为 | 适用场景 |
|------|------|------|----------|
| **L0** | 字符串黑名单匹配 | **直接阻断** | rm -rf, DROP TABLE, sudo, eval(), exec(), __import__, os.system 等 12 个危险关键词 |
| **L1** | 正则模式匹配 | **直接阻断** | 命令替换 $()、反引号、管道链 ||/&&、命令分隔符 ;、重定向到 /dev、wget/curl 写系统目录 等 8 个危险模式 |
| **L2** | 白名单分类 | 安全命令放行，非白名单阻断 | command_exec 白名单(ls/cat/grep/python/git 等 23 个)、query_database 仅允许 SELECT、file_write 禁止写系统目录(/etc/bin/usr 等) |
| **L3** | LLM 安全审查 | Mini Model 评审，返回 SAFE/UNSAFE/UNCERTAIN | L2 未放行且用户角色≥L3 时触发。SAFE→放行，UNSAFE→阻断，UNCERTAIN→升级到L4 |
| **L4** | Human-in-the-loop | **阻断等待人工审批** | L3 不确定时升级，或用户角色仅为L2(viewer)时L2阻断不可升级。生成唯一 approval_id，人工通过 API approve/reject |

**审批链流程**：
```
L0 黑名单匹配 ──匹配→ 阻断
                ──未匹配→ L1 正则匹配 ──匹配→ 阻断
                              ──未匹配→ L2 白名单 ──在白名单→ 放行
                                            ──不在白名单→ 用户角色=L2(viewer)? → 阻断(不可升级)
                                                          → 用户角色≥L3? → L3 LLM审查 ──SAFE→ 放行
                                                                               ──UNSAFE→ 阻断
                                                                               ──UNCERTAIN→ L4 人工审批 → 阻断等待
```

**设计原则**：
- L0/L1 是**绝对防线**，无论用户角色都强制执行，无法绕过
- L2 是**分级门槛**，viewer 角色无法升级，admin/manager/operator 可以升级到 L3
- L3 是**智能审查**，用小模型做安全判断，降低人工审批负担
- L4 是**最终兜底**，任何不确定的操作都必须由人工确认

#### 4.4 沙箱执行 (Sandbox)

- **Docker 容器隔离**：command_exec 在独立容器中执行，限制内存(256m)、禁止网络(默认)、超时控制(30s)
- **容器生命周期**：创建 → 执行 → 获取输出 → 销毁，不留痕迹
- **回退机制**：Docker 不可用时回退到宿主机 subprocess 执行
- **安全镜像**：内置 python:3.11-slim 基础镜像，预装 bash/curl/jq/git/numpy/pandas

### 5. 上下文管理 (Context)

解决 LLM 上下文窗口有限的核心问题：

| 参数 | 值 | 说明 |
|------|-----|------|
| max_context_tokens | 64,000 | 最大上下文窗口 |
| compression_threshold | 4,000 tokens | 触发压缩的最低消息数 |
| flush_threshold | 60,000 tokens | 触发 Pre-Flush 的 token 数 |
| placeholder_threshold | 2,000 tokens | 大工具输出替换为文件引用 |
| keep_recent_messages | 20 | 压缩时保留最近消息数 |

**三种压缩策略**：
- **Summarization**：Mini Model 生成历史对话摘要，替换原始消息
- **Context Editing**：删除低价值消息，保留最近和高权重内容
- **Placeholder**：超过 2000 token 的工具输出替换为文件引用，仅保留最近 3 个完整结果

### 6. Middleware Chain

10 层 Middleware 构成 Agent 的完整生命周期管线：

```
请求进入
  │
  ▼
AuthInjectionMiddleware ──── 验证用户身份，初始化工作空间 (Before Agent)
  │
  ▼
MemoryInjectionMiddleware ── 注入记忆+Skill+Plugin manifest (Before Model)
  │
  ▼
SummarizationMiddleware ──── 历史对话压缩 (Before Model)
  │
  ▼
ContextEditingMiddleware ─── 删除低价值消息 (Before Model)
  │
  ▼
PreFlushMiddleware ────────── 冲刷前保存关键信息 (Before Model)
  │
  ▼
ToolFilterMiddleware ──────── 按角色过滤可用工具 (Wrap Model)
  │
  ▼
SecurityCheckMiddleware ──── L0-L4 审批链 (Wrap Tool)
  │
  ▼
SandboxMiddleware ────────── 命令路由到沙箱 (Wrap Tool)
  │
  ▼
OutputValidationMiddleware ── Pydantic 结构化输出验证 (After Model)
  │
  ▼
MemoryArchiveMiddleware ──── 归档会话+触发进化 (After Agent)
  │
  ▼
响应输出
```

### 7. 多智能体协作 (Multi-Agent)

#### 7.1 SubAgent 系统

主 Agent 可通过 `spawn_subagent` 工具委派子任务给临时子 Agent：

- **阻塞式执行**：父 Agent 等待子 Agent 完成，获取结果后继续
- **工具过滤**：子 Agent 不包含 `spawn_subagent`，防止递归
- **深度限制**：子 Agent 不再产生子 Agent，最多一层嵌套
- **独立上下文**：子 Agent 有自己的 system_prompt 和 UserContext

**角色工具集**：
| SubAgent 角色 | 可用工具 |
|---------------|----------|
| PLANNER / EVALUATOR | READONLY_TOOLS (file_read, web_search, query_database) |
| GENERATOR / WORKER | FULL_TOOLS (全部基础工具) |

#### 7.2 Background Task 系统

异步任务队列，支持非阻塞的 Agent 任务执行：

- **提交**：submit() 创建后台任务，立即返回 task_id
- **执行**：Worker 循环异步处理，最大并发数可配置
- **状态查询**：get_status() 检查任务进度 (pending/running/completed/failed)
- **生命周期**：随 Gateway lifespan 启动/停止

### 8. 进化系统 (Evolution)

#### 8.1 三 Agent 验证 (Three-Agent Verification)

Skill 创建/修改的质量保障流程：Planner → Generator → Evaluator 循环迭代：

1. **Planner**：分析需求，制定 Skill 编写计划
2. **Generator**：按计划编写 Skill 内容
3. **Evaluator**：评估 Skill 质量 (清晰度、完整性、可操作性)，评分 ≥7 通过
4. 未通过时迭代修改，最多 3 轮

仅用于 Skill 创建和进化，不介入核心执行路径。

#### 8.2 GEPA 进化优化 (Evolutionary Prompt Optimization)

对已有 Skill 进行进化搜索优化：

- **评估**：用 Mini Model 对 Skill 的 Clarity/Completeness/Actionability 三维度评分
- **变异**：生成多个候选变体
- **筛选**：Pareto 优化，保留综合评分最高的变体
- **部署条件**：新变体需比原版提升 >0.5 分才部署

#### 8.3 自主进化 (AutoEvolver)

- **检测需求**：分析对话摘要，识别 Skill 覆盖空白
- **自动创建**：通过三 Agent 验证自动创建新 Skill
- **触发时机**：MemoryArchiveMiddleware 在 `auto_evolve_enabled` 时自动触发检测

### 9. 专家智能体 (Expert Agent)

专家 Agent 是独立人格的专用 Agent，有自己的 SOUL.md 人格文件、Skill 列表、MCP 工具列表和角色权限配置。

#### 双入口设计

专家智能体支持两种调用方式：

1. **智能体广场直路由**：通过 Gateway API `/api/agents/{name}/chat` 直接调用
2. **SubAgent 派**：主 Agent 通过 `spawn_subagent(expert_id="equipment_monitor")` 调用

**路由机制**：`GatewayRouter` 检查 `user_ctx.agent_id`，匹配到专家 Profile 时路由到对应专家 Agent。

#### 专家 Profile

专家 Profile 支持两个来源：

| 来源 | 存储位置 | 可修改 | 说明 |
|------|---------|--------|------|
| 文件系统 | `agents/{name}/profile.yaml` | 手动编辑 YAML | 预置专家，只读 |
| API 创建 | `data/agents/{name}.json` | 通过 API CRUD | 运行时创建，admin 权限 |

**完整配置字段（API 来源）**：
```json
{
  "name": "equipment_analyzer",
  "display_name": "设备分析专家",
  "description": "使用 MCP 数据库工具分析设备数据",
  "role": "manager",
  "soul_file": "data/agents/equipment_analyzer/SOUL.md",
  "skills": ["data_analysis", "report_generator"],
  "mcp_tools": ["filesystem:read", "database:query"],
  "model_preference": "primary",
  "max_context_tokens": 32000,
  "source": "api",
  "created_by": "admin",
  "created_at": "2026-05-24T12:00:00Z",
  "updated_at": "2026-05-24T12:00:00Z"
}
```

**权限控制**：
- `skills` 列表不能超过角色 `skill_access` 级别允许的 Skill
- `mcp_tools` 列表不能超过角色在 `rbac.yaml` 中允许的 MCP 工具
- 提交时由 `ExpertAgentValidator` 校验，自动拒绝越权选择
- 专家智能体运行时使用其配置的角色（而非调用用户的角色）进行工具过滤

#### 管理 API（仅 admin）

```
GET    /api/agents/manage               — 列出所有智能体（CRUD + 文件系统）
POST   /api/agents/manage               — 创建新专家智能体
GET    /api/agents/manage/{name}        — 获取智能体详情（含 SOUL 内容）
PUT    /api/agents/manage/{name}        — 更新专家智能体（仅 API 来源）
DELETE /api/agents/manage/{name}        — 删除专家智能体（仅 API 来源）
```

**创建表单辅助 API**：
```
GET    /api/roles/{role}/skills         — 列出该角色可用的 Skill
GET    /api/roles/{role}/mcp-tools      — 列出该角色可用的 MCP 工具
```

#### 内置专家 (3个)

| 专家 | 角色 | Skill Plugin | 功能 |
|------|------|-------------|------|
| equipment_monitor | operator | industrial | 设备巡检、故障诊断 |
| quality_inspector | operator | industrial | 质量检验、标准合规 |
| production_scheduler | manager | industrial | 生产调度、瓶颈分析 |

#### Agent Registry

- `scan_profiles()`：扫描 `agents/` 目录加载 YAML Profile（文件来源，只读）
- `scan_api_profiles()`：扫描 `data/agents/` 加载 JSON Profile（API 来源，可读写）
- `register()` / `unregister()` / `get()` / `list_profiles()`：注册/注销/查询/列表
- `load_soul_content()`：读取 SOUL.md 人格内容（自动判断来源）
- `generate_manifest()`：生成专家广场展示清单

#### ExpertAgentStore

- JSON 文件 CRUD 存储 (`data/agents/{name}.json`)
- SOUL.md 内容存储为 `data/agents/{name}/SOUL.md`
- 支持创建、读取、更新、删除操作

#### ExpertAgentValidator

- `validate_skills_from_profile(role, skills)` — 过滤越权 Skill
- `validate_mcp_tools_from_profile(role, mcp_tools)` — 过滤越权 MCP 工具
- 支持 `"*"` 和 `"server:*"` 通配符匹配

### 10. Agent Teams

队长-队员协作模式，使用同构成员 + 动态 prompt + 共享 TaskBoard + 主动认领。

#### 核心机制

- **同构成员**：队员使用相同的 Agent 实例，通过 `role_prompt` 动态赋予不同角色
- **TaskBoard**：共享任务队列，支持依赖追踪、认领机制、自动解锁
- **主动认领**：队员主动从 TaskBoard 认领可执行任务
- **空闲超时**：长时间不认领任务的队员自动关闭 (默认 300s)
- **队长委派**：队长通过 `delegate_task` 创建任务并分配 role_prompt

#### TaskBoard 任务生命周期

```
PENDING ──→ CLAIMED ──→ RUNNING ──→ COMPLETED
   │            │          │
   │            │          └──→ FAILED
   │            │
   └──→ BLOCKED (等待依赖完成)
            │
            └──→ PENDING (依赖完成后自动解锁)
```

#### 团队工具

| 工具 | 适用角色 | 功能 |
|------|----------|------|
| delegate_task | 队长 | 创建子任务，指定 role_prompt 和依赖关系 |
| read_task_board | 队长+队员 | 查看任务板状态 |
| collect_results | 队长 | 收集已完成任务的结果 |

#### 团队定义 (YAML)

```yaml
name: production_team
display_name: 生产协调组
captain: default
members:
  - equipment_monitor
  - quality_inspector
  - production_scheduler
description: 处理生产相关的综合问题
```

### 11. 定时调度 (Scheduler)

| 类型 | 实现 | 功能 |
|------|------|------|
| Heartbeat | APScheduler | 定期唤醒 Agent 执行主动监控 (默认 30min) |
| Cron | 5-field cron | 用户自定义定时任务，支持增删查 |

### 12. Gateway (L2)

#### REST API 端点

| 路径 | 方法 | 认证 | 功能 |
|------|------|------|------|
| `/api/chat` | POST | JWT/API Key | 同步对话 |
| `/ws/chat` | WebSocket | JWT/API Key | 流式对话 + 会话持久化 |
| `/api/auth/token` | POST | 密码 | JWT Token 创建 |
| `/api/auth/register` | POST | admin | 注册新用户 |
| `/api/skills` | GET | 无 | Skill 清单 |
| `/api/memory/{user_id}` | GET | 无 | 用户记忆文件 |
| `/api/sessions/{user_id}` | GET/POST | 无 | 会话列表/加载 |
| `/api/crons` | POST/GET/DELETE | JWT | 定时任务管理 |
| `/api/background` | POST/GET | JWT | 后台任务提交/查询 |
| `/api/agents` | GET | 无 | 专家智能体广场 |
| `/api/agents/{name}/chat` | POST | JWT/API Key | 专家智能体对话 |
| `/api/agents/manage` | GET/POST | admin | 专家智能体 CRUD |
| `/api/agents/manage/{name}` | GET/PUT/DELETE | admin | 单个智能体管理 |
| `/api/teams` | GET | 无 | 团队列表 |
| `/api/mcp/servers` | GET/POST | admin | MCP 服务端管理 |
| `/api/mcp/servers/{name}` | PUT/DELETE | admin | 单个 MCP 服务端 |
| `/api/mcp/servers/{name}/connect` | POST | admin | 连接 MCP 服务端 |
| `/api/mcp/servers/{name}/disconnect` | POST | admin | 断开 MCP 服务端 |
| `/api/mcp/tools` | GET | 无 | 已发现 MCP 工具（支持 ?role=） |
| `/api/roles/{role}/skills` | GET | 无 | 角色可用 Skill 列表 |
| `/api/roles/{role}/mcp-tools` | GET | 无 | 角色可用 MCP 工具列表 |
| `/api/skills/verify` | POST | admin/manager | 三 Agent Skill 验证 |
| `/api/skills/optimize/{name}` | POST | admin/manager | GEPA Skill 优化 |
| `/api/evolution/auto` | POST | JWT | 触发自主进化 |
| `/api/plugins` | GET | 无 | Plugin 清单 |
| `/api/approvals/pending` | GET | 无 | L4 待审批列表 |
| `/api/approvals/{id}/approve` | POST | 无 | L4 批准 |
| `/api/approvals/{id}/reject` | POST | 无 | L4 拒绝 |
| `/api/dingtalk/callback` | POST | 签名 | 钉钉机器人回调 |
| `/health` | GET | 无 | 健康检查 |

#### 关键机制

- **Lane Queue**：基于 asyncio.Lock 的会话串行化，防止同一会话并发请求冲突

---

### WebSocket 对话流程详解

#### 连接建立

```
前端 useWebSocket.connect(agentId?)
│
├─ pendingAgentRef.current = agentId      ← useRef，不受 React 闭包影响
├─ new WebSocket("ws://localhost:3000/ws/chat")
│  (Vite proxy → ws://localhost:8000/ws/chat)
│
│                              后端 @app.websocket("/ws/chat")
│                              await websocket.accept()
│
└─ ws.onopen → 认证帧             接收第一帧 →
   {                                {
     token: "eyJ...",                 "token": "...",
     user_id: "admin",                "user_id": "admin",
     agent_id: "equipment_monitor"    "agent_id": "equipment_monitor"
       │ "" 表示通用智能体          }
   }
```

#### Agent 创建（分叉逻辑）

```
authenticate_user(token) → UserContext
│
├─ agent_id 非空 且 在 Expert Registry 中
│  └─ create_expert_agent_for_user()
│     ├─ 加载 SOUL.md 人格文件
│     ├─ agent_ctx.role = profile.role（使用专家 Agent 自身角色）
│     ├─ system_prompt = 专属人格 + Skill 指令
│     ├─ 工具集 = BASE_TOOLS + profile.mcp_tools 允许的 MCP 工具
│     ├─ Skill 过滤 = 仅注入 profile.skills 中配置的 Skill
│     └─ 日志: agent_created agent_type=expert agent_id=xxx
│
└─ agent_id 为空 或 未注册
   └─ create_agent_for_user()
      ├─ 通用 system_prompt（无专属人格）
      ├─ 工具集按 role 分三级 + 角色允许的 MCP 工具:
      │   ├─ admin/manager + team_enabled → CAPTAIN_TOOLS (11)
      │   ├─ admin/manager               → ALL_TOOLS     (8)
      │   └─ operator/viewer             → BASE_TOOLS    (7)
      └─ 日志: agent_created agent_type=generic
```

#### 流式对话循环

```
前端 send("你好")
│
├─ ws.readyState === OPEN?
│  ├─ YES → ws.send({content:"你好"})
│  └─ NO  → pendingQueue 暂存，连接建立后自动发送
│
│                              后端 chat loop
│                              agent.stream({messages:[...]}, stream_mode="updates")
│
│                              每轮返回 {node_name: {messages: [...]}}
│                              ├─ model 节点 → AI 回复内容
│                              └─ tools 节点 → 工具执行结果
│
│  ← chunk 事件 {type:"chunk", content:"你好！"}
│  ← chunk 事件 {type:"chunk", content:"我是设备..."}
│  ← tool_call  {type:"tool_call", name:"file_read", args:{...}}
│  ← done       {type:"done"}
│
├─ chatStore.handleStreamEvent()
│  ├─ "chunk"      → addStreamingChunk() → StreamOutput 组件逐字渲染
│  ├─ "tool_call"  → addToolCall()       → ToolCallCard 组件展示
│  ├─ "done"       → finalizeStream()    → 消息写入 messages 列表
│  └─ "session_start" → 更新 currentSessionId
│
└─ 会话持久化 (每产生一条消息即写盘)
   session_persistence.write_message(user_id, session_id, msg, agent_id)
   ↓
   data/sessions/{user_id}/{session_id}.jsonl
   {"timestamp":"...","type":"human","content":"你好","agent_id":"equipment_monitor"}
   {"timestamp":"...","type":"ai","content":"我是设备...","agent_id":"equipment_monitor"}
```

#### 专家切换流程

```
用户点击 "设备巡检专家" (SessionList)
│
├─ ChatPage.switchAgent("equipment_monitor")
│
├─ 1. authStore.setAgentId("equipment_monitor")  ← Zustand + localStorage 同步
├─ 2. disconnect()
│     ├─ reconnectAttempts = 3   → 禁止旧 ws.onclose 触发重连
│     └─ wsRef.current = null    → 标记旧连接废弃
├─ 3. chatStore.startNewSession() → 清空 messages/streaming/toolCalls
├─ 4. connect("equipment_monitor")
│     ├─ pendingAgentRef.current = "equipment_monitor"
│     ├─ new WebSocket() → wsRef.current = newWs
│     └─ ws.onopen → 发送 {..., agent_id:"equipment_monitor"}
│        └─ 过期连接检测: ws !== wsRef.current → close() 丢弃
│
├─ UI 切换中: 输入框禁用, placeholder="正在连接...", 按钮 loading
└─ 连接完成后: pendingQueue 中排队消息自动发出
```

#### 消息队列机制

| 场景 | 行为 |
|------|------|
| WebSocket OPEN 时 send() | 直接发送 |
| WebSocket CONNECTING 时 send() | 消息暂存到 `pendingQueue`，`onopen` 后自动 flush |
| 快速连续切换专家 | 旧连接的 `onopen` 被废弃检测拦截，只有最新连接生效 |
| 连接断开 | 自动重连（3 次，间隔 5s），重连时保留 `pendingAgentRef` |
| 认证失败 (401) | 设置 `authFailed` 标志，停止重连，强制登出 |

#### 通用 vs 专家智能体对比

| 维度 | 通用智能体 | 专家智能体 |
|------|-----------|-----------|
| agent_id | `""` | `"equipment_monitor"` 等 |
| 创建函数 | `create_agent_for_user()` | `create_expert_agent_for_user()` |
| System Prompt | 通用企业助手 | SOUL.md 人格 + 选定 Skill 指令 |
| 工具集 | 按角色 BASE/ALL/CAPTAIN + 角色 MCP 工具 | BASE_TOOLS + profile.mcp_tools |
| 工具权限角色 | 登录用户角色 | 专家配置的角色 |
| Skill 注入 | 全部角色可用 Skill | 仅 profile.skills 中配置的 Skill |
| 会话记录 | `agent_id=""` | `agent_id="equipment_monitor"` |
| UI 展示 | "默认智能体" | "设备巡检专家 🔧" |
| 管理方式 | 无 | 文件系统（YAML）或 API 动态管理 |

#### 中间件链（两种 Agent 共享）

```
每条消息流经 9 层中间件:
1. AuthInjectionMiddleware    → 确保 UserContext 存在
2. MemoryInjectionMiddleware  → 注入 SOUL/USER/MEMORY 长期记忆
3. SummarizationMiddleware    → Token 超阈值时压缩历史
4. PreFlushMiddleware         → 上下文接近上限时冲刷到中期记忆
5. ToolFilterMiddleware       → 根据 RBAC 过滤越权工具
6. SecurityCheckMiddleware    → L0→L1→L2→L3→L4 五级审批 (仅危险工具)
7. SandboxMiddleware          → Docker 隔离执行 command_exec
8. OutputValidationMiddleware → 校验输出格式
9. MemoryArchiveMiddleware    → 会话内容归档到长期记忆
```
- **Session Persistence**：JSONL 文件存储，崩溃安全的消息日志
- **Channel Adapter**：统一适配层，每个渠道(Web/钉钉/飞书/企微)实现 normalize + format_response

---

## 安全机制设计详解

### 安全设计哲学

本平台遵循**纵深防御 (Defense in Depth)** 原则，在每个层级都设置安全防线，确保单点突破不会导致全局风险：

```
用户认证(JWT/APIKey) → RBAC权限控制 → 工具过滤 → 五级审批链 → 沙箱隔离 → 输出验证 → 记忆归档审计
```

### 认证安全

| 控制项 | 实现 |
|--------|------|
| 用户存储 | JSON 文件 (`data/users.json`) + bcrypt 哈希密码 |
| 登录接口 | `POST /api/auth/token` → UserStore.authenticate() → JWT 签发 |
| Token 算法 | HS256 + bcrypt 密码哈希 |
| Token 过期 | 8小时强制过期 (jwt_expire_minutes=480) |
| Token payload | user_id + role + tenant_id + exp |
| API Key | 独立 Key-Context 映射，支持即时撤销 (register/validate/revoke) |
| 密码存储 | bcrypt 哈希 + salt，不存储明文 |
| 防枚举攻击 | 登录失败不区分用户不存在和密码错误 |
| 注册控制 | `/api/auth/register` 仅 admin 可调用

### 授权安全

- **角色最小权限**：viewer 仅 4 个只读工具，operator 不含 command_exec/file_write
- **工具动态过滤**：ToolFilterMiddleware 在运行时根据角色和权限过滤可用工具
- **Skill 访问分级**：all / enterprise / production / report 四级 Skill 可见性
- **团队工具限制**：队长工具(delegate_task/collect_results)仅 admin/manager 可用

### 审批安全

五级审批是防止 Agent 误操作的核心防线，关键设计原则：

1. **L0/L1 不可绕过**：黑名单和正则匹配对所有角色强制执行，无升级通道
2. **分级升级**：viewer 停在 L2，admin/manager/operator 可升级到 L3/L4
3. **LLM 审查降负担**：L3 用 Mini Model 自动判断 80%+ 的边缘情况，减少人工审批量
4. **人工兜底**：L4 是最终安全阀，任何 L3 不确定的操作必须人工确认
5. **可追溯**：每个 L4 审批有唯一 approval_id，支持审计追踪

### 执行安全

| 控制项 | 实现 |
|--------|------|
| 命令隔离 | Docker 容器执行，内存限制 256m |
| 网络隔离 | 默认禁止网络访问 (network_disabled=True) |
| 超时控制 | 30秒强制超时，超时后 kill + remove |
| 容器清理 | auto_remove=False + 手动 remove(force=True)，确保无残留 |
| 输出截断 | stdout/stderr 最大 10000 字符 |
| 文件写入保护 | L2 禁止写入 /etc /bin /usr /root /var /sys /proc |
| 数据库只读 | L2 仅允许 SELECT 查询，禁止 DDL/DML |

### 记忆安全

- **专家记忆隔离**：不同专家 Agent 的记忆空间完全隔离
- **用户记忆隔离**：不同用户的记忆路径独立 (`workspace/users/{user_id}/`)
- **会话级隔离**：Redis 短期记忆按 session_id + user_id 存储

---

## 用户管理

### 用户存储 (UserStore)

**文件：** `harness/security/auth.py`

基于 JSON 文件的用户存储，密码 bcrypt 哈希。用户文件存储在 `data/users.json`，JSON 结构：

```json
{
  "admin": {
    "password_hash": "$2b$12$...",
    "role": "admin"
  }
}
```

**特性：**
- 密码始终 bcrypt 哈希 + salt，绝不存储明文
- 首次启动自动创建 4 个默认用户
- 支持通过 `/api/auth/register` 接口运行时注册新用户（需 admin 权限）

**默认用户表：**

| 用户ID | 初始密码 | 角色 | 说明 |
|--------|----------|------|------|
| `admin` | `admin123` | 管理员 | 最高权限，可注册用户、管理审批 |
| `manager` | `manager123` | 经理 | 管理权限，可管理 Skill/Cron/Team |
| `operator` | `operator123` | 操作员 | 日常使用，无 command_exec 和 file_write |
| `viewer` | `viewer123` | 观察员 | 只读查看，仅 4 个基础工具 |

### 登录流程

```
POST /api/auth/token { user_id, password }
  ├─ UserStore.authenticate() → bcrypt 验证密码
  ├─ 成功 → JWT 签发 (HS256, 8h 过期, payload: user_id/role/tenant_id)
  ├─ 密码错误 → 401 "Invalid user ID or password"
  └─ 用户不存在 → 401 (不区分用户不存在和密码错误，防枚举攻击)
```

JWT token 返回后：
1. 前端存入 `localStorage` (key: `token`, `userId`, `role`)
2. 所有后续请求通过 `Authorization: Bearer <token>` 携带
3. `authenticate_user()` 在网关层验证 token，提取 `UserContext`
4. 前端注销时清除 `localStorage` 并重置状态

### 认证机制

平台支持两种认证方式，由 `authenticate_user()` 统一处理：

| 方式 | 优先级 | 适用场景 | 管理 |
|------|--------|----------|------|
| **API Key** | 先于 JWT | 外部系统调用、脚本、CI/CD | `APIKeyManager` 内存存储，支持 register/validate/revoke |
| **JWT Token** | 后于 API Key | 前端 Web UI 用户 | `TokenManager` 创建/验证，有效期 8 小时 |

```
authenticate_user(api_key, token):
  1. 若 api_key 存在 → APIKeyManager.validate_key() → 匹配则返回 UserContext
  2. 若 token 存在 → TokenManager.validate_token() → 解码成功则返回 UserContext
  3. 均无效 → 401 Unauthorized
```

### 角色与权限系统

#### 四角色层级

**文件：** `runtime/context_schema.py:7` — `UserRole` 枚举

```
admin (管理员) → manager (经理) → operator (操作员) → viewer (观察员)
```

#### 完整权限矩阵

| 权限维度 | admin | manager | operator | viewer |
|----------|-------|---------|----------|--------|
| **工具** `file_read` | ✅ | ✅ | ✅ | ✅ |
| `file_write` | ✅ | ✅ | ❌ | ❌ |
| `command_exec` | ✅ | ❌ | ❌ | ❌ |
| `web_search` | ✅ | ✅ | ✅ | ✅ |
| `query_database` | ✅ | ✅ | ✅ | ✅ |
| `send_notification` | ✅ | ✅ | ✅ | ❌ |
| `memory_manage` | ✅ | ✅ | ✅ | ✅ |
| `spawn_subagent` | ✅* | ✅* | ❌ | ❌ |
| `delegate_task` | ✅** | ✅** | ❌ | ❌ |
| `collect_results` | ✅** | ✅** | ❌ | ❌ |
| `read_task_board` | ✅** | ✅** | ❌ | ❌ |
| **MCP 工具访问** | 全部 (`"*"`) | 按配置 | 无 | 无 |
| **Skill 访问** | all | enterprise | production | report |
| **审批上限** | L3 | L3 | L3 | L2 |
| **注册用户** | ✅ | ❌ | ❌ | ❌ |
| **管理 Skills** | ✅ | ✅ | ❌ | ❌ |
| **管理 Crons** | ✅ | ✅ | ❌ | ❌ |
| **管理 MCP 服务端** | ✅ | ❌ | ❌ | ❌ |
| **管理专家智能体** | ✅ | ❌ | ❌ | ❌ |
| **前端管理面板** | ✅ | ✅ | ❌ | ❌ |
| **审批标签页** | ✅ | ❌ | ❌ | ❌ |

> \* 角色在 `SUBAGENT_CAPABLE_ROLES` 中  
> \** 角色在 `CAPTAIN_CAPABLE_ROLES` 中且 `team_enabled=True`

#### RBAC 配置

**文件：** `config/rbac.yaml` / `config/settings.yaml:rbac`

```yaml
rbac:
  roles:
    admin:
      tools: [file_read, file_write, command_exec, web_search, query_database, send_notification, memory_manage]
      mcp_tools: ["*"]
      skill_access: all
      approval_level: L3
    manager:
      tools: [file_read, file_write, web_search, query_database, send_notification, memory_manage]
      mcp_tools: ["filesystem:read", "database:query"]
      skill_access: enterprise
      approval_level: L3
    operator:
      tools: [file_read, web_search, query_database, send_notification, memory_manage]
      mcp_tools: []
      skill_access: production
      approval_level: L3
    viewer:
      tools: [file_read, web_search, query_database, memory_manage]
      mcp_tools: []
      skill_access: report
      approval_level: L2
```

配置通过 `harness/security/rbac.py` 惰性加载为 `dict[UserRole, list[str]]`，在运行时的两个关键位置生效：

1. **Agent 创建时** (`runtime/agent.py:50-55`)：根据角色选择工具集 `BASE_TOOLS` / `ALL_TOOLS` / `CAPTAIN_TOOLS`
2. **每次模型调用时** (`harness/middleware/tool_filter.py`)：从 LLM 可见工具列表中移除越权工具

#### 前端角色守卫

**文件：** `web/src/components/RoleGuard.tsx`

- 路由级：`/admin` 路由仅 `admin|manager` 可访问
- 标签页级：AdminPanel 内 `approvals` 标签仅 `admin`，`skills/crons/teams` 仅 `admin|manager`，`mcp/expert-agents` 仅 `admin`
- 角色通过 `useAuth()` hook (`isAdmin`, `isManager`, `isOperator`, `isViewer`) 暴露给组件

### 用户注册

```
POST /api/auth/register { user_id, password, role }
  └─ 要求调用者 role=admin (通过 JWT 校验)
  └─ 检查用户是否已存在 → 409 Conflict
  └─ UserStore.create_user() → bcrypt 哈希密码 → 写入 users.json
```

---

## 配置管理

### 配置架构

**文件：** `runtime/config.py`

基于 **pydantic-settings** 的 `BaseSettings`，所有配置统一到 `AgentConfig` 模型。配置从 5 个来源按优先级加载：

```
初始化参数 (kwargs)  — 最高优先级
  ↓ 覆盖
OS 环境变量 (AI_AGENT_ 前缀)
  ↓ 覆盖
.env 文件 (项目根目录)
  ↓ 覆盖
config/settings.yaml  — 最低文件优先级
  ↓ 覆盖
文件秘密源 (未使用)
```

### 配置分组详解

#### LLM 配置

| 配置项 | 默认值 | 环境变量 | 说明 |
|--------|--------|----------|------|
| `llm_primary_provider` | `deepseek` | `AI_AGENT_LLM_PRIMARY_PROVIDER` | 主模型提供商 |
| `llm_primary_model` | `deepseek-v3` | `AI_AGENT_LLM_PRIMARY_MODEL` | 主模型名称 |
| `llm_primary_temperature` | `0.1` | `AI_AGENT_LLM_PRIMARY_TEMPERATURE` | 温度参数 |
| `llm_primary_max_tokens` | `4096` | `AI_AGENT_LLM_PRIMARY_MAX_TOKENS` | 最大 token 数 |
| `llm_fallback_provider` | `openai` | `AI_AGENT_LLM_FALLBACK_PROVIDER` | 备用模型提供商 |
| `llm_fallback_model` | `gpt-4o` | `AI_AGENT_LLM_FALLBACK_MODEL` | 备用模型名称 |

#### API 密钥

| 配置项 | 默认值 | 环境变量 | 说明 |
|--------|--------|----------|------|
| `deepseek_api_key` | `""` | `AI_AGENT_DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
| `openai_api_key` | `""` | `AI_AGENT_OPENAI_API_KEY` | OpenAI API 密钥 |
| `anthropic_api_key` | `""` | `AI_AGENT_ANTHROPIC_API_KEY` | Anthropic API 密钥 |
| `zhipu_api_key` | `""` | `AI_AGENT_ZHIPU_API_KEY` | 智谱 API 密钥 |

密钥自动注入：`runtime/models.py` 中的 `_inject_api_key()` 从 `AgentConfig` 读取密钥并设置为 `os.environ`，供 LangChain `init_chat_model()` 使用。

#### Gateway 配置

| 配置项 | 默认值 | 环境变量 | 说明 |
|--------|--------|----------|------|
| `gateway_host` | `0.0.0.0` | `AI_AGENT_GATEWAY_HOST` | 监听地址 |
| `gateway_port` | `8000` | `AI_AGENT_GATEWAY_PORT` | 监听端口 |
| `gateway_workers` | `1` | `AI_AGENT_GATEWAY_WORKERS` | Uvicorn worker 数（开发环境=1） |

#### 记忆系统配置

| 配置项 | 默认值 | 环境变量 | 说明 |
|--------|--------|----------|------|
| `memory_base_dir` | `data/workspace` | `AI_AGENT_MEMORY_BASE_DIR` | 长期记忆存储根路径 |
| `project_root` | `""` | `AI_AGENT_PROJECT_ROOT` | 项目根目录（空=自动检测） |
| `max_memory_tokens` | `2000` | `AI_AGENT_MAX_MEMORY_TOKENS` | 注入上下文的记忆 token 预算 |

#### 上下文管理配置

| 配置项 | 默认值 | 环境变量 | 说明 |
|--------|--------|----------|------|
| `max_context_tokens` | `64000` | `AI_AGENT_MAX_CONTEXT_TOKENS` | 模型上下文窗口总容量 |
| `compression_threshold` | `4000` | `AI_AGENT_COMPRESSION_THRESHOLD` | 触发压缩的 token 阈值 |
| `flush_threshold` | `60000` | `AI_AGENT_FLUSH_THRESHOLD` | 触发持久化冲刷的 token 阈值 |
| `max_flush_per_session` | `1` | `AI_AGENT_MAX_FLUSH_PER_SESSION` | 每次会话最大冲刷次数 |
| `placeholder_threshold` | `2000` | `AI_AGENT_PLACEHOLDER_THRESHOLD` | 文件引用替换阈值 |
| `keep_recent_messages` | `20` | `AI_AGENT_KEEP_RECENT_MESSAGES` | 压缩时保留的最近消息数 |

#### 安全配置

| 配置项 | 默认值 | 环境变量 | 说明 |
|--------|--------|----------|------|
| `jwt_secret` | `change-this-in-production` | `AI_AGENT_JWT_SECRET` | JWT 签名密钥（生产必须更换） |
| `jwt_algorithm` | `HS256` | `AI_AGENT_JWT_ALGORITHM` | JWT 签名算法 |
| `jwt_expire_minutes` | `480` | `AI_AGENT_JWT_EXPIRE_MINUTES` | JWT 过期时间（分钟，8h） |

#### 进化系统配置

| 配置项 | 默认值 | 环境变量 | 说明 |
|--------|--------|----------|------|
| `evolution_enabled` | `True` | `AI_AGENT_EVOLUTION_ENABLED` | 是否启用进化系统 |
| `auto_evolve_enabled` | `False` | `AI_AGENT_AUTO_EVOLVE_ENABLED` | 是否自动触发进化 |
| `gepa_max_candidates` | `3` | `AI_AGENT_GEPA_MAX_CANDIDATES` | GEPA 生成的候选 Skill 数 |
| `three_agent_max_rounds` | `3` | `AI_AGENT_THREE_AGENT_MAX_ROUNDS` | 三 Agent 验证最大迭代轮次 |
| `subagent_timeout` | `120` | `AI_AGENT_SUBAGENT_TIMEOUT` | 子 Agent 执行超时（秒） |
| `background_max_concurrent` | `3` | `AI_AGENT_BACKGROUND_MAX_CONCURRENT` | 最大并发后台任务数 |

#### 专家与团队配置

| 配置项 | 默认值 | 环境变量 | 说明 |
|--------|--------|----------|------|
| `expert_enabled` | `True` | `AI_AGENT_EXPERT_ENABLED` | 是否启用专家 Agent |
| `team_enabled` | `True` | `AI_AGENT_TEAM_ENABLED` | 是否启用团队/队长模式 |
| `member_idle_timeout` | `300` | `AI_AGENT_MEMBER_IDLE_TIMEOUT` | 团队成员空闲超时（秒） |
| `team_max_members` | `5` | `AI_AGENT_TEAM_MAX_MEMBERS` | 每团队最大成员数 |
| `task_board_max_tasks` | `20` | `AI_AGENT_TASK_BOARD_MAX_TASKS` | 每任务板最大任务数 |

#### 沙箱与基础设施配置

| 配置项 | 默认值 | 环境变量 | 说明 |
|--------|--------|----------|------|
| `sandbox_enabled` | `False` | `AI_AGENT_SANDBOX_ENABLED` | 启用 Docker 沙箱 |
| `sandbox_docker_image` | `ai-agent-sandbox:latest` | `AI_AGENT_SANDBOX_DOCKER_IMAGE` | 沙箱 Docker 镜像 |
| `sandbox_timeout_seconds` | `30` | `AI_AGENT_SANDBOX_TIMEOUT_SECONDS` | Docker 执行超时 |
| `sandbox_max_memory` | `256m` | `AI_AGENT_SANDBOX_MAX_MEMORY` | Docker 内存限制 |
| `redis_url` | `redis://localhost:6379/0` | `AI_AGENT_REDIS_URL` | Redis 连接 |
| `pg_host` | `localhost` | `AI_AGENT_PG_HOST` | PostgreSQL 主机 |
| `pg_database` | `ai_agent_platform` | `AI_AGENT_PG_DATABASE` | PostgreSQL 数据库 |
| `log_level` | `INFO` | `AI_AGENT_LOG_LEVEL` | 日志级别 |
| `heartbeat_interval` | `30` | `AI_AGENT_HEARTBEAT_INTERVAL` | 心跳间隔（分钟） |

### .env 文件

**文件：** `.env` (不纳入版本控制)

最简配置示例（仅需 API key）：

```bash
AI_AGENT_DEEPSEEK_API_KEY=sk-your-key-here
```

完整配置参考 `.env.example`，包含所有可用环境变量说明。

### config/settings.yaml

**文件：** `config/settings.yaml`

YAML 提供嵌套结构的配置，包含仅存在于 YAML 中的非 `AgentConfig` 字段：

| 节点 | 内容 | 加载方式 |
|------|------|----------|
| `security.approval` | L0 黑名单 (17 关键词)、L1 正则 (8 模式)、L2 安全命令 (27 允许) | 由 `approval.py` 直接解析 YAML |
| `rbac.roles` | 四角色工具列表 + skill_access + approval_level | 由 `rbac.py` 惰性加载 |
| `skill.builtin_dirs` | 内置 Skill 目录列表 | 由 `SkillManager` 读取 |
| `memory.long_term.bootstrap_files` | 启动时创建的记忆文件 | 由 `LongTermMemory` 读取 |

### 配置优先级实战

以 `gateway_port` 为例：

```
1. 代码直接传参: AgentConfig(gateway_port=9000)  → 9000
2. OS 环境变量:   export AI_AGENT_GATEWAY_PORT=8080  → 8080
3. .env 文件:     AI_AGENT_GATEWAY_PORT=8000        → 8000
4. settings.yaml: gateway.port: 8000               → 8000 (默认)
```

> **生产部署注意事项：** `jwt_secret` 默认值为 `"change-this-in-production"`，生产环境必须通过环境变量更换为安全的随机密钥。API 密钥应当仅通过环境变量注入，绝不可写入 YAML 或 `.env` 纳入 Git 仓库。

---

## 项目结构

```
ai-agent-framework/
├── harness/                  # Harness 层 (L3) — 企业级能力
│   ├── memory/               # 四层记忆系统
│   │   ├── manager.py        # MemoryManager — 记忆协调器
│   │   ├── long_term.py      # LongTermMemory — 文件持久化
│   │   ├── short_term.py     # ShortTermMemory — Redis 会话缓存
│   │   ├── mid_term.py       # MidTermMemory — PostgreSQL+pgvector
│   │   ├── evolution.py      # MemoryEvolution — LLM 记忆提取
│   │   └── types.py          # 记忆类型定义
│   ├── context/              # 上下文管理
│   │   ├── compressor.py     # ContextCompressor — 压缩+冲刷
│   │   ├── flush.py          # PreFlushMiddleware
│   │   ├── placeholder.py    # FileReferenceEdit
│   │   └── types.py          # ContextConfig
│   ├── skill/                # Skill 系统
│   │   ├── manager.py        # SkillManager
│   │   ├── manifest.py       # ManifestGenerator
│   │   ├── plugin.py         # PluginManager
│   │   └── types.py          # SkillInfo/PluginInfo
│   ├── security/             # 安全系统
│   │   ├── auth.py           # TokenManager + APIKeyManager + UserStore
│   │   ├── rbac.py           # RBAC 权限控制
│   │   ├── approval.py       # 五级审批 ApprovalChecker
│   │   └── types.py          # ApprovalLevel/ApprovalResult
│   ├── middleware/            # Middleware Chain (10层)
│   │   ├── auth_injection.py
│   │   ├── memory_injection.py
│   │   ├── memory_archive.py
│   │   ├── tool_filter.py
│   │   ├── security_check.py
│   │   ├── sandbox.py
│   │   ├── output_validation.py
│   │   └── types.py
│   ├── multi_agent/          # 多智能体协作
│   │   ├── subagent.py       # SubAgentRunner
│   │   ├── background.py     # BackgroundTaskManager
│   │   └── types.py          # SubAgentConfig/SubAgentResult
│   ├── evolution/            # 进化系统
│   │   ├── three_agent.py    # ThreeAgentVerifier
│   │   ├── gepa.py           # GEPAOptimizer
│   │   ├── auto_evolve.py    # AutoEvolver
│   │   └ and types.py          # 进化类型定义
│   ├── mcp/                   # MCP 集成
│   │   ├── manager.py        # MCPManager — 连接编排
│   │   ├── client.py         # MCPClient — 单服务端连接
│   │   ├── config.py         # MCPServerStore — JSON 持久化
│   │   └── types.py          # MCPServerConfig/MCPToolInfo
│   ├── expert/               # 专家智能体
│   │   ├── registry.py       # AgentRegistry
│   │   ├── agent_factory.py  # create_expert_agent
│   │   ├── store.py          # ExpertAgentStore — JSON CRUD
│   │   ├── validator.py      # ExpertAgentValidator — 权限校验
│   │   └── types.py          # AgentProfile
│   ├── team/                 # Agent Teams
│   │   ├── task_board.py     # TaskBoardManager
│   │   ├── member_pool.py    # TeamMemberPool + TeamManager
│   │   └ and types.py          # TaskItem/TaskBoard/TeamConfig
│   ├── sandbox/              # 沙箱执行
│   │   ├── runner.py         # SandboxRunner (Docker)
│   │   └── image.py          # SandboxImageManager
│   └── scheduler/            # 定时调度
│       ├── heartbeat.py      # HeartbeatScheduler
│       ├── cron.py           # CronScheduler
│       └── types.py          # CronTask/HeartbeatResult
│
├── gateway/                  # Gateway 层 (L2)
│   ├── server.py             # FastAPI 服务 + 全部 REST/WebSocket 端点
│   ├── router.py             # GatewayRouter + SessionManager
│   ├── session.py            # SessionPersistence (JSONL)
│   ├── lane.py               # LaneQueue (会话串行化)
│   ├── types.py              # StandardMessage/AgentResponse
│   └── adapters/             # Channel 适配器
│       ├── base.py           # ChannelAdapter (ABC)
│       ├── web.py            # WebAdapter
│       └── dingtalk.py       # DingTalkAdapter
│
├── runtime/                  # Agent Runtime 层 (L4)
│   ├── agent.py              # create_agent_for_user
│   ├── config.py             # AgentConfig (50+ 配置项)
│   ├── context_schema.py     # UserContext + UserRole
│   ├── models.py             # create_primary/fallback/mini_model
│   ├── tools.py              # 7基础工具 + spawn_subagent + 团队工具
│   └── __init__.py
│
├── agents/                   # 专家智能体定义
│   ├── equipment_monitor/    # 设备巡检专家
│   │   ├── profile.yaml
│   │   └── SOUL.md
│   ├── quality_inspector/    # 质量检验专家
│   │   ├── profile.yaml
│   │   └── SOUL.md
│   ├── production_scheduler/ # 生产调度专家
│   │   ├── profile.yaml
│   │   └ and SOUL.md
│   └── teams/                # 团队定义
│       └ production_team.yaml
│
├── skills/                   # Skill 内容目录
│   ├── builtin/              # 内置 Skill (7个)
│   │   ├── file_manager/SKILL.md
│   │   ├── knowledge_search/SKILL.md
│   │   ├── report_generator/SKILL.md
│   │   ├── schedule_manager/SKILL.md
│   │   ├── notification/SKILL.md
│   │   ├── database_query/SKILL.md
│   │   └ data_analysis/SKILL.md
│   └── plugins/              # Plugin 定义
│       ├── industrial/PLUGIN.md
│       └ enterprise/PLUGIN.md
│
├── data/                     # 运行数据
│   ├── agents/               # API 创建的专家智能体
│   │   ├── {name}.json       # AgentProfile JSON
│   │   └   {name}/SOUL.md      # Agent 人格文件
│   ├── mcp_servers.json      # MCP 服务端配置
│   ├── users.json            # 用户数据
│   └ sessions/               # 会话持久化 (JSONL)
│
├── config/                   # 配置管理
│   ├── settings.yaml         # 主配置 (模型/网关/记忆/安全/Skill/RBAC)
│   └ rbac.yaml               # RBAC 角色权限定义
│
├── tests/                    # 测试 (241个)
│   ├── unit/
│   │   ├── test_memory.py
│   │   ├── test_security.py
│   │   ├── test_skill.py
│   │   ├── test_context.py
│   │   ├── test_subagent.py
│   │   ├── test_background.py
│   │   ├── test_three_agent.py
│   │   ├── test_gepa.py
│   │   ├── test_auto_evolve.py
│   │   ├── test_plugin.py
│   │   ├── test_expert.py
│   │   ├── test_team.py
│   │   └ ...
│
├── web/                       # L1 Channel — React 前端
│   └── src/
│       ├── pages/
│       │   ├── ExpertAgentManager.tsx  # 专家智能体 CRUD
│       │   ├── MCPServerManager.tsx    # MCP 服务端管理
│       │   └ AdminPanel.tsx            # 管理面板（含新标签页）
│       ├── components/
│       │   ├── SkillSelector.tsx       # Skill 选择器
│       │   └ MCPToolSelector.tsx       # MCP 工具选择器
│       ├── store/
│       │   ├── mcpStore.ts            # MCP Zustand store
│       │   └ expertAgentStore.ts      # 专家智能体 Zustand store
│       ├── api/
│       │   ├── mcp.ts                 # MCP API 客户端
│       │   └ expert-agents.ts         # 专家智能体 API 客户端
│       ├── types/
│       │   ├── api.ts                 # API 类型（含 MCP/Agent CRUD）
│       │   └ agent.ts                 # AgentProfile 接口
│       └ ...
│
└── docs/                     # 设计文档
    └── architecture-deep-dive.md  # 架构深度解析
```

---

## 快速启动

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate      # Windows

# 安装依赖
pip install -e ".[dev,llm-deepseek,llm-openai]"

# 配置环境变量
cp .env.example .env
# 编辑 .env 配置 API Keys

# 启动服务
python -m gateway.server
```

## 运行测试

```bash
# 使用项目虚拟环境
source .venv/bin/activate

# 运行全部测试
pytest tests/ -v

# 运行特定模块测试
pytest tests/unit/test_security.py -v
pytest tests/unit/test_expert.py -v
pytest tests/unit/test_team.py -v
```

## 技术栈

| 类别 | 技术 |
|------|------|
| Agent Runtime | LangChain v1 (create_agent + AgentMiddleware) |
| Gateway | FastAPI + Uvicorn + WebSocket |
| MCP | MCP Python SDK (mcp>=1.0.0) — 外部工具集成 |
| Frontend | React 18 + TypeScript 5 + Ant Design 5 + Zustand |
| LLM | DeepSeek / OpenAI GPT / Anthropic Claude / Zhipu GLM |
| 长期记忆 | File System (Markdown) |
| 中期记忆 | PostgreSQL + pgvector |
| 短期记忆 | Redis |
| 安全认证 | JWT (python-jose) + bcrypt |
| 沙箱 | Docker (python:3.11-slim) |
| 定时 | APScheduler |
| 搜索 | DuckDuckGo Search |
| 日志 | structlog |
| 配置 | Pydantic BaseSettings + YAML |

## 实施进度

| Phase | 名称 | 状态 | 内容 |
|-------|------|------|------|
| Phase 1 | MVP | 已完成 | 基础 Agent + 记忆 + Skill + 安全 + Gateway |
| Phase 2 | 企业级 | 已完成 | RBAC + 五级审批 + 沙箱 + 上下文管理 + 钉钉 + 定时 |
| Phase 3 | 智能进化 | 已完成 | SubAgent + Background + 三Agent验证 + GEPA + 自主进化 + Plugin + 204测试 |
| Phase 4 | 高级特性 | 已完成 | 专家智能体 + Agent Teams + 241测试 (K8s/监控暂不实现) |

## License

Private — internal use only.