from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field, TypeAdapter, model_validator

from .matching import clean_title

_SCHEME_RE = re.compile(r"^extInput:([a-zA-Z0-9_]+)")


class PowerStatusPayload(BaseModel):
    status: str = "unknown"


class SystemInfo(BaseModel):
    product: str = ""
    model: str = ""
    area: str = ""
    language: str = ""
    generation: str = ""
    model_name: str = ""
    model_info: str = ""


class PlayingContentInfo(BaseModel):
    uri: str = ""
    title: str = ""
    source: str = ""


class VolumeEntry(BaseModel):
    target: str = ""
    volume: int = 0
    mute: bool = False
    min_volume: int = Field(0, alias="minVolume")
    max_volume: int = Field(100, alias="maxVolume")
    model_config = {"populate_by_name": True}


class RawInput(BaseModel):
    uri: str = ""
    title: str = ""
    label: str = ""
    connection: bool = False
    icon: str | None = None


class AppEntry(BaseModel):
    title: str = ""
    uri: str = ""
    icon: str | None = None


class RpcError(BaseModel):
    code: int = -1
    message: str = ""

    @model_validator(mode="before")
    @classmethod
    def _unpack(cls, value: Any) -> dict[str, Any]:
        if isinstance(value, list) and value:
            code = value[0] if isinstance(value[0], int) else -1
            message = value[1] if len(value) > 1 else ""
            return {"code": code, "message": str(message)}
        if isinstance(value, dict):
            return value
        return {"code": -1, "message": str(value)}


class RpcRequest(BaseModel):
    method: str
    version: str = "1.0"
    id: int = 0
    params: list[Any] = Field(default_factory=list)


class RpcResponse(BaseModel):
    result: Any = Field(default_factory=list)
    error: RpcError | None = None


class Input(BaseModel):
    name: str
    uri: str
    port: int | None
    kind: str
    connected: bool
    active: bool = False
    cec: bool = False


class App(BaseModel):
    title: str
    uri: str
    icon: str | None = None

    def matches_package(self, package: str) -> bool:
        return bool(package) and package in self.uri


class InputSummary(BaseModel):
    name: str
    uri: str


class TVState(BaseModel):
    power: str = "unreachable"
    input: InputSummary | None = None
    foreground_app: dict[str, Any] | None = None
    volume: int | None = None
    muted: bool | None = None
    reachable: bool = False
    stale_fields: list[str] = Field(default_factory=list)


class VolumeCommand(BaseModel):
    level: int | None = None
    delta: int | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> VolumeCommand:
        if (self.level is None) == (self.delta is None):
            raise ValueError("Provide exactly one of `level` or `delta`.")
        return self


class SupportedApis(BaseModel):
    services: dict[str, list[str]] = Field(default_factory=dict)


def port_key(uri: str) -> tuple[str, int | None]:
    m = _SCHEME_RE.match(uri or "")
    kind = m.group(1).lower() if m else "unknown"
    if kind == "cec":
        kind = "hdmi"

    port: int | None = None
    qs = parse_qs(urlparse(uri).query)
    if "port" in qs:
        raw = qs["port"][0]
        if raw.isdigit():
            port = int(raw)

    return (kind, port)


def is_cec(uri: str) -> bool:
    return (uri or "").startswith("extInput:cec")


_raw_input_list = TypeAdapter(list[RawInput])
_volume_entries = TypeAdapter(list[VolumeEntry])


def merge_inputs(raw: list[RawInput], active_uri: str | None = None) -> list[Input]:
    groups: dict[tuple[str, int | None], dict[str, RawInput | None]] = {}

    for entry in raw:
        key = port_key(entry.uri)
        slot = groups.setdefault(key, {"cec": None, "plain": None})
        slot["cec" if is_cec(entry.uri) else "plain"] = entry

    active_key = port_key(active_uri) if active_uri else None

    merged: list[Input] = []
    for key, slot in groups.items():
        cec_entry, plain_entry = slot["cec"], slot["plain"]
        primary = cec_entry or plain_entry
        if primary is None:
            continue

        connected = bool(cec_entry) or bool(plain_entry and plain_entry.connection)

        label = clean_title(primary.label)
        title = clean_title(primary.title)

        merged.append(
            Input(
                name=label or title or f"{key[0].upper()} {key[1]}",
                uri=primary.uri,
                port=key[1],
                kind=key[0],
                connected=connected,
                active=(active_key == key),
                cec=bool(cec_entry),
            )
        )

    merged.sort(key=lambda i: (i.kind, i.port if i.port is not None else 99))
    return merged


def parse_raw_inputs(raw: Any) -> list[RawInput]:
    return _raw_input_list.validate_python(raw if isinstance(raw, list) else [])


def parse_volume_entries(raw: Any) -> list[VolumeEntry]:
    entries = raw if isinstance(raw, list) else ([raw] if raw else [])
    return _volume_entries.validate_python(entries)
