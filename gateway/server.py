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
from email.parser import BytesParser
from email.policy import default as email_default_policy

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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
from harness.sandbox.manager import SandboxManager
from harness.multi_agent.background import BackgroundTaskManager
from harness.evolution.three_agent import ThreeAgentVerifier
from harness.evolution.gepa import GEPAOptimizer
from harness.evolution.auto_evolve import AutoEvolver
from harness.multi_agent.subagent import SubAgentRunner
from harness.skill.plugin import PluginManager
from harness.expert.registry import AgentRegistry
from harness.expert.agent_factory import create_expert_agent
from harness.expert.types import AgentProfile, EndpointConfig
from harness.external_agent.types import ExternalEndpoint, get_adapter
from harness.external_agent.proxy import AgentProxyHandler

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
expert_registry.scan_api_profiles(Path(config.project_root))
session_mgr = SessionManager()
web_adapter = WebAdapter()
session_persistence = SessionPersistence(config.get_memory_base_dir())
heartbeat_scheduler = HeartbeatScheduler(config, interval_minutes=config.heartbeat_interval)

# Memory heartbeat task — batch-extracts cross-session facts/prefs periodically
from harness.memory.heartbeat import MemoryHeartbeatTask
memory_heartbeat_task = MemoryHeartbeatTask(memory_manager, config)
heartbeat_scheduler.register_async_task(memory_heartbeat_task, "memory_heartbeat")
cron_scheduler = CronScheduler(config)
lane_queue = LaneQueue()
dingtalk_adapter = DingTalkAdapter()
sandbox_runner = SandboxManager.from_config(config)
background_manager = BackgroundTaskManager(config, memory_manager, skill_manager, approval_checker, sandbox_runner)

# MCP manager
from harness.mcp.manager import MCPManager
from harness.middleware.tool_filter import set_mcp_manager
from runtime.tools import set_background_manager
mcp_manager = MCPManager(Path(config.project_root))
set_mcp_manager(mcp_manager)

# Register background_manager for submit_background_task tool access
set_background_manager(background_manager)


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


def require_admin(authorization: str = Header(default=None)) -> UserContext:
    """Authenticate and verify admin role. Raises 401/403 if not."""
    auth_header = authorization or ""
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    api_key = auth_header if not auth_header.startswith("Bearer ") else ""
    user_ctx = authenticate_user(api_key=api_key, token=token)
    if user_ctx.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admin can perform this action")
    return user_ctx


def authenticate_optional(authorization: str = Header(default=None)) -> UserContext | None:
    """Authenticate user if token present. Returns None if no credentials.
    Does NOT raise 401 — caller decides access level for unauthenticated users."""
    auth_header = (authorization or "").strip()
    if not auth_header:
        return None
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    api_key = auth_header if not auth_header.startswith("Bearer ") else ""
    try:
        return authenticate_user(api_key=api_key, token=token)
    except HTTPException:
        return None


def require_role_or_above(min_role: UserRole) -> callable:
    """Decorator/factory: returns a dependency that requires the caller to have min_role or higher."""
    def _check(authorization: str = Header(default=None)) -> UserContext:
        auth_header = authorization or ""
        token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
        api_key = auth_header if not auth_header.startswith("Bearer ") else ""
        user_ctx = authenticate_user(api_key=api_key, token=token)
        if user_ctx.role.level < min_role.level:
            raise HTTPException(status_code=403, detail=f"Requires {min_role.value} role or higher")
        return user_ctx
    return _check


