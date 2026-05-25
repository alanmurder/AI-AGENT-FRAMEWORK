"""AgentProxyHandler — HTTP proxy forwarding to external agent/workflow endpoints."""

import os
import json
import asyncio
import structlog
from collections.abc import AsyncIterator

import httpx

from harness.external_agent.types import (
    ExternalEndpoint, ProxyResult, get_adapter,
)

logger = structlog.get_logger()


class AgentProxyHandler:
    """Forwards chat requests to external agent/workflow endpoints.

    Supports:
    - Synchronous invoke (for REST API)
    - Streaming invoke via SSE (for WebSocket)
    - Connection testing
    """

    def __init__(self, endpoint: ExternalEndpoint, protocol: str = "openai-chat"):
        self.endpoint = endpoint
        self.protocol = protocol
        self._adapter = get_adapter(protocol)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.endpoint.timeout_seconds)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def invoke(
        self, message: str, user_id: str = "default", session_id: str = "",
        history: list[dict] | None = None,
    ) -> ProxyResult:
        """Synchronous (non-streaming) call to the external endpoint."""
        headers = self._adapter.build_headers(self.endpoint)
        body = self._adapter.build_request(message, user_id, session_id, self.endpoint, history)
        body["stream"] = False

        client = await self._get_client()
        try:
            resp = await client.request(
                method=self.endpoint.method,
                url=self.endpoint.url,
                headers=headers,
                json=body,
            )
            data = resp.json()
            content = self._adapter.extract_response(data)
            logger.info("external_agent_response", url=self.endpoint.url, status=resp.status_code)
            return ProxyResult(content=content, status_code=resp.status_code, metadata=data)
        except httpx.TimeoutException:
            logger.warning("external_agent_timeout", url=self.endpoint.url)
            return ProxyResult(content="", error="External agent request timed out", status_code=504)
        except Exception as e:
            logger.error("external_agent_error", url=self.endpoint.url, error=str(e))
            return ProxyResult(content="", error=str(e), status_code=502)

    async def stream(
        self, message: str, user_id: str = "default", session_id: str = "",
        history: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        """Streaming call (SSE) to the external endpoint. Yields text chunks."""
        headers = self._adapter.build_headers(self.endpoint)
        body = self._adapter.build_request(message, user_id, session_id, self.endpoint, history)
        body["stream"] = True

        client = await self._get_client()
        try:
            async with client.stream(
                method=self.endpoint.method,
                url=self.endpoint.url,
                headers=headers,
                json=body,
            ) as response:
                if response.status_code >= 400:
                    logger.warning("external_agent_stream_error", url=self.endpoint.url, status=response.status_code)
                    yield f"[外部智能体返回错误: HTTP {response.status_code}]"
                    return

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            return
                        try:
                            data = json.loads(data_str)
                            chunk = self._adapter.extract_stream_chunk(data)
                            if chunk:
                                yield chunk
                        except json.JSONDecodeError:
                            continue
        except httpx.TimeoutException:
            yield "[外部智能体请求超时]"
        except Exception as e:
            logger.error("external_agent_stream_error", url=self.endpoint.url, error=str(e))
            yield f"[外部智能体连接错误: {str(e)}]"

    async def test_connection(self) -> dict:
        """Test connectivity to the external endpoint with a simple ping request."""
        headers = self._adapter.build_headers(self.endpoint)
        body = self._adapter.build_request("__ping__", "test", "test", self.endpoint)
        body["stream"] = False

        client = await self._get_client()
        try:
            resp = await client.request(
                method=self.endpoint.method,
                url=self.endpoint.url,
                headers=headers,
                json=body,
            )
            return {
                "reachable": True,
                "status_code": resp.status_code,
                "response_preview": str(resp.json())[:200],
            }
        except httpx.TimeoutException:
            return {"reachable": False, "error": "Connection timed out"}
        except Exception as e:
            return {"reachable": False, "error": str(e)}
