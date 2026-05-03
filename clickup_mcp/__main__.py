from __future__ import annotations

import argparse

from .server import mcp


def main() -> None:
    parser = argparse.ArgumentParser(prog="clickup-mcp")
    parser.add_argument(
        "--transport",
        default="streamable-http",
        help="MCP transport. Recommended: streamable-http",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--path", default="/mcp", help="HTTP mount path for streamable-http transport")
    args = parser.parse_args()

    # FastMCP: transport names are "streamable-http" or "stdio" (others may exist in newer versions).
    if args.transport in ("http", "streamable", "streamable_http"):
        transport = "streamable-http"
    else:
        transport = args.transport

    if transport == "streamable-http":
        mcp.run(transport=transport, host=args.host, port=args.port, path=args.path)
    else:
        mcp.run(transport=transport)


if __name__ == "__main__":
    main()