async def read_uploaded_file(
    request: Request,
    fallback_filename: str,
    max_bytes: int = 20 * 1024 * 1024,
) -> tuple[str, bytes]:
    """Read a small uploaded file without requiring python-multipart at app import time."""
    body = await request.body()
    if len(body) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Upload is too large; max {max_bytes} bytes")

    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        raw_message = (
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode()
            + body
        )
        message = BytesParser(policy=email_default_policy).parsebytes(raw_message)
        if not message.is_multipart():
            raise HTTPException(status_code=400, detail="Invalid multipart upload")
        for part in message.iter_parts():
            if part.get_content_disposition() != "form-data":
                continue
            if part.get_param("name", header="content-disposition") != "file":
                continue
            filename = part.get_filename() or fallback_filename
            payload = part.get_payload(decode=True)
            if payload is None:
                payload = str(part.get_content()).encode("utf-8")
            return filename, payload
        raise HTTPException(status_code=400, detail="Multipart upload must include a 'file' field")

    filename = request.headers.get("x-filename") or fallback_filename
    return filename, body


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("gateway_starting", host=config.gateway_host, port=config.gateway_port)
    await mcp_manager.initialize()
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
    await mcp_manager.shutdown()
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
        agent = create_agent_for_user(user_ctx, config, memory_manager, skill_manager, approval_checker, sandbox_runner, mcp_manager=mcp_manager)
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
async def list_skills(authorization: str = Header(default=None)):
    """List available skills for the authenticated user's role."""
    user_ctx = authenticate_optional(authorization)
    if user_ctx is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    from harness.skill.types import SkillManifest

    skills = skill_manager.list_skills_for_role(user_ctx.role)
    manifest = SkillManifest(skills=skills)
    return {
        "manifest": manifest.to_text(),
        "skills": [
            {
                "name": skill.name,
                "description": skill.description,
                "category": skill.category.value,
                "access": skill.access.value,
                "version": skill.version,
                "location": skill.location,
            }
            for skill in manifest.skills
        ],
    }


@app.post("/api/skills/import-zip")
async def import_skill_zip_endpoint(
    request: Request,
    overwrite: bool = True,
    authorization: str = Header(default=None),
):
    """Import one or more Skill packages from a zip upload (admin only)."""
    user_ctx = require_admin(authorization)
    filename, content = await read_uploaded_file(request, fallback_filename="skills.zip")
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Skill import requires a .zip file")

    from zipfile import BadZipFile

    from harness.skill.importer import SkillImportError, import_skill_zip

    try:
        result = import_skill_zip(
            content,
            Path(config.project_root) / "skills" / "extensions",
            overwrite=overwrite,
        )
    except BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Invalid zip archive") from exc
    except SkillImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info(
        "skill_zip_imported",
        user_id=user_ctx.user_id,
        filename=filename,
        imported=result.imported,
        skipped=result.skipped,
    )
    return {"imported": result.imported, "skipped": result.skipped}


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
    redis_ok = False
    try:
        await memory_manager.short_term.redis.ping()
        redis_ok = True
    except Exception:
        pass
    return {
        "status": "ok",
        "version": "0.1.0",
        "redis": "connected" if redis_ok else "disconnected",
        "sandbox": sandbox_runner.healthcheck(),
    }


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
async def list_experts(authorization: str = Header(default=None)):
    """Agent marketplace — list expert agents visible to the user's role.

    Unauthenticated → viewer-level agents only.
    Authenticated → agents with role level ≤ user's role level."""
    user_ctx = authenticate_optional(authorization)
    max_level = user_ctx.role.level if user_ctx else UserRole.VIEWER.level

    all_profiles = expert_registry.list_profiles()
    visible = [p for p in all_profiles if UserRole(p.role).level <= max_level]

    return {
        "manifest": expert_registry.generate_manifest(),
        "agents": [
            {"name": p.name, "display_name": p.display_name, "description": p.description,
             "role": p.role, "skill_plugin": p.skill_plugin, "type": p.type, "source": p.source}
            for p in visible
        ],
    }


