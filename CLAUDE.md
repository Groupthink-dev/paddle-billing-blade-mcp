# paddle-billing-blade-mcp — Development Boot

Paddle Billing MCP server. 40 tools, async httpx client, FastMCP framework.

## Architecture

- **src/paddle_billing_blade_mcp/server.py** — FastMCP server with 40 `@mcp.tool` functions
- **src/paddle_billing_blade_mcp/client.py** — Async PaddleClient (httpx), error hierarchy, webhook HMAC verification
- **src/paddle_billing_blade_mcp/formatters.py** — Token-efficient output: pipe-delimited lists, detail views, field selection
- **src/paddle_billing_blade_mcp/models.py** — Constants, write/confirm gates, env validation, money formatting, secret scrubbing
- **src/paddle_billing_blade_mcp/auth.py** — BearerAuthMiddleware for HTTP transport

## Key patterns

- **Write gate**: `require_write()` checks `PADDLE_WRITE_ENABLED=true`
- **Confirm gate**: `require_confirm(confirm, action)` for destructive ops (cancel, delete)
- **Lazy client**: `_get_client()` singleton, constructed on first tool call
- **Error handling**: All tools catch `PaddleError` and return `f"Error: {e}"`
- **Credential scrubbing**: `scrub_secrets()` masks `pdl_*` and Bearer tokens in errors

## Build & test

```bash
make install-dev    # uv sync --group dev --group test
make test           # pytest
make check          # ruff check + ruff format --check + mypy
make run            # PADDLE_MCP_TRANSPORT=stdio (default)
```

## Contract

Implements `billing-v1` (28 operations: 6 required, 8 recommended, 6 optional, 8 gated).
Registered in sidereal-plugin-registry as `plugins/tools/paddle-billing-blade-mcp.json`.
