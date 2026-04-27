"""Token-efficient output formatters for Paddle Billing data.

Design principles:
- Concise by default (one line per item)
- Null fields omitted
- Pipe-delimited lists
- Lists capped and annotated with total count
- Money in human-readable format ($29.00 USD)
- Dates in short format (2026-03-15 14:30)
"""

from __future__ import annotations

from typing import Any

from paddle_billing_blade_mcp.models import DEFAULT_LIMIT, format_money

# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def format_datetime(iso_str: str | None) -> str:
    """Format ISO datetime to short form: '2026-03-15T14:30:00Z' -> '2026-03-15 14:30'."""
    if not iso_str:
        return "?"
    # Strip timezone suffix and take first 16 chars
    clean = iso_str.replace("Z", "").replace("+00:00", "")
    return clean[:16].replace("T", " ")


def format_date(iso_str: str | None) -> str:
    """Format ISO datetime to date only: '2026-03-15T14:30:00Z' -> '2026-03-15'."""
    if not iso_str:
        return "?"
    return iso_str[:10]


def format_billing_cycle(cycle: dict[str, Any] | None) -> str:
    """Format billing cycle: {'interval': 'month', 'frequency': 1} -> 'monthly'."""
    if not cycle:
        return "one-time"
    interval = cycle.get("interval", "?")
    freq = cycle.get("frequency", 1)
    if freq == 1:
        return f"{interval}ly" if interval in ("month", "year") else f"every {interval}"
    return f"every {freq} {interval}s"


def format_billing_period(period: dict[str, Any] | None) -> str:
    """Format billing period: {'starts_at': '...', 'ends_at': '...'} -> '2026-03-01 to 2026-03-31'."""
    if not period:
        return "?"
    start = format_date(period.get("starts_at"))
    end = format_date(period.get("ends_at"))
    return f"{start} to {end}"


# ---------------------------------------------------------------------------
# Price helpers
# ---------------------------------------------------------------------------


def _format_unit_price(price_data: dict[str, Any]) -> str:
    """Extract and format the unit price from a price or item object."""
    unit_price = price_data.get("unit_price") or {}
    amount = unit_price.get("amount", "0")
    currency = unit_price.get("currency_code", "???")
    return format_money(amount, currency)


def _format_price_with_cycle(price_data: dict[str, Any]) -> str:
    """Format price with billing cycle: '$29.00 USD/month'."""
    price_str = _format_unit_price(price_data)
    cycle = price_data.get("billing_cycle")
    if cycle:
        interval = cycle.get("interval", "?")
        freq = cycle.get("frequency", 1)
        if freq == 1:
            return f"{price_str}/{interval}"
        return f"{price_str}/every {freq} {interval}s"
    return price_str


# ---------------------------------------------------------------------------
# Field selection
# ---------------------------------------------------------------------------


def select_fields(data: dict[str, Any], fields: str | None) -> dict[str, Any]:
    """Filter dict to only requested fields.

    Args:
        data: The full entity dict.
        fields: Comma-separated field names (e.g., "id,name,status"). None returns all.

    Returns:
        Filtered dict, always including 'id' if present.
    """
    if not fields:
        return data
    wanted = {f.strip() for f in fields.split(",")}
    if "id" in data:
        wanted.add("id")
    return {k: v for k, v in data.items() if k in wanted}


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def format_pagination(meta: dict[str, Any] | None, shown: int) -> str:
    """Generate pagination hint from Paddle API meta.

    Returns:
        Hint string like '... 48 more (pass after="cur_xyz" to continue)' or empty.
    """
    if not meta:
        return ""
    pagination = meta.get("pagination", {})
    if not pagination.get("has_more"):
        return ""
    estimated = pagination.get("estimated_total")
    next_url = pagination.get("next")
    # Extract 'after' cursor from next URL if available
    after_cursor = ""
    if next_url and "after=" in next_url:
        after_cursor = next_url.split("after=")[-1].split("&")[0]

    remaining = f"{estimated - shown}" if estimated and estimated > shown else "more"
    if after_cursor:
        return f'… {remaining} more (pass after="{after_cursor}" to continue)'
    return f"… {remaining} more"


