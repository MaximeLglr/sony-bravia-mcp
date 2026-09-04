from __future__ import annotations

import argparse
import logging
import sys

from bravia_client import BraviaError, client_from_env

from .server import create_mcp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bravia-mcp", description="Sony Bravia MCP server.")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        default="stdio",
        help="MCP transport (default: stdio). http and sse serve over the network.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address for http/sse transports (default: %(default)s).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Bind port for http/sse transports (default: %(default)s).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        tv = client_from_env()
    except BraviaError as exc:
        print(f"bravia-mcp: {exc.message}", file=sys.stderr)
        return 2

    mcp = create_mcp(client_factory=lambda: tv)
    if args.transport == "stdio":
        mcp.run(transport="stdio", show_banner=False)
    else:
        mcp.run(
            transport=args.transport,
            host=args.host,
            port=args.port,
            show_banner=False,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
