"""Gateway server — FastAPI with WebSocket streaming and REST API."""

import os
import uuid
import json
import structlog
import structlog.stdlib
import structlog.dev
from pathlib import Path
import time as _time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from runtime.config import AgentConfig
from runtime.context_schema import UserContext, UserRole
from runtime.agent import create_agent_for_user
from harness.memory.manager import MemoryManager
from runtime.models import create_mini_model
from harness.skill.manager import SkillManager
from harness.security.auth import TokenManager, APIKeyManager, UserStore
from harness.security.approval import ApprovalChecker
from harness.scheduler import HeartbeatScheduler, CronScheduler, create_cron_task
from gateway.router import GatewayRouter, SessionManager
from gateway.adapters.web import WebAdapter
from gateway.types import ChannelType, AgentResponse
from gateway.session import SessionPersistence
from gateway.lane import LaneQueue
from gateway.adapters.dingtalk import DingTalkAdapter
from harness.sandbox.runner import SandboxRunner
from harness.multi_agent.background import BackgroundTaskManager
from harness.evolution.three_agent import ThreeAgentVerifier
from harness.evolution.gepa import GEPAOptimizer
from harness.evolution.auto_evolve import AutoEvolver
from harness.multi_agent.subagent import SubAgentRunner
from harness.skill.plugin import PluginManager
from harness.expert.registry import AgentRegistry
from harness.expert.agent_factory import create_expert_agent

# Configure structlog — uses stdlib logging so output goes to both console and file
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="%H:%M:%S"),
        structlog.dev.ConsoleRenderer(colors=False),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)
logger = structlog.get_logger()

# Global instances
config = AgentConfig()
if not config.project_root:
    config.project_root = str(Path(__file__).parent.parent)
memory_manager = MemoryManager(config, mini_model=create_mini_model(config))
skill_manager = SkillManager(config)
token_manager = TokenManager(config.jwt_secret, config.jwt_algorithm, config.jwt_expire_minutes)
api_key_manager = APIKeyManager()
user_store = UserStore()
approval_checker = ApprovalChecker(mini_model=create_mini_model(config))
router = GatewayRouter()
expert_registry = AgentRegistry()
expert_registry.scan_profiles(Path(config.project_root) / "agents")
session_mgr = SessionManager()
web_adapter = WebAdapter()
session_persistence = SessionPersistence(config.get_memory_base_dir())
heartbeat_scheduler = HeartbeatScheduler(config, interval_minutes=config.heartbeat_interval)
cron_scheduler = CronScheduler(config)
lane_queue = LaneQueue()
dingtalk_adapter = DingTalkAdapter()
sandbox_runner = SandboxRunner()
background_manager = BackgroundTaskManager(config, memory_manager, skill_manager, approval_checker, sandbox_runner)


def authenticate_user(api_key: str = None, token: str = None) -> UserContext:
    """Authenticate user via API Key or JWT token."""
    # Try API Key first
    if api_key:
        user_ctx = api_key_manager.validate_key(api_key)
        if user_ctx:
            return user_ctx

    # Try JWT token
    if token:
        user_ctx = token_manager.validate_token(token)
        if user_ctx:
            return user_ctx

    raise HTTPException(status_code=401, detail="Invalid or missing authentication")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("gateway_starting", host=config.gateway_host, port=config.gateway_port)
    await memory_manager.connect_mid_term()
    heartbeat_scheduler.start()
    cron_scheduler.start()
    await background_manager.start_worker()
    logger.info("schedulers_started", heartbeat_interval=config.heartbeat_interval)
    yield
    heartbeat_scheduler.stop()
    cron_scheduler.stop()
    await background_manager.stop_worker()
    await memory_manager.disconnect_mid_term()
    logger.info("gateway_stopping")


