from __future__ import annotations

from ..config import BraviaConfig
from ..errors import BraviaError, TVUnreachable
from ..matching import clean_title
from ..models import InputSummary, TVState
from ..transport import BraviaTransport
from .audio import AudioService
from .av_content import AvContentService
from .system import SystemService


class StateService:
    def __init__(
        self,
        transport: BraviaTransport,
        config: BraviaConfig,
        system: SystemService,
        av_content: AvContentService,
        audio: AudioService,
    ):
        self.transport = transport
        self.config = config
        self.system = system
        self.av_content = av_content
        self.audio = audio

    async def get_state(self) -> TVState:
        state = TVState()
        stale: list[str] = []

        try:
            state.power = await self.system.power_status()
            state.reachable = True
        except TVUnreachable:
            return state
        except BraviaError:
            state.power = "unknown"
            state.reachable = True
            stale.append("power")

        if state.power != "active":
            state.stale_fields = stale
            return state

        try:
            current = await self.av_content.playing_content()
            if current:
                inputs = await self.av_content.list_inputs()
                match = AvContentService.active_input(inputs, current)
                state.input = (
                    InputSummary(name=match.name, uri=match.uri)
                    if match
                    else InputSummary(
                        name=clean_title(current.title), uri=current.uri
                    )
                )
        except BraviaError:
            stale.append("input")

        try:
            vol = await self.audio.volume_info()
            if vol:
                state.volume = vol.volume
                state.muted = vol.mute
        except BraviaError:
            stale.extend(["volume", "muted"])

        stale.append("foreground_app")

        state.stale_fields = stale
        return state
