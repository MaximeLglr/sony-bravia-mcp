# bravia-client — L1 + L2

Standalone client layer for the Sony Bravia MCP server (PRD §9, lot L1),
usable on its own, as a CLI, without MCP. The FastMCP wrapper (L2) sits on top
and exposes the same operations as an MCP server over stdio.

## Installation

```bash
pip install -e .
cp .env.example .env      # fill in BRAVIA_PSK
```

The `.env` file is loaded automatically by the client (pydantic-settings);
no `source .env` needed.

## Usage

```bash
bravia state                  # consolidated state
bravia inputs                 # inputs, CEC/HDMI deduplicated
bravia input "Apple TV"     # switch (and wake the Apple TV via CEC)
bravia input "PlayStation 5"
bravia apps [--refresh]
bravia app "YouTube"
bravia power on|off
bravia volume --level 20      # or --delta -5
bravia mute on|off
bravia methods                # getSupportedApiInfo
bravia -v state               # debug traces
```

Every error prints JSON with `error`, `message` and `hint`.

## Architecture

```
src/bravia_client/
├── config.py      # BraviaConfig (pydantic-settings): host, psk, mac, limits
├── errors.py      # exception hierarchy + Sony error-code map
├── models.py      # Pydantic wire/domain models, CEC/HDMI input merge
├── matching.py    # wire hygiene: HTML entities, non-breaking spaces
├── transport.py   # JSON-RPC envelope, retries, serialization lock, reconnect
├── wol.py         # Wake-on-LAN magic packet
├── services/      # one module per Sony API service
└── client.py     # BraviaClient facade

src/bravia_mcp/
├── server.py      # FastMCP instance, lifespan, the 8 tools
└── __main__.py    # entry point: argparse, logging, exit codes
```

## What the layer absorbs

**CEC/HDMI deduplication.** One connector appears twice in
`getCurrentExternalInputsStatus`. Merged by port: name and URI from CEC when
it exists, and `connected` true if CEC knows the device **or** HDMI reports
connected — a sleeping PS5 shows up in CEC while `hdmi?port=4` reports
`connection: false`.

**Opaque app URIs.** `com.sony.dtv.` + package + activity concatenated with no
separator, both containing dots. Never parsed: stored whole, indexed by title.
Matching against a package name (L3) is substring-based.

**Exact names, no guessing.** `set_input` and `launch_app` take the exact
name/title returned by `list_inputs`/`list_apps` (case-insensitive). No fuzzy
matching: the caller (LLM or human) sees the list and picks — a silent
approximation on a physical device is worse than a clear error. Unknown names
come back with the `available` list.

**Retries.** Exponential backoff on network errors and 5xx (WebApiCore
restarting), never on application errors: a 403 is deterministic.

**Two-level power-on.** `setPowerStatus` over REST first. Wake-on-LAN
fallback only if the API is unreachable. Caveat: the MAC is likely
randomized, WoL is unreliable over Wi-Fi.

**Partial degradation.** `get_state` never fails as a whole; unreadable
fields are listed in `stale_fields`.

**Serialization.** One JSON-RPC call in flight at a time: `BraviaTransport`
holds an `asyncio.Lock` around the whole retry loop. WebApiCore handles
concurrency poorly; the wrapper can now issue concurrent tool calls safely.

**Reconnect.** On a network failure with one attempt left, the transport
closes and reopens the HTTP client before the last try. A TV unplugged and
plugged back in recovers without restarting the server.

## MCP server (L2)

```bash
bravia-mcp                          # stdio (default), reads BRAVIA_HOST / BRAVIA_PSK from the environment
bravia-mcp -v                       # debug traces on stderr
bravia-mcp --transport http         # streamable HTTP on 127.0.0.1:8000/mcp
bravia-mcp --transport http --host 0.0.0.0 --port 9000
bravia-mcp --transport sse          # legacy SSE, same flags
```

stdio is the default: the client (Claude Desktop, Cursor, Vibe) launches the
server as a subprocess and talks over stdin/stdout. The `http` transport runs
a standalone uvicorn server — use it when several clients share one server or
when the client runs on another machine.

Client configuration (Claude Desktop, Cursor, or any MCP client):

```json
{
  "mcpServers": {
    "bravia": {
      "command": "bravia-mcp",
      "env": {
        "BRAVIA_HOST": "192.168.1.42",
        "BRAVIA_PSK": "your-pre-shared-key",
        "BRAVIA_MAC": "EE:B2:EB:B7:99:A6",
        "BRAVIA_MAX_VOLUME": "40"
      }
    }
  }
}
```

No secret on the command line — the PSK travels only through the
environment. The server starts even with the TV off or unplugged: the first
tool call returns a `TV_UNREACHABLE` error payload with a hint instead of
crashing.

For the HTTP transport, point the client at the URL instead:

```json
{
  "mcpServers": {
    "bravia": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

### Tools

| Tool | Key limits |
|---|---|
| `get_tv_state` | consolidated state, never fails as a whole |
| `list_inputs` | CEC/HDMI deduplicated by port |
| `list_apps` | 6 h cache, `refresh=true` to bypass |
| `set_power` | WoL fallback on power-on |
| `set_input` | exact name (case-insensitive), may wake the device via CEC |
| `launch_app` | exact title, whole opaque URIs |
| `set_volume` | `level` or `delta`, capped at `BRAVIA_MAX_VOLUME` |
| `set_mute` | on/off |

Every tool returns either the expected payload or an error object with
`error`, `message` and `hint` — never an exception. Unknown names come back
with an `available` list.

### Known limits

- No now-playing information: the TV does not expose it over this API.
- No deeplink support before L4.
- Volume is capped client-side (`BRAVIA_MAX_VOLUME`, default 40).
- App list is cached for 6 hours.
- Selecting an input wakes the device via CEC as a side effect.
- The PSK travels in cleartext over HTTP.
- Wake-on-LAN is unreliable over Wi-Fi (randomized MAC).

## Security

The PSK travels in cleartext over HTTP. It is never logged and never
accepted as a command-line argument (shell history, process table).
Environment variable only, `.env` in `.gitignore`.

## Tests

```bash
pytest
```

71 tests: 59 against a fake TV replaying the real K-55XR8M2 responses
(HTML entities and non-breaking spaces included), 12 for the MCP wrapper
(tool inventory, error contract, serialization, reconnection, PSK hygiene,
subprocess handshake). No network access.

## Remaining work

- L3: androidtvremote2 pairing, fill `foreground_app`
- L4: `open_deeplink`
