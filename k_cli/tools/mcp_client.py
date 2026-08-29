"""
mcp_client.py - Universal Model Context Protocol (MCP) Client & Manager for K-CLI
Project Bankai Engine

Complete implementation of the Model Context Protocol (MCP) client specification (JSON-RPC 2.0).
Supports:
1. Standard MCP Transports:
   - StdioClientTransport: Subprocess stdin/stdout communication (Node/npx, Python, native binaries)
   - HttpClientTransport: Direct HTTP POST JSON-RPC 2.0 communication
   - SSEClientTransport: Server-Sent Events (SSE) stream + HTTP POST message endpoint
2. MCPClient:
   - Lifecycle management (initialize, notifications/initialized, ping, close)
   - Tool discovery & invocation (tools/list, tools/call)
   - Resource access (resources/list, resources/read, resources/templates/list)
   - Prompt templates (prompts/list, prompts/get)
   - Tool schema conversion (OpenAI, Anthropic, Gemini function schemas)
3. MCPManager:
   - Multi-server orchestrator & configuration loader (.kcli/mcp.json, ~/.kcli/mcp.json)
   - Server lifecycle routing & auto-connect
   - Aggregated tool, resource, and prompt catalogs
   - Namespaced & direct tool invocation
4. CLI Helper functions & programmatic utilities
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import re
import shlex
import shutil
import sys
import time
import urllib.parse
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Tuple, TypeVar, Union

import httpx

# Configure module-level logger
logger = logging.getLogger("k_cli.mcp_client")

# Protocol Constants
LATEST_PROTOCOL_VERSION = "2024-11-05"
SUPPORTED_PROTOCOL_VERSIONS = [
    "2024-11-05",
    "2024-10-07",
    "0.1.0",
]
JSONRPC_VERSION = "2.0"
CLIENT_INFO = {
    "name": "k-cli",
    "version": "0.3.0",
}

# Standard JSON-RPC 2.0 Error Codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


# ==============================================================================
# 0. Sync / Async Compatibility Runner
# ==============================================================================

T = TypeVar("T")


def run_sync(coro: Coroutine[Any, Any, T]) -> T:
    """
    Executes a coroutine synchronously from both sync threads and active asyncio event loops.
    Prevents 'RuntimeError: This event loop is already running'.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We are inside an active event loop. Run in a dedicated worker thread.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lambda: asyncio.run(coro))
            return future.result()
    else:
        return asyncio.run(coro)


# ==============================================================================
# 1. Exceptions
# ==============================================================================

class MCPError(Exception):
    """Base exception for all Model Context Protocol errors."""
    pass


class MCPTransportError(MCPError):
    """Raised when transport communication fails or disconnects unexpectedly."""
    pass


class MCPProtocolError(MCPError):
    """Raised when a JSON-RPC 2.0 protocol violation or server error occurs."""

    def __init__(self, message: str, code: Optional[int] = None, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class MCPTimeoutError(MCPError):
    """Raised when an MCP operation or request times out."""
    pass


class MCPServerNotFoundError(MCPError):
    """Raised when a requested server is not defined or registered."""
    pass


class MCPToolExecutionError(MCPError):
    """Raised when tool execution produces an error or fails validation."""
    pass


# ==============================================================================
# 2. Enums and Data Models
# ==============================================================================

class MCPTransportType(str, Enum):
    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"

    @classmethod
    def from_str(cls, val: str) -> "MCPTransportType":
        v = str(val).lower().strip()
        if v in ("sse", "server-sent-events"):
            return cls.SSE
        if v in ("http", "https", "rest", "post"):
            return cls.HTTP
        return cls.STDIO


class MCPServerStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""
    name: str
    transport: str = "stdio"
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    cwd: Optional[str] = None
    url: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    disabled: bool = False
    auto_approve: List[str] = field(default_factory=list)
    timeout: float = 30.0

    def to_dict(self) -> Dict[str, Any]:
        res: Dict[str, Any] = {
            "transport": self.transport,
            "disabled": self.disabled,
            "timeout": self.timeout,
        }
        if self.command:
            res["command"] = self.command
        if self.args:
            res["args"] = self.args
        if self.env:
            res["env"] = self.env
        if self.cwd:
            res["cwd"] = self.cwd
        if self.url:
            res["url"] = self.url
        if self.headers:
            res["headers"] = self.headers
        if self.auto_approve:
            res["auto_approve"] = self.auto_approve
        return res

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "MCPServerConfig":
        transport = str(data.get("transport", "stdio")).lower()
        if "url" in data and "command" not in data:
            if transport not in ("sse", "http"):
                transport = "sse" if "/sse" in str(data.get("url", "")).lower() else "http"

        args = data.get("args", [])
        if isinstance(args, str):
            args = shlex.split(args)
        elif not isinstance(args, list):
            args = [str(args)]

        return cls(
            name=name,
            transport=transport,
            command=data.get("command"),
            args=[str(a) for a in args],
            env={str(k): str(v) for k, v in data.get("env", {}).items()},
            cwd=data.get("cwd"),
            url=data.get("url"),
            headers={str(k): str(v) for k, v in data.get("headers", {}).items()},
            disabled=bool(data.get("disabled", False)),
            auto_approve=list(data.get("auto_approve", data.get("autoApprove", []))),
            timeout=float(data.get("timeout", 30.0)),
        )


@dataclass
class MCPTool:
    """Represents an MCP Tool definition discovered from an MCP server."""
    name: str
    description: str = ""
    inputSchema: Dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    server_name: Optional[str] = None

    @property
    def qualified_name(self) -> str:
        """Returns server-prefixed name if server_name is set, else bare name."""
        if self.server_name:
            return f"{self.server_name}:{self.name}"
        return self.name

    def to_dict(self) -> Dict[str, Any]:
        res = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.inputSchema,
        }
        if self.server_name:
            res["server_name"] = self.server_name
        return res

    @classmethod
    def from_dict(cls, data: Dict[str, Any], server_name: Optional[str] = None) -> "MCPTool":
        return cls(
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            inputSchema=data.get("inputSchema", data.get("input_schema", {"type": "object", "properties": {}})),
            server_name=server_name or data.get("server_name"),
        )

    def to_openai_tool(self, use_qualified_name: bool = False) -> Dict[str, Any]:
        """Convert to OpenAI / OpenAI-compatible function calling schema."""
        fn_name = self.qualified_name if use_qualified_name else self.name
        # Sanitize name for OpenAI (letters, numbers, underscores, dashes, up to 64 chars)
        sanitized_name = re.sub(r"[^a-zA-Z0-9_-]", "_", fn_name)[:64]
        return {
            "type": "function",
            "function": {
                "name": sanitized_name,
                "description": self.description or f"MCP tool: {self.name}",
                "parameters": self.inputSchema or {"type": "object", "properties": {}},
            },
        }

    def to_anthropic_tool(self, use_qualified_name: bool = False) -> Dict[str, Any]:
        """Convert to Anthropic Claude tool calling schema."""
        fn_name = self.qualified_name if use_qualified_name else self.name
        sanitized_name = re.sub(r"[^a-zA-Z0-9_-]", "_", fn_name)[:64]
        return {
            "name": sanitized_name,
            "description": self.description or f"MCP tool: {self.name}",
            "input_schema": self.inputSchema or {"type": "object", "properties": {}},
        }

    def to_gemini_tool(self, use_qualified_name: bool = False) -> Dict[str, Any]:
        """Convert to Google Gemini function declaration schema."""
        fn_name = self.qualified_name if use_qualified_name else self.name
        sanitized_name = re.sub(r"[^a-zA-Z0-9_]", "_", fn_name)[:64]
        return {
            "name": sanitized_name,
            "description": self.description or f"MCP tool: {self.name}",
            "parameters": self.inputSchema or {"type": "object", "properties": {}},
        }