@app.post("/api/agents/{name}/chat", response_model=ExpertChatResponse)
async def chat_with_expert(name: str, request: ExpertChatRequest, authorization: str = Header(default=None)):
    """Chat directly with a specific expert agent.

    Internal agents: creates a LangChain Agent with the profile configuration.
    External agents: proxies the request to the external endpoint via HTTP.
    """
    auth_header = authorization or ""
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    api_key = auth_header if not auth_header.startswith("Bearer ") else ""
    user_ctx = authenticate_user(api_key=api_key, token=token)

    profile = expert_registry.get(name)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Expert agent '{name}' not found")

    # Check role visibility
    agent_role = UserRole(profile.role)
    if agent_role.level > user_ctx.role.level:
        raise HTTPException(status_code=403, detail="无权访问该专家智能体")

    user_ctx.user_id = request.user_id or user_ctx.user_id
    user_ctx.agent_id = name
    user_ctx.session_id = request.session_id or str(uuid.uuid4())

    # ── External agent: proxy to remote endpoint ──
    if profile.is_external and profile.endpoint:
        ext = ExternalEndpoint(
            url=profile.endpoint.url,
            protocol=profile.endpoint.protocol,
            method=profile.endpoint.method,
            auth_type=profile.endpoint.auth_type,
            auth_credential=profile.endpoint.auth_credential,
            auth_header_name=profile.endpoint.auth_header_name,
            timeout_seconds=profile.endpoint.timeout_seconds,
            headers=profile.endpoint.headers,
        )
        proxy = AgentProxyHandler(ext, ext.protocol)
        result = await proxy.invoke(request.content, user_ctx.user_id, user_ctx.session_id)
        await proxy.close()

        if result.error:
            raise HTTPException(status_code=result.status_code, detail=result.error)

        # Persist the exchange
        session_persistence.write_message(
            user_ctx.user_id, user_ctx.session_id,
            {"timestamp": "", "type": "human", "content": request.content}, agent_id=name,
        )
        session_persistence.write_message(
            user_ctx.user_id, user_ctx.session_id,
            {"timestamp": "", "type": "ai", "content": result.content}, agent_id=name,
        )
        return ExpertChatResponse(content=result.content, session_id=user_ctx.session_id)

    # ── Internal agent: create LangChain Agent ──
    root = Path(config.project_root)
    soul_content = expert_registry.load_soul_content(name, root)

    agent = create_expert_agent(
        profile, soul_content, user_ctx, config,
        memory_manager, skill_manager, approval_checker, sandbox_runner,
        mcp_manager=mcp_manager,
    )

    session_key = session_mgr.create_session_key(ChannelType.WEB, user_ctx.user_id, expert_id=name)
    await lane_queue.acquire(session_key)
    try:
        memory_manager.init_user(user_ctx.user_id)
        result = agent.invoke(
            {"messages": [{"role": "user", "content": request.content}]},
            config={"configurable": {"context": user_ctx}},
        )

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


# --- MCP Server Management API (admin only) ---


class MCPServerRequest(BaseModel):
    name: str
    transport: str = "stdio"
    command: str = ""
    args: list[str] = []
    url: str = ""
    enabled: bool = True
    env: dict[str, str] = {}


class ResourceRolesRequest(BaseModel):
    roles: list[str]


@app.get("/api/mcp/servers")
async def list_mcp_servers(authorization: str = Header(default=None)):
    """List all configured MCP servers."""
    require_admin(authorization)

    servers = mcp_manager.list_servers()
    return {
        "servers": [
            {"name": s.name, "transport": s.transport, "command": s.command,
             "args": s.args, "url": s.url, "enabled": s.enabled}
            for s in servers
        ]
    }


@app.get("/api/mcp/servers/{name:path}")
async def get_mcp_server(name: str, authorization: str = Header(default=None)):
    """Get MCP server details and discovered tools."""
    require_admin(authorization)

    config = mcp_manager.get_server(name)
    if not config:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
    tools = mcp_manager.get_server_tools(name)
    return {
        "config": {"name": config.name, "transport": config.transport, "command": config.command,
                   "args": config.args, "url": config.url, "enabled": config.enabled},
        "tools": [{"server_name": t.server_name, "tool_name": t.tool_name, "description": t.description} for t in tools],
    }


@app.post("/api/mcp/servers")
async def create_mcp_server(req: MCPServerRequest, authorization: str = Header(default=None)):
    """Create a new MCP server configuration (admin only)."""
    require_admin(authorization)

    from harness.mcp.types import MCPServerConfig
    cfg = MCPServerConfig(
        name=req.name, transport=req.transport, command=req.command,
        args=req.args, url=req.url, enabled=req.enabled, env=req.env,
    )
    await mcp_manager.add_server(cfg)
    return {"message": f"MCP server '{req.name}' created", "name": req.name}