# ---------------------------------------------------------------------------
# List formatters (pipe-delimited, one line per item)
# ---------------------------------------------------------------------------


def format_product_list(response: dict[str, Any], limit: int = DEFAULT_LIMIT) -> str:
    """Format product list.

    Example::

        pro_abc123 | Pro Plan | active | standard
        pro_def456 | Enterprise | active | standard
        … 8 more (pass after="pro_def456" to continue)
    """
    items = response.get("data", [])
    if not items:
        return "No products found."

    shown = items[:limit]
    lines: list[str] = []
    for p in shown:
        parts = [
            p.get("id", "?"),
            p.get("name", "(unnamed)"),
            p.get("status", "?"),
            p.get("type", "?"),
        ]
        tax = p.get("tax_category")
        if tax:
            parts.append(f"tax={tax}")
        lines.append(" | ".join(parts))

    hint = format_pagination(response.get("meta"), len(shown))
    if hint:
        lines.append(hint)
    return "\n".join(lines)


def format_price_list(response: dict[str, Any], limit: int = DEFAULT_LIMIT) -> str:
    """Format price list.

    Example::

        pri_abc123 | Monthly | $29.00 USD | active | monthly
        pri_def456 | Annual | $290.00 USD | active | yearly
    """
    items = response.get("data", [])
    if not items:
        return "No prices found."

    shown = items[:limit]
    lines: list[str] = []
    for p in shown:
        parts = [
            p.get("id", "?"),
            p.get("description", "(no description)"),
            _format_unit_price(p),
            p.get("status", "?"),
            format_billing_cycle(p.get("billing_cycle")),
        ]
        product_id = p.get("product_id")
        if product_id:
            parts.append(f"product={product_id}")
        lines.append(" | ".join(parts))

    hint = format_pagination(response.get("meta"), len(shown))
    if hint:
        lines.append(hint)
    return "\n".join(lines)


def format_customer_list(response: dict[str, Any], limit: int = DEFAULT_LIMIT) -> str:
    """Format customer list.

    Example::

        ctm_abc123 | alice@example.com | Alice Smith | active
    """
    items = response.get("data", [])
    if not items:
        return "No customers found."

    shown = items[:limit]
    lines: list[str] = []
    for c in shown:
        parts = [
            c.get("id", "?"),
            c.get("email", "(no email)"),
            c.get("name") or "(unnamed)",
            c.get("status", "?"),
        ]
        locale = c.get("locale")
        if locale:
            parts.append(f"locale={locale}")
        lines.append(" | ".join(parts))

    hint = format_pagination(response.get("meta"), len(shown))
    if hint:
        lines.append(hint)
    return "\n".join(lines)


def format_subscription_list(response: dict[str, Any], limit: int = DEFAULT_LIMIT) -> str:
    """Format subscription list.

    Example::

        sub_abc123 | ctm_def456 | active | $29.00 USD/month | next: 2026-04-01
    """
    items = response.get("data", [])
    if not items:
        return "No subscriptions found."

    shown = items[:limit]
    lines: list[str] = []
    for s in shown:
        parts = [
            s.get("id", "?"),
            s.get("customer_id", "?"),
            s.get("status", "?"),
        ]
        # First item price
        sub_items = s.get("items", [])
        if sub_items:
            first_price = sub_items[0].get("price", {})
            parts.append(_format_price_with_cycle(first_price))
            if len(sub_items) > 1:
                parts.append(f"+{len(sub_items) - 1} items")

        next_billed = s.get("next_billed_at")
        if next_billed:
            parts.append(f"next: {format_date(next_billed)}")

        lines.append(" | ".join(parts))

    hint = format_pagination(response.get("meta"), len(shown))
    if hint:
        lines.append(hint)
    return "\n".join(lines)