@dataclass
class MCPToolResult:
    """Represents the execution result of calling an MCP Tool."""
    content: List[Dict[str, Any]] = field(default_factory=list)
    is_error: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)
    server_name: Optional[str] = None
    tool_name: Optional[str] = None

    @property
    def text(self) -> str:
        """Extracts and concatenates all text content items."""
        texts: List[str] = []
        for item in self.content:
            if isinstance(item, dict):
                item_type = item.get("type", "text")
                if item_type == "text" and "text" in item:
                    texts.append(str(item["text"]))
                elif item_type == "resource" and "resource" in item:
                    res_data = item["resource"]
                    if isinstance(res_data, dict) and "text" in res_data:
                        texts.append(str(res_data["text"]))
                elif "data" in item:
                    texts.append(str(item["data"]))
            elif isinstance(item, str):
                texts.append(item)
        return "\n".join(texts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "isError": self.is_error,
            "text": self.text,
            "server_name": self.server_name,
            "tool_name": self.tool_name,
        }

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        server_name: Optional[str] = None,
        tool_name: Optional[str] = None,
    ) -> "MCPToolResult":
        content = data.get("content", [])
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        elif not isinstance(content, list):
            content = [{"type": "text", "text": str(content)}]

        return cls(
            content=content,
            is_error=bool(data.get("isError", data.get("is_error", False))),
            raw=data,
            server_name=server_name,
            tool_name=tool_name,
        )


@dataclass
class MCPResource:
    """Represents an MCP Resource (document, data blob, file)."""
    uri: str
    name: str = ""
    description: Optional[str] = None
    mime_type: Optional[str] = None
    text: Optional[str] = None
    blob: Optional[str] = None
    server_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        res: Dict[str, Any] = {
            "uri": self.uri,
            "name": self.name,
        }
        if self.description:
            res["description"] = self.description
        if self.mime_type:
            res["mimeType"] = self.mime_type
        if self.text is not None:
            res["text"] = self.text
        if self.blob is not None:
            res["blob"] = self.blob
        if self.server_name:
            res["server_name"] = self.server_name
        return res

    @classmethod
    def from_dict(cls, data: Dict[str, Any], server_name: Optional[str] = None) -> "MCPResource":
        return cls(
            uri=str(data.get("uri", "")),
            name=str(data.get("name", "")),
            description=data.get("description"),
            mime_type=data.get("mimeType", data.get("mime_type")),
            text=data.get("text"),
            blob=data.get("blob"),
            server_name=server_name or data.get("server_name"),
        )


@dataclass
class MCPResourceTemplate:
    """Represents an MCP Resource URI Template."""
    uri_template: str
    name: str = ""
    description: Optional[str] = None
    mime_type: Optional[str] = None
    server_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        res: Dict[str, Any] = {
            "uriTemplate": self.uri_template,
            "name": self.name,
        }
        if self.description:
            res["description"] = self.description
        if self.mime_type:
            res["mimeType"] = self.mime_type
        if self.server_name:
            res["server_name"] = self.server_name
        return res

    @classmethod
    def from_dict(cls, data: Dict[str, Any], server_name: Optional[str] = None) -> "MCPResourceTemplate":
        return cls(
            uri_template=str(data.get("uriTemplate", data.get("uri_template", ""))),
            name=str(data.get("name", "")),
            description=data.get("description"),
            mime_type=data.get("mimeType", data.get("mime_type")),
            server_name=server_name or data.get("server_name"),
        )


@dataclass
class MCPPromptArgument:
    name: str
    description: Optional[str] = None
    required: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "required": self.required,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPPromptArgument":
        return cls(
            name=str(data.get("name", "")),
            description=data.get("description"),
            required=bool(data.get("required", False)),
        )


@dataclass
class MCPPrompt:
    name: str
    description: Optional[str] = None
    arguments: List[MCPPromptArgument] = field(default_factory=list)
    server_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        res: Dict[str, Any] = {
            "name": self.name,
            "arguments": [arg.to_dict() for arg in self.arguments],
        }
        if self.description:
            res["description"] = self.description
        if self.server_name:
            res["server_name"] = self.server_name
        return res

    @classmethod
    def from_dict(cls, data: Dict[str, Any], server_name: Optional[str] = None) -> "MCPPrompt":
        args = [MCPPromptArgument.from_dict(a) for a in data.get("arguments", [])]
        return cls(
            name=str(data.get("name", "")),
            description=data.get("description"),
            arguments=args,
            server_name=server_name or data.get("server_name"),
        )


@dataclass
class MCPPromptMessage:
    role: str
    content: Union[str, Dict[str, Any], List[Dict[str, Any]]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPPromptMessage":
        return cls(
            role=str(data.get("role", "user")),
            content=data.get("content", ""),
        )


@dataclass
class MCPPromptResult:
    description: Optional[str] = None
    messages: List[MCPPromptMessage] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "messages": [m.to_dict() for m in self.messages],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPPromptResult":
        messages = [MCPPromptMessage.from_dict(m) for m in data.get("messages", [])]
        return cls(
            description=data.get("description"),
            messages=messages,
        )


# ==============================================================================
# 3. Transports
# ==============================================================================

class BaseClientTransport:
    """Abstract Base Class for MCP Client Transports."""

    async def start(self) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError

    async def send_message(self, message: Dict[str, Any]) -> None:
        raise NotImplementedError

    def is_connected(self) -> bool:
        raise NotImplementedError

    def set_message_handler(self, handler: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]) -> None:
        self._message_handler = handler


