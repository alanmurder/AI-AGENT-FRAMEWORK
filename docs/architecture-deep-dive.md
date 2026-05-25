# AI Agent Platform — 架构深度解析

> 按六层架构（L1→L6）组织，每层包含职责、文件清单、核心流程与代码实现细节。

---

## 目录

- [L1 Channel — 用户接入层](#l1-channel--用户接入层)
- [L2 Gateway — 网关路由层](#l2-gateway--网关路由层)
- [L3 Harness — 企业级能力层](#l3-harness--企业级能力层)
  - [3.1 Memory — 四层记忆系统](#31-memory--四层记忆系统)
  - [3.2 Skill — 技能系统](#32-skill--技能系统)
  - [3.3 Security — 安全系统](#33-security--安全系统)
  - [3.4 Context — 上下文管理](#34-context--上下文管理)
  - [3.5 Middleware — 中间件链](#35-middleware--中间件链)
  - [3.6 Multi-Agent — 多智能体协作](#36-multi-agent--多智能体协作)
  - [3.7 Evolution — 进化系统](#37-evolution--进化系统)
  - [3.8 Expert — 专家智能体](#38-expert--专家智能体)
  - [3.9 Team — 智能体团队](#39-team--智能体团队)
  - [3.10 Sandbox — 沙箱执行](#310-sandbox--沙箱执行)
  - [3.11 Scheduler — 定时调度](#311-scheduler--定时调度)
  - [3.12 MCP — 外部工具集成](#312-mcp--外部工具集成)
  - [3.13 External Agent — 外部智能体接入](#313-external-agent--外部智能体接入)
- [L4 Agent Runtime — 智能体运行时](#l4-agent-runtime--智能体运行时)
- [L5 LLM Provider — 模型接入层](#l5-llm-provider--模型接入层)
- [L6 Infrastructure — 基础设施层](#l6-infrastructure--基础设施层)

---

## L1 Channel — 用户接入层

**职责：** 接收用户输入、格式化输出，屏蔽不同渠道（Web/钉钉/飞书/企微）的差异。

### 关键文件

| 文件 | 作用 |
|------|------|
| `web/src/` | React 18 前端，Ant Design 5 UI，Zustand 状态管理 |
| `gateway/adapters/base.py` | `ChannelAdapter` 抽象基类，定义 `connect/receive/send/disconnect` |
| `gateway/adapters/web.py` | `WebAdapter`，Web 通道适配器 |
| `gateway/adapters/dingtalk.py` | `DingTalkAdapter`，钉钉机器人回调 + Webhook 出站 |
| `gateway/types.py` | `ChannelType` 枚举 (WEB/DINGTALK/FEISHU/WECOM) |

### 核心数据流

```
用户浏览器 (React)
  ├─ REST → fetch/api → Vite proxy → FastAPI REST
  └─ WebSocket → ws://localhost:3000/ws/chat → Vite proxy → ws://localhost:8000/ws/chat

钉钉群聊
  └─ HTTP POST callback → DingTalkAdapter.normalize() → 统一消息格式
```

### 统一消息格式 (`gateway/types.py`)

```python
class ChannelType(str, Enum):
    WEB = "web"
    DINGTALK = "dingtalk"
    FEISHU = "feishu"
    WECOM = "wecom"

class StandardMessage:
    user_id: str
    content: str
    channel: ChannelType
    session_id: str = ""
    metadata: dict = {}
```

---

## L2 Gateway — 网关路由层

**职责：** 接收所有入站请求，身份认证，路由到正确的智能体，流式响应返回。

### 关键文件

| 文件 | 作用 |
|------|------|
| `gateway/server.py` | FastAPI 应用，所有 REST/WebSocket 端点 |
| `gateway/router.py` | `GatewayRouter` 智能体路由 + `SessionManager` 会话键管理 |
| `gateway/lane.py` | `LaneQueue` 会话串行化（asyncio.Lock） |
| `gateway/session.py` | `SessionPersistence` JSONL 会话持久化 |

### REST API 端点

| 路径 | 方法 | 认证 | 功能 |
|------|------|------|------|
| `/health` | GET | 无 | 健康检查 |
| `/api/auth/token` | POST | 密码 | 登录 → JWT |
| `/api/auth/register` | POST | admin | 注册新用户 |
| `/api/chat` | POST | JWT | 同步对话 |
| `/ws/chat` | WebSocket | JWT | 流式对话 |
| `/api/agents` | GET | JWT | 专家智能体列表 |
| `/api/agents/{name}/chat` | POST | JWT | 专家对话 |
| `/api/agents/manage` | GET/POST | admin | 专家智能体 CRUD |
| `/api/agents/manage/{name}` | GET/PUT/DELETE | admin | 单个智能体管理 |
| `/api/agents/manage/{name}/test-connection` | POST | admin | 外部智能体连接测试 |
| `/api/skills` | GET | JWT | 技能清单 |
| `/api/skills/verify` | POST | admin/manager | 三 Agent 验证 |
| `/api/skills/optimize/{name}` | POST | admin/manager | GEPA 优化 |
| `/api/mcp/servers` | GET/POST | admin | MCP 服务端管理 |
| `/api/mcp/servers/{name}` | PUT/DELETE | admin | 单个 MCP 服务端 |
| `/api/mcp/servers/{name}/connect` | POST | admin | 连接 MCP 服务端 |
| `/api/mcp/servers/{name}/disconnect` | POST | admin | 断开 MCP 服务端 |
| `/api/mcp/tools` | GET | 无 | 已发现 MCP 工具 |
| `/api/roles/{role}/skills` | GET | 无 | 角色可用 Skill |
| `/api/roles/{role}/mcp-tools` | GET | 无 | 角色可用 MCP 工具 |
| `/api/memory/{user_id}` | GET | JWT | 读取记忆文件 |
| `/api/sessions/{user_id}` | GET | JWT | 会话列表 |
| `/api/sessions/{user_id}/{session_id}` | GET | JWT | 会话消息回放 |
| `/api/crons` | POST/GET/DELETE | JWT | 定时任务 |
| `/api/background` | POST/GET | JWT | 后台任务 |
| `/api/approvals/pending` | GET | JWT | L4 待审批 |
| `/api/approvals/{id}/approve` | POST | JWT | L4 批准 |
| `/api/approvals/{id}/reject` | POST | JWT | L4 拒绝 |
| `/api/evolution/auto` | POST | JWT | 自主进化 |
| `/api/teams` | GET | JWT | 团队列表 |
| `/api/plugins` | GET | JWT | 插件列表 |

### 认证流程

```python
# gateway/server.py: authenticate_user()
def authenticate_user(api_key=None, token=None) -> UserContext:
    if api_key:
        return api_key_manager.validate_key(api_key)   # ① API Key 优先
    if token:
        return token_manager.validate_token(token)      # ② JWT 次之
    raise HTTPException(401)                             # ③ 两者都无 → 401
```

### WebSocket 对话流程（详见 README Gateway 章节）

```
前端 connect(agentId)
  → ws.onopen → {token, user_id, agent_id}
    → 后端 auth → 创建 Agent (expert/generic)
      → session_start event
        → 用户发送消息 → agent.stream(stream_mode="updates")
          → chunk/tool_call/done events → 前端 UI 更新
```

### 全局单例初始化

```python
# gateway/server.py — 模块级初始化（gateway_workers=1 保证单例）
config = AgentConfig()
if not config.project_root:
    config.project_root = str(Path(__file__).parent.parent)

memory_manager = MemoryManager(config, mini_model)
skill_manager = SkillManager(config)
token_manager = TokenManager(config.jwt_secret, ...)
api_key_manager = APIKeyManager()
user_store = UserStore()                    # data/users.json
approval_checker = ApprovalChecker(mini_model)
expert_registry = AgentRegistry()
expert_registry.scan_profiles(Path(config.project_root) / "agents")
session_persistence = SessionPersistence(config.get_memory_base_dir())
sandbox_runner = SandboxRunner()
background_manager = BackgroundTaskManager(...)
heartbeat_scheduler / cron_scheduler / lane_queue / ...
```

---

## L3 Harness — 企业级能力层

### 3.1 Memory — 四层记忆系统

**职责：** 让智能体在不同时间跨度上保持和利用信息。

#### 关键文件

| 文件 | 作用 |
|------|------|
| `harness/memory/manager.py` | `MemoryManager` — 四层协调器 |
| `harness/memory/types.py` | 类型定义：`MemoryType`、`MemoryFile`、`MemoryContext` |
| `harness/memory/long_term.py` | `LongTermMemory` — 文件系统持久化 |
| `harness/memory/mid_term.py` | `MidTermMemory` — PostgreSQL + pgvector |
| `harness/memory/short_term.py` | `ShortTermMemory` — Redis 会话缓存 |
| `harness/memory/evolution.py` | `MemoryEvolution` — LLM 提取偏好/事实 |

#### 四层架构

```
L1 长期记忆 (LongTermMemory)
  ├─ 存储: 文件系统 (data/workspace/)
  ├─ 文件: SOUL.md / USER.md / MEMORY.md
  ├─ 生命周期: 永久
  └─ 内容: 智能体人格、用户偏好、关键事实

L2 中期记忆 (MidTermMemory)
  ├─ 存储: PostgreSQL + pgvector
  ├─ 生命周期: 30 天保留
  ├─ 内容: 会话摘要、每日日志、事实向量
  └─ 检索: pgvector 语义搜索 + ts_vector 全文搜索

L3 短期记忆 (ShortTermMemory)
  ├─ 存储: Redis (TTL=3600s)
  ├─ 生命周期: 会话级
  └─ 内容: 当前对话消息、会话状态

L4 工作记忆 (Working Memory)
  ├─ 存储: Agent 运行时上下文
  ├─ 生命周期: 当前对话轮次
  └─ 内容: 当前 tool_call 结果、中间推理
```

#### MemoryContext 结构

```python
@dataclass
class MemoryContext:
    soul_content: str = ""           # 智能体人格
    user_content: str = ""           # 用户偏好
    memory_content: str = ""         # 关键事实
    daily_log_content: str = ""      # 每日日志
    mid_term_search_result: str = "" # 中期记忆搜索结果

    def to_prompt_section(self) -> str:
        # 编译为结构化提示块，注入到模型上下文
```

#### 记忆注入时机

```
MemoryInjectionMiddleware (before_model)
  ├─ 加载 MemoryContext（SOUL + USER + MEMORY + daily_log）
  ├─ 拼接 Skill Manifest
  ├─ 如果有 mid_term 搜索 → 附加结果
  └─ 注入到系统消息前
```

---

### 3.2 Skill — 技能系统

**职责：** 为智能体提供可遵循的操作规程，通过 Markdown 文件定义，按需加载。

#### 关键文件

| 文件 | 作用 |
|------|------|
| `harness/skill/manager.py` | `SkillManager` — 技能发现/加载协调器 |
| `harness/skill/manifest.py` | `ManifestGenerator` — 扫描 SKILL.md 生成清单 |
| `harness/skill/plugin.py` | `PluginManager` — 插件分组 |
| `harness/skill/types.py` | `SkillInfo`、`SkillManifest`、访问级别枚举 |

#### SKILL.md 格式

```markdown
---
name: database_query
description: Query production or business data
category: data
access: production
---

# Database Query Skill
...操作指南...
```

元数据字段：`name`、`description`、`category`、`access`（`all | enterprise | production | report`）

#### 技能生命周期

```
启动时: SkillManager 扫描 skills/builtin/ 和 skills/extensions/
  → ManifestGenerator 解析 SKILL.md 元数据
    → 生成 SkillManifest（所有技能的摘要文本）
      → 注入到 Agent 的 MemoryInjectionMiddleware

对话中: Agent 按需调用 load_instruction("database_query")
  → SkillManager 返回完整 SKILL.md 内容
    → Agent 按照指令执行操作
```

#### 内置技能（7 个）

| 技能 | 用途 |
|------|------|
| `database_query` | 生产/业务数据查询 |
| `data_analysis` | 数据分析 |
| `file_manager` | 文件读写管理 |
| `knowledge_search` | 信息检索 |
| `notification` | 告警通知 |
| `report_generator` | 报告生成 |
| `schedule_manager` | 排程管理 |

#### 技能访问分级

```
all         → admin 可见全部
enterprise  → manager 可见企业级
production  → operator 可见生产相关
report      → viewer 仅可见报告类
```

---

### 3.3 Security — 安全系统

**职责：** 身份认证、RBAC 权限控制、五级审批链（纵深防御）。

#### 关键文件

| 文件 | 作用 |
|------|------|
| `harness/security/auth.py` | `TokenManager` (JWT) + `APIKeyManager` + `UserStore` (密码) |
| `harness/security/rbac.py` | 从 `config/rbac.yaml` 加载角色工具映射 |
| `harness/security/approval.py` | `ApprovalChecker` — L0→L4 五级审批 |
| `harness/security/types.py` | `ApprovalLevel` / `ApprovalResult` |

#### 五级审批流程

```python
def check(content, tool_name, user_ctx) -> ApprovalResult:
    # L0: 黑名单关键词匹配
    if blacklist_matches(content): return BLOCKED(L0)
    
    # L1: 正则表达式模式匹配
    if pattern_matches(content): return BLOCKED(L1)
    
    # L2: 白名单检查
    if on_whitelist(content, tool_name): return APPROVED
    
    # viewer 停在 L2
    if user_max_level == L2: return BLOCKED(L2)
    
    # L3: LLM 审查（mini_model）
    verdict = llm_review(content, tool_name)
    if verdict == SAFE: return APPROVED(L3)
    if verdict == UNSAFE: return BLOCKED(L3)
    if verdict == UNCERTAIN: escalate to L4
    
    # L4: 人工审批
    return PENDING_L4(approval_id)
```

#### 审批规则配置 (`config/settings.yaml`)

```yaml
security:
  approval:
    l0_blacklist: ["rm -rf", "DROP TABLE", "sudo", "eval(", "exec(", ...]
    l1_patterns: ["$(...)", "`...`", "||", "&&", "wget ... -O /etc/...", ...]
    l2_safe_commands:
      command_exec: [ls, cat, grep, python, git, docker ps, ...]
      query_database: [SELECT]
      file_write_protected_dirs: [/etc/, /bin/, /usr/, /root/, ...]
```

#### RBAC 角色-工具映射

```yaml
# config/rbac.yaml
rbac:
  roles:
    admin:    {tools: [file_read,file_write,command_exec,web_search,...], approval_level: L3}
    manager:  {tools: [file_read,file_write,web_search,...],             approval_level: L3}
    operator: {tools: [file_read,web_search,query_database,...],         approval_level: L3}
    viewer:   {tools: [file_read,web_search,query_database,...],         approval_level: L2}
```

#### 认证方式

| 方式 | 实现 | 适用场景 |
|------|------|----------|
| JWT Token | HS256，8h 过期，payload 含 user_id/role/tenant_id | Web UI 用户 |
| API Key | 内存 Key-Context 映射，支持即时撤销 | 外部系统/脚本 |
| 密码 | bcrypt 哈希，JSON 文件存储 (`data/users.json`) | 所有用户 |

---

### 3.4 Context — 上下文管理

**职责：** 管理 Agent 的上下文窗口，防止溢出，用压缩和冲刷保持长对话。

#### 关键文件

| 文件 | 作用 |
|------|------|
| `harness/context/compressor.py` | `ContextCompressor` — 创建总结和编辑中间件 |
| `harness/context/placeholder.py` | `FileReferenceEdit` — 大型文件内容替换为引用 |
| `harness/context/flush.py` | `PreFlushMiddleware` — 上下文冲刷 |
| `harness/context/types.py` | `ContextConfig` 配置数据类 |

#### ContextConfig 参数

```python
@dataclass
class ContextConfig:
    max_tokens: int = 64000              # 模型上下文总容量
    compression_threshold: int = 4000    # 触发压缩的 token 阈值
    flush_threshold: int = 60000         # 触发持久化冲刷的 token 阈值
    max_flush_per_session: int = 1       # 每会话最多冲刷次数
    placeholder_threshold: int = 2000    # 文件引用替换阈值
    keep_recent_messages: int = 20       # 压缩时保留最近消息数
```

#### 压缩流程

```
当上下文 token 数 > compression_threshold (4000):
  1. SummarizationMiddleware 触发
     ├─ 将 early messages 发送给 mini_model
     ├─ mini_model 生成摘要
     └─ 用摘要替换原始消息（节省 token）

当上下文 token 数 > flush_threshold (60000):
  2. PreFlushMiddleware 触发
     ├─ 注入"请保存关键信息"指令
     ├─ Agent 提取关键事实
     ├─ LongTermMemory.append_file() → MEMORY.md
     └─ 清除已归档的早期消息
```

---

### 3.5 Middleware — 中间件链

**职责：** Agent 运行时的拦截器管道，在模型调用前后执行安全、记忆、过滤逻辑。

#### 注册顺序（9 层）

```python
# runtime/agent.py — create_agent_for_user()
agent = create_agent(
    model=model,
    tools=tools,
    system_prompt=system_prompt,
    middleware=[
        AuthInjectionMiddleware(user_ctx),        # ① 注入用户上下文
        MemoryInjectionMiddleware(...),            # ② 注入记忆+技能
        compressor.create_summarization_middleware(), # ③ 总结压缩
        compressor.create_context_editing_middleware(), # ④ 上下文编辑
        PreFlushMiddleware(...),                   # ⑤ 冲刷检查
        ToolFilterMiddleware(),                    # ⑥ 工具过滤
        SecurityCheckMiddleware(approval_checker), # ⑦ 安全检查
        SandboxMiddleware(sandbox_runner),         # ⑧ 沙箱执行
        OutputValidationMiddleware(),              # ⑨ 输出校验
        MemoryArchiveMiddleware(...),              # ⑩ 记忆归档
    ],
)
```

#### 各中间件详情

| 序号 | 中间件 | 类型 | 执行时机 | 核心逻辑 |
|------|--------|------|----------|----------|
| ① | AuthInjection | before_agent | Agent 处理前 | 验证 UserContext 存在，初始化用户工作空间 |
| ② | MemoryInjection | before_model | 每次 LLM 调用前 | 注入 SOUL/USER/MEMORY + Skill 清单到提示 |
| ③ | Summarization | wrap_model_call | 每次 LLM 调用前 | Token 超阈值 → 压缩历史 |
| ④ | ContextEditing | wrap_model_call | 每次 LLM 调用前 | 大型文件内容 → 引用占位符 |
| ⑤ | PreFlush | before_model | 每次 LLM 调用前 | 上下文接近上限 → 注入保存指令 |
| ⑥ | ToolFilter | wrap_model_call | 每次 LLM 调用前 | 根据 RBAC 移除越权工具 |
| ⑦ | SecurityCheck | wrap_tool_call | 危险工具调用时 | L0→L4 审批链 |
| ⑧ | Sandbox | wrap_tool_call | command_exec 调用时 | Docker 容器隔离执行 |
| ⑨ | OutputValidation | after_model | LLM 返回后 | 输出格式校验 |
| ⑩ | MemoryArchive | after_agent | Agent 处理完成后 | 会话摘要归档，触发进化检查 |

---

### 3.6 Multi-Agent — 多智能体协作

**职责：** 支持子智能体委派和后台任务执行。

#### 关键文件

| 文件 | 作用 |
|------|------|
| `harness/multi_agent/subagent.py` | `SubAgentRunner` — 创建隔离子智能体 |
| `harness/multi_agent/background.py` | `BackgroundTaskManager` — 异步后台任务队列 |
| `harness/multi_agent/types.py` | 子智能体角色、配置和结果类型 |

#### 子智能体角色

```python
class SubAgentRole(str, Enum):
    PLANNER = "planner"       # 规划
    GENERATOR = "generator"   # 生成
    EVALUATOR = "evaluator"   # 评估
    WORKER = "worker"         # 执行
```

#### SubAgentRunner 执行流程

```
spawn_subagent(role, task, system_prompt, expert_id?)
  │
  ├─ SubAgentRunner.run()
  │  ├─ 创建独立的 Agent 实例（隔离上下文）
  │  ├─ 限制中间件链（最小化，无递归子智能体）
  │  └─ 返回 SubAgentResult {output, tool_calls, duration_ms}
```

#### BackgroundTaskManager 队列模型

```
POST /api/background {name, prompt}
  → BackgroundTaskManager.submit()
    → asyncio.Queue
      → worker 循环取任务
        → 创建 Agent → invoke() → 写结果
          → 可选: 结果写入文件或通知用户
```

---

### 3.7 Evolution — 进化系统

**职责：** 自动创建和优化技能，持续改进智能体能力。

#### 关键文件

| 文件 | 作用 |
|------|------|
| `harness/evolution/three_agent.py` | `ThreeAgentVerifier` — 三智能体协作创建技能 |
| `harness/evolution/gepa.py` | `GEPAOptimizer` — 进化式提示优化 |
| `harness/evolution/auto_evolve.py` | `AutoEvolver` — 自动进化触发器 |

#### ThreeAgentVerifier 流程

```
Planner Agent (规划)
  → 分析需求 → 输出技能规范 + 评估标准
    ↓
Generator Agent (生成)
  → 根据规范写 SKILL.md
    ↓
Evaluator Agent (评估)
  → 对照标准打分 → 未通过?
    ↓ (最多 3 轮)
    ↓ 通过 → 保存 SKILL.md
```

#### GEPAOptimizer 流程

```
1. 加载当前技能 → 获取 baseline_score
2. 生成 3 个候选变体（不同方向改进）
3. 对每个候选打分
4. 选择最优 → 如果分数 > original → 替换
```

---

### 3.8 Expert — 专家智能体

**职责：** 创建具有专属人格（SOUL.md）、Skill 列表、MCP 工具列表和角色权限的专业智能体。支持三种来源：文件系统预置（YAML）、API 动态配置（JSON）、外部接入（HTTP 代理）。外部智能体的详细设计见 [3.13 External Agent](#313-external-agent--外部智能体接入)。

#### 关键文件

| 文件 | 作用 |
|------|------|
| `harness/expert/registry.py` | `AgentRegistry` — 扫描/注册/查询专家（合并文件+API来源） |
| `harness/expert/agent_factory.py` | `create_expert_agent()` / `create_expert_agent_for_user()` — 专家智能体工厂 |
| `harness/expert/store.py` | `ExpertAgentStore` — API 创建的智能体 JSON 存储 |
| `harness/expert/validator.py` | `ExpertAgentValidator` — 权限越级防护校验 |
| `harness/expert/types.py` | `AgentProfile` — 专家配置模型（含 skills/mcp_tools） |

#### AgentProfile (完整模型)

```python
class AgentProfile(BaseModel):
    name: str
    display_name: str
    description: str
    soul_file: str
    skill_plugin: str = ""
    model_preference: str = "primary"
    max_context_tokens: int = 32000
    role: str = "operator"
    skills: list[str] = []       # Skill 名称列表
    mcp_tools: list[str] = []    # MCP 工具 (server:tool 格式)
    source: str = "file"         # "file" | "api"
    created_by: str = ""
    created_at: str = ""
    updated_at: str = ""
```

#### create_expert_agent_for_user 流程

```python
def create_expert_agent_for_user(profile, user_ctx, ...):
    # 1. 使用专家配置的角色 (而非调用用户角色)
    agent_role = UserRole(profile.role)
    expert_ctx = UserContext(..., role=agent_role, agent_id=profile.name)

    # 2. 加载 SOUL.md 人格
    soul = registry.load_soul_content(profile.name, root)

    # 3. 工具 = BASE_TOOLS + profile.mcp_tools 允许的 MCP 工具
    tools = list(BASE_TOOLS)
    if mcp_manager and profile.mcp_tools:
        role_mcp_access = get_role_mcp_tool_access()
        mcp_tools = mcp_manager.get_tools_for_role(agent_role, role_mcp_access)
        tools.extend([t for t in mcp_tools if full_name in profile.mcp_tools])

    # 4. 构建 Agent
    agent = create_agent(model, tools, system_prompt=soul, middleware=[...])
    return agent
```

#### 双来源 Registry

```
启动时:
  1. AgentRegistry.scan_profiles(root / "agents")
     → 遍历 agents/*/profile.yaml → 解析 YAML → source="file" (只读)
  2. AgentRegistry.scan_api_profiles(root)
     → 遍历 data/agents/*.json → 解析 JSON → source="api" (可读写)
     → API 来源优先级高于文件来源
```

#### 权限校验 (ExpertAgentValidator)

```
创建/更新专家智能体时:
  1. validate_skills_from_profile(role, skills) → 过滤越权 Skill
     - 获取角色最大 SkillAccess level
     - 仅保留 access.level ≤ max_level 的 Skill
  2. validate_mcp_tools_from_profile(role, mcp_tools) → 过滤越权 MCP 工具
     - 获取角色的 mcp_tools 允许列表
     - admin "*" 通配符 → 全部放行
     - 支持 "server:*" 模式匹配
```

---

### 3.9 Team — 智能体团队

**职责：** 多专家协同，通过任务看板（TaskBoard）实现队长-成员协作模式。

#### 关键文件

| 文件 | 作用 |
|------|------|
| `harness/team/task_board.py` | `TaskBoardManager` — 带依赖的状态机 |
| `harness/team/member_pool.py` | `TeamMemberPool` + `TeamManager` |
| `harness/team/types.py` | `TaskItem`、`TaskBoard`、`TeamConfig` |

#### TaskBoard 状态机

```
PENDING ──claim──→ CLAIMED ──run──→ RUNNING ──submit──→ COMPLETED
  │                   │                    │               │
  └── blocked by ─────┘                    └── error ──→ FAILED
      dependencies
```

#### 队长工作流

```
Captain Agent (admin/manager + team_enabled)
  │
  ├─ delegate_task(task, assignee, dependencies)
  │   → TaskBoardManager.create_task() → 状态=PENDING
  │
  ├─ read_task_board()
  │   → 查询所有任务状态 → 格式化输出
  │
  └─ collect_results()
      → 收集所有 COMPLETED 任务的结果
```

---

### 3.10 Sandbox — 沙箱执行

**职责：** 隔离执行不信任的命令，防止影响宿主机。

#### 关键文件

| 文件 | 作用 |
|------|------|
| `harness/sandbox/runner.py` | `SandboxRunner` — Docker 容器生命周期 |
| `harness/sandbox/image.py` | `SandboxImageManager` — 镜像构建/缓存 |

#### 执行流程

```
SandboxMiddleware.wrap_tool_call("command_exec", args)
  │
  ├─ sandbox_enabled? → YES
  │  └─ SandboxRunner.execute(command, timeout=30, max_memory="256m")
  │     ├─ docker run --rm --network=none --memory=256m ...
  │     ├─ 捕获 stdout/stderr (max 10KB)
  │     └─ 返回结果 → ToolMessage
  │
  └─ sandbox_enabled? → NO
     └─ 回退到 subprocess 本地执行
```

#### 安全约束

| 限制项 | 值 |
|--------|-----|
| 执行超时 | 30 秒 |
| 内存限制 | 256 MB |
| 网络隔离 | `network=none` |
| 输出截断 | 10 KB |
| 容器清理 | 执行后强制 remove |

---

### 3.11 Scheduler — 定时调度

**职责：** 心跳健康检查和用户定时任务。

#### 关键文件

| 文件 | 作用 |
|------|------|
| `harness/scheduler/heartbeat.py` | `HeartbeatScheduler` — APScheduler 心跳 |
| `harness/scheduler/cron.py` | `CronScheduler` + `create_cron_task()` |
| `harness/scheduler/types.py` | `CronTask`、`HeartbeatResult` |

#### 心跳机制

```
HeartbeatScheduler (每 30 分钟)
  → 创建独立 Agent 实例
    → invoke("请执行系统健康检查")
      → 返回 HeartbeatResult {status, issues, suggestions}
```

#### Cron 任务

```
POST /api/crons {name, cron_expression, prompt}
  → create_cron_task()
    → CronScheduler.add_task(task)
      → 到时 → 创建 Agent → invoke(prompt) → 回调 → 持久化结果
```

---

### 3.12 MCP — 外部工具集成

**职责：** 连接外部 MCP (Model Context Protocol) 服务，发现工具，按角色过滤并包装为 LangChain 工具供 Agent 使用。

#### 关键文件

| 文件 | 作用 |
|------|------|
| `harness/mcp/manager.py` | `MCPManager` — 编排所有服务端连接和工具注册 |
| `harness/mcp/client.py` | `MCPClient` — 单个 stdio/SSE 服务端连接 |
| `harness/mcp/config.py` | `MCPServerStore` — JSON 持久化 (`data/mcp_servers.json`) |
| `harness/mcp/types.py` | `MCPServerConfig`、`MCPToolInfo` |

#### 连接流程

```
Gateway lifespan.startup()
  → MCPManager.initialize()
    → 遍历 data/mcp_servers.json 中 enabled 服务端
      → MCPClient(server_config)
        → transport=="stdio": stdio_client(command, args, env)
        → transport=="sse":   sse_client(url)
        → ClientSession(read, write)
          → await session.initialize()
            → await session.list_tools() → 发现工具
              → 包装为 LangChain @tool 函数
                func_name = f"mcp__{server_name}__{tool_name}"
              → 注册到 MCPManager._tools[func_name]
```

#### MCP 工具包装

```python
@langchain_tool("mcp__filesystem__read", description="[MCP:filesystem] Read file contents")
def _wrapper(**kwargs) -> str:
    # 异步调用：在同步上下文中使用 asyncio
    return client.call_tool("read", kwargs)
```

工具名使用 `mcp__{server}__{tool}` 双下划线分隔格式。`ToolFilterMiddleware` 解析此前缀，与 `rbac.yaml` 中 `mcp_tools` 配置（`server:tool` 格式）匹配进行过滤。

#### 角色过滤

```
RBAC 配置 (rbac.yaml):
  admin:    mcp_tools: ["*"]                          → 全部 MCP 工具
  manager:  mcp_tools: ["filesystem:read", "db:query"] → 指定工具
  operator: mcp_tools: []                              → 无 MCP 工具
  viewer:   mcp_tools: []                              → 无 MCP 工具
```

支持通配符：`"*"` (全部)、`"server:*"` (某服务器的全部工具)。

`ToolFilterMiddleware` 在每次模型调用时执行 MCP 工具过滤：解析 `mcp__filesystem__read` → `filesystem:read` → 在角色允许列表中匹配。

#### MCP 服务端存储格式

```json
{
  "filesystem": {
    "name": "filesystem",
    "transport": "stdio",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
    "enabled": true,
    "env": {}
  }
}
```

环境变量使用 `${VAR}` 占位符，连接时从进程环境解析，不持久化密钥原文。

---

### 3.13 External Agent — 外部智能体接入

**职责：** 将已有的垂域智能体/工作流服务接入平台，通过 HTTP 代理转发实现对话，无需平台组装运行时。

#### 关键文件

| 文件 | 作用 |
|------|------|
| `harness/external_agent/proxy.py` | `AgentProxyHandler` — HTTP 转发 + SSE 流式读取 |
| `harness/external_agent/types.py` | `ExternalEndpoint`、协议适配器 (`OpenAICompatibleAdapter`、`SimpleJsonAdapter`) |

#### 与配置型专家的本质区别

```
配置型 (internal):  平台组装 SOUL + Skill + MCP → LangChain Agent → 本地执行
外部型 (external):  平台注册端点 → Gateway 路由 → HTTP 代理转发 → 外部服务执行
```

外部智能体**不需要** `soul_file`、`skills`、`mcp_tools` 字段 — 这些都由外部服务自己管理。平台只负责认证、可见性控制和请求转发。

#### AgentProxyHandler 流程

```python
class AgentProxyHandler:
    def __init__(self, endpoint: ExternalEndpoint, protocol: str):
        self._adapter = get_adapter(protocol)  # OpenAICompatibleAdapter / SimpleJsonAdapter

    async def invoke(self, message, user_id, session_id, history):
        headers = self._adapter.build_headers(self.endpoint)  # 含认证
        body = self._adapter.build_request(message, user_id, session_id, ...)
        resp = await httpx.post(self.endpoint.url, headers=headers, json=body)
        return ProxyResult(content=self._adapter.extract_response(resp.json()))

    async def stream(self, message, user_id, session_id, history):
        # 使用 httpx.stream() 读取 SSE，逐行解析
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                chunk = self._adapter.extract_stream_chunk(json.loads(data_str))
                if chunk:
                    yield chunk
```

#### Gateway 路由分支

```
WebSocket / REST 收到 chat 请求 (agent_id)
  ├─ profile.is_external → AgentProxyHandler.stream/invoke()
  │   └─ logger: agent_type=external
  └─ profile.is_internal → create_expert_agent_for_user()
      └─ logger: agent_type=expert
```

#### 协议适配器

**OpenAICompatibleAdapter**：适配兼容 OpenAI Chat API 的服务。
- 请求体：`{"messages": [...], "stream": true, "user": "..."}`
- 响应提取：`choices[0].message.content`
- 流式提取：`choices[0].delta.content`

**SimpleJsonAdapter**：适配通用 JSON REST 端点。
- 请求体：`{"input": "用户消息", "user": "...", "history": [...]}`
- 响应提取：从 `output`/`result`/`response`/`content` 字段中获取

#### 安全设计

| 层级 | 措施 |
|------|------|
| 认证凭据保护 | `${ENV_VAR}` 占位符，运行时解析，JSON 存储不包含明文 |
| 角色可见性 | 复用 `UserRole.level` — 用户只能看到/对话 ≤ 自己角色的外部智能体 |
| 管理权限 | 创建/修改/删除/测试连接均需 `require_admin` |
| 超时保护 | `timeout_seconds` 可配置，默认 120s |
| 错误隔离 | 外部端点不可达返回友好错误，不崩溃 Agent 进程 |
| 连接测试 | `POST /api/agents/manage/{name}/test-connection` — 保存前验证可达性 |

---

## L4 Agent Runtime — 智能体运行时

**职责：** 根据用户角色和配置创建 LangChain Agent 实例，装配工具集和中间件链。

### 关键文件

| 文件 | 作用 |
|------|------|
| `runtime/agent.py` | `create_agent_for_user()` — 通用智能体工厂 |
| `runtime/tools.py` | 11 个工具定义 + 4 个工具集 |
| `runtime/models.py` | 模型创建：primary / fallback / mini |
| `runtime/config.py` | `AgentConfig` — pydantic-settings 配置 |
| `runtime/context_schema.py` | `UserContext` + `UserRole` |

### 工具集分级

```python
BASE_TOOLS = [file_read, file_write, command_exec, web_search, query_database,
              send_notification, memory_manage]                               # 7 个

ALL_TOOLS = BASE_TOOLS + [spawn_subagent]                                    # 8 个

CAPTAIN_TOOLS = ALL_TOOLS + [delegate_task, read_task_board, collect_results] # 11 个

MEMBER_TOOLS = [file_read, file_write, command_exec, web_search, query_database,
                send_notification, memory_manage, read_task_board]            # 8 个
```

### 角色→工具集映射

```python
# 工具集选择
if user_ctx.role in CAPTAIN_CAPABLE_ROLES and config.team_enabled:
    tools = list(CAPTAIN_TOOLS)       # admin/manager + team → 11 个
elif user_ctx.role in SUBAGENT_CAPABLE_ROLES:
    tools = list(ALL_TOOLS)           # admin/manager → 8 个
else:
    tools = list(BASE_TOOLS)          # operator/viewer → 7 个

# 附加角色允许的 MCP 工具
if mcp_manager:
    role_mcp_access = get_role_mcp_tool_access()
    tools.extend(mcp_manager.get_tools_for_role(user_ctx.role, role_mcp_access))
```

---

## L5 LLM Provider — 模型接入层

**职责：** 统一模型接口，多提供商支持，API 密钥注入，主备切换。

### 关键文件

| 文件 | 作用 |
|------|------|
| `runtime/models.py` | 模型工厂函数 + API 密钥注入 |

### 模型分层

```python
# 主模型（对话/Agent 核心）
create_primary_model(config) → "deepseek:deepseek-chat"
  temperature=0.1, max_tokens=4096

# 备用模型（主模型不可用时）
create_fallback_model(config) → "openai:gpt-4o"

# 微模型（压缩/评估/审批，快速轻量）
create_mini_model(config) → "deepseek:deepseek-chat"
  temperature=0.0, max_tokens=2048
```

### 多提供商支持

```python
# API 密钥自动注入
def _inject_api_key(config):
    if config.deepseek_api_key:
        os.environ["DEEPSEEK_API_KEY"] = config.deepseek_api_key
    if config.openai_api_key:
        os.environ["OPENAI_API_KEY"] = config.openai_api_key
    # ... anthropic, zhipu

# 模型字符串 → LangChain init_chat_model()
model = init_chat_model("deepseek:deepseek-chat")
```

---

## L6 Infrastructure — 基础设施层

**职责：** 数据存储、缓存、沙箱依赖。

### 关键组件

| 组件 | 技术 | 配置文件 | 用途 |
|------|------|----------|------|
| 长期记忆 | 文件系统 | `data/workspace/` | SOUL/USER/MEMORY 文件 |
| 中期记忆 | PostgreSQL + pgvector | `config.py pg_*` | 语义检索、全文搜索 |
| 短期记忆 | Redis | `redis_url` | 会话消息缓存 |
| 会话持久化 | JSONL 文件 | `data/workspace/sessions/` | 崩溃安全消息日志 |
| 用户存储 | JSON 文件 | `data/users.json` | bcrypt 密码用户库 |
| 日志 | RotatingFile | `data/logs/api.log + gateway.log` | API 日志 + 系统运行日志 |
| Docker | Docker Engine | `sandbox_*` | 命令执行隔离 |
| 调度器 | APScheduler | `heartbeat_interval` | 心跳 + 定时任务 |

### 配置加载顺序

```
1. 代码默认值 (runtime/config.py)
2. config/settings.yaml (AgentConfig 仅 4 个匹配字段)
3. .env 文件 (AI_AGENT_ 前缀)
4. OS 环境变量 (覆盖 .env)
5. 构造函数传参 (最高优先级)
```

---

## 数据流全景图

```
┌─────────────────────────────────────────────────────────────┐
│ L1 CHANNEL         用户浏览器 / 钉钉 / 飞书                  │
└──────────────────────┬──────────────────────────────────────┘
                       │ REST / WebSocket
┌──────────────────────┴──────────────────────────────────────┐
│ L2 GATEWAY          FastAPI app                             │
│                     authenticate_user() → UserContext        │
│                     ├─ REST: /api/chat → lane_queue          │
│                     └─ WS:   /ws/chat → session_persistence  │
└──────────────────────┬──────────────────────────────────────┘
                       │ create_expert_agent() / create_agent_for_user()
┌──────────────────────┴──────────────────────────────────────┐
│ L3 HARNESS          9-layer Middleware Chain                 │
│                     AuthInjection → MemoryInjection          │
│                     → Summarization → ContextEditing          │
│                     → PreFlush → ToolFilter                  │
│                     → SecurityCheck(L0-L4) → Sandbox         │
│                     → OutputValidation → MemoryArchive        │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────────┐
│ L4 AGENT RUNTIME   create_agent(model, tools, middleware)    │
│                    Tools: file_read/write, command_exec,     │
│                           web_search, query_database, ...    │
└──────────────────────┬──────────────────────────────────────┘
                       │ init_chat_model()
┌──────────────────────┴──────────────────────────────────────┐
│ L5 LLM PROVIDER    DeepSeek / OpenAI / Anthropic / GLM      │
│                    Primary → Fallback → Mini                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────────┐
│ L6 INFRASTRUCTURE  PostgreSQL+pgvector / Redis / Docker     │
│                    data/workspace/  data/users.json          │
│                    data/logs/ (api.log + gateway.log)        │
└─────────────────────────────────────────────────────────────┘
```

---

## 关键设计决策

### 1. gateway_workers = 1（非多进程）

全局单例（memory_manager、approval_checker、expert_registry 等）是模块级初始化的。多 worker 会导致重复初始化，且内存中的 L4 审批队列和任务看板无法共享。

### 2. stream_mode="updates"（非 values）

LangGraph 的 `values` 模式每次返回完整状态（含历史消息），导致重复。`updates` 模式仅返回增量更新 `{node_name: {messages: [new_msg]}}`，避免重复 + 减少网络传输。

### 3. pendingAgentRef（非 authStore.agentId）

React `useCallback` 闭包捕获渲染快照中的 `authStore.agentId`，在异步 `ws.onopen` 中读取时可能已过期。`useRef` 不受渲染周期影响，同步写入后立即读取一定是最新值。

### 4. YAML 配置 vs AgentConfig

`settings.yaml` 中的审批规则、RBAC 等由各自业务模块直接 `yaml.safe_load()` 读取，不经过 `AgentConfig`。`AgentConfig` 仅管理基础设施类参数（LLM、Gateway、JWT 等）。