def format_transaction_list(response: dict[str, Any], limit: int = DEFAULT_LIMIT) -> str:
    """Format transaction list.

    Example::

        txn_abc123 | ctm_def456 | $29.00 USD | completed | 2026-03-15 | sub_ghi789
    """
    items = response.get("data", [])
    if not items:
        return "No transactions found."

    shown = items[:limit]
    lines: list[str] = []
    for t in shown:
        parts = [
            t.get("id", "?"),
            t.get("customer_id") or "?",
        ]
        # Total from details
        details = t.get("details", {})
        totals = details.get("totals", {}) if details else {}
        grand_total = totals.get("grand_total")
        currency = t.get("currency_code", "???")
        if grand_total:
            parts.append(format_money(grand_total, currency))
        else:
            parts.append("?")

        parts.append(t.get("status", "?"))
        parts.append(format_date(t.get("billed_at") or t.get("created_at")))

        sub_id = t.get("subscription_id")
        if sub_id:
            parts.append(sub_id)

        origin = t.get("origin")
        if origin:
            parts.append(f"origin={origin}")

        lines.append(" | ".join(parts))

    hint = format_pagination(response.get("meta"), len(shown))
    if hint:
        lines.append(hint)
    return "\n".join(lines)


def format_adjustment_list(response: dict[str, Any], limit: int = DEFAULT_LIMIT) -> str:
    """Format adjustment list.

    Example::

        adj_abc123 | txn_def456 | refund | $10.00 USD | approved | 2026-03-15
    """
    items = response.get("data", [])
    if not items:
        return "No adjustments found."

    shown = items[:limit]
    lines: list[str] = []
    for a in shown:
        parts = [
            a.get("id", "?"),
            a.get("transaction_id", "?"),
            a.get("action", "?"),
        ]
        totals = a.get("totals", {})
        total = totals.get("total")
        currency = a.get("currency_code", "???")
        if total:
            parts.append(format_money(total, currency))

        parts.append(a.get("status", "?"))
        parts.append(format_date(a.get("created_at")))

        lines.append(" | ".join(parts))

    hint = format_pagination(response.get("meta"), len(shown))
    if hint:
        lines.append(hint)
    return "\n".join(lines)


def format_adjustment_detail(response: dict[str, Any]) -> str:
    """Format a single adjustment.

    Paddle's ``GET /adjustments?id=X`` returns a list-shaped response.
    Unwrap the first item; if absent, report not found.
    """
    items = response.get("data") or []
    if isinstance(items, dict):
        a = items
    elif items:
        a = items[0]
    else:
        return "Adjustment not found."

    lines: list[str] = []
    lines.append(f"ID: {a.get('id', '?')}")
    lines.append(f"Transaction: {a.get('transaction_id', '?')}")
    lines.append(f"Action: {a.get('action', '?')}")
    lines.append(f"Status: {a.get('status', '?')}")

    totals = a.get("totals") or {}
    total = totals.get("total")
    currency = a.get("currency_code", "???")
    if total:
        lines.append(f"Total: {format_money(total, currency)}")

    if reason := a.get("reason"):
        lines.append(f"Reason: {reason}")
    if customer_id := a.get("customer_id"):
        lines.append(f"Customer: {customer_id}")
    if subscription_id := a.get("subscription_id"):
        lines.append(f"Subscription: {subscription_id}")
    if created_at := a.get("created_at"):
        lines.append(f"Created: {format_datetime(created_at)}")
    if credit_applied := a.get("credit_applied_to_balance"):
        lines.append(f"Credit applied: {credit_applied}")

    return "\n".join(lines)


