from __future__ import annotations

import asyncio
import itertools
import logging
from typing import Any

import httpx
from pydantic import ValidationError

from .config import BraviaConfig
from .errors import (
    SONY_ERROR_MAP,
    AuthFailed,
    BraviaError,
    TVUnreachable,
    UnsupportedMethod,
    WebApiUnavailable,
)
from .models import RpcRequest, RpcResponse

log = logging.getLogger("bravia")


class BraviaTransport:
    def __init__(self, config: BraviaConfig, handler: httpx.AsyncBaseTransport | None = None):
        self.config = config
        self._handler = handler
        self._ids = itertools.count(1)
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    async def open(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=f"{self.config.scheme}://{self.config.host}",
            timeout=self.config.timeout,
            verify=False,
            headers={"Content-Type": "application/json"},
            transport=self._handler,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> BraviaTransport:
        await self.open()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def call(
        self,
        service: str,
        method: str,
        params: list[Any] | None = None,
        version: str = "1.0",
        *,
        authed: bool = True,
        retries: int | None = None,
    ) -> Any:
        if self._client is None:
            raise RuntimeError("Client not open: use `async with`.")

        payload = RpcRequest(
            method=method,
            version=version,
            id=next(self._ids),
            params=params if params is not None else [],
        ).model_dump()
        headers = {"X-Auth-PSK": self.config.psk} if authed else {}
        attempts = self.config.retries if retries is None else retries
        last_exc: Exception | None = None

        async with self._lock:
            for attempt in range(attempts):
                try:
                    resp = await self._client.post(
                        f"/sony/{service}", json=payload, headers=headers
                    )
                except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
                    last_exc = exc
                    log.debug("%s.%s attempt %d: %s", service, method, attempt + 1, exc)
                    if attempt + 1 < attempts:
                        if attempt + 2 == attempts and self._client is not None:
                            await self.close()
                            await self.open()
                        await asyncio.sleep(2**attempt * 0.5)
                        continue
                    raise TVUnreachable(f"{self.config.host} is not responding.") from exc

                if resp.status_code == 403:
                    raise AuthFailed()

                if resp.status_code >= 500:
                    last_exc = httpx.HTTPStatusError(
                        f"HTTP {resp.status_code}", request=resp.request, response=resp
                    )
                    if attempt + 1 < attempts:
                        await asyncio.sleep(2**attempt * 0.5)
                        continue
                    raise WebApiUnavailable(f"HTTP {resp.status_code} on {method}.")

                if resp.status_code == 404:
                    raise UnsupportedMethod(f"Unknown service: {service}.")

                try:
                    body = RpcResponse.model_validate(resp.json())
                except (ValueError, ValidationError) as exc:
                    raise WebApiUnavailable(f"Unreadable response on {method}.") from exc

                if body.error is not None:
                    exc_cls = SONY_ERROR_MAP.get(body.error.code, BraviaError)
                    raise exc_cls(
                        f"{method}: [{body.error.code}] {body.error.message}",
                        sony_code=body.error.code,
                    )

                return body.result

            raise WebApiUnavailable(f"{method} failed.") from last_exc

    @staticmethod
    def first(result: Any) -> Any:
        if isinstance(result, list) and result:
            return result[0]
        return result