app = FastAPI(title="AI Agent Platform", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# --- Request logging middleware ---
@app.middleware("http")
async def log_requests(request: Request, call_next):
    import logging as _logging
    start = _time.time()
    response = await call_next(request)
    duration_ms = (_time.time() - start) * 1000
    _logging.getLogger("api.request").info(
        "method=%-6s  status=%s  duration=%-8sms  path=%s%s%s",
        request.method,
        response.status_code,
        round(duration_ms, 1),
        request.url.path,
        f"?{request.query_params}" if request.query_params else "",
        f"  client={request.client.host}" if request.client else "",
    )
    return response


# --- REST API Endpoints ---


class ChatRequest(BaseModel):
    content: str
    user_id: str = "default"
    session_id: str = ""


class ChatResponse(BaseModel):
    content: str
    session_id: str


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, authorization: str = Header(default=None)):
    """REST API chat endpoint — synchronous response with lane queue serialization."""
    # Authentication
    auth_header = authorization or ""
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    api_key = auth_header if not auth_header.startswith("Bearer ") else ""
    user_ctx = authenticate_user(api_key=api_key, token=token)

    # Override user_id from request if authenticated
    user_ctx.user_id = request.user_id or user_ctx.user_id
    if not request.session_id:
        user_ctx.session_id = str(uuid.uuid4())

    # Lane queue: serialize per-user requests
    session_key = session_mgr.create_session_key(ChannelType.WEB, user_ctx.user_id)
    await lane_queue.acquire(session_key)
    try:
        # Initialize user workspace if needed
        memory_manager.init_user(user_ctx.user_id)

        # Create agent and invoke — one agent per request for REST
        agent = create_agent_for_user(user_ctx, config, memory_manager, skill_manager, approval_checker, sandbox_runner)
        result = agent.invoke(
            {"messages": [{"role": "user", "content": request.content}]},
            config={"configurable": {"context": user_ctx}},
        )

        # Extract response and persist messages
        response_content = ""
        for msg in result.get("messages", []):
            if hasattr(msg, "content") and msg.type == "ai":
                response_content = msg.content
            session_persistence.write_message(user_ctx.user_id, user_ctx.session_id, msg)

        return ChatResponse(content=response_content, session_id=user_ctx.session_id)
    finally:
        lane_queue.release(session_key)


class LoginRequest(BaseModel):
    user_id: str
    password: str


class RegisterRequest(BaseModel):
    user_id: str
    password: str
    role: str = "operator"


@app.post("/api/auth/token")
async def create_token(req: LoginRequest):
    """Login: verify password, return JWT token + role."""
    user_ctx = user_store.authenticate(req.user_id, req.password)
    if user_ctx is None:
        logger.warning("login_failed", user_id=req.user_id)
        raise HTTPException(status_code=401, detail="Invalid user ID or password")
    token = token_manager.create_token(user_ctx.user_id, user_ctx.role)
    logger.info("login_success", user_id=req.user_id, role=user_ctx.role.value)
    return {"token": token, "user_id": user_ctx.user_id, "role": user_ctx.role.value}


@app.post("/api/auth/register")
async def register_user(req: RegisterRequest, authorization: str = Header(default=None)):
    """Register a new user (requires admin token)."""
    auth_header = authorization or ""
    token_str = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    caller = None
    if token_str:
        caller = token_manager.validate_token(token_str)
    if caller is None or caller.role != UserRole.ADMIN:
        logger.warning("register_denied", user_id=req.user_id, reason="not_admin")
        raise HTTPException(status_code=403, detail="Only admin can register new users")

    if not req.user_id or not req.password:
        raise HTTPException(status_code=400, detail="user_id and password are required")

    ok = user_store.create_user(req.user_id, req.password, req.role)
    if not ok:
        logger.warning("register_conflict", user_id=req.user_id)
        raise HTTPException(status_code=409, detail=f"User '{req.user_id}' already exists")

    logger.info("user_registered", user_id=req.user_id, role=req.role, by=caller.user_id)
    return {"message": f"User '{req.user_id}' created", "user_id": req.user_id, "role": req.role}


@app.get("/api/skills")
async def list_skills():
    """List available skills."""
    return {"manifest": skill_manager.generate_manifest()}


@app.get("/api/memory/{user_id}")
async def get_memory(user_id: str, file: str = "MEMORY", authorization: str = Header(default=None)):
    """Read a memory file for a user."""
    from harness.memory.types import MemoryFile
    if not file.endswith(".md"):
        file = f"{file}.md"
    try:
        mem_file = MemoryFile(file)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid memory file: {file}. Valid options: SOUL.md, USER.md, MEMORY.md")

    content = memory_manager.long_term.read_file(user_id, mem_file)
    return {"user_id": user_id, "file": file, "content": content}


