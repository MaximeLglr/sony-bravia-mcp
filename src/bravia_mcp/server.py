from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.context import Context

from bravia_client import BraviaClient, BraviaError, client_from_env


def create_mcp(client_factory: Callable[[], BraviaClient] = client_from_env) -> FastMCP:
    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        tv = client_factory()
        await tv.connect()
        try:
            yield {"tv": tv}
        finally:
            await tv.aclose()

    mcp = FastMCP("bravia", lifespan=lifespan)

    @mcp.tool
    async def get_tv_state(ctx: Context) -> dict[str, Any]:
        """État consolidé de la TV : alimentation, entrée active, application au premier plan, volume, muet.

        Retourne un objet avec `power` ("active" ou "standby"), `input` (nom et URI de
        l'entrée active), `foreground_app`, `volume`, `muted`, `reachable` et
        `stale_fields` (champs non lus). Ne échoue jamais si la TV répond partiellement.
        """
        tv: BraviaClient = ctx.lifespan_context["tv"]
        try:
            return (await tv.get_state()).model_dump()
        except BraviaError as exc:
            return exc.to_dict()

    @mcp.tool
    async def list_inputs(ctx: Context) -> dict[str, Any] | list[dict[str, Any]]:
        """Entrées HDMI de la TV, dédupliquées CEC/HDMI par port.

        Chaque entrée a un `name` convivial, une `uri` opaque, un `port`, un `kind`,
        un `connected` (true si le périphérique est détecté) et un `active`.
        Utilisez le `name` avec set_input.
        """
        tv: BraviaClient = ctx.lifespan_context["tv"]
        try:
            return [i.model_dump() for i in await tv.list_inputs()]
        except BraviaError as exc:
            return exc.to_dict()

    @mcp.tool
    async def list_apps(ctx: Context, refresh: bool = False) -> dict[str, Any] | list[dict[str, Any]]:
        """Applications installées sur la TV, indexées par titre.

        Chaque application a un `title` convivial et une `uri` opaque. Utilisez le
        `title` avec launch_app. La liste est mise en cache 6 heures ; passez
        `refresh=true` pour la forcer.
        """
        tv: BraviaClient = ctx.lifespan_context["tv"]
        try:
            return [a.model_dump(exclude={"icon"}) for a in await tv.list_apps(refresh=refresh)]
        except BraviaError as exc:
            return exc.to_dict()

    @mcp.tool
    async def set_power(ctx: Context, on: bool) -> dict[str, Any]:
        """Allume ou éteint la TV.

        `on=true` allume (avec repli Wake-on-LAN si l'API est injoignable),
        `on=false` met en veille. Retourne l'état consolidé après la commande.
        """
        tv: BraviaClient = ctx.lifespan_context["tv"]
        try:
            return (await tv.set_power(on)).model_dump()
        except BraviaError as exc:
            return exc.to_dict()

    @mcp.tool
    async def set_input(ctx: Context, name: str) -> dict[str, Any]:
        """Sélectionne une entrée HDMI par son nom exact.

        Le nom doit être celui retourné par list_inputs (la casse est ignorée).
        Un nom inconnu retourne une erreur INPUT_NOT_FOUND avec la liste
        `available`. Sélectionner une entrée peut réveiller le périphérique via
        CEC. Retourne l'état consolidé après la commande.
        """
        tv: BraviaClient = ctx.lifespan_context["tv"]
        try:
            return (await tv.set_input(name)).model_dump()
        except BraviaError as exc:
            return exc.to_dict()

    @mcp.tool
    async def launch_app(ctx: Context, name: str) -> dict[str, Any]:
        """Lance une application par son titre exact.

        Le titre doit être celui retourné par list_apps (la casse est ignorée).
        Un titre inconnu retourne une erreur APP_NOT_FOUND avec la liste
        `available`. Retourne l'état consolidé après la commande.
        """
        tv: BraviaClient = ctx.lifespan_context["tv"]
        try:
            return (await tv.launch_app(name)).model_dump()
        except BraviaError as exc:
            return exc.to_dict()

    @mcp.tool
    async def set_volume(
        ctx: Context, level: int | None = None, delta: int | None = None
    ) -> dict[str, Any]:
        """Règle le volume : `level` pour une valeur absolue, `delta` pour un ajustement relatif.

        Fournissez exactement un des deux paramètres. Le volume est plafonné côté
        client (40 par défaut). Retourne l'état consolidé après la commande.
        """
        tv: BraviaClient = ctx.lifespan_context["tv"]
        try:
            return (await tv.set_volume(level=level, delta=delta)).model_dump()
        except BraviaError as exc:
            return exc.to_dict()

    @mcp.tool
    async def set_mute(ctx: Context, on: bool) -> dict[str, Any]:
        """Active ou désactive le mode muet.

        `on=true` coupe le son, `on=false` le rétablit. Retourne l'état consolidé
        après la commande.
        """
        tv: BraviaClient = ctx.lifespan_context["tv"]
        try:
            return (await tv.set_mute(on)).model_dump()
        except BraviaError as exc:
            return exc.to_dict()

    return mcp


mcp = create_mcp()