def format_event_type_list(response: dict[str, Any]) -> str:
    """Format event type listing.

    Example::

        subscription.activated | Triggered when a subscription becomes active
        subscription.canceled  | Triggered when a subscription is canceled
    """
    items = response.get("data") or []
    if not items:
        return "No event types found."

    lines: list[str] = []
    for et in items:
        name = et.get("name", "?")
        desc = et.get("description") or et.get("group", "")
        if desc:
            lines.append(f"{name} | {desc}")
        else:
            lines.append(name)
    return "\n".join(lines)


def format_discount_list(response: dict[str, Any], limit: int = DEFAULT_LIMIT) -> str:
    """Format discount list.

    Example::

        dis_abc123 | 20% off | percentage | active | code=SAVE20
    """
    items = response.get("data", [])
    if not items:
        return "No discounts found."

    shown = items[:limit]
    lines: list[str] = []
    for d in shown:
        parts = [
            d.get("id", "?"),
            d.get("description", "(no description)"),
            d.get("type", "?"),
            d.get("status", "?"),
        ]
        amount = d.get("amount")
        if amount:
            if d.get("type") == "percentage":
                parts.append(f"{amount}%")
            else:
                currency = d.get("currency_code", "???")
                parts.append(format_money(amount, currency))

        code = d.get("code")
        if code:
            parts.append(f"code={code}")

        lines.append(" | ".join(parts))

    hint = format_pagination(response.get("meta"), len(shown))
    if hint:
        lines.append(hint)
    return "\n".join(lines)


def format_notification_list(response: dict[str, Any], limit: int = DEFAULT_LIMIT) -> str:
    """Format notification list.

    Example::

        ntf_abc123 | subscription.created | delivered | 2026-03-15 14:30
    """
    items = response.get("data", [])
    if not items:
        return "No notifications found."

    shown = items[:limit]
    lines: list[str] = []
    for n in shown:
        parts = [
            n.get("id", "?"),
            n.get("type", "?"),
            n.get("status", "?"),
            format_datetime(n.get("occurred_at")),
        ]
        attempts = n.get("times_attempted")
        if attempts and attempts > 1:
            parts.append(f"attempts={attempts}")

        lines.append(" | ".join(parts))

    hint = format_pagination(response.get("meta"), len(shown))
    if hint:
        lines.append(hint)
    return "\n".join(lines)


def format_event_list(response: dict[str, Any], limit: int = DEFAULT_LIMIT) -> str:
    """Format event list.

    Example::

        evt_abc123 | subscription.activated | 2026-03-15 14:30
    """
    items = response.get("data", [])
    if not items:
        return "No events found."

    shown = items[:limit]
    lines: list[str] = []
    for e in shown:
        parts = [
            e.get("event_id", "?"),
            e.get("event_type", "?"),
            format_datetime(e.get("occurred_at")),
        ]
        lines.append(" | ".join(parts))

    hint = format_pagination(response.get("meta"), len(shown))
    if hint:
        lines.append(hint)
    return "\n".join(lines)


def format_address_list(response: dict[str, Any], limit: int = DEFAULT_LIMIT) -> str:
    """Format address list.

    Example::

        add_abc123 | US | San Francisco, CA 94102 | active
    """
    items = response.get("data", [])
    if not items:
        return "No addresses found."

    shown = items[:limit]
    lines: list[str] = []
    for a in shown:
        parts = [a.get("id", "?"), a.get("country_code", "?")]
        location_parts: list[str] = []
        if city := a.get("city"):
            location_parts.append(city)
        if region := a.get("region"):
            location_parts.append(region)
        if postal := a.get("postal_code"):
            location_parts.append(postal)
        if location_parts:
            parts.append(", ".join(location_parts))
        parts.append(a.get("status", "?"))
        lines.append(" | ".join(parts))

    hint = format_pagination(response.get("meta"), len(shown))
    if hint:
        lines.append(hint)
    return "\n".join(lines)