@app.get("/api/sessions/{user_id}")
async def list_sessions(user_id: str):
    """List all session IDs for a user, with agent metadata."""
    return {"user_id": user_id, "sessions": session_persistence.list_sessions(user_id)}


@app.get("/api/sessions/{user_id}/{session_id}")
async def get_session(user_id: str, session_id: str):
    """Load a session's messages for replay/recovery."""
    messages = session_persistence.load_session(user_id, session_id)
    return {"user_id": user_id, "session_id": session_id, "messages": messages}


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0", "schedulers": "running"}


# --- Cron Task API ---


class CronTaskRequest(BaseModel):
    name: str
    cron_expression: str
    user_id: str
    prompt: str
    channel: str = "web"


class CronTaskResponse(BaseModel):
    task_id: str
    name: str
    cron_expression: str
    user_id: str
    prompt: str
    channel: str
    status: str


@app.post("/api/crons", response_model=CronTaskResponse)
async def create_cron(req: CronTaskRequest, authorization: str = Header(default=None)):
    """Create a new cron task."""
    auth_header = authorization or ""
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    api_key = auth_header if not auth_header.startswith("Bearer ") else ""
    user_ctx = authenticate_user(api_key=api_key, token=token)

    task = create_cron_task(
        name=req.name,
        cron_expression=req.cron_expression,
        user_id=req.user_id or user_ctx.user_id,
        prompt=req.prompt,
        channel=req.channel,
    )

    def on_cron_complete(result):
        logger.info("cron_completed", task_id=task.task_id, summary=result.summary[:100])

    cron_scheduler.add_task(task)
    cron_scheduler.register_callback(task.task_id, on_cron_complete)
    logger.info("cron_created", task_id=task.task_id, name=req.name, expression=req.cron_expression, user_id=user_ctx.user_id)

    return CronTaskResponse(
        task_id=task.task_id,
        name=task.name,
        cron_expression=task.cron_expression,
        user_id=task.user_id,
        prompt=task.prompt,
        channel=task.channel,
        status=task.status.value,
    )


@app.get("/api/crons/{user_id}", response_model=list[CronTaskResponse])
async def list_crons(user_id: str):
    """List all cron tasks for a user."""
    tasks = cron_scheduler.list_tasks(user_id=user_id)
    return [
        CronTaskResponse(
            task_id=t.task_id,
            name=t.name,
            cron_expression=t.cron_expression,
            user_id=t.user_id,
            prompt=t.prompt,
            channel=t.channel,
            status=t.status.value,
        )
        for t in tasks
    ]


