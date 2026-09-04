from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MAX_VOLUME = 40
APPS_CACHE_TTL = 6 * 3600


class BraviaConfig(BaseSettings):
    host: str
    psk: str
    mac: str | None = None
    scheme: Literal["http", "https"] = "http"
    timeout: float = 5.0
    max_volume: int = Field(DEFAULT_MAX_VOLUME, ge=0, le=100)
    retries: int = 3
    apps_cache_ttl: float = APPS_CACHE_TTL

    model_config = SettingsConfigDict(env_prefix="BRAVIA_", env_file=".env")

    @field_validator("mac")
    @classmethod
    def _validate_mac(cls, value: str | None) -> str | None:
        if value is None:
            return value
        clean = value.replace(":", "").replace("-", "").replace(".", "")
        if len(clean) != 12 or not all(c in "0123456789abcdefABCDEF" for c in clean):
            raise ValueError(f"Invalid MAC address: {value}")
        return value

    @property
    def mac_hex(self) -> str | None:
        if self.mac is None:
            return None
        return self.mac.replace(":", "").replace("-", "").replace(".", "").lower()
