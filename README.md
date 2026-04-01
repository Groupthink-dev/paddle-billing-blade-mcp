# paddle-billing-blade-mcp

Paddle Billing MCP server for Claude and other LLM agents. Token-efficient, security-first, Sidereal-native.

40 tools covering products, prices, customers, subscriptions, transactions, adjustments, discounts, payment methods, notifications, events, webhooks, reports, and simulations.

## Why another Paddle MCP?

- **SecOps** -- Mandatory environment isolation (sandbox/production), write gating, confirm gate for destructive operations, credential scrubbing in all error paths
- **Token efficiency** -- Pipe-delimited lists, field selection, human-readable money, null-field omission, pagination hints with cursor -- not raw JSON dumps
- **Sidereal ecosystem** -- `billing-v1` contract, plugin manifest, webhook verification for future dispatch integration

## Comparison

| Capability | paddle-billing-blade-mcp | @paddle/paddle-mcp |
|---|---|---|
| Token-efficient responses | Pipe-delimited, field selection, summarised | Raw JSON.stringify (full objects) |
| Write gating | Per-operation env var gate | Coarse 3-tier filter |
| Destructive op confirmation | `confirm=true` required | None |
| Environment isolation | Mandatory sandbox/production, fail closed | Required but accepts CLI arg |
| API key security | Env var only, credential scrubbing | Env var or CLI arg |
| Webhook HMAC verification | Built-in tool | Not available |
| Money formatting | Human-readable ($29.00 USD) | Raw cents ("2900") |
| Field selection | `fields` parameter on detail views | Not available |
| Pagination hints | Cursor + "N more" hints | Single page, manual cursor |
| Tests | 143 unit tests | Zero tests |
| Sidereal integration | billing-v1 contract, plugin manifest | None |
| Runtime | Python (uv) | Node.js (npx) |

### Token efficiency: before and after

**@paddle/paddle-mcp** (raw JSON, ~800 tokens):
```json
{"data":[{"id":"pro_abc123","name":"Pro Plan","description":"Professional subscription plan with all features","type":"standard","tax_category":"standard","image_url":null,"custom_data":null,"status":"active","import_meta":null,"created_at":"2026-03-15T10:00:00.000000Z","updated_at":"2026-03-15T10:00:00.000000Z"}],"meta":{"request_id":"req_abc","pagination":{"per_page":50,"next":"...","has_more":true,"estimated_total":25}}}
```

**paddle-billing-blade-mcp** (pipe-delimited, ~50 tokens):
```
pro_abc123 | Pro Plan | active | standard | tax=standard
... 24 more (pass after="pro_abc123" to continue)
```

## Quick start