@app.post("/api/mcp/servers/import")
async def import_mcp_servers(
    request: Request,
    overwrite: bool = True,
    authorization: str = Header(default=None),
):
    """Import MCP server configurations from JSON/YAML upload (admin only)."""
    user_ctx = require_admin(authorization)
    filename, content = await read_uploaded_file(request, fallback_filename="mcp.yaml")
    lower_name = filename.lower()
    if not lower_name.endswith((".json", ".yaml", ".yml")):
        raise HTTPException(status_code=400, detail="MCP import requires a .json, .yaml, or .yml file")

    from harness.mcp.importer import MCPImportError, parse_mcp_server_configs

    try:
        server_configs = parse_mcp_server_configs(content, filename)
    except MCPImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid MCP config: {exc}") from exc

    imported: list[str] = []
    skipped: list[str] = []
    errors: list[dict[str, str]] = []
    for server_config in server_configs:
        existing = mcp_manager.get_server(server_config.name)
        if existing and not overwrite:
            skipped.append(server_config.name)
            continue
        if existing:
            await mcp_manager.remove_server(server_config.name)
        try:
            await mcp_manager.add_server(server_config)
            imported.append(server_config.name)
        except Exception as exc:
            if mcp_manager.get_server(server_config.name):
                imported.append(server_config.name)
            errors.append({"name": server_config.name, "error": str(exc)})
            logger.warning(
                "mcp_import_connect_failed",
                user_id=user_ctx.user_id,
                server=server_config.name,
                exc_info=True,
            )

    logger.info(
        "mcp_servers_imported",
        user_id=user_ctx.user_id,
        filename=filename,
        imported=imported,
        skipped=skipped,
        errors=len(errors),
    )
    return {"imported": imported, "skipped": skipped, "errors": errors}


