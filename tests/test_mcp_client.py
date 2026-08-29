"""
test_mcp_client.py - Comprehensive Unit & Integration Tests for Universal MCP Client
Project Bankai Engine

Tests:
1. Data models and serialization (MCPServerConfig, MCPTool, MCPToolResult, MCPResource, MCPPrompt, etc.)
2. Tool schema conversion (OpenAI, Anthropic, Gemini, multi-provider converters)
3. Transports (StdioClientTransport, HttpClientTransport, SSEClientTransport)
4. MCPClient JSON-RPC 2.0 protocol engine (initialize, ping, tools, resources, prompts, pagination, cancellation)
5. MCPManager multi-server orchestrator (config loading/saving, server lifecycle, routing, discovery)
6. CLI helper functions (mcp_list_servers, mcp_add_server, mcp_remove_server, mcp_test_connection)
7. Typer CLI commands integration (k mcp list/add/remove/test/tools/call)
8. Edge cases, error handling, timeouts, and sync/async concurrency
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_root_dir = Path(__file__).parent.parent
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))

import httpx
import pytest
from typer.testing import CliRunner

from k_cli.cli import app
from k_cli.tools.mcp_client import (
    BaseClientTransport,
    HttpClientTransport,
    MCPClient,
    MCPError,
    MCPManager,
    MCPPrompt,
    MCPPromptArgument,
    MCPPromptMessage,
    MCPPromptResult,
    MCPProtocolError,
    MCPResource,
    MCPResourceTemplate,
    MCPServerConfig,
    MCPServerNotFoundError,
    MCPServerStatus,
    MCPTimeoutError,
    MCPTool,
    MCPToolExecutionError,
    MCPToolResult,
    MCPTransportError,
    MCPTransportType,
    SSEClientTransport,
    StdioClientTransport,
    convert_mcp_tool_to_anthropic,
    convert_mcp_tool_to_gemini,
    convert_mcp_tool_to_openai,
    convert_mcp_tools_to_provider_schema,
    mcp_add_server,
    mcp_list_servers,
    mcp_remove_server,
    mcp_test_connection,
    run_sync,
)

runner = CliRunner()


def async_test(coro_fn):
    """Helper decorator to run async test functions synchronously with asyncio.run()."""
    def wrapper(*args, **kwargs):
        return asyncio.run(coro_fn(*args, **kwargs))
    return wrapper


# ==============================================================================
# 1. Data Models & Serialization Tests
# ==============================================================================

def test_mcp_transport_type_from_str():
    assert MCPTransportType.from_str("stdio") == MCPTransportType.STDIO
    assert MCPTransportType.from_str("STDIO") == MCPTransportType.STDIO
    assert MCPTransportType.from_str("sse") == MCPTransportType.SSE
    assert MCPTransportType.from_str("server-sent-events") == MCPTransportType.SSE
    assert MCPTransportType.from_str("http") == MCPTransportType.HTTP
    assert MCPTransportType.from_str("https") == MCPTransportType.HTTP
    assert MCPTransportType.from_str("post") == MCPTransportType.HTTP
    assert MCPTransportType.from_str("unknown") == MCPTransportType.STDIO


def test_mcp_server_config_serialization():
    cfg = MCPServerConfig(
        name="github",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_TOKEN": "ghp_123"},
        cwd="/tmp",
        disabled=False,
        timeout=45.0,
    )
    d = cfg.to_dict()
    assert d["command"] == "npx"
    assert d["args"] == ["-y", "@modelcontextprotocol/server-github"]
    assert d["env"] == {"GITHUB_TOKEN": "ghp_123"}
    assert d["cwd"] == "/tmp"
    assert d["timeout"] == 45.0
    assert not d["disabled"]

    # Reconstruct
    cfg2 = MCPServerConfig.from_dict("github", d)
    assert cfg2.name == "github"
    assert cfg2.command == "npx"
    assert cfg2.args == ["-y", "@modelcontextprotocol/server-github"]
    assert cfg2.env["GITHUB_TOKEN"] == "ghp_123"
    assert cfg2.cwd == "/tmp"
    assert cfg2.timeout == 45.0


def test_mcp_server_config_url_auto_transport():
    cfg_sse = MCPServerConfig.from_dict("remote", {"url": "http://localhost:8000/sse"})
    assert cfg_sse.transport == "sse"

    cfg_http = MCPServerConfig.from_dict("remote_http", {"url": "http://localhost:8000/api"})
    assert cfg_http.transport == "http"


def test_mcp_tool_model():
    tool = MCPTool(
        name="calculate_sum",
        description="Add two numbers",
        inputSchema={
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"},
            },
            "required": ["a", "b"],
        },
        server_name="math_srv",
    )
    assert tool.qualified_name == "math_srv:calculate_sum"

    d = tool.to_dict()
    assert d["name"] == "calculate_sum"
    assert d["server_name"] == "math_srv"

    reconstructed = MCPTool.from_dict(d)
    assert reconstructed.name == "calculate_sum"
    assert reconstructed.server_name == "math_srv"


def test_mcp_tool_result_text_extraction():
    # Multiple text parts
    res = MCPToolResult(
        content=[
            {"type": "text", "text": "First line"},
            {"type": "text", "text": "Second line"},
        ]
    )
    assert res.text == "First line\nSecond line"
    assert not res.is_error

    # Resource content part
    res_resource = MCPToolResult(
        content=[
            {"type": "resource", "resource": {"text": "Resource content"}},
        ]
    )
    assert res_resource.text == "Resource content"

    # Direct string content
    res_str = MCPToolResult.from_dict({"content": "Direct text content", "isError": True})
    assert res_str.text == "Direct text content"
    assert res_str.is_error


def test_mcp_resource_and_prompt_models():
    res = MCPResource(
        uri="file:///workspace/README.md",
        name="README.md",
        description="Main documentation",
        mime_type="text/markdown",
        text="# Project Bankai",
        server_name="files",
    )
    res_dict = res.to_dict()
    assert res_dict["uri"] == "file:///workspace/README.md"
    assert res_dict["mimeType"] == "text/markdown"

    res_back = MCPResource.from_dict(res_dict)
    assert res_back.uri == "file:///workspace/README.md"
    assert res_back.text == "# Project Bankai"

    # Resource Template
    rt = MCPResourceTemplate(
        uri_template="db://users/{id}",
        name="User record",
        mime_type="application/json",
        server_name="db",
    )
    rt_dict = rt.to_dict()
    assert rt_dict["uriTemplate"] == "db://users/{id}"
    rt_back = MCPResourceTemplate.from_dict(rt_dict)
    assert rt_back.uri_template == "db://users/{id}"

    # Prompt
    prompt = MCPPrompt(
        name="code_review",
        description="Review code diff",
        arguments=[
            MCPPromptArgument(name="diff", description="Git diff text", required=True),
        ],
        server_name="dev",
    )
    p_dict = prompt.to_dict()
    assert p_dict["name"] == "code_review"
    assert len(p_dict["arguments"]) == 1

    prompt_back = MCPPrompt.from_dict(p_dict)
    assert prompt_back.name == "code_review"
    assert prompt_back.arguments[0].name == "diff"
    assert prompt_back.arguments[0].required is True


# ==============================================================================
# 2. Tool Schema Conversion Tests
# ==============================================================================

def test_convert_to_openai_tool():
    tool = MCPTool(
        name="fetch_issue",
        description="Fetch a GitHub issue by number",
        inputSchema={
            "type": "object",
            "properties": {
                "issue_number": {"type": "integer", "description": "Issue ID"},
            },
            "required": ["issue_number"],
        },
        server_name="github",
    )

    # Bare name
    openai_schema = tool.to_openai_tool(use_qualified_name=False)
    assert openai_schema["type"] == "function"
    assert openai_schema["function"]["name"] == "fetch_issue"
    assert openai_schema["function"]["description"] == "Fetch a GitHub issue by number"
    assert openai_schema["function"]["parameters"]["required"] == ["issue_number"]

    # Qualified name
    openai_qual = tool.to_openai_tool(use_qualified_name=True)
    assert openai_qual["function"]["name"] == "github_fetch_issue"


def test_convert_to_anthropic_tool():
    tool = MCPTool(
        name="search_code",
        description="Search codebase for symbol",
        inputSchema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
        },
        server_name="workspace",
    )
    anthropic_schema = tool.to_anthropic_tool(use_qualified_name=True)
    assert anthropic_schema["name"] == "workspace_search_code"
    assert anthropic_schema["description"] == "Search codebase for symbol"
    assert "input_schema" in anthropic_schema
    assert anthropic_schema["input_schema"]["properties"]["query"]["type"] == "string"


def test_convert_to_gemini_tool():
    tool = MCPTool(
        name="run_query",
        description="Run database query",
        inputSchema={
            "type": "object",
            "properties": {"sql": {"type": "string"}},
        },
    )
    gemini_schema = tool.to_gemini_tool()
    assert gemini_schema["name"] == "run_query"
    assert gemini_schema["description"] == "Run database query"
    assert gemini_schema["parameters"]["properties"]["sql"]["type"] == "string"


def test_convert_mcp_tools_to_provider_schema():
    tools = [
        MCPTool(name="t1", description="Tool 1"),
        MCPTool(name="t2", description="Tool 2"),
    ]

    # OpenAI / Ollama / llama.cpp
    openai_list = convert_mcp_tools_to_provider_schema(tools, provider="openai")
    assert len(openai_list) == 2
    assert openai_list[0]["type"] == "function"
    assert openai_list[0]["function"]["name"] == "t1"

    # Anthropic Claude
    claude_list = convert_mcp_tools_to_provider_schema(tools, provider="anthropic")
    assert len(claude_list) == 2
    assert "input_schema" in claude_list[0]
    assert claude_list[0]["name"] == "t1"

    # Gemini
    gemini_list = convert_mcp_tools_to_provider_schema(tools, provider="gemini")
    assert len(gemini_list) == 2
    assert "parameters" in gemini_list[0]
    assert gemini_list[0]["name"] == "t1"


def test_standalone_schema_converters():
    raw_dict = {
        "name": "calc",
        "description": "Calculate math expression",
        "inputSchema": {"type": "object", "properties": {"expr": {"type": "string"}}},
    }
    o = convert_mcp_tool_to_openai(raw_dict)
    assert o["type"] == "function"
    assert o["function"]["name"] == "calc"

    a = convert_mcp_tool_to_anthropic(raw_dict)
    assert a["name"] == "calc"
    assert "input_schema" in a

    g = convert_mcp_tool_to_gemini(raw_dict)
    assert g["name"] == "calc"
    assert "parameters" in g


# ==============================================================================
# 3. Transports Tests
# ==============================================================================

@async_test
async def test_stdio_client_transport_lifecycle():
    # Launch a simple Python process that echoes JSON-RPC messages back
    python_echo_code = (
        "import sys, json\n"
        "for line in sys.stdin:\n"
        "    if not line.strip(): continue\n"
        "    msg = json.loads(line)\n"
        "    if 'id' in msg:\n"
        "        resp = {'jsonrpc': '2.0', 'id': msg['id'], 'result': {'echo': msg.get('method')}}\n"
        "        sys.stdout.write(json.dumps(resp) + '\\n')\n"
        "        sys.stdout.flush()\n"
    )

    transport = StdioClientTransport(
        command=sys.executable,
        args=["-c", python_echo_code],
    )

    received_messages: List[dict] = []

    async def on_message(msg: dict):
        received_messages.append(msg)

    transport.set_message_handler(on_message)

    await transport.start()
    assert transport.is_connected()

    # Send message
    await transport.send_message({"jsonrpc": "2.0", "id": 1, "method": "ping"})

    # Wait briefly for echo
    for _ in range(20):
        if received_messages:
            break
        await asyncio.sleep(0.05)

    assert len(received_messages) == 1
    assert received_messages[0]["id"] == 1
    assert received_messages[0]["result"]["echo"] == "ping"

    # Close transport
    await transport.close()
    assert not transport.is_connected()


@async_test
async def test_stdio_client_transport_nonexistent_command():
    transport = StdioClientTransport(command="this_command_definitely_does_not_exist_12345")
    with pytest.raises(MCPTransportError):
        await transport.start()


@async_test
async def test_http_client_transport():
    received_messages: List[dict] = []

    async def on_message(msg: dict):
        received_messages.append(msg)

    transport = HttpClientTransport(url="http://mock-mcp-server.local/rpc")
    transport.set_message_handler(on_message)

    mock_resp = MagicMock()
    mock_resp.content = b'{"jsonrpc": "2.0", "id": 10, "result": {"status": "ok"}}'
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"jsonrpc": "2.0", "id": 10, "result": {"status": "ok"}}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        await transport.start()
        assert transport.is_connected()

        await transport.send_message({"jsonrpc": "2.0", "id": 10, "method": "test"})

        # Allow task dispatch
        await asyncio.sleep(0.02)

        assert len(received_messages) == 1
        assert received_messages[0]["result"]["status"] == "ok"

        await transport.close()
        assert not transport.is_connected()


@async_test
async def test_sse_client_transport_event_parsing():
    received_messages: List[dict] = []

    async def on_message(msg: dict):
        received_messages.append(msg)

    transport = SSEClientTransport(url="http://mock-sse.local/sse")
    transport.set_message_handler(on_message)

    # Test handling of events
    await transport._handle_sse_event("endpoint", "http://mock-sse.local/messages?sessionId=abc123")
    assert transport.post_url == "http://mock-sse.local/messages?sessionId=abc123"

    await transport._handle_sse_event("message", json.dumps({"jsonrpc": "2.0", "id": 42, "result": {"val": 999}}))

    await asyncio.sleep(0.02)
    assert len(received_messages) == 1
    assert received_messages[0]["id"] == 42
    assert received_messages[0]["result"]["val"] == 999


# ==============================================================================
# 4. MCPClient Protocol Engine Tests
# ==============================================================================

class MockTransport(BaseClientTransport):
    """Deterministic in-memory mock transport for testing JSON-RPC 2.0 engine."""

    def __init__(self):
        self.connected = False
        self.sent_messages: List[dict] = []
        self._message_handler = None
        self.responses: Dict[str, Any] = {}

    def is_connected(self) -> bool:
        return self.connected

    async def start(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.connected = False

    async def send_message(self, message: dict) -> None:
        self.sent_messages.append(message)
        method = message.get("method")
        req_id = message.get("id")

        # Automatically generate response if configured
        if req_id is not None and self._message_handler:
            if method in self.responses:
                resp_payload = self.responses[method](message.get("params", {}))
                resp = {"jsonrpc": "2.0", "id": req_id, "result": resp_payload}
                asyncio.create_task(self._message_handler(resp))
            elif method == "initialize":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {"name": "mock-server", "version": "1.0.0"},
                        "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                    },
                }
                asyncio.create_task(self._message_handler(resp))
            elif method == "ping":
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
                asyncio.create_task(self._message_handler(resp))


@async_test
async def test_mcp_client_handshake_and_ping():
    config = MCPServerConfig(name="test_srv", transport="stdio", command="dummy")
    transport = MockTransport()
    client = MCPClient(name="test_srv", config=config, transport=transport)

    assert not client.is_connected()
    ok = await client.connect_async()
    assert ok is True
    assert client.is_connected()
    assert client.server_info["name"] == "mock-server"
    assert client.protocol_version == "2024-11-05"

    # Ping test
    ping_ok = await client.ping_async()
    assert ping_ok is True

    # Check that initialize and notifications/initialized were sent
    methods_sent = [m.get("method") for m in transport.sent_messages]
    assert "initialize" in methods_sent
    assert "notifications/initialized" in methods_sent

    await client.disconnect_async()
    assert not client.is_connected()


@async_test
async def test_mcp_client_tools_list_and_call():
    config = MCPServerConfig(name="tool_srv", transport="stdio", command="dummy")
    transport = MockTransport()

    # Configure tool list response
    transport.responses["tools/list"] = lambda params: {
        "tools": [
            {
                "name": "lookup_docs",
                "description": "Lookup documentation",
                "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
            }
        ]
    }

    # Configure tool call response
    transport.responses["tools/call"] = lambda params: {
        "content": [{"type": "text", "text": f"Found docs for {params.get('arguments', {}).get('query')}"}],
        "isError": False,
    }

    client = MCPClient(name="tool_srv", config=config, transport=transport)
    await client.connect_async()

    tools = await client.list_tools_async()
    assert len(tools) == 1
    assert tools[0].name == "lookup_docs"
    assert tools[0].server_name == "tool_srv"

    result = await client.call_tool_async("lookup_docs", {"query": "asyncio"})
    assert not result.is_error
    assert "Found docs for asyncio" in result.text
    assert result.server_name == "tool_srv"
    assert result.tool_name == "lookup_docs"

    await client.disconnect_async()


@async_test
async def test_mcp_client_resources_and_prompts():
    config = MCPServerConfig(name="res_srv", transport="stdio", command="dummy")
    transport = MockTransport()

    transport.responses["resources/list"] = lambda params: {
        "resources": [
            {
                "uri": "memo://notes/1",
                "name": "Project Memo",
                "mimeType": "text/plain",
            }
        ]
    }

    transport.responses["resources/read"] = lambda params: {
        "contents": [
            {
                "uri": params.get("uri"),
                "mimeType": "text/plain",
                "text": "Meeting notes content here.",
            }
        ]
    }

    transport.responses["prompts/list"] = lambda params: {
        "prompts": [
            {
                "name": "summarize",
                "description": "Summarize text",
                "arguments": [{"name": "text", "required": True}],
            }
        ]
    }

    transport.responses["prompts/get"] = lambda params: {
        "description": "Summary prompt",
        "messages": [
            {"role": "user", "content": f"Please summarize: {params.get('arguments', {}).get('text')}"}
        ],
    }

    client = MCPClient(name="res_srv", config=config, transport=transport)
    await client.connect_async()

    # Resources
    resources = await client.list_resources_async()
    assert len(resources) == 1
    assert resources[0].uri == "memo://notes/1"

    res_content = await client.read_resource_async("memo://notes/1")
    assert res_content.text == "Meeting notes content here."

    # Prompts
    prompts = await client.list_prompts_async()
    assert len(prompts) == 1
    assert prompts[0].name == "summarize"

    p_result = await client.get_prompt_async("summarize", {"text": "Long story short"})
    assert len(p_result.messages) == 1
    assert "Please summarize: Long story short" in p_result.messages[0].content

    await client.disconnect_async()


@async_test
async def test_mcp_client_protocol_error_handling():
    config = MCPServerConfig(name="err_srv", transport="stdio", command="dummy")
    transport = MockTransport()
    client = MCPClient(name="err_srv", config=config, transport=transport)
    await client.connect_async()

    # Simulate server returning JSON-RPC error
    async def inject_error():
        await asyncio.sleep(0.01)
        req_id = list(client._pending_requests.keys())[0]
        err_msg = {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": "Method not found", "data": "Extra info"},
        }
        await client._handle_incoming_message(err_msg)

    asyncio.create_task(inject_error())

    with pytest.raises(MCPProtocolError) as exc_info:
        await client.send_request_async("unknown_method")

    assert exc_info.value.code == -32601
    assert "Method not found" in str(exc_info.value)

    await client.disconnect_async()


@async_test
async def test_mcp_client_timeout_handling():
    config = MCPServerConfig(name="timeout_srv", transport="stdio", command="dummy", timeout=0.1)
    transport = MockTransport()
    # Don't register response handler to trigger timeout
    client = MCPClient(name="timeout_srv", config=config, transport=transport)
    await client.connect_async()

    with pytest.raises(MCPTimeoutError):
        await client.send_request_async("hanging_method", timeout=0.05)

    # Verify that cancellation notification was sent
    cancelled = any(m.get("method") == "notifications/cancelled" for m in transport.sent_messages)
    assert cancelled

    await client.disconnect_async()


def test_mcp_client_synchronous_wrappers():
    config = MCPServerConfig(name="sync_srv", transport="stdio", command="dummy")
    transport = MockTransport()
    transport.responses["tools/list"] = lambda p: {
        "tools": [{"name": "sync_tool", "description": "Sync tool test"}]
    }
    transport.responses["tools/call"] = lambda p: {
        "content": [{"type": "text", "text": "Sync call result"}]
    }

    client = MCPClient(name="sync_srv", config=config, transport=transport)
    ok = client.connect()
    assert ok is True
    assert client.is_connected()

    tools = client.list_tools()
    assert len(tools) == 1
    assert tools[0].name == "sync_tool"

    res = client.call_tool("sync_tool", {})
    assert res.text == "Sync call result"

    client.disconnect()
    assert not client.is_connected()


# ==============================================================================
# 5. MCPManager Orchestrator Tests
# ==============================================================================

def test_mcp_manager_config_load_and_save(tmp_path):
    config_file = tmp_path / ".kcli" / "mcp.json"
    mgr = MCPManager(config_path=config_file, auto_load=False)

    # Add servers
    mgr.add_server("github", {"command": "npx", "args": ["-y", "github-server"]})
    mgr.add_server("local_py", MCPServerConfig(name="local_py", command="python", args=["server.py"]))

    assert config_file.is_file()

    # Load in fresh manager instance
    mgr2 = MCPManager(config_path=config_file)
    assert len(mgr2.server_configs) == 2
    assert "github" in mgr2.server_configs
    assert "local_py" in mgr2.server_configs
    assert mgr2.server_configs["github"].command == "npx"

    # Remove server
    ok = mgr2.remove_server("github")
    assert ok is True
    assert len(mgr2.server_configs) == 1

    # Reload again
    mgr3 = MCPManager(config_path=config_file)
    assert len(mgr3.server_configs) == 1
    assert "local_py" in mgr3.server_configs


def test_mcp_manager_routing_and_tool_dispatch(tmp_path):
    mgr = MCPManager(config_path=tmp_path / "mcp.json", auto_load=False)

    # Server 1: Git tools
    cfg1 = MCPServerConfig(name="git", transport="stdio", command="dummy")
    t1 = MockTransport()
    t1.responses["tools/list"] = lambda p: {"tools": [{"name": "commit", "description": "Git commit"}]}
    t1.responses["tools/call"] = lambda p: {"content": [{"type": "text", "text": "Committed patch"}]}
    c1 = MCPClient("git", cfg1, transport=t1)

    # Server 2: Web tools
    cfg2 = MCPServerConfig(name="web", transport="stdio", command="dummy")
    t2 = MockTransport()
    t2.responses["tools/list"] = lambda p: {"tools": [{"name": "fetch", "description": "Fetch URL"}]}
    t2.responses["tools/call"] = lambda p: {"content": [{"type": "text", "text": "HTML content"}]}
    c2 = MCPClient("web", cfg2, transport=t2)

    mgr.server_configs["git"] = cfg1
    mgr.clients["git"] = c1
    mgr.server_configs["web"] = cfg2
    mgr.clients["web"] = c2

    # Connect both
    mgr.connect_all()

    # List all tools
    all_tools = mgr.list_tools()
    assert len(all_tools) == 2
    names = [t.name for t in all_tools]
    assert "commit" in names
    assert "fetch" in names

    # Call tool with direct name
    res1 = mgr.call_tool("commit", {"message": "Initial"})
    assert res1.text == "Committed patch"

    # Call tool with namespaced name 'git:commit'
    res2 = mgr.call_tool("git:commit", {})
    assert res2.text == "Committed patch"

    # Call tool with double underscore 'web__fetch'
    res3 = mgr.call_tool("web__fetch", {"url": "https://example.com"})
    assert res3.text == "HTML content"

    # Call tool with explicit server_name
    res4 = mgr.call_tool("fetch", {}, server_name="web")
    assert res4.text == "HTML content"

    # Schema converters
    openai_schemas = mgr.get_openai_tools()
    assert len(openai_schemas) == 2

    anthropic_schemas = mgr.get_anthropic_tools()
    assert len(anthropic_schemas) == 2

    gemini_schemas = mgr.get_gemini_tools()
    assert len(gemini_schemas) == 2

    # Cleanup
    mgr.disconnect_all()


def test_mcp_manager_call_nonexistent_tool(tmp_path):
    mgr = MCPManager(config_path=tmp_path / "mcp.json", auto_load=False)
    with pytest.raises(MCPToolExecutionError):
        mgr.call_tool("nonexistent_tool_xyz")


# ==============================================================================
# 6. CLI Helper Functions Tests
# ==============================================================================

def test_cli_helpers(tmp_path):
    cfg_file = tmp_path / "mcp.json"

    # Add server
    ok = mcp_add_server(
        name="test_srv",
        command="python",
        args=["-m", "mcp_server"],
        env={"API_KEY": "secret"},
        config_path=cfg_file,
    )
    assert ok is True

    # List servers
    servers = mcp_list_servers(config_path=cfg_file)
    assert len(servers) == 1
    assert servers[0]["name"] == "test_srv"
    assert servers[0]["command"] == "python"

    # Remove server
    rem_ok = mcp_remove_server("test_srv", config_path=cfg_file)
    assert rem_ok is True

    servers_after = mcp_list_servers(config_path=cfg_file)
    assert len(servers_after) == 0


def test_mcp_test_connection_helper(tmp_path):
    mgr = MCPManager(config_path=tmp_path / "mcp.json", auto_load=False)
    cfg = MCPServerConfig(name="diag_srv", transport="stdio", command="dummy")
    transport = MockTransport()
    transport.responses["tools/list"] = lambda p: {"tools": [{"name": "ping_tool"}]}
    transport.responses["resources/list"] = lambda p: {"resources": []}
    transport.responses["prompts/list"] = lambda p: {"prompts": []}

    client = MCPClient("diag_srv", cfg, transport=transport)
    mgr.server_configs["diag_srv"] = cfg
    mgr.clients["diag_srv"] = client

    res = mcp_test_connection("diag_srv", manager=mgr)
    assert res["success"] is True
    assert res["connected"] is True
    assert res["ping"] is True
    assert len(res["tools"]) == 1
    assert res["tools"][0]["name"] == "ping_tool"


# ==============================================================================
# 7. Typer CLI Commands Integration Tests
# ==============================================================================

def test_typer_cli_mcp_list_empty(tmp_path):
    cfg_file = tmp_path / "mcp.json"
    result = runner.invoke(app, ["mcp", "list", "--config", str(cfg_file)])
    assert result.exit_code == 0
    assert "No MCP servers configured" in result.output


def test_typer_cli_mcp_add_and_list(tmp_path):
    cfg_file = tmp_path / "mcp.json"

    # Add server
    result_add = runner.invoke(
        app,
        ["mcp", "add", "cli_srv", "echo", "hello", "--config", str(cfg_file)],
    )
    assert result_add.exit_code == 0
    assert "successfully registered" in result_add.output

    # List servers
    result_list = runner.invoke(app, ["mcp", "list", "--config", str(cfg_file)])
    assert result_list.exit_code == 0
    assert "cli_srv" in result_list.output
    assert "echo" in result_list.output

    # Remove server
    result_rm = runner.invoke(app, ["mcp", "remove", "cli_srv", "--config", str(cfg_file)])
    assert result_rm.exit_code == 0
    assert "removed successfully" in result_rm.output


def test_typer_cli_mcp_test_and_call(tmp_path):
    cfg_file = tmp_path / "mcp.json"

    # Create manager and mock server
    mgr = MCPManager(config_path=cfg_file, auto_load=False)
    cfg = MCPServerConfig(name="calc", transport="stdio", command="dummy")
    t = MockTransport()
    t.responses["tools/list"] = lambda p: {
        "tools": [{"name": "add", "description": "Add numbers", "inputSchema": {"type": "object"}}]
    }
    t.responses["tools/call"] = lambda p: {"content": [{"type": "text", "text": "42"}]}
    t.responses["resources/list"] = lambda p: {"resources": []}
    t.responses["prompts/list"] = lambda p: {"prompts": []}

    client = MCPClient("calc", cfg, transport=t)
    mgr.add_server("calc", cfg, save=True)
    mgr.clients["calc"] = client

    with patch("k_cli.cli.MCPManager", return_value=mgr):
        # Test tools command
        res_tools = runner.invoke(app, ["mcp", "tools", "--config", str(cfg_file)])
        assert res_tools.exit_code == 0
        assert "add" in res_tools.output

        # Test call command
        res_call = runner.invoke(app, ["mcp", "call", "add", '{"a": 20, "b": 22}'])
        assert res_call.exit_code == 0
        assert "42" in res_call.output


# ==============================================================================
# 8. Sync/Async Runner and Concurrency Tests
# ==============================================================================

def test_run_sync_utility():
    async def sample_coro(val: int) -> int:
        await asyncio.sleep(0.01)
        return val * 2

    # From synchronous thread
    out = run_sync(sample_coro(21))
    assert out == 42


@async_test
async def test_run_sync_from_inside_event_loop():
    async def sample_coro(msg: str) -> str:
        await asyncio.sleep(0.01)
        return f"Echo: {msg}"

    # run_sync should detect active event loop and execute in worker thread without raising RuntimeError
    out = run_sync(sample_coro("hello world"))
    assert out == "Echo: hello world"


# ==============================================================================
# 9. Advanced Pagination, Notification & Edge Case Tests
# ==============================================================================

@async_test
async def test_mcp_client_pagination_tools_and_resources():
    config = MCPServerConfig(name="paginated_srv", transport="stdio", command="dummy")
    transport = MockTransport()

    # Pagination simulation for tools/list
    def handle_tools_list(params):
        cursor = params.get("cursor")
        if not cursor:
            return {
                "tools": [{"name": "tool_page_1"}],
                "nextCursor": "cursor_page_2",
            }
        elif cursor == "cursor_page_2":
            return {
                "tools": [{"name": "tool_page_2"}],
                "nextCursor": None,
            }
        return {"tools": []}

    # Pagination simulation for resources/list
    def handle_resources_list(params):
        cursor = params.get("cursor")
        if not cursor:
            return {
                "resources": [{"uri": "res://page1", "name": "Res Page 1"}],
                "nextCursor": "res_cursor_2",
            }
        elif cursor == "res_cursor_2":
            return {
                "resources": [{"uri": "res://page2", "name": "Res Page 2"}],
                "nextCursor": None,
            }
        return {"resources": []}

    transport.responses["tools/list"] = handle_tools_list
    transport.responses["resources/list"] = handle_resources_list

    client = MCPClient("paginated_srv", config=config, transport=transport)
    await client.connect_async()

    tools = await client.list_tools_async()
    assert len(tools) == 2
    assert tools[0].name == "tool_page_1"
    assert tools[1].name == "tool_page_2"

    resources = await client.list_resources_async()
    assert len(resources) == 2
    assert resources[0].uri == "res://page1"
    assert resources[1].uri == "res://page2"

    await client.disconnect_async()


@async_test
async def test_mcp_client_cache_invalidation_on_notification():
    config = MCPServerConfig(name="notify_srv", transport="stdio", command="dummy")
    transport = MockTransport()

    call_count = 0

    def handle_tools_list(params):
        nonlocal call_count
        call_count += 1
        return {"tools": [{"name": f"tool_v{call_count}"}]}

    transport.responses["tools/list"] = handle_tools_list

    client = MCPClient("notify_srv", config=config, transport=transport)
    await client.connect_async()

    # First call: hits transport
    tools1 = await client.list_tools_async()
    assert len(tools1) == 1
    assert tools1[0].name == "tool_v1"
    assert call_count == 1

    # Second call: cached
    tools2 = await client.list_tools_async()
    assert tools2[0].name == "tool_v1"
    assert call_count == 1

    # Send notification from server that tools list changed
    notification_msg = {
        "jsonrpc": "2.0",
        "method": "notifications/tools/list_changed",
        "params": {},
    }
    await client._handle_incoming_message(notification_msg)

    # Next call: cache is invalidated, fetches fresh list
    tools3 = await client.list_tools_async()
    assert tools3[0].name == "tool_v2"
    assert call_count == 2

    await client.disconnect_async()


@async_test
async def test_mcp_client_resource_templates():
    config = MCPServerConfig(name="tmpl_srv", transport="stdio", command="dummy")
    transport = MockTransport()
    transport.responses["resources/templates/list"] = lambda p: {
        "resourceTemplates": [
            {
                "uriTemplate": "file:///{path}",
                "name": "Local Files",
                "description": "File system access",
            }
        ]
    }

    client = MCPClient("tmpl_srv", config=config, transport=transport)
    await client.connect_async()

    templates = await client.list_resource_templates_async()
    assert len(templates) == 1
    assert templates[0].uri_template == "file:///{path}"
    assert templates[0].name == "Local Files"
    assert templates[0].server_name == "tmpl_srv"

    await client.disconnect_async()


def test_mcp_manager_auto_connect_and_resource_fallback(tmp_path):
    mgr = MCPManager(config_path=tmp_path / "mcp.json", auto_load=False)

    cfg = MCPServerConfig(name="doc_srv", transport="stdio", command="dummy")
    transport = MockTransport()
    transport.responses["resources/read"] = lambda p: {
        "contents": [{"uri": "doc://api/v1", "text": "API Documentation"}]
    }
    transport.responses["prompts/get"] = lambda p: {
        "description": "Doc prompt",
        "messages": [{"role": "assistant", "content": "Here is API doc"}],
    }

    client = MCPClient("doc_srv", cfg, transport=transport)
    mgr.server_configs["doc_srv"] = cfg
    mgr.clients["doc_srv"] = client

    # Read resource with search fallback
    res = mgr.read_resource("doc://api/v1")
    assert res.text == "API Documentation"

    # Get prompt with search fallback
    p = mgr.get_prompt("doc_prompt", {})
    assert p.description == "Doc prompt"


def test_mcp_manager_remove_nonexistent():
    mgr = MCPManager(auto_load=False)
    assert mgr.remove_server("nonexistent_srv", save=False) is False


def test_mcp_test_connection_failure():
    mgr = MCPManager(auto_load=False)
    # Server with invalid command that will fail to connect
    cfg = MCPServerConfig(name="bad_srv", transport="stdio", command="nonexistent_binary_xyz_999")
    mgr.server_configs["bad_srv"] = cfg

    res = mcp_test_connection("bad_srv", manager=mgr)
    assert res["success"] is False
    assert res["connected"] is False
    assert res["error"] is not None


def test_typer_cli_mcp_invalid_action():
    result = runner.invoke(app, ["mcp", "invalid_action_name"])
    assert result.exit_code in (1, 2)