```bash
# Install
uv tool install paddle-billing-blade-mcp

# Configure (stdio mode -- default)
export PADDLE_API_KEY="pdl_sdbx_..."
export PADDLE_ENVIRONMENT="sandbox"

# Run
paddle-billing-blade-mcp
```

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "paddle": {
      "command": "uvx",
      "args": ["paddle-billing-blade-mcp"],
      "env": {
        "PADDLE_API_KEY": "pdl_sdbx_...",
        "PADDLE_ENVIRONMENT": "sandbox"
      }
    }
  }
}
```

### HTTP transport (remote/tunnel access)

```bash
export PADDLE_MCP_TRANSPORT="http"
export PADDLE_MCP_HOST="127.0.0.1"
export PADDLE_MCP_PORT="8769"
export PADDLE_MCP_API_TOKEN="your-bearer-token"  # optional, enables auth
paddle-billing-blade-mcp
```

## Security model

### Environment isolation

`PADDLE_ENVIRONMENT` must be `sandbox` or `production`. Missing or invalid values fail closed -- no accidental operations against the wrong environment.

### Write gate

All mutating operations require `PADDLE_WRITE_ENABLED=true`. Without it, the server is read-only.

### Confirm gate

Destructive operations that are difficult or impossible to reverse require `confirm=true`:
- Cancel subscription
- Delete payment method
- Delete notification setting
- Run simulation

### Credential scrubbing

API keys (`pdl_*`) and Bearer tokens are scrubbed from all error messages. Credentials never leak through tool responses.

### Bearer auth (HTTP transport)

When `PADDLE_MCP_API_TOKEN` is set, every HTTP request must include a matching `Authorization: Bearer <token>` header. Constant-time comparison via `secrets.compare_digest`.

## Configuration

| Variable | Required | Description |
|---|---|---|
| `PADDLE_API_KEY` | Yes | Paddle API key (`pdl_sdbx_*` or `pdl_live_*`) |
| `PADDLE_ENVIRONMENT` | Yes | `sandbox` or `production` |
| `PADDLE_WRITE_ENABLED` | No | Set to `true` to enable write operations |
| `PADDLE_WEBHOOK_SECRET` | No | Webhook signing secret for HMAC verification |
| `PADDLE_MCP_TRANSPORT` | No | `stdio` (default) or `http` |
| `PADDLE_MCP_HOST` | No | HTTP host (default `127.0.0.1`) |
| `PADDLE_MCP_PORT` | No | HTTP port (default `8769`) |
| `PADDLE_MCP_API_TOKEN` | No | Bearer token for HTTP transport auth |

## Tools (40)

### Meta (2)

| Tool | R/W | Description |
|---|---|---|
| `paddle_info` | R | Environment, connectivity, configuration status |
| `paddle_ip_addresses` | R | Paddle IPs for webhook firewall allowlisting |

### Products & Prices (8)

| Tool | R/W | Description |
|---|---|---|
| `paddle_products` | R | List products (status, tax_category filters) |
| `paddle_product` | R | Get product detail, optional inline prices |
| `paddle_create_product` | W | Create product |
| `paddle_update_product` | W | Update product |
| `paddle_prices` | R | List prices (product_id, status filters) |
| `paddle_price` | R | Get price detail with billing cycle |
| `paddle_create_price` | W | Create price (amount, currency, billing cycle, trial) |
| `paddle_update_price` | W | Update price |

### Customers (11)

| Tool | R/W | Description |
|---|---|---|
| `paddle_customers` | R | List/search customers |
| `paddle_customer` | R | Get customer detail |
| `paddle_create_customer` | W | Create customer |
| `paddle_update_customer` | W | Update customer |
| `paddle_customer_credit` | R | Credit balance |
| `paddle_customer_portal` | W | Create portal session URL |
| `paddle_customer_addresses` | R | List or get addresses |
| `paddle_create_address` | W | Create address |
| `paddle_update_address` | W | Update address |
| `paddle_customer_businesses` | R | List or get businesses |
| `paddle_create_business` | W | Create business |

### Subscriptions (7)

| Tool | R/W | Description |
|---|---|---|
| `paddle_subscriptions` | R | List (status, customer_id, price_id filters) |
| `paddle_subscription` | R | Get detail with items and billing period |
| `paddle_update_subscription` | W | Update items, proration |
| `paddle_subscription_lifecycle` | W+C | Pause/resume/cancel (confirm for cancel) |
| `paddle_activate_subscription` | W | Activate trialing subscription |
| `paddle_subscription_charge` | W | One-time charge |
| `paddle_preview_subscription` | R | Preview update/charge pricing |

### Transactions (5)

| Tool | R/W | Description |
|---|---|---|
| `paddle_transactions` | R | List (status, customer, subscription, date range) |
| `paddle_transaction` | R | Get detail with totals and line items |
| `paddle_create_transaction` | W | Create transaction |
| `paddle_preview_transaction` | R | Preview pricing |
| `paddle_invoice_pdf` | R | Invoice PDF download URL |

### Adjustments & Discounts (6)

| Tool | R/W | Description |
|---|---|---|
| `paddle_adjustments` | R | List (transaction_id, action filter) |
| `paddle_create_adjustment` | W | Create refund/credit/chargeback |
| `paddle_discounts` | R | List discounts |
| `paddle_discount` | R | Get discount detail |
| `paddle_create_discount` | W | Create discount |
| `paddle_update_discount` | W | Update discount |

### Payment Methods (2)

| Tool | R/W | Description |
|---|---|---|
| `paddle_payment_methods` | R | List customer payment methods |
| `paddle_delete_payment_method` | W+C | Delete (confirm required) |

### Notifications & Events (7)

| Tool | R/W | Description |
|---|---|---|
| `paddle_notification_settings` | R | List notification destinations |
| `paddle_create_notification_setting` | W | Create webhook destination |
| `paddle_delete_notification_setting` | W+C | Delete (confirm required) |
| `paddle_notifications` | R | List notifications |
| `paddle_notification` | R | Get detail with delivery logs |
| `paddle_replay_notification` | W | Replay a notification |
| `paddle_events` | R | List events |

### Webhooks (2)

| Tool | R/W | Description |
|---|---|---|
| `paddle_verify_webhook` | R | HMAC-SHA256 signature verification |
| `paddle_parse_event` | R | Parse webhook payload |

### Reports (3)

| Tool | R/W | Description |
|---|---|---|
| `paddle_reports` | R | List reports |
| `paddle_create_report` | W | Create report |
| `paddle_report_csv` | R | CSV download URL |

### Simulations (3)

| Tool | R/W | Description |
|---|---|---|
| `paddle_simulations` | R | List simulations |
| `paddle_create_simulation` | W | Create simulation |
| `paddle_run_simulation` | W+C | Execute simulation (confirm required) |

**R/W legend:** R = read, W = write (`PADDLE_WRITE_ENABLED=true`), W+C = write + confirm (`confirm=true`)

## Development

```bash
make install-dev    # Install with dev + test dependencies
make test           # Run tests
make check          # Lint + format check + type check
make run            # Run server (stdio)
```

## Sidereal integration

This MCP implements the `billing-v1` service contract with full conformance (6/6 required, 8/8 recommended, 6/6 optional operations). Registered in the [Sidereal Plugin Registry](https://github.com/groupthink-dev/sidereal-plugin-registry) as a certified plugin.

## Licence

MIT
