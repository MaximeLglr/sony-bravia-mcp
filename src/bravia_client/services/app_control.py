from __future__ import annotations

import time

from pydantic import TypeAdapter

from ..config import BraviaConfig
from ..matching import clean_title
from ..models import App, AppEntry
from ..transport import BraviaTransport

_app_entries = TypeAdapter(list[AppEntry])


class AppControlService:
    def __init__(self, transport: BraviaTransport, config: BraviaConfig):
        self.transport = transport
        self.config = config
        self._cache: tuple[float, list[App]] | None = None

    async def list_apps(self, refresh: bool = False) -> list[App]:
        now = time.monotonic()
        if not refresh and self._cache:
            stamp, cached = self._cache
            if now - stamp < self.config.apps_cache_ttl:
                return cached

        res = await self.transport.call("appControl", "getApplicationList")
        raw = self.transport.first(res)
        entries = _app_entries.validate_python(raw if isinstance(raw, list) else [])

        apps = [
            App(title=clean_title(entry.title), uri=entry.uri, icon=entry.icon)
            for entry in entries
            if entry.uri
        ]
        self._cache = (now, apps)
        return apps

    async def launch_app_uri(self, uri: str) -> None:
        await self.transport.call("appControl", "setActiveApp", [{"uri": uri}])