class StdioClientTransport(BaseClientTransport):
    """
    Subprocess Stdio Transport for MCP Client.
    Communicates via newline-delimited JSON-RPC messages over stdin/stdout.
    Captures stderr in a buffer for debugging.
    """

    def __init__(
        self,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ):
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.cwd = cwd
        self.process: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._message_handler: Optional[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = None
        self._is_closing = False
        self.stderr_log: List[str] = []

    def is_connected(self) -> bool:
        return self.process is not None and self.process.returncode is None and not self._is_closing

    async def start(self) -> None:
        if self.is_connected():
            return

        cmd_path = shutil.which(self.command) or self.command
        full_env = os.environ.copy()
        full_env.update(self.env)

        try:
            self.process = await asyncio.create_subprocess_exec(
                cmd_path,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=full_env,
                cwd=self.cwd,
            )
        except Exception as e:
            raise MCPTransportError(f"Failed to launch stdio subprocess '{self.command}': {e}") from e

        self._is_closing = False
        self._reader_task = asyncio.create_task(self._read_stdout_loop())
        self._stderr_task = asyncio.create_task(self._read_stderr_loop())

    async def _read_stdout_loop(self) -> None:
        if not self.process or not self.process.stdout:
            return

        while not self._is_closing:
            try:
                line_bytes = await self.process.stdout.readline()
                if not line_bytes:
                    break  # EOF

                line_str = line_bytes.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                try:
                    msg = json.loads(line_str)
                except json.JSONDecodeError as jde:
                    logger.debug("Failed to decode JSON line from stdio: %s (%s)", line_str, jde)
                    continue

                if self._message_handler and isinstance(msg, dict):
                    asyncio.create_task(self._message_handler(msg))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in stdio stdout reader loop: %s", e)
                break

    async def _read_stderr_loop(self) -> None:
        if not self.process or not self.process.stderr:
            return

        while not self._is_closing:
            try:
                line_bytes = await self.process.stderr.readline()
                if not line_bytes:
                    break
                line_str = line_bytes.decode("utf-8", errors="replace").rstrip()
                if line_str:
                    self.stderr_log.append(line_str)
                    if len(self.stderr_log) > 200:
                        self.stderr_log.pop(0)
                    logger.debug("[MCP stdio stderr] %s", line_str)
            except asyncio.CancelledError:
                break
            except Exception:
                break

    async def send_message(self, message: Dict[str, Any]) -> None:
        if not self.is_connected() or not self.process or not self.process.stdin:
            raise MCPTransportError("Stdio transport is not connected.")

        try:
            line = json.dumps(message) + "\n"
            self.process.stdin.write(line.encode("utf-8"))
            await self.process.stdin.drain()
        except Exception as e:
            raise MCPTransportError(f"Failed to write message to stdio stdin: {e}") from e

    async def close(self) -> None:
        self._is_closing = True
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        if self._stderr_task and not self._stderr_task.done():
            self._stderr_task.cancel()

        if self.process:
            try:
                if self.process.stdin and not self.process.stdin.is_closing():
                    self.process.stdin.close()
                    await self.process.stdin.wait_closed()
            except Exception:
                pass

            try:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    self.process.kill()
                    await self.process.wait()
            except ProcessLookupError:
                pass
            except Exception as e:
                logger.debug("Error while terminating process: %s", e)
            finally:
                self.process = None


class HttpClientTransport(BaseClientTransport):
    """
    Direct HTTP POST Transport for MCP Client.
    Sends JSON-RPC 2.0 requests via standard HTTP POST and parses response JSON.
    """

    def __init__(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
    ):
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._connected = False
        self._message_handler: Optional[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = None

    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    async def start(self) -> None:
        if self.is_connected():
            return
        default_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "k-cli/0.3.0 MCPClient",
        }
        default_headers.update(self.headers)
        self._client = httpx.AsyncClient(
            headers=default_headers,
            timeout=httpx.Timeout(self.timeout, connect=10.0),
        )
        self._connected = True

    async def send_message(self, message: Dict[str, Any]) -> None:
        if not self.is_connected() or not self._client:
            raise MCPTransportError("HTTP transport is not connected.")

        try:
            resp = await self._client.post(self.url, json=message)
            resp.raise_for_status()

            if resp.content:
                try:
                    data = resp.json()
                    if self._message_handler and isinstance(data, dict):
                        asyncio.create_task(self._message_handler(data))
                except Exception as je:
                    logger.debug("HTTP response is not valid JSON: %s", je)
        except Exception as e:
            raise MCPTransportError(f"HTTP POST request failed: {e}") from e

    async def close(self) -> None:
        self._connected = False
        if self._client:
            await self._client.aclose()
            self._client = None


class SSEClientTransport(BaseClientTransport):
    """
    Server-Sent Events (SSE) Transport for MCP Client.
    Connects to SSE endpoint via GET to stream events/messages from server.
    Discovers the POST endpoint from the 'endpoint' SSE event to send requests.
    """

    def __init__(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
    ):
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout
        self.post_url: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._sse_task: Optional[asyncio.Task] = None
        self._connected = False
        self._is_closing = False
        self._endpoint_event = asyncio.Event()
        self._message_handler: Optional[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = None

    def is_connected(self) -> bool:
        return self._connected and not self._is_closing

    async def start(self) -> None:
        if self.is_connected():
            return

        default_headers = {
            "Accept": "text/event-stream",
            "User-Agent": "k-cli/0.3.0 MCPClient-SSE",
        }
        default_headers.update(self.headers)
        self._client = httpx.AsyncClient(
            headers=default_headers,
            timeout=httpx.Timeout(None, connect=10.0),
        )
        self._is_closing = False
        self._endpoint_event.clear()
        self._sse_task = asyncio.create_task(self._stream_sse_loop())

        # Wait for SSE connection or timeout
        try:
            await asyncio.wait_for(self._endpoint_event.wait(), timeout=min(10.0, self.timeout))
            self._connected = True
        except asyncio.TimeoutError:
            # If server does not send an explicit endpoint event, fallback post_url to base URL
            if not self.post_url:
                self.post_url = self.url
            self._connected = True

    async def _stream_sse_loop(self) -> None:
        if not self._client:
            return

        current_event = "message"
        data_buffer: List[str] = []

        try:
            async with self._client.stream("GET", self.url) as response:
                if response.status_code >= 400:
                    logger.error("SSE stream failed with HTTP %d", response.status_code)
                    return

                async for line in response.aiter_lines():
                    if self._is_closing:
                        break

                    line = line.strip()
                    if not line:
                        # Empty line signals dispatch of the accumulated event
                        if data_buffer:
                            full_data = "\n".join(data_buffer)
                            data_buffer.clear()
                            await self._handle_sse_event(current_event, full_data)
                        current_event = "message"
                        continue

                    if line.startswith("event:"):
                        current_event = line[len("event:"):].strip()
                    elif line.startswith("data:"):
                        data_buffer.append(line[len("data:"):].strip())

                # Flush any remainder
                if data_buffer:
                    full_data = "\n".join(data_buffer)
                    await self._handle_sse_event(current_event, full_data)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("SSE stream closed or encountered error: %s", e)
        finally:
            self._connected = False

    async def _handle_sse_event(self, event: str, data: str) -> None:
        if event == "endpoint":
            # Endpoint event provides URL for sending POST requests
            resolved_url = data.strip()
            if resolved_url.startswith("http://") or resolved_url.startswith("https://"):
                self.post_url = resolved_url
            else:
                self.post_url = urllib.parse.urljoin(self.url, resolved_url)
            self._endpoint_event.set()
        elif event == "message":
            self._endpoint_event.set()
            try:
                msg = json.loads(data)
                if self._message_handler and isinstance(msg, dict):
                    asyncio.create_task(self._message_handler(msg))
            except Exception as e:
                logger.debug("Failed to decode JSON from SSE message: %s", e)

    async def send_message(self, message: Dict[str, Any]) -> None:
        if not self.is_connected() or not self._client:
            raise MCPTransportError("SSE Transport is not connected.")

        target_url = self.post_url or self.url
        headers = {"Content-Type": "application/json"}
        headers.update(self.headers)

        try:
            resp = await self._client.post(target_url, json=message, headers=headers)
            resp.raise_for_status()
            # If server responds directly with JSON on the POST response
            if resp.content:
                try:
                    data = resp.json()
                    if self._message_handler and isinstance(data, dict):
                        asyncio.create_task(self._message_handler(data))
                except Exception:
                    pass
        except Exception as e:
            raise MCPTransportError(f"Failed to post message over SSE transport: {e}") from e

    async def close(self) -> None:
        self._is_closing = True
        self._connected = False
        if self._sse_task and not self._sse_task.done():
            self._sse_task.cancel()
        if self._client:
            await self._client.aclose()
            self._client = None


# ==============================================================================
# 4. MCPClient
# ==============================================================================

class MCPClient:
    """
    Model Context Protocol (MCP) Client.
    Manages connection, protocol handshake, tools, resources, and prompts with an MCP server.
    Provides both asynchronous and synchronous execution interfaces.
    """

    def __init__(
        self,
        name: str,
        config: MCPServerConfig,
        transport: Optional[BaseClientTransport] = None,
    ):
        self.name = name
        self.config = config
        self.transport = transport or self._create_transport(config)
        self.status = MCPServerStatus.DISCONNECTED
        self.server_info: Dict[str, Any] = {}
        self.server_capabilities: Dict[str, Any] = {}
        self.protocol_version: str = LATEST_PROTOCOL_VERSION

        self._request_id = 0
        self._pending_requests: Dict[Union[int, str], asyncio.Future] = {}
        self._tools_cache: Optional[List[MCPTool]] = None
        self._resources_cache: Optional[List[MCPResource]] = None
        self._prompts_cache: Optional[List[MCPPrompt]] = None

    @staticmethod
    def _create_transport(config: MCPServerConfig) -> BaseClientTransport:
        transport_type = MCPTransportType.from_str(config.transport)
        if transport_type == MCPTransportType.STDIO:
            if not config.command:
                raise ValueError(f"Server '{config.name}' requires a 'command' for stdio transport.")
            return StdioClientTransport(
                command=config.command,
                args=config.args,
                env=config.env,
                cwd=config.cwd,
            )
        elif transport_type == MCPTransportType.SSE:
            if not config.url:
                raise ValueError(f"Server '{config.name}' requires a 'url' for SSE transport.")
            return SSEClientTransport(
                url=config.url,
                headers=config.headers,
                timeout=config.timeout,
            )
        elif transport_type == MCPTransportType.HTTP:
            if not config.url:
                raise ValueError(f"Server '{config.name}' requires a 'url' for HTTP transport.")
            return HttpClientTransport(
                url=config.url,
                headers=config.headers,
                timeout=config.timeout,
            )
        raise ValueError(f"Unsupported transport '{config.transport}' for server '{config.name}'.")

    def is_connected(self) -> bool:
        return self.status == MCPServerStatus.CONNECTED and self.transport is not None and self.transport.is_connected()

    # --------------------------------------------------------------------------
    # Async Connection Lifecycle
    # --------------------------------------------------------------------------

    async def connect_async(self) -> bool:
        """Asynchronously connect to the server and perform the initialize handshake."""
        if self.is_connected():
            return True

        self.status = MCPServerStatus.CONNECTING
        try:
            self.transport.set_message_handler(self._handle_incoming_message)
            await self.transport.start()

            # Perform initialize handshake
            init_params = {
                "protocolVersion": LATEST_PROTOCOL_VERSION,
                "capabilities": {
                    "roots": {"listChanged": True},
                    "sampling": {},
                },
                "clientInfo": CLIENT_INFO,
            }

            init_result = await self.send_request_async("initialize", init_params, timeout=self.config.timeout)

            self.protocol_version = init_result.get("protocolVersion", LATEST_PROTOCOL_VERSION)
            self.server_info = init_result.get("serverInfo", {})
            self.server_capabilities = init_result.get("capabilities", {})

            # Send initialized notification
            await self.send_notification_async("notifications/initialized", {})

            self.status = MCPServerStatus.CONNECTED
            return True
        except Exception as e:
            self.status = MCPServerStatus.ERROR
            await self.disconnect_async()
            logger.error("Failed to connect to MCP server '%s': %s", self.name, e)
            raise MCPTransportError(f"Failed to connect to MCP server '{self.name}': {e}") from e

    async def disconnect_async(self) -> None:
        """Asynchronously disconnect and release resources."""
        self.status = MCPServerStatus.DISCONNECTED
        # Fail any pending requests
        for req_id, fut in list(self._pending_requests.items()):
            if not fut.done():
                fut.set_exception(MCPTransportError("Client disconnected."))
        self._pending_requests.clear()
        self._tools_cache = None
        self._resources_cache = None
        self._prompts_cache = None

        if self.transport:
            await self.transport.close()

    # --------------------------------------------------------------------------
    # JSON-RPC 2.0 Request / Notification Engine
    # --------------------------------------------------------------------------

    async def _handle_incoming_message(self, message: Dict[str, Any]) -> None:
        """Dispatches incoming JSON-RPC 2.0 messages (Responses, Errors, Notifications)."""
        # 1. Response or Error (has 'id')
        if "id" in message and message["id"] is not None:
            req_id = message["id"]
            future = self._pending_requests.pop(req_id, None)
            if future and not future.done():
                if "error" in message and message["error"]:
                    err = message["error"]
                    code = err.get("code")
                    msg = err.get("message", "Unknown error")
                    data = err.get("data")
                    future.set_exception(MCPProtocolError(f"MCP Server Error [{code}]: {msg}", code=code, data=data))
                else:
                    future.set_result(message.get("result", {}))
        # 2. Server Notification (no 'id')
        elif "method" in message:
            method = message["method"]
            params = message.get("params", {})
            if method in ("notifications/tools/list_changed", "notifications/resources/list_changed"):
                self._tools_cache = None
                self._resources_cache = None
            logger.debug("Received notification from server '%s': %s", self.name, method)

    async def send_request_async(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        """Sends a JSON-RPC 2.0 request and awaits the result."""
        if not self.transport or (not self.transport.is_connected() and method != "initialize"):
            raise MCPTransportError(f"Cannot send request '{method}'; server '{self.name}' is disconnected.")

        self._request_id += 1
        req_id = self._request_id
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending_requests[req_id] = future

        payload: Dict[str, Any] = {
            "jsonrpc": JSONRPC_VERSION,
            "id": req_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        effective_timeout = timeout if timeout is not None else self.config.timeout

        try:
            await self.transport.send_message(payload)
            result = await asyncio.wait_for(future, timeout=effective_timeout)
            return result
        except asyncio.TimeoutError:
            self._pending_requests.pop(req_id, None)
            # Send cancellation notification to server
            try:
                await self.send_notification_async("notifications/cancelled", {"requestId": req_id, "reason": "timeout"})
            except Exception:
                pass
            raise MCPTimeoutError(f"Request '{method}' (id={req_id}) to server '{self.name}' timed out after {effective_timeout}s.")
        except Exception:
            self._pending_requests.pop(req_id, None)
            raise

    async def send_notification_async(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        """Sends a JSON-RPC 2.0 notification (no response expected)."""
        if not self.transport or not self.transport.is_connected():
            return

        payload: Dict[str, Any] = {
            "jsonrpc": JSONRPC_VERSION,
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        try:
            await self.transport.send_message(payload)
        except Exception as e:
            logger.debug("Failed to send notification '%s' to '%s': %s", method, self.name, e)

    # --------------------------------------------------------------------------
    # Ping & Health Check
    # --------------------------------------------------------------------------

    async def ping_async(self) -> bool:
        """Sends a ping request to check server liveliness."""
        try:
            await self.send_request_async("ping", {}, timeout=5.0)
            return True
        except Exception:
            return False

    # --------------------------------------------------------------------------
    # Tools API
    # --------------------------------------------------------------------------

    async def list_tools_async(self, refresh: bool = False) -> List[MCPTool]:
        """Discovers tools exposed by the MCP server."""
        if self._tools_cache is not None and not refresh:
            return self._tools_cache

        tools: List[MCPTool] = []
        cursor: Optional[str] = None

        while True:
            params: Dict[str, Any] = {}
            if cursor:
                params["cursor"] = cursor

            result = await self.send_request_async("tools/list", params)
            raw_tools = result.get("tools", [])
            for item in raw_tools:
                tools.append(MCPTool.from_dict(item, server_name=self.name))

            cursor = result.get("nextCursor")
            if not cursor:
                break

        self._tools_cache = tools
        return tools

    async def call_tool_async(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> MCPToolResult:
        """Executes a tool on the MCP server."""
        params = {
            "name": tool_name,
            "arguments": arguments or {},
        }
        result_data = await self.send_request_async("tools/call", params)
        return MCPToolResult.from_dict(result_data, server_name=self.name, tool_name=tool_name)

    # --------------------------------------------------------------------------
    # Resources API
    # --------------------------------------------------------------------------

    async def list_resources_async(self, refresh: bool = False) -> List[MCPResource]:
        """Lists resources published by the MCP server."""
        if self._resources_cache is not None and not refresh:
            return self._resources_cache

        resources: List[MCPResource] = []
        cursor: Optional[str] = None

        while True:
            params: Dict[str, Any] = {}
            if cursor:
                params["cursor"] = cursor

            result = await self.send_request_async("resources/list", params)
            raw_resources = result.get("resources", [])
            for item in raw_resources:
                resources.append(MCPResource.from_dict(item, server_name=self.name))

            cursor = result.get("nextCursor")
            if not cursor:
                break

        self._resources_cache = resources
        return resources

    async def read_resource_async(self, uri: str) -> MCPResource:
        """Reads a specific resource URI from the MCP server."""
        params = {"uri": uri}
        result = await self.send_request_async("resources/read", params)
        contents = result.get("contents", [])
        if not contents:
            return MCPResource(uri=uri, name=uri, server_name=self.name)

        first = contents[0]
        return MCPResource(
            uri=first.get("uri", uri),
            name=first.get("name", uri.split("/")[-1]),
            mime_type=first.get("mimeType"),
            text=first.get("text"),
            blob=first.get("blob"),
            server_name=self.name,
        )

    async def list_resource_templates_async(self) -> List[MCPResourceTemplate]:
        """Lists resource URI templates exposed by the server."""
        try:
            result = await self.send_request_async("resources/templates/list", {})
            raw_templates = result.get("resourceTemplates", [])
            return [MCPResourceTemplate.from_dict(t, server_name=self.name) for t in raw_templates]
        except Exception:
            return []

    # --------------------------------------------------------------------------
    # Prompts API
    # --------------------------------------------------------------------------

    async def list_prompts_async(self, refresh: bool = False) -> List[MCPPrompt]:
        """Lists prompt templates defined on the MCP server."""
        if self._prompts_cache is not None and not refresh:
            return self._prompts_cache

        prompts: List[MCPPrompt] = []
        cursor: Optional[str] = None

        while True:
            params: Dict[str, Any] = {}
            if cursor:
                params["cursor"] = cursor

            result = await self.send_request_async("prompts/list", params)
            raw_prompts = result.get("prompts", [])
            for item in raw_prompts:
                prompts.append(MCPPrompt.from_dict(item, server_name=self.name))

            cursor = result.get("nextCursor")
            if not cursor:
                break

        self._prompts_cache = prompts
        return prompts

    async def get_prompt_async(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> MCPPromptResult:
        """Retrieves and fills a prompt template."""
        params = {
            "name": name,
            "arguments": arguments or {},
        }
        result = await self.send_request_async("prompts/get", params)
        return MCPPromptResult.from_dict(result)

    # --------------------------------------------------------------------------
    # Synchronous Wrappers
    # --------------------------------------------------------------------------

    def connect(self) -> bool:
        return run_sync(self.connect_async())

    def disconnect(self) -> None:
        return run_sync(self.disconnect_async())

    def ping(self) -> bool:
        return run_sync(self.ping_async())

    def list_tools(self, refresh: bool = False) -> List[MCPTool]:
        return run_sync(self.list_tools_async(refresh=refresh))

    def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> MCPToolResult:
        return run_sync(self.call_tool_async(tool_name, arguments))

    def list_resources(self, refresh: bool = False) -> List[MCPResource]:
        return run_sync(self.list_resources_async(refresh=refresh))

    def read_resource(self, uri: str) -> MCPResource:
        return run_sync(self.read_resource_async(uri))

    def list_prompts(self, refresh: bool = False) -> List[MCPPrompt]:
        return run_sync(self.list_prompts_async(refresh=refresh))

    def get_prompt(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> MCPPromptResult:
        return run_sync(self.get_prompt_async(name, arguments))

    # --------------------------------------------------------------------------
    # Schema Converters
    # --------------------------------------------------------------------------

    def get_tools_openai_schema(self, use_qualified_names: bool = False) -> List[Dict[str, Any]]:
        tools = self.list_tools()
        return [t.to_openai_tool(use_qualified_name=use_qualified_names) for t in tools]

    def get_tools_anthropic_schema(self, use_qualified_names: bool = False) -> List[Dict[str, Any]]:
        tools = self.list_tools()
        return [t.to_anthropic_tool(use_qualified_name=use_qualified_names) for t in tools]

    def get_tools_gemini_schema(self, use_qualified_names: bool = False) -> List[Dict[str, Any]]:
        tools = self.list_tools()
        return [t.to_gemini_tool(use_qualified_name=use_qualified_names) for t in tools]


# ==============================================================================
# 5. MCPManager
# ==============================================================================

class MCPManager:
    """
    Central MCP Manager for K-CLI.
    Handles server discovery from config files (.kcli/mcp.json, ~/.kcli/mcp.json),
    manages server lifecycles, and routes tool, resource, and prompt requests.
    """

    DEFAULT_CONFIG_FILENAMES = [
        ".kcli/mcp.json",
        "mcp.json",
        "~/.kcli/mcp.json",
        "~/.config/kcli/mcp.json",
    ]

    def __init__(self, config_path: Optional[Union[str, Path]] = None, auto_load: bool = True):
        self.config_path: Optional[Path] = Path(config_path).expanduser().resolve() if config_path else None
        self.server_configs: Dict[str, MCPServerConfig] = {}
        self.clients: Dict[str, MCPClient] = {}

        if auto_load:
            self.load_config(self.config_path)

    # --------------------------------------------------------------------------
    # Configuration Management
    # --------------------------------------------------------------------------

    def find_default_config_path(self) -> Optional[Path]:
        """Finds the highest priority existing config file."""
        for candidate in self.DEFAULT_CONFIG_FILENAMES:
            p = Path(candidate).expanduser()
            if not p.is_absolute():
                p = (Path.cwd() / p).resolve()
            if p.is_file():
                return p
        return None

    def load_config(self, config_path: Optional[Union[str, Path]] = None) -> bool:
        """
        Loads server definitions from the specified path or standard search locations.
        Supports Claude Desktop, Cursor, Antigravity, and K-CLI schema formats.
        """
        target: Optional[Path] = None
        if config_path:
            target = Path(config_path).expanduser().resolve()
        else:
            target = self.find_default_config_path()

        if not target or not target.is_file():
            return False

        self.config_path = target
        try:
            content = target.read_text(encoding="utf-8")
            data = json.loads(content)
        except Exception as e:
            logger.error("Failed to parse MCP configuration file '%s': %s", target, e)
            return False

        # Support 'mcpServers', 'servers', or direct dictionary
        servers_dict = data.get("mcpServers", data.get("servers", data))
        if not isinstance(servers_dict, dict):
            return False

        self.server_configs.clear()
        for name, cfg in servers_dict.items():
            if isinstance(cfg, dict):
                try:
                    self.server_configs[name] = MCPServerConfig.from_dict(name, cfg)
                except Exception as ex:
                    logger.warning("Skipping invalid server config for '%s': %s", name, ex)

        return True

    def save_config(self, config_path: Optional[Union[str, Path]] = None) -> bool:
        """Persists current server configurations to disk."""
        target = Path(config_path).expanduser().resolve() if config_path else self.config_path
        if not target:
            target = (Path.cwd() / ".kcli" / "mcp.json").resolve()

        self.config_path = target
        target.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "mcpServers": {
                name: cfg.to_dict() for name, cfg in self.server_configs.items()
            }
        }

        try:
            target.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return True
        except Exception as e:
            logger.error("Failed to save MCP configuration to '%s': %s", target, e)
            return False

    def add_server(
        self,
        name: str,
        config: Union[MCPServerConfig, Dict[str, Any]],
        save: bool = True,
    ) -> MCPServerConfig:
        """Adds or updates a server definition in the manager."""
        if isinstance(config, dict):
            cfg_obj = MCPServerConfig.from_dict(name, config)
        else:
            cfg_obj = config

        self.server_configs[name] = cfg_obj

        # If a client was already connected under this name, recreate it
        if name in self.clients:
            self.disconnect_server(name)

        if save:
            self.save_config()

        return cfg_obj

    def remove_server(self, name: str, save: bool = True) -> bool:
        """Removes a server definition and disconnects its client."""
        if name in self.clients:
            self.disconnect_server(name)

        if name in self.server_configs:
            del self.server_configs[name]
            if save:
                self.save_config()
            return True
        return False

    def get_server_config(self, name: str) -> Optional[MCPServerConfig]:
        return self.server_configs.get(name)

    # --------------------------------------------------------------------------
    # Client Lifecycle Management
    # --------------------------------------------------------------------------

    def get_client(self, name: str, auto_create: bool = True) -> Optional[MCPClient]:
        """Retrieves or creates an MCPClient for the given server name."""
        if name in self.clients:
            return self.clients[name]

        if not auto_create:
            return None

        cfg = self.server_configs.get(name)
        if not cfg:
            return None

        client = MCPClient(name=name, config=cfg)
        self.clients[name] = client
        return client

    async def connect_server_async(self, name: str, config: Optional[MCPServerConfig] = None) -> MCPClient:
        """Asynchronously connects to an MCP server by name."""
        if config:
            self.add_server(name, config, save=False)

        client = self.get_client(name)
        if not client:
            raise MCPServerNotFoundError(f"Server '{name}' is not configured.")

        if not client.is_connected():
            await client.connect_async()

        return client

    def connect_server(self, name: str, config: Optional[MCPServerConfig] = None) -> MCPClient:
        return run_sync(self.connect_server_async(name, config))

    async def disconnect_server_async(self, name: str) -> None:
        """Asynchronously disconnects a named MCP server."""
        if name in self.clients:
            client = self.clients[name]
            await client.disconnect_async()
            del self.clients[name]

    def disconnect_server(self, name: str) -> None:
        return run_sync(self.disconnect_server_async(name))

    async def connect_all_async(self) -> Dict[str, bool]:
        """Asynchronously connects to all non-disabled configured servers."""
        results: Dict[str, bool] = {}
        for name, cfg in self.server_configs.items():
            if cfg.disabled:
                continue
            try:
                client = await self.connect_server_async(name)
                results[name] = client.is_connected()
            except Exception as e:
                logger.error("Failed to connect server '%s': %s", name, e)
                results[name] = False
        return results

    def connect_all(self) -> Dict[str, bool]:
        return run_sync(self.connect_all_async())

    async def disconnect_all_async(self) -> None:
        """Asynchronously disconnects all active MCP clients."""
        for name in list(self.clients.keys()):
            await self.disconnect_server_async(name)

    def disconnect_all(self) -> None:
        return run_sync(self.disconnect_all_async())

    def list_servers(self) -> List[Dict[str, Any]]:
        """Returns structured status information for all registered MCP servers."""
        out: List[Dict[str, Any]] = []
        for name, cfg in self.server_configs.items():
            client = self.clients.get(name)
            is_conn = client.is_connected() if client else False
            status = client.status.value if client else ("disabled" if cfg.disabled else "disconnected")

            tool_count = len(client._tools_cache) if client and client._tools_cache is not None else 0
            resource_count = len(client._resources_cache) if client and client._resources_cache is not None else 0
            prompt_count = len(client._prompts_cache) if client and client._prompts_cache is not None else 0

            out.append({
                "name": name,
                "transport": cfg.transport,
                "command": cfg.command or cfg.url or "",
                "status": status,
                "connected": is_conn,
                "disabled": cfg.disabled,
                "tool_count": tool_count,
                "resource_count": resource_count,
                "prompt_count": prompt_count,
            })
        return out

    # --------------------------------------------------------------------------
    # Aggregated Tool Discovery & Execution
    # --------------------------------------------------------------------------

    async def list_tools_async(self, server_name: Optional[str] = None) -> List[MCPTool]:
        """Lists tools across all connected servers or for a specific server."""
        if server_name:
            client = await self.connect_server_async(server_name)
            return await client.list_tools_async()

        all_tools: List[MCPTool] = []
        for name in list(self.server_configs.keys()):
            if self.server_configs[name].disabled:
                continue
            try:
                client = await self.connect_server_async(name)
                tools = await client.list_tools_async()
                all_tools.extend(tools)
            except Exception as e:
                logger.debug("Failed to list tools for '%s': %s", name, e)

        return all_tools

    def list_tools(self, server_name: Optional[str] = None) -> List[MCPTool]:
        return run_sync(self.list_tools_async(server_name))

    async def call_tool_async(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        server_name: Optional[str] = None,
    ) -> MCPToolResult:
        """
        Executes a tool.
        Supports qualified names like 'server_name:tool_name' or 'server_name__tool_name'.
        If server_name is not provided, searches all connected or configured servers.
        """
        arguments = arguments or {}
        target_server = server_name
        target_tool = tool_name

        # Parse namespace delimiters
        if ":" in tool_name:
            target_server, target_tool = tool_name.split(":", 1)
        elif "__" in tool_name and not server_name:
            possible_server, possible_tool = tool_name.split("__", 1)
            if possible_server in self.server_configs:
                target_server = possible_server
                target_tool = possible_tool

        if target_server:
            client = await self.connect_server_async(target_server)
            return await client.call_tool_async(target_tool, arguments)

        # Search across all servers for matching tool
        for s_name in self.server_configs.keys():
            if self.server_configs[s_name].disabled:
                continue
            try:
                client = await self.connect_server_async(s_name)
                tools = await client.list_tools_async()
                for t in tools:
                    if t.name == target_tool:
                        return await client.call_tool_async(target_tool, arguments)
            except Exception:
                continue

        raise MCPToolExecutionError(f"Tool '{tool_name}' not found on any active MCP server.")

    def call_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        server_name: Optional[str] = None,
    ) -> MCPToolResult:
        return run_sync(self.call_tool_async(tool_name, arguments, server_name))

    # --------------------------------------------------------------------------
    # Aggregated Resource & Prompt APIs
    # --------------------------------------------------------------------------

    async def list_resources_async(self, server_name: Optional[str] = None) -> List[MCPResource]:
        if server_name:
            client = await self.connect_server_async(server_name)
            return await client.list_resources_async()

        all_res: List[MCPResource] = []
        for name in self.server_configs.keys():
            if self.server_configs[name].disabled:
                continue
            try:
                client = await self.connect_server_async(name)
                res = await client.list_resources_async()
                all_res.extend(res)
            except Exception:
                continue
        return all_res

    def list_resources(self, server_name: Optional[str] = None) -> List[MCPResource]:
        return run_sync(self.list_resources_async(server_name))

    async def read_resource_async(self, uri: str, server_name: Optional[str] = None) -> MCPResource:
        if server_name:
            client = await self.connect_server_async(server_name)
            return await client.read_resource_async(uri)

        # Try active clients first
        for client in self.clients.values():
            if client.is_connected():
                try:
                    return await client.read_resource_async(uri)
                except Exception:
                    continue

        # Fallback to searching all configured servers
        for name in self.server_configs.keys():
            try:
                client = await self.connect_server_async(name)
                return await client.read_resource_async(uri)
            except Exception:
                continue

        raise MCPError(f"Resource '{uri}' could not be read from any MCP server.")

    def read_resource(self, uri: str, server_name: Optional[str] = None) -> MCPResource:
        return run_sync(self.read_resource_async(uri, server_name))

    async def list_prompts_async(self, server_name: Optional[str] = None) -> List[MCPPrompt]:
        if server_name:
            client = await self.connect_server_async(server_name)
            return await client.list_prompts_async()

        all_prompts: List[MCPPrompt] = []
        for name in self.server_configs.keys():
            if self.server_configs[name].disabled:
                continue
            try:
                client = await self.connect_server_async(name)
                p = await client.list_prompts_async()
                all_prompts.extend(p)
            except Exception:
                continue
        return all_prompts

    def list_prompts(self, server_name: Optional[str] = None) -> List[MCPPrompt]:
        return run_sync(self.list_prompts_async(server_name))

    async def get_prompt_async(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        server_name: Optional[str] = None,
    ) -> MCPPromptResult:
        if server_name:
            client = await self.connect_server_async(server_name)
            return await client.get_prompt_async(name, arguments)

        for s_name in self.server_configs.keys():
            try:
                client = await self.connect_server_async(s_name)
                return await client.get_prompt_async(name, arguments)
            except Exception:
                continue

        raise MCPError(f"Prompt '{name}' could not be found on any MCP server.")

    def get_prompt(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        server_name: Optional[str] = None,
    ) -> MCPPromptResult:
        return run_sync(self.get_prompt_async(name, arguments, server_name))

    # --------------------------------------------------------------------------
    # Tool Schema Conversion Aggregators
    # --------------------------------------------------------------------------

    def get_openai_tools(self, server_name: Optional[str] = None, use_qualified_names: bool = False) -> List[Dict[str, Any]]:
        tools = self.list_tools(server_name)
        return [t.to_openai_tool(use_qualified_name=use_qualified_names) for t in tools]

    def get_anthropic_tools(self, server_name: Optional[str] = None, use_qualified_names: bool = False) -> List[Dict[str, Any]]:
        tools = self.list_tools(server_name)
        return [t.to_anthropic_tool(use_qualified_name=use_qualified_names) for t in tools]

    def get_gemini_tools(self, server_name: Optional[str] = None, use_qualified_names: bool = False) -> List[Dict[str, Any]]:
        tools = self.list_tools(server_name)
        return [t.to_gemini_tool(use_qualified_name=use_qualified_names) for t in tools]


# ==============================================================================
# 6. Global Tool Schema Conversion Utilities
# ==============================================================================

def convert_mcp_tool_to_openai(tool: Union[MCPTool, Dict[str, Any]]) -> Dict[str, Any]:
    """Converts an MCP tool into an OpenAI function tool definition."""
    if isinstance(tool, MCPTool):
        return tool.to_openai_tool()
    t = MCPTool.from_dict(tool)
    return t.to_openai_tool()


def convert_mcp_tool_to_anthropic(tool: Union[MCPTool, Dict[str, Any]]) -> Dict[str, Any]:
    """Converts an MCP tool into an Anthropic tool definition."""
    if isinstance(tool, MCPTool):
        return tool.to_anthropic_tool()
    t = MCPTool.from_dict(tool)
    return t.to_anthropic_tool()


def convert_mcp_tool_to_gemini(tool: Union[MCPTool, Dict[str, Any]]) -> Dict[str, Any]:
    """Converts an MCP tool into a Google Gemini function declaration."""
    if isinstance(tool, MCPTool):
        return tool.to_gemini_tool()
    t = MCPTool.from_dict(tool)
    return t.to_gemini_tool()


def convert_mcp_tools_to_provider_schema(
    tools: List[Union[MCPTool, Dict[str, Any]]],
    provider: str = "openai",
) -> List[Dict[str, Any]]:
    """Converts a list of MCP tools into schemas matching the target LLM provider."""
    p = str(provider).lower().strip()
    result: List[Dict[str, Any]] = []
    for tool in tools:
        if "anthropic" in p or "claude" in p:
            result.append(convert_mcp_tool_to_anthropic(tool))
        elif "gemini" in p or "google" in p:
            result.append(convert_mcp_tool_to_gemini(tool))
        else:
            # Default to OpenAI / OpenAI-compatible / Ollama / llama.cpp
            result.append(convert_mcp_tool_to_openai(tool))
    return result


# ==============================================================================
# 7. CLI Helper Functions
# ==============================================================================

def mcp_list_servers(
    config_path: Optional[Union[str, Path]] = None,
    manager: Optional[MCPManager] = None,
) -> List[Dict[str, Any]]:
    """CLI Helper: lists all servers and their status."""
    mgr = manager or MCPManager(config_path=config_path)
    return mgr.list_servers()


def mcp_add_server(
    name: str,
    command: Optional[str] = None,
    args: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
    url: Optional[str] = None,
    transport: str = "stdio",
    config_path: Optional[Union[str, Path]] = None,
) -> bool:
    """CLI Helper: adds a new server definition to mcp.json."""
    mgr = MCPManager(config_path=config_path, auto_load=True)
    cfg = MCPServerConfig(
        name=name,
        command=command,
        args=args or [],
        env=env or {},
        url=url,
        transport=transport,
    )
    mgr.add_server(name, cfg, save=True)
    return True


def mcp_remove_server(name: str, config_path: Optional[Union[str, Path]] = None) -> bool:
    """CLI Helper: removes a server from mcp.json."""
    mgr = MCPManager(config_path=config_path, auto_load=True)
    return mgr.remove_server(name, save=True)


def mcp_test_connection(
    name: str,
    config_path: Optional[Union[str, Path]] = None,
    manager: Optional[MCPManager] = None,
) -> Dict[str, Any]:
    """CLI Helper: tests connection to a named MCP server and queries its tools/resources."""
    mgr = manager or MCPManager(config_path=config_path)
    start_time = time.time()
    try:
        client = mgr.connect_server(name)
        ping_ok = client.ping()
        tools = client.list_tools(refresh=True)
        resources = client.list_resources(refresh=True)
        prompts = client.list_prompts(refresh=True)
        duration_ms = round((time.time() - start_time) * 1000, 2)

        return {
            "success": True,
            "name": name,
            "connected": True,
            "ping": ping_ok,
            "duration_ms": duration_ms,
            "server_info": client.server_info,
            "protocol_version": client.protocol_version,
            "tools": [t.to_dict() for t in tools],
            "resources": [r.to_dict() for r in resources],
            "prompts": [p.to_dict() for p in prompts],
            "error": None,
        }
    except Exception as e:
        duration_ms = round((time.time() - start_time) * 1000, 2)
        return {
            "success": False,
            "name": name,
            "connected": False,
            "ping": False,
            "duration_ms": duration_ms,
            "server_info": {},
            "protocol_version": None,
            "tools": [],
            "resources": [],
            "prompts": [],
            "error": str(e),
        }