def format_business_list(response: dict[str, Any], limit: int = DEFAULT_LIMIT) -> str:
    """Format business list.

    Example::

        biz_abc123 | Acme Corp | active | tax=US123456
    """
    items = response.get("data", [])
    if not items:
        return "No businesses found."

    shown = items[:limit]
    lines: list[str] = []
    for b in shown:
        parts = [
            b.get("id", "?"),
            b.get("name", "(unnamed)"),
            b.get("status", "?"),
        ]
        tax_id = b.get("tax_identifier")
        if tax_id:
            parts.append(f"tax={tax_id}")
        lines.append(" | ".join(parts))

    hint = format_pagination(response.get("meta"), len(shown))
    if hint:
        lines.append(hint)
    return "\n".join(lines)


def format_payment_method_list(response: dict[str, Any], limit: int = DEFAULT_LIMIT) -> str:
    """Format payment method list.

    Example::

        paymtd_abc123 | card | visa ****4242 | exp 12/2028
    """
    items = response.get("data", [])
    if not items:
        return "No payment methods found."

    shown = items[:limit]
    lines: list[str] = []
    for pm in shown:
        parts = [pm.get("id", "?"), pm.get("type", "?")]
        card = pm.get("card")
        if card:
            brand = card.get("type", "")
            last4 = card.get("last4", "????")
            parts.append(f"{brand} ****{last4}")
            exp_month = card.get("expiry_month")
            exp_year = card.get("expiry_year")
            if exp_month and exp_year:
                parts.append(f"exp {exp_month:02d}/{exp_year}")
        lines.append(" | ".join(parts))

    hint = format_pagination(response.get("meta"), len(shown))
    if hint:
        lines.append(hint)
    return "\n".join(lines)


def format_report_list(response: dict[str, Any], limit: int = DEFAULT_LIMIT) -> str:
    """Format report list.

    Example::

        rep_abc123 | transactions | ready | 2026-03-15
    """
    items = response.get("data", [])
    if not items:
        return "No reports found."

    shown = items[:limit]
    lines: list[str] = []
    for r in shown:
        parts = [
            r.get("id", "?"),
            r.get("type", "?"),
            r.get("status", "?"),
            format_date(r.get("created_at")),
        ]
        lines.append(" | ".join(parts))

    hint = format_pagination(response.get("meta"), len(shown))
    if hint:
        lines.append(hint)
    return "\n".join(lines)


def format_notification_setting_list(response: dict[str, Any], limit: int = DEFAULT_LIMIT) -> str:
    """Format notification setting list.

    Example::

        ntfset_abc123 | url | https://example.com/webhook | active | 5 events
    """
    items = response.get("data", [])
    if not items:
        return "No notification settings found."

    shown = items[:limit]
    lines: list[str] = []
    for ns in shown:
        parts = [
            ns.get("id", "?"),
            ns.get("type", "?"),
            ns.get("destination", "?"),
            "active" if ns.get("active") else "inactive",
        ]
        events = ns.get("subscribed_events", [])
        if events:
            parts.append(f"{len(events)} events")
        lines.append(" | ".join(parts))

    hint = format_pagination(response.get("meta"), len(shown))
    if hint:
        lines.append(hint)
    return "\n".join(lines)


def format_simulation_list(response: dict[str, Any], limit: int = DEFAULT_LIMIT) -> str:
    """Format simulation list.

    Example::

        sim_abc123 | subscription_creation | active | ntfset_def456
    """
    items = response.get("data", [])
    if not items:
        return "No simulations found."

    shown = items[:limit]
    lines: list[str] = []
    for s in shown:
        parts = [
            s.get("id", "?"),
            s.get("type") or s.get("scenario_type", "?"),
            s.get("status", "?"),
            s.get("notification_setting_id", "?"),
        ]
        lines.append(" | ".join(parts))

    hint = format_pagination(response.get("meta"), len(shown))
    if hint:
        lines.append(hint)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Detail formatters (key: value, null-field omission)
# ---------------------------------------------------------------------------


