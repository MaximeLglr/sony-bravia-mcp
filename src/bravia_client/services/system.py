from __future__ import annotations

import asyncio
import logging
import time

from ..config import BraviaConfig
from ..errors import BraviaError, TVUnreachable
from ..models import PowerStatusPayload, SystemInfo
from ..transport import BraviaTransport

log = logging.getLogger("bravia")

POWER_POLL_TIMEOUT = 15.0
POWER_POLL_INTERVAL = 1.0


class SystemService:
    def __init__(self, transport: BraviaTransport, config: BraviaConfig):
        self.transport = transport
        self.config = config

    async def power_status(self) -> str:
        res = self.transport.first(
            await self.transport.call("system", "getPowerStatus")
        )
        return PowerStatusPayload.model_validate(res or {}).status

    async def system_info(self) -> SystemInfo:
        res = self.transport.first(
            await self.transport.call("system", "getSystemInformation")
        )
        return SystemInfo.model_validate(res or {})

    async def set_power(self, on: bool) -> None:
        await self.transport.call("system", "setPowerStatus", [{"status": bool(on)}])

    async def wait_for_power(self, expected: str, timeout: float = POWER_POLL_TIMEOUT) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if await self.power_status() == expected:
                    return
            except BraviaError:
                pass
            await asyncio.sleep(POWER_POLL_INTERVAL)
        log.warning("State %s not confirmed after %.0f s.", expected, timeout)

    async def wait_for_api(self, timeout: float = POWER_POLL_TIMEOUT) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                await self.transport.call("system", "getPowerStatus", retries=1)
                return
            except BraviaError:
                await asyncio.sleep(POWER_POLL_INTERVAL)
        raise TVUnreachable("No response after the Wake-on-LAN packet.")