@app.put("/api/mcp/servers/{name}")
async def update_mcp_server(name: str, req: MCPServerRequest, authorization: str = Header(default=None)):
    """Update an MCP server configuration (admin only)."""
    require_admin(authorization)

    existing = mcp_manager.get_server(name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")

    from harness.mcp.types import MCPServerConfig
    cfg = MCPServerConfig(
        name=name, transport=req.transport, command=req.command,
        args=req.args, url=req.url, enabled=req.enabled, env=req.env,
    )
    await mcp_manager.remove_server(name)
    await mcp_manager.add_server(cfg)
    return {"message": f"MCP server '{name}' updated", "name": name}


@app.delete("/api/mcp/servers/{name}")
async def delete_mcp_server(name: str, authorization: str = Header(default=None)):
    """Delete an MCP server configuration (admin only)."""
    require_admin(authorization)
    removed = await mcp_manager.remove_server(name)
    if not removed:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
    return {"deleted": name}


@app.post("/api/mcp/servers/{name}/connect")
async def connect_mcp_server(name: str, authorization: str = Header(default=None)):
    """Connect/reconnect to an MCP server (admin only)."""
    require_admin(authorization)
    tools = await mcp_manager.connect_server(name)
    return {"status": "connected", "server": name, "tools": len(tools)}


@app.post("/api/mcp/servers/{name}/disconnect")
async def disconnect_mcp_server(name: str, authorization: str = Header(default=None)):
    """Disconnect from an MCP server (admin only)."""
    require_admin(authorization)
    await mcp_manager.disconnect_server(name)
    return {"status": "disconnected", "server": name}


@app.get("/api/rbac/resources")
async def list_rbac_resources(authorization: str = Header(default=None)):
    """List skills and MCP servers with their RBAC role assignments."""
    require_admin(authorization)

    from harness.security import rbac

    all_skills = skill_manager.list_skills() if hasattr(skill_manager, "list_skills") else []
    servers = mcp_manager.list_servers()

    return {
        "roles": [role.value for role in UserRole],
        "skills": [
            {
                "name": skill.name,
                "description": skill.description,
                "access": skill.access.value if hasattr(skill.access, "value") else str(skill.access),
                "roles": [
                    role.value
                    for role in rbac.roles_for_skill(skill.name, all_skills)
                ],
            }
            for skill in all_skills
        ],
        "mcp_servers": [
            {
                "name": server.name,
                "enabled": server.enabled,
                "roles": [
                    role.value
                    for role in rbac.roles_for_mcp_server(server.name)
                ],
            }
            for server in servers
        ],
    }


@app.put("/api/rbac/skills/{skill_name:path}/roles")
async def update_skill_roles(
    skill_name: str,
    req: ResourceRolesRequest,
    authorization: str = Header(default=None),
):
    """Update exact RBAC role assignments for a skill."""
    require_admin(authorization)

    from harness.security import rbac

    all_skills = skill_manager.list_skills() if hasattr(skill_manager, "list_skills") else []
    if not any(skill.name == skill_name for skill in all_skills):
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    try:
        roles = rbac.normalize_roles(req.roles)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rbac.set_skill_roles(skill_name, roles, all_skills)
    return {
        "name": skill_name,
        "roles": [role.value for role in rbac.roles_for_skill(skill_name, all_skills)],
    }


@app.put("/api/rbac/mcp-servers/{server_name:path}/roles")
async def update_mcp_server_roles(
    server_name: str,
    req: ResourceRolesRequest,
    authorization: str = Header(default=None),
):
    """Update exact RBAC role assignments for an MCP server."""
    require_admin(authorization)

    if mcp_manager.get_server(server_name) is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' not found")

    from harness.security import rbac

    try:
        roles = rbac.normalize_roles(req.roles)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rbac.set_mcp_server_roles(server_name, roles)
    return {
        "name": server_name,
        "roles": [role.value for role in rbac.roles_for_mcp_server(server_name)],
    }


@app.get("/api/mcp/tools")
async def list_mcp_tools(role: str = "", authorization: str = Header(default=None)):
    """List discovered MCP tools filtered by the caller's role.
    Requires auth. Returns only tools the caller's role is allowed to use."""
    user_ctx = authenticate_optional(authorization)
    if user_ctx is None:
        return {"tools": []}

    from harness.security.rbac import get_role_mcp_tool_access, mcp_tool_allowed
    allowed = get_role_mcp_tool_access().get(user_ctx.role, [])

    all_tools = [
        t for t in mcp_manager.get_all_tools_info()
        if mcp_tool_allowed(t.full_name, allowed)
    ]

    # Further filter by requested role (for admin viewing other roles)
    if role:
        try:
            target = UserRole(role)
            target_allowed = get_role_mcp_tool_access().get(target, [])
            all_tools = [
                t for t in all_tools
                if mcp_tool_allowed(t.full_name, target_allowed)
            ]
        except ValueError:
            pass

    return {
        "tools": [{"server_name": t.server_name, "tool_name": t.tool_name, "full_name": t.full_name,
                    "description": t.description} for t in all_tools]
    }


# --- Expert Agent CRUD API (admin only) ---


class AgentEndpointRequest(BaseModel):
    url: str
    protocol: str = "openai-chat"
    method: str = "POST"
    auth_type: str = "none"
    auth_credential: str = ""
    auth_header_name: str = "Authorization"
    timeout_seconds: int = 120
    headers: dict[str, str] = {}


class CreateAgentRequest(BaseModel):
    name: str
    display_name: str
    description: str
    soul_content: str = ""
    role: str = "operator"
    type: str = "internal"
    skills: list[str] = []
    mcp_tools: list[str] = []
    model_preference: str = "primary"
    max_context_tokens: int = 32000
    endpoint: AgentEndpointRequest | None = None


class UpdateAgentRequest(BaseModel):
    display_name: str | None = None
    description: str | None = None
    soul_content: str | None = None
    role: str | None = None
    type: str | None = None
    skills: list[str] | None = None
    mcp_tools: list[str] | None = None
    model_preference: str | None = None
    max_context_tokens: int | None = None
    endpoint: AgentEndpointRequest | None = None


@app.get("/api/agents/manage")
async def list_manageable_agents(authorization: str = Header(default=None)):
    """List all expert agents (file-based and API-created). Admin only."""
    require_admin(authorization)
    return {
        "agents": [
            {
                "name": p.name, "display_name": p.display_name, "description": p.description,
                "role": p.role, "skill_plugin": p.skill_plugin, "model_preference": p.model_preference,
                "max_context_tokens": p.max_context_tokens, "skills": p.skills, "mcp_tools": p.mcp_tools,
                "source": p.source, "type": p.type,
                "endpoint": p.endpoint.model_dump() if p.endpoint else None,
                "created_by": p.created_by, "created_at": p.created_at, "updated_at": p.updated_at,
            }
            for p in expert_registry.list_profiles()
        ]
    }


@app.post("/api/agents/manage")
async def create_agent(req: CreateAgentRequest, authorization: str = Header(default=None)):
    """Create a new expert agent (admin only). Supports internal and external types."""
    user_ctx = require_admin(authorization)

    if expert_registry.get(req.name):
        raise HTTPException(status_code=409, detail=f"Agent '{req.name}' already exists")

    is_external = req.type == "external"

    from harness.expert.validator import ExpertAgentValidator

    if is_external:
        # External agents don't need SOUL/Skills/MCP — they have their own
        valid_skills = []
        valid_mcp = []
        soul_path = ""
    else:
        all_skills = skill_manager.list_skills() if hasattr(skill_manager, "list_skills") else []
        try:
            valid_skills = ExpertAgentValidator.validate_skills_from_profile(req.role, req.skills, all_skills)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        valid_mcp = ExpertAgentValidator.validate_mcp_tools_from_profile(req.role, req.mcp_tools)
        soul_path = str(expert_registry.store.save_soul(req.name, req.soul_content))

    # Build endpoint config
    endpoint_config = None
    if is_external and req.endpoint:
        endpoint_config = EndpointConfig(
            url=req.endpoint.url,
            protocol=req.endpoint.protocol,
            method=req.endpoint.method,
            auth_type=req.endpoint.auth_type,
            auth_credential=req.endpoint.auth_credential,
            auth_header_name=req.endpoint.auth_header_name,
            timeout_seconds=req.endpoint.timeout_seconds,
            headers=req.endpoint.headers,
        )

    profile = AgentProfile(
        name=req.name,
        display_name=req.display_name,
        description=req.description,
        soul_file=soul_path,
        role=req.role,
        type=req.type,
        skills=valid_skills,
        mcp_tools=valid_mcp,
        model_preference=req.model_preference,
        max_context_tokens=req.max_context_tokens,
        endpoint=endpoint_config,
        source="api",
        created_by=user_ctx.user_id,
    )
    expert_registry.store.save(profile)
    expert_registry.register(profile)

    logger.info("expert_agent_created", name=req.name, type=req.type, role=req.role, by=user_ctx.user_id)
    return {"message": f"Agent '{req.name}' created", "agent": profile.model_dump()}


@app.get("/api/agents/manage/{name}")
async def get_agent(name: str, authorization: str = Header(default=None)):
    """Get expert agent details. Admin only."""
    require_admin(authorization)
    profile = expert_registry.get(name)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    root = Path(config.project_root)
    soul_content = expert_registry.load_soul_content(name, root)
    return {"agent": profile.model_dump(), "soul_content": soul_content}


@app.put("/api/agents/manage/{name}")
async def update_agent(name: str, req: UpdateAgentRequest, authorization: str = Header(default=None)):
    """Update an expert agent (admin only, API-created only). Supports internal and external types."""
    user_ctx = require_admin(authorization)
    profile = expert_registry.get(name)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    if profile.source == "file":
        raise HTTPException(status_code=403, detail="Cannot modify file-based agents. Edit the profile.yaml directly.")

    if req.display_name is not None:
        profile.display_name = req.display_name
    if req.description is not None:
        profile.description = req.description
    if req.role is not None:
        profile.role = req.role
    if req.type is not None:
        profile.type = req.type

    from harness.expert.validator import ExpertAgentValidator

    # If switching to external, skip skill/mcp/soul validation
    is_external = profile.type == "external"

    if not is_external and (req.skills is not None or req.role is not None):
        all_skills = skill_manager.list_skills() if hasattr(skill_manager, "list_skills") else []
        try:
            profile.skills = ExpertAgentValidator.validate_skills_from_profile(
                profile.role,
                req.skills if req.skills is not None else profile.skills,
                all_skills,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not is_external and (req.mcp_tools is not None or req.role is not None):
        profile.mcp_tools = ExpertAgentValidator.validate_mcp_tools_from_profile(
            profile.role,
            req.mcp_tools if req.mcp_tools is not None else profile.mcp_tools,
        )
    if req.model_preference is not None:
        profile.model_preference = req.model_preference
    if req.max_context_tokens is not None:
        profile.max_context_tokens = req.max_context_tokens

    if req.soul_content is not None and not is_external:
        expert_registry.store.save_soul(name, req.soul_content)
        profile.soul_file = str(expert_registry.store.get_soul_path(name))

    if req.endpoint is not None:
        profile.endpoint = EndpointConfig(
            url=req.endpoint.url, protocol=req.endpoint.protocol,
            method=req.endpoint.method, auth_type=req.endpoint.auth_type,
            auth_credential=req.endpoint.auth_credential,
            auth_header_name=req.endpoint.auth_header_name,
            timeout_seconds=req.endpoint.timeout_seconds,
            headers=req.endpoint.headers,
        )

    profile.updated_at = ""
    expert_registry.store.save(profile)
    expert_registry.register(profile)

    logger.info("expert_agent_updated", name=name, type=profile.type, by=user_ctx.user_id)
    return {"message": f"Agent '{name}' updated", "agent": profile.model_dump()}


@app.post("/api/agents/manage/{name}/test-connection")
async def test_agent_connection(name: str, authorization: str = Header(default=None)):
    """Test connectivity to an external agent's endpoint (admin only)."""
    require_admin(authorization)
    profile = expert_registry.get(name)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    if not profile.is_external or not profile.endpoint:
        raise HTTPException(status_code=400, detail="Only external agents support connection testing")

    ext = ExternalEndpoint(
        url=profile.endpoint.url, protocol=profile.endpoint.protocol,
        method=profile.endpoint.method, auth_type=profile.endpoint.auth_type,
        auth_credential=profile.endpoint.auth_credential,
        auth_header_name=profile.endpoint.auth_header_name,
        timeout_seconds=profile.endpoint.timeout_seconds,
        headers=profile.endpoint.headers,
    )
    proxy = AgentProxyHandler(ext, ext.protocol)
    result = await proxy.test_connection()
    await proxy.close()
    return result


@app.delete("/api/agents/manage/{name}")
async def delete_agent(name: str, authorization: str = Header(default=None)):
    """Delete an expert agent (admin only, API-created only)."""
    user_ctx = require_admin(authorization)
    profile = expert_registry.get(name)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    if profile.source == "file":
        raise HTTPException(status_code=403, detail="Cannot delete file-based agents. Remove the profile.yaml directly.")

    expert_registry.store.delete(name)
    expert_registry.unregister(name)
    logger.info("expert_agent_deleted", name=name, by=user_ctx.user_id)
    return {"deleted": name}


# --- Role-filtered Skill and MCP Tool listing ---


@app.get("/api/roles/{role}/skills")
async def get_role_skills(role: str, authorization: str = Header(default=None)):
    """List skills available for a specific role (used in agent creation form).
    Requires auth. User can only query roles at or below their own level."""
    user_ctx = authenticate_optional(authorization)
    if user_ctx is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        target_role = UserRole(role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {role}")

    # Prevent privilege escalation: can only query own level or below
    if target_role.level > user_ctx.role.level:
        target_role = user_ctx.role

    from harness.expert.validator import ExpertAgentValidator
    from harness.security.rbac import role_allows_skill

    skill_list = skill_manager.list_skills() if hasattr(skill_manager, 'list_skills') else []
    result = []
    for skill in skill_list:
        result.append({
            "name": skill.name if hasattr(skill, 'name') else str(skill),
            "description": skill.description if hasattr(skill, 'description') else "",
            "access": skill.access.value if hasattr(skill, 'access') else "unknown",
            "allowed": role_allows_skill(target_role, skill),
        })
    return {"role": target_role.value, "skill_access": ExpertAgentValidator.get_role_skill_level(target_role.value), "skills": result}


@app.get("/api/roles/{role}/mcp-tools")
async def get_role_mcp_tools(role: str, authorization: str = Header(default=None)):
    """List MCP tools available for a specific role (used in agent creation form).
    Requires auth. User can only query roles at or below their own level."""
    user_ctx = authenticate_optional(authorization)
    if user_ctx is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        target_role = UserRole(role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {role}")

    # Prevent privilege escalation: can only query own level or below
    if target_role.level > user_ctx.role.level:
        target_role = user_ctx.role

    from harness.expert.validator import ExpertAgentValidator
    from harness.security.rbac import mcp_tool_allowed
    allowed = ExpertAgentValidator.get_role_mcp_tools(target_role.value)
    all_tools = mcp_manager.get_all_tools_info()

    result = []
    for tool in all_tools:
        result.append({
            "name": tool.full_name,
            "server_name": tool.server_name,
            "tool_name": tool.tool_name,
            "description": tool.description,
            "allowed": mcp_tool_allowed(tool.full_name, allowed),
        })
    return {"role": target_role.value, "mcp_tools": result}


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
        agent = create_agent_for_user(user_ctx, config, memory_manager, skill_manager, approval_checker, sandbox_runner, mcp_manager=mcp_manager)
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

        # Determine agent type: external (proxy) vs internal (LangChain) vs generic
        is_external = False
        external_proxy = None
        profile = None

        if agent_id and expert_registry.get(agent_id):
            profile = expert_registry.get(agent_id)
            agent_role = UserRole(profile.role)
            if agent_role.level > user_ctx.role.level:
                await websocket.send_text(json.dumps({"type": "error", "content": "无权访问该专家智能体"}))
                await websocket.close(code=4003)
                return

            if profile.is_external and profile.endpoint:
                is_external = True
                ext = ExternalEndpoint(
                    url=profile.endpoint.url, protocol=profile.endpoint.protocol,
                    method=profile.endpoint.method, auth_type=profile.endpoint.auth_type,
                    auth_credential=profile.endpoint.auth_credential,
                    auth_header_name=profile.endpoint.auth_header_name,
                    timeout_seconds=profile.endpoint.timeout_seconds,
                    headers=profile.endpoint.headers,
                )
                external_proxy = AgentProxyHandler(ext, ext.protocol)
                logger.info("agent_created", agent_type="external", agent_id=agent_id, user_id=user_id)
            else:
                root = Path(config.project_root)
                soul_content = expert_registry.load_soul_content(agent_id, root)
                agent = create_expert_agent(
                    profile, soul_content, user_ctx, config,
                    memory_manager, skill_manager, approval_checker, sandbox_runner,
                    mcp_manager=mcp_manager,
                )
                logger.info("agent_created", agent_type="expert", agent_id=agent_id, user_id=user_id, session_id=user_ctx.session_id)
        else:
            agent = create_agent_for_user(user_ctx, config, memory_manager, skill_manager, approval_checker, sandbox_runner, mcp_manager=mcp_manager)
            logger.info("agent_created", agent_type="generic", user_id=user_id, session_id=user_ctx.session_id)

        # Send session info
        await websocket.send_text(json.dumps({
            "type": "session_start",
            "user_id": user_ctx.user_id,
            "session_id": user_ctx.session_id,
            "agent_id": agent_id,
            "agent_type": "external" if is_external else ("expert" if profile else "generic"),
        }))

        logger.info("ws_connected", user_id=user_ctx.user_id, session_id=user_ctx.session_id)

        # Chat loop
        while True:
            data = await websocket.receive_text()
            msg_data = json.loads(data)
            user_message = msg_data.get("content", "")

            if not user_message:
                continue

            logger.info("chat_message_received", user_id=user_id, session_id=user_ctx.session_id, agent_id=agent_id, msg_len=len(user_message))

            if is_external:
                # ── External agent: stream via HTTP proxy ──
                full_response = ""
                async for chunk_text in external_proxy.stream(user_message, user_ctx.user_id, user_ctx.session_id):
                    full_response += chunk_text
                    await websocket.send_text(json.dumps({"type": "chunk", "content": chunk_text}))

                # Persist exchange
                session_persistence.write_message(
                    user_ctx.user_id, user_ctx.session_id,
                    {"timestamp": "", "type": "human", "content": user_message}, agent_id=agent_id,
                )
                session_persistence.write_message(
                    user_ctx.user_id, user_ctx.session_id,
                    {"timestamp": "", "type": "ai", "content": full_response}, agent_id=agent_id,
                )
            else:
                # ── Internal agent: LangChain stream ──
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
    finally:
        if external_proxy:
            await external_proxy.close()


# Mount frontend static files in production mode
if config.serve_static:
    from fastapi.responses import FileResponse
    _static_root = Path(config.project_root) / config.static_dir
    if _static_root.is_dir():
        # Serve /assets and other subdirectories as static files
        for _sub in _static_root.iterdir():
            if _sub.is_dir():
                app.mount(f"/{_sub.name}", StaticFiles(directory=str(_sub)), name=f"static-{_sub.name}")

        # SPA fallback: serve index.html for all paths that don't match a static file or API route
        @app.get("/{_full_path:path}")
        async def _serve_spa(_full_path: str):
            # Try to serve a matching static file first (e.g. /vite.svg)
            _file = (_static_root / _full_path).resolve()
            try:
                _file.relative_to(_static_root.resolve())
            except ValueError:
                raise HTTPException(status_code=404)
            if _file.is_file():
                return FileResponse(str(_file))
            # SPA fallback
            _index = _static_root / "index.html"
            if _index.is_file():
                return FileResponse(str(_index))
            raise HTTPException(status_code=404, detail="Frontend not found")

        logger.info("frontend_static_mounted", directory=str(_static_root))
    else:
        logger.warning("static_dir_not_found", directory=str(_static_root))


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