def format_product_detail(data: dict[str, Any], fields: str | None = None) -> str:
    """Format product detail."""
    d = select_fields(data, fields)
    return _format_detail(
        d,
        {
            "id": "ID",
            "name": "Name",
            "description": "Description",
            "type": "Type",
            "status": "Status",
            "tax_category": "Tax Category",
            "image_url": "Image",
            "created_at": ("Created", format_datetime),
            "updated_at": ("Updated", format_datetime),
            "custom_data": "Custom Data",
        },
    )


def format_price_detail(data: dict[str, Any], fields: str | None = None) -> str:
    """Format price detail."""
    d = select_fields(data, fields)
    lines: list[str] = []
    lines.append(f"ID: {d.get('id', '?')}")
    lines.append(f"Description: {d.get('description', '?')}")
    lines.append(f"Price: {_format_unit_price(d)}")
    lines.append(f"Status: {d.get('status', '?')}")
    lines.append(f"Billing: {format_billing_cycle(d.get('billing_cycle'))}")
    if product_id := d.get("product_id"):
        lines.append(f"Product: {product_id}")
    trial = d.get("trial_period")
    if trial:
        lines.append(f"Trial: {trial.get('frequency', '?')} {trial.get('interval', '?')}")
    qty = d.get("quantity")
    if qty:
        lines.append(f"Quantity: {qty.get('minimum', 1)}-{qty.get('maximum', '∞')}")
    overrides = d.get("unit_price_overrides")
    if overrides:
        lines.append(f"Price Overrides: {len(overrides)} countries")
    if d.get("created_at"):
        lines.append(f"Created: {format_datetime(d.get('created_at'))}")
    return "\n".join(lines)


def format_customer_detail(data: dict[str, Any], fields: str | None = None) -> str:
    """Format customer detail."""
    d = select_fields(data, fields)
    return _format_detail(
        d,
        {
            "id": "ID",
            "name": "Name",
            "email": "Email",
            "status": "Status",
            "locale": "Locale",
            "marketing_consent": "Marketing Consent",
            "created_at": ("Created", format_datetime),
            "updated_at": ("Updated", format_datetime),
            "custom_data": "Custom Data",
        },
    )


def format_subscription_detail(data: dict[str, Any], fields: str | None = None) -> str:
    """Format subscription detail."""
    d = select_fields(data, fields)
    lines: list[str] = []
    lines.append(f"ID: {d.get('id', '?')}")
    lines.append(f"Status: {d.get('status', '?')}")
    lines.append(f"Customer: {d.get('customer_id', '?')}")
    if d.get("address_id"):
        lines.append(f"Address: {d['address_id']}")
    if d.get("business_id"):
        lines.append(f"Business: {d['business_id']}")
    lines.append(f"Currency: {d.get('currency_code', '?')}")
    lines.append(f"Collection: {d.get('collection_mode', '?')}")

    # Items
    sub_items = d.get("items", [])
    if sub_items:
        lines.append(f"Items ({len(sub_items)}):")
        for item in sub_items:
            price = item.get("price", {})
            pid = price.get("id", "?")
            desc = price.get("description", "?")
            prc = _format_price_with_cycle(price)
            qty = item.get("quantity", 1)
            lines.append(f"  {pid} | {desc} | {prc} | qty={qty}")

    # Billing
    if d.get("current_billing_period"):
        lines.append(f"Current Period: {format_billing_period(d.get('current_billing_period'))}")
    if d.get("next_billed_at"):
        lines.append(f"Next Billed: {format_datetime(d.get('next_billed_at'))}")
    if d.get("started_at"):
        lines.append(f"Started: {format_datetime(d.get('started_at'))}")
    if d.get("first_billed_at"):
        lines.append(f"First Billed: {format_datetime(d.get('first_billed_at'))}")

    # State changes
    if d.get("paused_at"):
        lines.append(f"Paused: {format_datetime(d.get('paused_at'))}")
    if d.get("canceled_at"):
        lines.append(f"Canceled: {format_datetime(d.get('canceled_at'))}")

    # Discount
    discount = d.get("discount")
    if discount:
        lines.append(f"Discount: {discount.get('id', '?')}")

    # Scheduled change
    scheduled = d.get("scheduled_change")
    if scheduled:
        lines.append(f"Scheduled: {scheduled.get('action', '?')} at {format_datetime(scheduled.get('effective_at'))}")

    if d.get("custom_data"):
        lines.append(f"Custom Data: {d['custom_data']}")

    return "\n".join(lines)


