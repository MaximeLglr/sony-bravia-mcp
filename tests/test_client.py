from __future__ import annotations

import json

import httpx
import pytest
from conftest import make_client

from bravia_client import AppNotFound, AuthFailed, InputNotFound
from bravia_client.errors import WebApiUnavailable


async def test_list_inputs_dedup(client):
    async with client:
        inputs = await client.list_inputs()
    assert len(inputs) == 4
    names = [i.name for i in inputs]
    assert names == ["Apple TV", "HDMI 2", "HDMI 3 (eARC/ARC)", "PlayStation 5"]


async def test_list_inputs_cec_semantics(client):
    async with client:
        inputs = await client.list_inputs()
    ps5 = next(i for i in inputs if i.name == "PlayStation 5")
    assert ps5.connected is True
    assert ps5.uri.startswith("extInput:cec?port=4")
    appletv = next(i for i in inputs if i.name == "Apple TV")
    assert appletv.active is True
    hdmi2 = next(i for i in inputs if i.name == "HDMI 2")
    assert hdmi2.connected is False


async def test_set_input_exact_name(client):
    async with client:
        state = await client.set_input("Apple TV")
    assert state.input.name == "Apple TV"


async def test_set_input_case_insensitive(client):
    async with client:
        state = await client.set_input("playstation 5")
    assert state.input.name == "PlayStation 5"


async def test_set_input_unknown_raises(client):
    async with client:
        with pytest.raises(InputNotFound) as exc_info:
            await client.set_input("chromecast")
    assert "available" in exc_info.value.to_dict()


async def test_list_apps_titles_cleaned(client):
    async with client:
        apps = await client.list_apps()
    titles = [a.title for a in apps]
    assert "D\u00e9cor d'int\u00e9rieur" in titles
    assert "Play Store" in titles


async def test_launch_app_unknown_raises(client):
    async with client:
        with pytest.raises(AppNotFound):
            await client.launch_app("spotify")


async def test_get_state_full(client):
    async with client:
        state = await client.get_state()
    d = state.model_dump()
    assert d["power"] == "active"
    assert d["reachable"] is True
    assert d["input"]["name"] == "Apple TV"
    assert "foreground_app" in d["stale_fields"]


async def test_power_cycle(client):
    async with client:
        state = await client.set_power(False)
        assert state.power == "standby"
        assert state.reachable is True

        state = await client.set_power(True)
        assert state.power == "active"


async def test_retry_on_transient_5xx(tv):
    tv.fail_times = 2
    client = make_client(tv)
    async with client:
        state = await client.get_state()
    assert state.power == "active"


async def test_persistent_5xx_raises(tv):
    tv.fail_times = 99
    client = make_client(tv, retries=2)
    async with client:
        with pytest.raises(WebApiUnavailable):
            await client.power_status()


async def test_auth_failure(tv):
    client = make_client(tv)
    client.config.psk = "wrong"
    async with client:
        with pytest.raises(AuthFailed):
            await client.system_info()


async def test_mute(client):
    async with client:
        state = await client.set_mute(True)
    assert state.muted is True


async def test_stale_fields_when_volume_fails(tv):
    def failing_volume(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "getVolumeInformation":
            return httpx.Response(200, json={"error": [7, "Illegal State"], "id": body["id"]})
        return tv.handler(request)

    client = make_client(tv)
    client.transport._handler = httpx.MockTransport(failing_volume)
    async with client:
        state = await client.get_state()
    assert "volume" in state.stale_fields
    assert "muted" in state.stale_fields
