# sony-bravia-mcp

MCP server for Sony Bravia TVs. Control power, HDMI inputs, apps and volume
through the TV's built-in JSON-RPC API. Works with Claude Desktop, Cursor,
Vibe, or any MCP client — over stdio or HTTP.

Built with [FastMCP](https://github.com/jlowin/fastmcp), httpx and Pydantic.

## Requirements

- A Sony Bravia TV on the local network (2019+ models with the
  [Sony BRAVIA Professional API](https://pro-bravia.sony.net/))
- A Pre-Shared Key: on the TV, enable
  *Settings > Network & Internet > Home Network > IP Control > Authentication*
  and set a PSK

## Install

```bash
pip install -e .
cp .env.example .env   # set BRAVIA_HOST and BRAVIA_PSK
```

The `.env` file is loaded automatically; no `source` needed.

## MCP configuration

```json
{
  "mcpServers": {
    "bravia": {
      "command": "bravia-mcp",
      "env": {
        "BRAVIA_HOST": "192.168.1.42",
        "BRAVIA_PSK": "your-pre-shared-key"
      }
    }
  }
}
```

The server starts even with the TV off or unplugged: the first tool call
returns a `TV_UNREACHABLE` error with a hint instead of crashing.

### HTTP transport

stdio is the default. To serve over HTTP instead:

```bash
bravia-mcp --transport http              # 127.0.0.1:8000/mcp
bravia-mcp --transport http --host 0.0.0.0 --port 9000
```

```json
{
  "mcpServers": {
    "bravia": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

## Tools

| Tool | Description |
|---|---|
| `get_tv_state` | Consolidated state: power, input, volume, mute. Never fails as a whole |
| `list_inputs` | HDMI inputs, CEC/HDMI deduplicated by port |
| `list_apps` | Installed apps (6 h cache, `refresh=true` to bypass) |
| `set_power` | On/off, Wake-on-LAN fallback on power-on |
| `set_input` | Switch input by exact name (case-insensitive) |
| `launch_app` | Launch app by exact title (case-insensitive) |
| `set_volume` | Absolute `level` or relative `delta`, capped at `BRAVIA_MAX_VOLUME` |
| `set_mute` | Mute/unmute |

`set_input` and `launch_app` take the exact name returned by `list_inputs` /
`list_apps`. No fuzzy matching: the caller sees the list and picks. Unknown
names come back with the `available` list.

Every tool returns either the expected payload or an error object with
`error`, `message` and `hint` — never an exception.

## CLI

The client layer is usable on its own, without MCP:

```bash
bravia state                    # consolidated state
bravia inputs                   # list inputs
bravia input "Apple TV"         # switch input
bravia apps                     # list apps
bravia app "YouTube"            # launch app
bravia power on|off
bravia volume --level 20        # or --delta -5
bravia mute on|off
bravia methods                  # API methods supported by this firmware
bravia -v state                 # debug traces
```

## Design notes

- **CEC/HDMI deduplication** — one connector appears twice in the TV's
  response; merged by port, with CEC names preferred.
- **Wire hygiene** — the TV emits HTML entities and non-breaking spaces in
  app titles (`Play\xa0Store`, `Décor d&apos;intérieur`); decoded on arrival.
- **Retries** — exponential backoff on network errors and 5xx, never on
  application errors. One JSON-RPC call in flight at a time: the TV's API
  handles concurrency poorly.
- **Partial degradation** — unreadable fields are listed in `stale_fields`
  instead of failing the whole state.

## Known limits

- No now-playing information: the TV does not expose it over this API.
- Volume is capped client-side (`BRAVIA_MAX_VOLUME`, default 40).
- Selecting an input may wake the device via CEC as a side effect.
- The PSK travels in cleartext over HTTP — it is never logged and never
  accepted as a command-line argument. Environment variable only.
- Wake-on-LAN is unreliable over Wi-Fi (randomized MAC).

## Tests

```bash
pytest
```

63 tests against a fake TV replaying real K-55XR8M2 responses. No network
access. ruff, mypy (strict) and basedpyright are part of the checks.
