from __future__ import annotations

import json

import httpx
import pytest
from conftest import FakeTV

from bravia_client.config import BraviaConfig
from bravia_client.errors import (
    AuthFailed,
    TVStandby,
    TVUnreachable,
    UnsupportedMethod,
    WebApiUnavailable,
)
from bravia_client.transport import BraviaTransport


def make_transport(handler, **config_overrides) -> BraviaTransport:
    config = BraviaConfig(host="fake.local", psk="secret", _env_file=None, **config_overrides)
    return BraviaTransport(config, httpx.MockTransport(handler))


async def test_retry_on_5xx_then_success():
    tv = FakeTV()
    tv.fail_times = 2
    transport = make_transport(tv.handler)
    async with transport:
        result = await transport.call("system", "getPowerStatus")
    assert transport.first(result) == {"status": "active"}


async def test_persistent_5xx_raises_webapi_unavailable():
    tv = FakeTV()
    tv.fail_times = 99
    transport = make_transport(tv.handler, retries=2)
    async with transport:
        with pytest.raises(WebApiUnavailable):
            await transport.call("system", "getPowerStatus")


async def test_403_raises_auth_failed():
    def handler(request):
        return httpx.Response(403)

    transport = make_transport(handler)
    async with transport:
        with pytest.raises(AuthFailed):
            await transport.call("system", "getPowerStatus")


async def test_404_raises_unsupported_method():
    def handler(request):
        return httpx.Response(404)

    transport = make_transport(handler)
    async with transport:
        with pytest.raises(UnsupportedMethod):
            await transport.call("unknown", "someMethod")


async def test_sony_error_code_mapped_to_domain_error():
    def handler(request):
        return httpx.Response(200, json={"error": [40005, "Display Is Turned off"], "id": 1})

    transport = make_transport(handler)
    async with transport:
        with pytest.raises(TVStandby):
            await transport.call("avContent", "getPlayingContentInfo")


async def test_malformed_body_raises_webapi_unavailable():
    def handler(request):
        return httpx.Response(200, content=b"not json", headers={"Content-Type": "application/json"})

    transport = make_transport(handler)
    async with transport:
        with pytest.raises(WebApiUnavailable):
            await transport.call("system", "getPowerStatus")


async def test_network_error_raises_tv_unreachable():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    transport = make_transport(handler, retries=1)
    async with transport:
        with pytest.raises(TVUnreachable):
            await transport.call("system", "getPowerStatus")


async def test_call_before_open_raises_runtime_error():
    transport = make_transport(FakeTV().handler)
    with pytest.raises(RuntimeError):
        await transport.call("system", "getPowerStatus")


async def test_psk_header_sent_when_authed():
    seen = []

    def handler(request):
        seen.append(request.headers.get("X-Auth-PSK"))
        body = json.loads(request.content)
        return httpx.Response(200, json={"result": [], "id": body["id"]})

    transport = make_transport(handler)
    async with transport:
        await transport.call("system", "getPowerStatus")
        await transport.call("system", "getPowerStatus", authed=False)
    assert seen == ["secret", None]
