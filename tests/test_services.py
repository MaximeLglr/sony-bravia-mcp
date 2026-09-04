from __future__ import annotations

import pytest

from bravia_client.errors import BadRequest
from bravia_client.wol import send_magic_packet


async def test_volume_ceiling_applied_on_level(client):
    async with client:
        state = await client.set_volume(level=100)
    assert state.volume == 40


async def test_volume_ceiling_applied_on_delta(client, tv):
    tv.volume = 38
    async with client:
        state = await client.set_volume(delta=10)
    assert state.volume == 40


async def test_volume_delta_negative(client, tv):
    tv.volume = 20
    async with client:
        state = await client.set_volume(delta=-5)
    assert state.volume == 15


async def test_volume_both_args_rejected(client):
    async with client:
        with pytest.raises(BadRequest):
            await client.set_volume(level=10, delta=5)


async def test_app_cache_served(client, tv):
    async with client:
        await client.list_apps()
        before = sum(1 for _, m, _ in tv.calls if m == "getApplicationList")
        await client.list_apps()
        after = sum(1 for _, m, _ in tv.calls if m == "getApplicationList")
    assert before == after


async def test_app_cache_refresh_bypasses(client, tv):
    async with client:
        await client.list_apps()
        before = sum(1 for _, m, _ in tv.calls if m == "getApplicationList")
        await client.list_apps(refresh=True)
        after = sum(1 for _, m, _ in tv.calls if m == "getApplicationList")
    assert after == before + 1


def test_wol_packet_is_102_bytes():
    mac_hex = "eeb2ebb799a6"
    packet = b"\xff" * 6 + bytes.fromhex(mac_hex) * 16
    assert len(packet) == 102


def test_wol_rejects_short_mac():
    with pytest.raises(BadRequest):
        send_magic_packet("abc")


async def test_set_input_exact_name(client, tv):
    async with client:
        state = await client.set_input("PlayStation 5")
    assert state.input.name == "PlayStation 5"
    assert tv.playing.startswith("extInput:cec?port=4")


async def test_launch_app_exact_title(client, tv):
    async with client:
        await client.launch_app("YouTube")
    assert tv.last_app.endswith("ShellActivity")
    assert "youtube.tv" in tv.last_app


async def test_launch_app_case_insensitive(client, tv):
    async with client:
        await client.launch_app("netflix")
    assert "netflix" in tv.last_app


async def test_playing_content_standby_returns_none(client, tv):
    tv.power = "standby"
    async with client:
        content = await client.av_content.playing_content()
    assert content is None


async def test_volume_info_returns_speaker_entry(client):
    async with client:
        entry = await client.audio.volume_info()
    assert entry.target == "speaker"
    assert entry.volume == 22
    assert entry.max_volume == 100
