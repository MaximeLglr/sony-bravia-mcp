from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

import httpx
import pytest
from conftest import make_client
from fastmcp.client import Client

from bravia_client import BraviaClient
from bravia_client.config import BraviaConfig
from bravia_mcp.server import create_mcp

EXPECTED_TOOLS = {
    "get_tv_state",
    "list_inputs",
    "list_apps",
    "set_power",
    "set_input",
    "launch_app",
    "set_volume",
    "set_mute",
}


@pytest.fixture
def mcp_server(tv):
    return create_mcp(client_factory=lambda: make_client(tv, max_volume=40))


async def test_list_tools_exposes_exactly_eight_tools(mcp_server):
    async with Client(mcp_server) as client:
        tools = await client.list_tools()
    assert {t.name for t in tools} == EXPECTED_TOOLS


async def test_every_tool_has_a_description(mcp_server):
    async with Client(mcp_server) as client:
        tools = await client.list_tools()
    assert len(tools) == 8
    assert all(t.description for t in tools)


async def test_unreachable_tv_returns_error_payload():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    config = BraviaConfig(host="fake.local", psk="secret", retries=1, _env_file=None)
    server = create_mcp(
        client_factory=lambda: BraviaClient(
            config, handler=httpx.MockTransport(handler)
        )
    )
    async with Client(server) as client:
        result = await client.call_tool("list_inputs", {})
    assert result.data["error"] == "TV_UNREACHABLE"
    assert result.data["hint"]


async def test_unknown_input_returns_input_not_found(mcp_server):
    async with Client(mcp_server) as client:
        result = await client.call_tool("set_input", {"name": "inconnu"})
    assert result.data["error"] == "INPUT_NOT_FOUND"
    assert result.data["available"]


async def test_unknown_app_returns_app_not_found(mcp_server):
    async with Client(mcp_server) as client:
        result = await client.call_tool("launch_app", {"name": "inconnu"})
    assert result.data["error"] == "APP_NOT_FOUND"
    assert result.data["available"]


async def test_volume_capped_at_max_volume(mcp_server):
    async with Client(mcp_server) as client:
        result = await client.call_tool("set_volume", {"level": 100})
    assert result.data["volume"] == 40


class CountingTransport(httpx.AsyncBaseTransport):
    def __init__(self, tv):
        self.tv = tv
        self.inflight = 0
        self.max_inflight = 0

    async def handle_async_request(self, request):
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        await asyncio.sleep(0)
        try:
            return self.tv.handler(request)
        finally:
            self.inflight -= 1


async def test_concurrent_calls_are_serialized(tv):
    counting = CountingTransport(tv)
    config = BraviaConfig(host="fake.local", psk="secret", _env_file=None)
    server = create_mcp(
        client_factory=lambda: BraviaClient(config, handler=counting)
    )
    async with Client(server) as client:
        await asyncio.gather(
            client.call_tool("get_tv_state", {}),
            client.call_tool("get_tv_state", {}),
        )
    assert counting.max_inflight == 1


async def test_psk_never_logged(tv, caplog):
    tv.psk = "canary-psk-xyz"

    def unreachable(request):
        raise httpx.ConnectError("connection refused", request=request)

    down_config = BraviaConfig(
        host="fake.local", psk="canary-psk-xyz", retries=1, _env_file=None
    )
    ok_server = create_mcp(client_factory=lambda: make_client(tv))
    down_server = create_mcp(
        client_factory=lambda: BraviaClient(
            down_config, handler=httpx.MockTransport(unreachable)
        )
    )

    with caplog.at_level(logging.DEBUG):
        async with Client(ok_server) as client:
            await client.call_tool("get_tv_state", {})
            await client.call_tool("set_input", {"name": "inconnu"})
            await client.call_tool("launch_app", {"name": "inconnu"})
            await client.call_tool("set_volume", {"level": 100})
        async with Client(down_server) as client:
            await client.call_tool("list_inputs", {})

    assert "canary-psk-xyz" not in caplog.text


async def test_explicit_connect_aclose(tv):
    client = make_client(tv)
    await client.connect()
    state = await client.get_state()
    await client.aclose()
    assert state.power == "active"


class FlakyTransport(httpx.AsyncBaseTransport):
    def __init__(self, tv, failures):
        self.tv = tv
        self.failures = failures

    async def handle_async_request(self, request):
        if self.failures > 0:
            self.failures -= 1
            raise httpx.ConnectError("connection refused", request=request)
        return self.tv.handler(request)


async def test_reconnect_recreates_http_client(tv):
    flaky = FlakyTransport(tv, failures=2)
    config = BraviaConfig(host="fake.local", psk="secret", _env_file=None)
    client = BraviaClient(config, handler=flaky)
    server = create_mcp(client_factory=lambda: client)
    async with Client(server) as mcp_client:
        before = client.transport._client
        result = await mcp_client.call_tool("get_tv_state", {})
        after = client.transport._client
    assert result.data["power"] == "active"
    assert after is not before


def _clean_env():
    return {k: v for k, v in os.environ.items() if not k.startswith("BRAVIA_")}


async def test_subprocess_fails_without_psk(tmp_path):
    env = _clean_env()
    env["BRAVIA_HOST"] = "127.0.0.1"
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "bravia_mcp",
        cwd=tmp_path,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    assert proc.returncode == 2
    assert b"BRAVIA_PSK" in stderr
    assert stdout == b""


async def test_subprocess_handshake_over_stdio(tmp_path):
    env = _clean_env()
    env["BRAVIA_HOST"] = "127.0.0.1"
    env["BRAVIA_PSK"] = "canary-psk-xyz"
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "bravia_mcp",
        "--verbose",
        cwd=tmp_path,
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def send(payload):
        proc.stdin.write(json.dumps(payload).encode() + b"\n")
        await proc.stdin.drain()

    async def recv():
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=30)
        return json.loads(line)

    await send(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        }
    )
    initialized = await recv()
    if "error" in initialized:
        await send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            }
        )
        initialized = await recv()
    assert "result" in initialized

    await send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    await send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = await recv()
    assert {t["name"] for t in tools["result"]["tools"]} == EXPECTED_TOOLS

    proc.stdin.close()
    stderr = await asyncio.wait_for(proc.stderr.read(), timeout=30)
    await asyncio.wait_for(proc.wait(), timeout=30)
    assert b"canary-psk-xyz" not in stderr
