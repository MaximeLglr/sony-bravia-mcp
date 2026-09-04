from __future__ import annotations

from ..config import BraviaConfig
from ..models import VolumeCommand, VolumeEntry, parse_volume_entries
from ..transport import BraviaTransport


class AudioService:
    def __init__(self, transport: BraviaTransport, config: BraviaConfig):
        self.transport = transport
        self.config = config

    def _clamp(self, value: int) -> int:
        return max(0, min(value, self.config.max_volume))

    async def volume_info(self, target: str = "speaker") -> VolumeEntry | None:
        res = await self.transport.call("audio", "getVolumeInformation")
        parsed = parse_volume_entries(self.transport.first(res))
        for entry in parsed:
            if entry.target == target:
                return entry
        return parsed[0] if parsed else None

    async def _resolve_volume(self, cmd: VolumeCommand, target: str) -> str:
        """Volume wire value for setAudioVolume: absolute int or signed delta string."""
        if cmd.level is not None:
            return str(self._clamp(cmd.level))
        if cmd.delta is None:
            raise ValueError("VolumeCommand has neither level nor delta.")
        current = await self.volume_info(target)
        if current is None:
            return f"{cmd.delta:+d}"
        return str(self._clamp(current.volume + cmd.delta))

    async def set_volume(self, cmd: VolumeCommand, target: str = "speaker") -> None:
        value = await self._resolve_volume(cmd, target)
        await self.transport.call(
            "audio", "setAudioVolume", [{"target": target, "volume": value}]
        )

    async def set_mute(self, on: bool) -> None:
        await self.transport.call("audio", "setAudioMute", [{"status": bool(on)}])
