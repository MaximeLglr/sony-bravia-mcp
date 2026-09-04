from __future__ import annotations

from ..config import BraviaConfig
from ..errors import BraviaError
from ..models import Input, PlayingContentInfo, merge_inputs, parse_raw_inputs, port_key
from ..transport import BraviaTransport


class AvContentService:
    def __init__(self, transport: BraviaTransport, config: BraviaConfig):
        self.transport = transport
        self.config = config

    async def playing_content(self) -> PlayingContentInfo | None:
        try:
            res = self.transport.first(
                await self.transport.call("avContent", "getPlayingContentInfo")
            )
            return PlayingContentInfo.model_validate(res or {}) or None
        except BraviaError:
            return None

    async def list_inputs(self) -> list[Input]:
        res = await self.transport.call("avContent", "getCurrentExternalInputsStatus")
        raw = parse_raw_inputs(self.transport.first(res))
        current = await self.playing_content()
        return merge_inputs(raw, current.uri if current else None)

    async def set_input_uri(self, uri: str) -> None:
        await self.transport.call("avContent", "setPlayContent", [{"uri": uri}])

    @staticmethod
    def active_input(inputs: list[Input], current: PlayingContentInfo | None) -> Input | None:
        if current is None:
            return None
        key = port_key(current.uri)
        return next((i for i in inputs if (i.kind, i.port) == key), None)