@app.delete("/api/crons/{task_id}")
async def delete_cron(task_id: str):
    """Delete a cron task."""
    removed = cron_scheduler.remove_task(task_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Cron task '{task_id}' not found")
    return {"deleted": task_id}


# --- Background Task API ---


class BackgroundTaskRequest(BaseModel):
    name: str
    prompt: str
    user_id: str = "default"


class BackgroundTaskDetailResponse(BaseModel):
    task_id: str
    name: str
    user_id: str
    prompt: str
    status: str
    created_at: str
    completed_at: str
    result: str
    error: str | None


@app.post("/api/background", response_model=BackgroundTaskDetailResponse)
async def submit_background_task(req: BackgroundTaskRequest, authorization: str = Header(default=None)):
    """Submit a background task (non-blocking agent execution)."""
    auth_header = authorization or ""
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    api_key = auth_header if not auth_header.startswith("Bearer ") else ""
    user_ctx = authenticate_user(api_key=api_key, token=token)

    task_id = await background_manager.submit(
        name=req.name, prompt=req.prompt, user_id=req.user_id or user_ctx.user_id,
    )
    task = await background_manager.get_status(task_id)
    return BackgroundTaskDetailResponse(
        task_id=task.task_id, name=task.name, user_id=task.user_id,
        prompt=task.prompt, status=task.status,
        created_at=task.created_at, completed_at=task.completed_at,
        result=task.result, error=task.error,
    )


@app.get("/api/background/{user_id}", response_model=list[BackgroundTaskDetailResponse])
async def list_background_tasks(user_id: str):
    """List all background tasks for a user."""
    tasks = await background_manager.list_tasks(user_id=user_id)
    return [
        BackgroundTaskDetailResponse(
            task_id=t.task_id, name=t.name, user_id=t.user_id,
            prompt=t.prompt, status=t.status,
            created_at=t.created_at, completed_at=t.completed_at,
            result=t.result, error=t.error,
        )
        for t in tasks
    ]


@app.get("/api/background/task/{task_id}", response_model=BackgroundTaskDetailResponse)
async def get_background_task(task_id: str):
    """Get details of a specific background task."""
    task = await background_manager.get_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Background task '{task_id}' not found")
    return BackgroundTaskDetailResponse(
        task_id=task.task_id, name=task.name, user_id=task.user_id,
        prompt=task.prompt, status=task.status,
        created_at=task.created_at, completed_at=task.completed_at,
        result=task.result, error=task.error,
    )


# --- Expert Agent & Team API (Phase 4) ---


class ExpertChatRequest(BaseModel):
    content: str
    user_id: str = "default"
    session_id: str = ""


class ExpertChatResponse(BaseModel):
    content: str
    session_id: str


@app.get("/api/agents")
async def list_experts():
    """Agent marketplace — list all available expert agents."""
    return {
        "manifest": expert_registry.generate_manifest(),
        "agents": [
            {"name": p.name, "display_name": p.display_name, "description": p.description, "role": p.role, "skill_plugin": p.skill_plugin}
            for p in expert_registry.list_profiles()
        ],
    }


@app.post("/api/agents/{name}/chat", response_model=ExpertChatResponse)
async def chat_with_expert(name: str, request: ExpertChatRequest, authorization: str = Header(default=None)):
    """Chat directly with a specific expert agent."""
    auth_header = authorization or ""
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    api_key = auth_header if not auth_header.startswith("Bearer ") else ""
    user_ctx = authenticate_user(api_key=api_key, token=token)

    profile = expert_registry.get(name)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Expert agent '{name}' not found")

    user_ctx.user_id = request.user_id or user_ctx.user_id
    user_ctx.agent_id = name
    user_ctx.session_id = request.session_id or str(uuid.uuid4())

    root = Path(config.project_root)
    soul_content = expert_registry.load_soul_content(name, root)

    agent = create_expert_agent(
        profile, soul_content, user_ctx, config,
        memory_manager, skill_manager, approval_checker, sandbox_runner,
    )

    session_key = session_mgr.create_session_key(ChannelType.WEB, user_ctx.user_id, expert_id=name)
    await lane_queue.acquire(session_key)
    try:
        memory_manager.init_user(user_ctx.user_id)
        result = agent.invoke(
            {"messages": [{"role": "user", "content": request.content}]},
            config={"configurable": {"context": user_ctx}},
        )

        # Persist messages to session file
        for msg in result.get("messages", []):
            session_persistence.write_message(user_ctx.user_id, user_ctx.session_id, msg, agent_id=name)

        response_content = ""
        for msg in result.get("messages", []):
            if hasattr(msg, "content") and msg.type == "ai":
                response_content = msg.content

        return ExpertChatResponse(content=response_content, session_id=user_ctx.session_id)
    finally:
        lane_queue.release(session_key)


@app.get("/api/teams")
async def list_teams():
    """List all available teams."""
    from harness.team.member_pool import TeamManager
    root = Path(config.project_root)
    tm = TeamManager(config)
    teams = tm.scan_teams(root)
    return {
        "teams": [
            {"name": t.name, "display_name": t.display_name, "captain": t.captain, "members": t.members, "description": t.description}
            for t in teams
        ],
    }


@app.get("/api/agents/{name}/tasks")
async def get_expert_tasks(name: str, user_id: str = "default"):
    """Get TaskBoard status for an expert's team."""
    from harness.team.task_board import TaskBoardManager
    board = TaskBoardManager(config)
    board_id = f"team-{name}"
    tasks = board.list_tasks(board_id)
    return {
        "board_id": board_id,
        "tasks": [
            {"task_id": t.task_id, "description": t.description, "status": t.status, "assignee": t.assignee, "result": t.result[:200]}
            for t in tasks
        ],
    }


# --- Evolution & Plugin API (Phase 3) ---


class SkillVerifyRequest(BaseModel):
    requirement: str
    user_id: str = "default"


class SkillOptimizeRequest(BaseModel):
    user_id: str = "default"


class EvolutionAutoRequest(BaseModel):
    user_id: str = "default"


def _make_subagent_runner():
    """Create SubAgentRunner for evolution operations."""
    return SubAgentRunner(config, memory_manager, skill_manager, approval_checker, sandbox_runner)


@app.post("/api/skills/verify")
async def verify_skill(req: SkillVerifyRequest, authorization: str = Header(default=None)):
    """Trigger three-agent verification to create a new Skill."""
    auth_header = authorization or ""
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    api_key = auth_header if not auth_header.startswith("Bearer ") else ""
    user_ctx = authenticate_user(api_key=api_key, token=token)
    if user_ctx.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Only admin/manager can trigger skill verification")

    runner = _make_subagent_runner()
    verifier = ThreeAgentVerifier(runner, max_rounds=config.three_agent_max_rounds)
    result = verifier.verify(req.requirement, user_ctx)
    logger.info("skill_verify_completed", passed=result.passed, rounds=result.rounds, user_id=user_ctx.user_id)
    return {
        "passed": result.passed,
        "skill_content": result.skill_content[:500],
        "evaluation": result.evaluation[:300],
        "rounds": result.rounds,
        "suggestions": result.suggestions,
    }


@app.post("/api/skills/optimize/{skill_name}")
async def optimize_skill(skill_name: str, req: SkillOptimizeRequest, authorization: str = Header(default=None)):
    """Trigger GEPA optimization on an existing Skill."""
    auth_header = authorization or ""
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    api_key = auth_header if not auth_header.startswith("Bearer ") else ""
    user_ctx = authenticate_user(api_key=api_key, token=token)
    if user_ctx.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Only admin/manager can trigger skill optimization")

    skill_content = skill_manager.load_skill_content(skill_name)
    if not skill_content:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    runner = _make_subagent_runner()
    optimizer = GEPAOptimizer(runner, config)
    result = optimizer.optimize_skill(skill_name, skill_content, user_ctx)
    logger.info("skill_optimize_completed", skill_name=skill_name, original=result.original_score,
                improved=result.best_candidate.score if result.best_candidate else None, user_id=user_ctx.user_id)
    return {
        "optimized": result.optimized,
        "original_score": result.original_score,
        "best_candidate_score": result.best_candidate.score if result.best_candidate else None,
        "candidates_count": result.candidates_count,
    }


@app.post("/api/evolution/auto")
async def trigger_auto_evolution(req: EvolutionAutoRequest, authorization: str = Header(default=None)):
    """Trigger auto-evolution check for a user's recent conversations."""
    auth_header = authorization or ""
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    api_key = auth_header if not auth_header.startswith("Bearer ") else ""
    user_ctx = authenticate_user(api_key=api_key, token=token)

    if not config.auto_evolve_enabled:
        raise HTTPException(status_code=403, detail="Auto-evolution is not enabled")

    # Get recent conversation summary from mid-term memory
    summaries = await memory_manager.search_mid_term_recent(req.user_id or user_ctx.user_id, top_k=5, days=7)
    conversation_summary = "\n".join(summaries) if summaries else "(no recent conversations)"

    runner = _make_subagent_runner()
    verifier = ThreeAgentVerifier(runner, max_rounds=config.three_agent_max_rounds)
    evolver = AutoEvolver(runner, verifier, skill_manager, config)
    check_result = evolver.check_evolution_need(conversation_summary, req.user_id or user_ctx.user_id)

    return {
        "needs_evolution": check_result.needs_evolution,
        "reason": check_result.reason,
        "suggested_skill_name": check_result.suggested_skill_name,
    }


@app.get("/api/plugins")
async def list_plugins():
    """List all available Plugins."""
    pm = PluginManager(skill_manager)
    root = Path(config.project_root)
    plugins = pm.scan_plugins(root)
    return {
        "plugins": [
            {"name": p.name, "description": p.description, "skills": p.skills}
            for p in plugins
        ]
    }


@app.get("/api/plugins/{name}")
async def get_plugin(name: str):
    """Get details of a specific Plugin."""
    pm = PluginManager(skill_manager)
    root = Path(config.project_root)
    plugin = pm.load_plugin(name, root)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
    return {"name": plugin.name, "description": plugin.description, "skills": plugin.skills, "location": plugin.location}


# --- L4 Approval API ---


@app.get("/api/approvals/pending")
async def list_pending_approvals():
    """List all pending L4 human-in-the-loop approvals."""
    pending = approval_checker.list_pending()
    return {
        "pending_approvals": [
            {"approval_id": k, "level": v.level.value, "reason": v.reason, "details": v.details}
            for k, v in pending.items()
        ]
    }


@app.post("/api/approvals/{approval_id}/approve")
async def approve_l4(approval_id: str):
    """Approve a pending L4 request."""
    success = approval_checker.approve_pending(approval_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Approval '{approval_id}' not found")
    logger.info("approval_approved", approval_id=approval_id)
    return {"approval_id": approval_id, "status": "approved"}


@app.post("/api/approvals/{approval_id}/reject")
async def reject_l4(approval_id: str):
    """Reject a pending L4 request."""
    success = approval_checker.reject_pending(approval_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Approval '{approval_id}' not found")
    logger.info("approval_rejected", approval_id=approval_id)
    return {"approval_id": approval_id, "status": "rejected"}


# --- DingTalk Callback Endpoint ---


@app.post("/api/dingtalk/callback")
async def dingtalk_callback(request: dict):
    """Receive and process DingTalk bot callback messages.

    DingTalk sends user messages as HTTP POST callbacks to this endpoint.
    The adapter normalizes the message, creates an agent session, and
    processes the message.
    """
    # Verify signature for security
    timestamp = request.get("timestamp", "")
    sign = request.get("sign", "")
    if dingtalk_adapter.app_secret and not dingtalk_adapter.verify_callback_signature(timestamp, sign):
        raise HTTPException(status_code=401, detail="Invalid DingTalk signature")

    # Normalize the incoming message
    std_msg = dingtalk_adapter.normalize(request)

    if not std_msg.content:
        return {"success": True, "message": "Empty message ignored"}

    # Create user context
    user_ctx = UserContext(
        user_id=std_msg.user_id,
        role=UserRole.OPERATOR,
        tenant_id="default",
        permissions=[],
        memory_path="",
        session_id=str(uuid.uuid4()),
    )

    # Lane queue: serialize per-user requests
    is_group = std_msg.metadata.get("is_group", False)
    group_id = std_msg.metadata.get("conversation_id", "") if is_group else None
    session_key = session_mgr.create_session_key(ChannelType.DINGTALK, std_msg.user_id, group_id)
    await lane_queue.acquire(session_key)
    try:
        memory_manager.init_user(user_ctx.user_id)
        agent = create_agent_for_user(user_ctx, config, memory_manager, skill_manager, approval_checker, sandbox_runner)
        result = agent.invoke(
            {"messages": [{"role": "user", "content": std_msg.content}]},
            config={"configurable": {"context": user_ctx}},
        )

        # Extract response
        response_content = ""
        for msg in result.get("messages", []):
            if hasattr(msg, "content") and msg.type == "ai":
                response_content = msg.content

        # Send response back via DingTalk
        agent_response = AgentResponse(
            content=response_content,
            metadata={"user_id": std_msg.user_id},
        )
        sent = await dingtalk_adapter.send(std_msg.user_id, agent_response)

        return {"success": True, "response_sent": sent}
    finally:
        lane_queue.release(session_key)


# --- WebSocket Endpoint ---


@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """WebSocket chat endpoint — streaming response.

    The agent is created once per session (after auth) and reused for all messages,
    avoiding costly re-initialization on every message.
    """
    await websocket.accept()
    agent = None

    try:
        # First message must contain auth info
        auth_msg = await websocket.receive_text()
        auth_data = json.loads(auth_msg)

        api_key = auth_data.get("api_key", "")
        token = auth_data.get("token", "")
        user_id = auth_data.get("user_id", "default")
        agent_id = auth_data.get("agent_id", "")
        logger.info("ws_auth_received",
            user_id=user_id,
            agent_id=agent_id or "(none)",
            raw_keys=list(auth_data.keys()),
            token_len=len(token) if token else 0,
        )

        user_ctx = authenticate_user(api_key=api_key, token=token)
        user_ctx.user_id = user_id
        user_ctx.agent_id = agent_id
        user_ctx.session_id = str(uuid.uuid4())

        # Init workspace
        memory_manager.init_user(user_ctx.user_id)

        # Create agent: expert agent if agent_id specified, otherwise generic
        if agent_id and expert_registry.get(agent_id):
            profile = expert_registry.get(agent_id)
            root = Path(config.project_root)
            soul_content = expert_registry.load_soul_content(agent_id, root)
            agent = create_expert_agent(
                profile, soul_content, user_ctx, config,
                memory_manager, skill_manager, approval_checker, sandbox_runner,
            )
            logger.info("agent_created", agent_type="expert", agent_id=agent_id, user_id=user_id, session_id=user_ctx.session_id)
        else:
            agent = create_agent_for_user(user_ctx, config, memory_manager, skill_manager, approval_checker, sandbox_runner)
            logger.info("agent_created", agent_type="generic", user_id=user_id, session_id=user_ctx.session_id)

        # Send session info
        await websocket.send_text(json.dumps({
            "type": "session_start",
            "user_id": user_ctx.user_id,
            "session_id": user_ctx.session_id,
            "agent_id": agent_id,
        }))

        logger.info("ws_connected", user_id=user_ctx.user_id, session_id=user_ctx.session_id)

        # Chat loop — reuse the same agent instance
        while True:
            data = await websocket.receive_text()
            msg_data = json.loads(data)
            user_message = msg_data.get("content", "")

            if not user_message:
                continue

            logger.info("chat_message_received", user_id=user_id, session_id=user_ctx.session_id, agent_id=agent_id, msg_len=len(user_message))

            # Stream response using the session-persistent agent
            # stream_mode="updates" returns {node_name: {"messages": [...]}} per chunk
            for chunk in agent.stream(
                {"messages": [{"role": "user", "content": user_message}]},
                config={"configurable": {"context": user_ctx}},
                stream_mode="updates",
            ):
                for node_output in chunk.values():
                    if not node_output or not isinstance(node_output, dict):
                        continue
                    for msg in node_output.get("messages", []):
                        session_persistence.write_message(user_ctx.user_id, user_ctx.session_id, msg, agent_id=agent_id)
                        if hasattr(msg, "content") and msg.content and getattr(msg, "type", None) == "ai":
                            await websocket.send_text(json.dumps({
                                "type": "chunk",
                                "content": msg.content,
                            }))
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            for tc in msg.tool_calls:
                                await websocket.send_text(json.dumps({
                                    "type": "tool_call",
                                    "name": tc.get("name", ""),
                                    "args": tc.get("args", {}),
                                }))

            # Send completion signal
            await websocket.send_text(json.dumps({"type": "done"}))

    except WebSocketDisconnect:
        logger.info("ws_disconnected", user_id=user_ctx.user_id if 'user_ctx' in dir() else "unknown")
    except Exception as e:
        logger.error("ws_error", error=str(e))
        try:
            await websocket.send_text(json.dumps({"type": "error", "content": str(e)}))
        except Exception:
            pass


def main():
    """Run the gateway server."""
    import uvicorn
    import logging
    from logging.handlers import RotatingFileHandler
    from pathlib import Path

    log_dir = Path(config.project_root) / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)

    _fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    _fmt_console = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")

    def _make_handler(filename: str) -> RotatingFileHandler:
        h = RotatingFileHandler(log_dir / filename, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
        h.setFormatter(_fmt)
        return h

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(_fmt_console)
    console_handler.addFilter(lambda r: r.name != "uvicorn.access")  # uvicorn access already prints to console

    api_file_handler = _make_handler("api.log")
    gateway_file_handler = _make_handler("gateway.log")

    # --- API access log: uvicorn.access + our custom "api.request" logger ---
    api_logger = logging.getLogger("api.request")
    api_logger.setLevel(logging.INFO)
    api_logger.handlers = [console_handler, api_file_handler]
    api_logger.propagate = False

    uvicorn_logger = logging.getLogger("uvicorn.access")
    uvicorn_logger.handlers = [console_handler, api_file_handler]
    uvicorn_logger.propagate = False

    # --- System operation log: everything else → gateway.log ---
    logging.basicConfig(
        level=log_level,
        handlers=[console_handler, gateway_file_handler],
    )

    uvicorn.run(
        "gateway.server:app",
        host=config.gateway_host,
        port=config.gateway_port,
        workers=config.gateway_workers,
        log_level=config.log_level.lower(),
        access_log=True,
    )


if __name__ == "__main__":
    main()