def format_transaction_detail(data: dict[str, Any], fields: str | None = None) -> str:
    """Format transaction detail."""
    d = select_fields(data, fields)
    lines: list[str] = []
    lines.append(f"ID: {d.get('id', '?')}")
    lines.append(f"Status: {d.get('status', '?')}")
    lines.append(f"Origin: {d.get('origin', '?')}")
    if d.get("customer_id"):
        lines.append(f"Customer: {d['customer_id']}")
    if d.get("subscription_id"):
        lines.append(f"Subscription: {d['subscription_id']}")
    lines.append(f"Currency: {d.get('currency_code', '?')}")
    lines.append(f"Collection: {d.get('collection_mode', '?')}")

    # Totals
    details = d.get("details", {})
    totals = details.get("totals", {}) if details else {}
    if totals:
        currency = d.get("currency_code", "???")
        lines.append(f"Subtotal: {format_money(totals.get('subtotal', '0'), currency)}")
        tax = totals.get("tax")
        if tax and tax != "0":
            lines.append(f"Tax: {format_money(tax, currency)}")
        discount_val = totals.get("discount")
        if discount_val and discount_val != "0":
            lines.append(f"Discount: -{format_money(discount_val, currency)}")
        lines.append(f"Total: {format_money(totals.get('grand_total', '0'), currency)}")

    # Line items (summarised)
    line_items = details.get("line_items", []) if details else []
    if line_items:
        lines.append(f"Line Items ({len(line_items)}):")
        for li in line_items[:5]:
            product = li.get("product", {})
            name = product.get("name", "?")
            qty = li.get("quantity", 1)
            total = format_money(li.get("total", "0"), d.get("currency_code", "???"))
            lines.append(f"  {name} | qty={qty} | {total}")
        if len(line_items) > 5:
            lines.append(f"  … +{len(line_items) - 5} more")

    # Dates
    if d.get("billed_at"):
        lines.append(f"Billed: {format_datetime(d.get('billed_at'))}")
    if d.get("created_at"):
        lines.append(f"Created: {format_datetime(d.get('created_at'))}")

    # Invoice
    if d.get("invoice_number"):
        lines.append(f"Invoice: {d['invoice_number']}")

    if d.get("custom_data"):
        lines.append(f"Custom Data: {d['custom_data']}")

    return "\n".join(lines)


def format_discount_detail(data: dict[str, Any], fields: str | None = None) -> str:
    """Format discount detail."""
    d = select_fields(data, fields)
    lines: list[str] = []
    lines.append(f"ID: {d.get('id', '?')}")
    lines.append(f"Description: {d.get('description', '?')}")
    lines.append(f"Type: {d.get('type', '?')}")
    lines.append(f"Status: {d.get('status', '?')}")
    amount = d.get("amount")
    if amount:
        if d.get("type") == "percentage":
            lines.append(f"Amount: {amount}%")
        else:
            lines.append(f"Amount: {format_money(amount, d.get('currency_code', '???'))}")
    if d.get("code"):
        lines.append(f"Code: {d['code']}")
    if d.get("recur") is not None:
        lines.append(f"Recurring: {d['recur']}")
    if d.get("usage_limit"):
        lines.append(f"Usage Limit: {d['usage_limit']} (used: {d.get('times_used', 0)})")
    if d.get("expires_at"):
        lines.append(f"Expires: {format_datetime(d.get('expires_at'))}")
    if d.get("restrict_to"):
        lines.append(f"Restricted to: {len(d['restrict_to'])} items")
    return "\n".join(lines)


