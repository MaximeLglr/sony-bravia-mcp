from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

import httpx
from pydantic import ValidationError

from .config import BraviaConfig
from .errors import AppNotFound, BadRequest, InputNotFound, TVUnreachable
from .matching import clean_title
from .models import App, Input, SupportedApis, SystemInfo, TVState, VolumeCommand
from .services.app_control import AppControlService
from .services.audio import AudioService
from .services.av_content import AvContentService
from .services.state import StateService
from .services.system import SystemService
from .transport import BraviaTransport
from .wol import send_magic_packet

log = logging.getLogger("bravia")


class BraviaClient:
    def __init__(self, config: BraviaConfig, handler: httpx.AsyncBaseTransport | None = None):
        self.config = config
        self.transport = BraviaTransport(config, handler)
        self.system = SystemService(self.transport, config)
        self.av_content = AvContentService(self.transport, config)
        self.audio = AudioService(self.transport, config)
        self.app_control = AppControlService(self.transport, config)
        self.state = StateService(
            self.transport, config, self.system, self.av_content, self.audio
        )

    async def connect(self) -> None:
        await self.transport.open()

    async def aclose(self) -> None:
        await self.transport.close()

    async def __aenter__(self) -> BraviaClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def get_state(self) -> TVState:
        return await self.state.get_state()

    async def power_status(self) -> str:
        return await self.system.power_status()

    async def system_info(self) -> SystemInfo:
        return await self.system.system_info()

    async def list_inputs(self) -> list[Input]:
        return await self.av_content.list_inputs()

    async def set_input(self, name: str) -> TVState:
        inputs = await self.av_content.list_inputs()
        wanted = clean_title(name).casefold()
        match = next((i for i in inputs if clean_title(i.name).casefold() == wanted), None)
        if match is None:
            raise InputNotFound(
                f"No input is named \"{name}\".",
                available=[i.name for i in inputs],
            )
        await self.av_content.set_input_uri(match.uri)
        return await self.state.get_state()

    async def list_apps(self, *, refresh: bool = False) -> list[App]:
        return await self.app_control.list_apps(refresh=refresh)

    async def launch_app(self, name: str) -> TVState:
        apps = await self.app_control.list_apps()
        wanted = clean_title(name).casefold()
        match = next((a for a in apps if clean_title(a.title).casefold() == wanted), None)
        if match is None:
            raise AppNotFound(
                f"No application is titled \"{name}\".",
                available=[a.title for a in apps],
            )
        await self.app_control.launch_app_uri(match.uri)
        return await self.state.get_state()

    async def set_power(self, on: bool) -> TVState:
        try:
            await self.system.set_power(on)
        except TVUnreachable:
            if not on:
                raise
            mac_hex = self.config.mac_hex
            if not mac_hex:
                raise TVUnreachable(
                    "TV unreachable and no MAC address configured for "
                    "Wake-on-LAN (BRAVIA_MAC)."
                ) from None
            log.info("API unreachable, falling back to Wake-on-LAN.")
            send_magic_packet(mac_hex)
            await self.system.wait_for_api()
            await self.system.set_power(True)

        await self.system.wait_for_power("active" if on else "standby")
        return await self.state.get_state()

    async def set_volume(
        self,
        level: int | None = None,
        delta: int | None = None,
        target: str = "speaker",
    ) -> TVState:
        try:
            cmd = VolumeCommand(level=level, delta=delta)
        except ValidationError as exc:
            raise BadRequest("Provide exactly one of `level` or `delta`.") from exc
        await self.audio.set_volume(cmd, target)
        return await self.state.get_state()

    async def set_mute(self, on: bool) -> TVState:
        await self.audio.set_mute(on)
        return await self.state.get_state()

    async def supported_methods(
        self, services: Iterable[str] = ("system", "avContent", "audio", "appControl")
    ) -> dict[str, list[str]]:
        res = await self.transport.call(
            "guide", "getSupportedApiInfo", [{"services": list(services)}]
        )
        raw = self.transport.first(res)
        out: dict[str, list[str]] = {}
        for svc in raw if isinstance(raw, list) else []:
            out[svc.get("service", "?")] = sorted(
                api.get("name", "") for api in svc.get("apis", [])
            )
        return SupportedApis(services=out).services


def client_from_env(**overrides: Any) -> BraviaClient:
    try:
        config = BraviaConfig(**overrides)
    except ValidationError as exc:
        missing = next(
            (e["loc"][0] for e in exc.errors() if e["type"] == "missing"), None
        )
        if missing:
            raise BadRequest(f"BRAVIA_{str(missing).upper()} is not set.") from exc
        raise BadRequest(str(exc.errors()[0]["msg"])) from exc
    return BraviaClient(config)
