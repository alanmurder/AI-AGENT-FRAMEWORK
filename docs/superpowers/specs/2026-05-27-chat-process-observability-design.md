# Chat Process Observability Design

Date: 2026-05-27

## Goal

Improve the chat output so users can see the public process around an Agent response:

- which Skills were loaded and enabled for the current session;
- which Skill the Agent explicitly says it is using while answering;
- which tools are called during the response;
- matching backend logs for Skill loading, Skill-use declarations, process updates, and tool calls.

This must not expose private chain-of-thought. The UI should show concise, auditable process summaries such as "loaded Skills", "using Skill", "calling tool", and "generating answer".

## Current State

The WebSocket chat path in `gateway/server.py` streams `chunk`, `tool_call`, and `done` events from `agent.stream(..., stream_mode="updates")`. The frontend stores streamed text and active tool calls in `web/src/store/chatStore.ts`, renders tool calls with `ToolCallCard`, and renders the answer with `StreamOutput`.

Skills are currently injected by `MemoryInjectionMiddleware` through a prompt manifest generated from `SkillManager`. There is no user-facing event that shows which Skills were injected, and no explicit runtime event for "the Agent is using this Skill". Backend logging already uses `structlog` and writes to `data/logs/gateway.log`.

## Proposed Approach

Use a unified process event stream over the existing WebSocket connection.

Add structured event types alongside the existing `chunk`, `tool_call`, and `done` messages:

- `skill_manifest`: emitted once after session start for internal Agents, listing the role-filtered Skills available in this session.
- `skill_use`: emitted when the Agent explicitly declares it is using a Skill for the current answer.
- `progress`: emitted for public status updates such as "preparing response" or "generating answer".

Tool calls remain `tool_call`, but should include stable metadata when available: `id`, `session_id`, and `agent_id`.

The frontend will keep one ordered process timeline per streamed answer. The timeline will be shown in a compact process panel near the streaming response, with loaded Skills, declared Skill use, progress messages, and tool calls. The final AI message will retain its timeline so historical messages can display the same process information after streaming finishes.

## Event Schema

Extend `StreamEvent` with:

```json
{
  "type": "skill_manifest",
  "skills": [
    {
      "name": "file_manager",
      "description": "Read and write files",
      "category": "file_manager"
    }
  ],
  "role": "operator",
  "session_id": "..."
}
```

```json
{
  "type": "skill_use",
  "name": "knowledge_search",
  "phase": "answering",
  "reason": "Searching internal knowledge before answering",
  "session_id": "..."
}
```

```json
{
  "type": "progress",
  "stage": "generating_answer",
  "content": "Generating answer",
  "session_id": "..."
}
```

Existing `tool_call` events should become:

```json
{
  "type": "tool_call",
  "id": "call_...",
  "name": "file_read",
  "args": {},
  "session_id": "...",
  "agent_id": "..."
}
```

## Skill Loading Events

The canonical source for loaded Skills is the backend, not model output.

When an internal Agent session starts, the gateway should derive the same role/profile-filtered Skills that `MemoryInjectionMiddleware` will inject:

- generic Agent: `skill_manager.list_skills_for_role(user_ctx.role)`;
- expert Agent: role-filtered Skills further limited by `profile.skills`.

The gateway sends a `skill_manifest` event after `session_start` and logs `chat_skill_manifest_loaded` with `user_id`, `session_id`, `agent_id`, `role`, and `skill_names`.

This event represents "available and injected for this session", not proof that the Agent used every Skill.

## Explicit Skill Use

The Agent needs a public protocol for declaring Skill use. The system prompt should add a small instruction:

> When you decide to use a Skill, first emit a concise public process marker in the form `[skill_use name="..." phase="..." reason="..."]`. Do not include private reasoning.

The gateway will parse these markers out of AI content during streaming:

- convert them to `skill_use` events;
- remove the marker text from the visible answer content;
- log `chat_skill_use_declared`.

Only Skill names present in the session `skill_manifest` should be accepted. Unknown names should be ignored from the UI and logged as `chat_skill_use_ignored`.

This keeps "loaded Skills" grounded in backend state and "using Skill" grounded in an explicit Agent declaration.

## Frontend Design

Add process data to chat state:

- `activeProcessEvents`: ordered events for the current streamed answer;
- `process_events` on final `Message` objects for history and replay.

Add a compact `ProcessTimeline` component:

- default collapsed;
- summary line shows loaded Skill count, declared Skill-use count, and tool-call count;
- expanded view shows each process event in order;
- tool call rows can reuse or wrap `ToolCallCard`;
- loaded Skills are grouped to avoid a long noisy timeline when many Skills are available.

`ChatPage` should render the timeline for both historical AI messages and the active streaming answer. Existing chat bubbles remain the primary reading surface.

## Backend Logging

Use the existing `structlog` logger and `gateway.log`.

Add structured logs:

- `chat_skill_manifest_loaded`
- `chat_skill_use_declared`
- `chat_skill_use_ignored`
- `chat_tool_call_emitted`
- `chat_progress_emitted`

Each log should include `user_id`, `session_id`, `agent_id`, and any event-specific fields. Tool arguments should be logged as structured metadata, but large or sensitive values should be truncated before logging.

## Persistence

Extend session JSONL records to support optional `process_events` on AI messages. During each WebSocket turn:

- the gateway keeps process events in a per-turn list;
- the frontend keeps the same events in `activeProcessEvents` for live rendering;
- when the turn ends, the frontend attaches active process events to the final AI message in state;
- the backend writes the accumulated per-turn `process_events` on the final AI message record for that turn.

If the current LangGraph stream emits multiple AI messages for one turn, only the final persisted AI message should carry the full `process_events` list. Intermediate AI chunks should remain visible as stream chunks, not separate history records with partial process metadata.

Existing session files without `process_events` must continue to load normally.

## Error Handling

- If Skill listing fails, send no `skill_manifest` event and log a warning; chat should continue.
- If a malformed Skill-use marker appears, remove nothing and render content normally.
- If a declared Skill is unavailable for the session, do not show it as used; log the ignored declaration.
- External Agents are out of scope for Skill manifest and Skill-use parsing in this iteration because their Skills are owned by the external service. Their normal `chunk` and `done` behavior remains unchanged.

## Testing

Backend unit tests:

- serialize and persist messages with optional `process_events`;
- build the session Skill manifest for generic and expert Agents;
- parse valid Skill-use markers and strip them from visible content;
- ignore unknown Skill names;
- emit/log tool-call metadata without breaking existing `tool_call` behavior.

Frontend tests:

- `chatStore` handles `skill_manifest`, `skill_use`, `progress`, and enriched `tool_call`;
- `finalizeStream` attaches active process events to the AI message;
- `ProcessTimeline` renders collapsed summaries and expanded details.

Integration-level smoke check:

- run a chat message through WebSocket and confirm the browser receives `session_start`, `skill_manifest`, optional process/tool events, answer chunks, and `done` in order.

## Non-Goals

- Exposing private chain-of-thought or raw hidden model reasoning.
- Full distributed tracing across all middleware.
- Changing external Agent protocol behavior.
- Replacing existing session JSONL format.
- Building a separate observability dashboard.