def format_notification_detail(data: dict[str, Any]) -> str:
    """Format notification detail with optional delivery logs."""
    lines: list[str] = []
    lines.append(f"ID: {data.get('id', '?')}")
    lines.append(f"Type: {data.get('type', '?')}")
    lines.append(f"Status: {data.get('status', '?')}")
    lines.append(f"Occurred: {format_datetime(data.get('occurred_at'))}")
    if data.get("delivered_at"):
        lines.append(f"Delivered: {format_datetime(data.get('delivered_at'))}")
    if data.get("times_attempted"):
        lines.append(f"Attempts: {data['times_attempted']}")
    if data.get("notification_setting_id"):
        lines.append(f"Setting: {data['notification_setting_id']}")
    return "\n".join(lines)


def format_credit_balance(response: dict[str, Any]) -> str:
    """Format customer credit balance."""
    items = response.get("data", [])
    if not items:
        return "No credit balance."

    lines: list[str] = []
    for cb in items:
        currency = cb.get("currency_code", "???")
        balance = cb.get("balance", {})
        available = balance.get("available", "0")
        reserved = balance.get("reserved", "0")
        used = balance.get("used", "0")
        avail_fmt = format_money(available, currency)
        reserved_fmt = format_money(reserved, currency)
        used_fmt = format_money(used, currency)
        lines.append(f"{currency}: available={avail_fmt} | reserved={reserved_fmt} | used={used_fmt}")
    return "\n".join(lines)


def format_webhook_verification(result: dict[str, Any]) -> str:
    """Format webhook verification result."""
    if result.get("valid"):
        event_type = result.get("event_type", "?")
        event_id = result.get("event_id", "?")
        occurred = format_datetime(result.get("occurred_at"))
        return f"Valid webhook: {event_type} | {event_id} | {occurred}"
    return f"Invalid webhook: {result.get('error', 'verification failed')}"


def format_event_detail(data: dict[str, Any]) -> str:
    """Format a parsed event/webhook payload."""
    lines: list[str] = []
    lines.append(f"Event: {data.get('event_type', '?')}")
    lines.append(f"ID: {data.get('event_id', '?')}")
    lines.append(f"Occurred: {format_datetime(data.get('occurred_at'))}")

    entity = data.get("data", {})
    if entity:
        entity_id = entity.get("id", "?")
        status = entity.get("status")
        lines.append(f"Entity: {entity_id}")
        if status:
            lines.append(f"Status: {status}")

    return "\n".join(lines)


def format_ip_addresses(data: dict[str, Any]) -> str:
    """Format Paddle IP addresses for webhook allowlisting."""
    ips = data.get("data", [])
    if not ips:
        return "No IP addresses returned."

    lines = ["Paddle IP addresses (for webhook firewall allowlisting):"]
    for ip_entry in ips:
        if isinstance(ip_entry, dict):
            lines.append(f"  {ip_entry.get('ipv4_cidr', '?')}")
        else:
            lines.append(f"  {ip_entry}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Generic detail formatter
# ---------------------------------------------------------------------------


def _format_detail(data: dict[str, Any], field_map: dict[str, Any]) -> str:
    """Format a detail view using a field mapping.

    field_map values can be:
    - str: label (value used as-is)
    - tuple[str, callable]: (label, transform_fn)
    """
    lines: list[str] = []
    for key, spec in field_map.items():
        value = data.get(key)
        if value is None:
            continue
        if isinstance(spec, tuple):
            label, transform = spec
            lines.append(f"{label}: {transform(value)}")
        else:
            lines.append(f"{spec}: {value}")
    return "\n".join(lines) if lines else "(no data)"
