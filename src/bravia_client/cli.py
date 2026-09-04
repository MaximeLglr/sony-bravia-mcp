from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import Any

from .client import BraviaClient, client_from_env
from .errors import BraviaError


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


async def _state(tv: BraviaClient, args: argparse.Namespace) -> dict[str, Any]:
    return (await tv.get_state()).model_dump()


async def _inputs(tv: BraviaClient, args: argparse.Namespace) -> list[dict[str, Any]]:
    return [i.model_dump() for i in await tv.list_inputs()]


async def _input(tv: BraviaClient, args: argparse.Namespace) -> dict[str, Any]:
    return (await tv.set_input(args.name)).model_dump()


async def _apps(tv: BraviaClient, args: argparse.Namespace) -> list[dict[str, Any]]:
    return [a.model_dump(exclude={"icon"}) for a in await tv.list_apps(refresh=args.refresh)]


async def _app(tv: BraviaClient, args: argparse.Namespace) -> dict[str, Any]:
    return (await tv.launch_app(args.name)).model_dump()


async def _power(tv: BraviaClient, args: argparse.Namespace) -> dict[str, Any]:
    return (await tv.set_power(args.value == "on")).model_dump()


async def _volume(tv: BraviaClient, args: argparse.Namespace) -> dict[str, Any]:
    return (await tv.set_volume(level=args.level, delta=args.delta)).model_dump()


async def _mute(tv: BraviaClient, args: argparse.Namespace) -> dict[str, Any]:
    return (await tv.set_mute(args.value == "on")).model_dump()


async def _methods(tv: BraviaClient, args: argparse.Namespace) -> dict[str, list[str]]:
    return await tv.supported_methods()


async def _info(tv: BraviaClient, args: argparse.Namespace) -> dict[str, Any]:
    return (await tv.system_info()).model_dump()


DISPATCH: dict[str, Any] = {
    "state": _state,
    "inputs": _inputs,
    "input": _input,
    "apps": _apps,
    "app": _app,
    "power": _power,
    "volume": _volume,
    "mute": _mute,
    "methods": _methods,
    "info": _info,
}


async def _run(args: argparse.Namespace) -> int:
    try:
        client = client_from_env()
    except BraviaError as exc:
        _print(exc.to_dict())
        return 2

    async with client as tv:
        try:
            _print(await DISPATCH[args.command](tv, args))
        except BraviaError as exc:
            _print(exc.to_dict())
            return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bravia", description="Sony Bravia client.")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("state", help="Consolidated TV state")
    sub.add_parser("inputs", help="Inputs, CEC/HDMI deduplicated")
    sub.add_parser("methods", help="Methods exposed by this firmware")
    sub.add_parser("info", help="System information")

    p = sub.add_parser("input", help="Switch to an input")
    p.add_argument("name")

    p = sub.add_parser("apps", help="Installed applications")
    p.add_argument("--refresh", action="store_true", help="Bypass the cache")

    p = sub.add_parser("app", help="Launch an application")
    p.add_argument("name")

    p = sub.add_parser("power", help="Power on or off")
    p.add_argument("value", choices=["on", "off"])

    p = sub.add_parser("volume", help="Set the volume")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--level", type=int)
    g.add_argument("--delta", type=int)

    p = sub.add_parser("mute", help="Mute or unmute")
    p.add_argument("value", choices=["on", "off"])

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
