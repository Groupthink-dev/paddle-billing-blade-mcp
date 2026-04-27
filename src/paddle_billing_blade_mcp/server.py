"""Paddle Blade MCP Server — Paddle Billing API operations.

Token-efficient by default: pipe-delimited lists, field selection,
human-readable money, null-field omission. Write operations gated
behind PADDLE_WRITE_ENABLED=true. Destructive operations require
confirm=true.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from paddle_billing_blade_mcp.client import PaddleClient, PaddleError
from paddle_billing_blade_mcp.formatters import (
    format_address_list,
    format_adjustment_detail,
    format_adjustment_list,
    format_business_list,
    format_credit_balance,
    format_customer_detail,
    format_customer_list,
    format_datetime,
    format_discount_detail,
    format_discount_list,
    format_event_detail,
    format_event_list,
    format_event_type_list,
    format_ip_addresses,
    format_notification_detail,
    format_notification_list,
    format_notification_setting_list,
    format_payment_method_list,
    format_price_detail,
    format_price_list,
    format_product_detail,
    format_product_list,
    format_report_list,
    format_simulation_list,
    format_subscription_detail,
    format_subscription_list,
    format_transaction_detail,
    format_transaction_list,
    format_webhook_verification,
)
from paddle_billing_blade_mcp.models import DEFAULT_LIMIT, require_confirm, require_write

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Transport configuration
# ---------------------------------------------------------------------------

TRANSPORT = os.environ.get("PADDLE_MCP_TRANSPORT", "stdio")
HTTP_HOST = os.environ.get("PADDLE_MCP_HOST", "127.0.0.1")
HTTP_PORT = int(os.environ.get("PADDLE_MCP_PORT", "8769"))

# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "PaddleBlade",
    instructions=(
        "Paddle Billing API operations. Manage products, prices, customers, "
        "subscriptions, and transactions. Token-efficient responses with "
        "pipe-delimited lists, field selection, and human-readable money. "
        "Write operations require PADDLE_WRITE_ENABLED=true. "
        "Destructive operations (cancel, delete) require confirm=true."
    ),
)

# Lazy-initialized client
_client: PaddleClient | None = None


async def _get_client() -> PaddleClient:
    """Get or create the PaddleClient singleton."""
    global _client  # noqa: PLW0603
    if _client is None:
        _client = PaddleClient()
        logger.info("PaddleClient: env=%s", _client.environment)
    return _client


def _error(e: PaddleError) -> str:
    """Format a client error as a user-friendly string."""
    return f"Error: {e}"


# ===========================================================================
# Meta tools
# ===========================================================================


@mcp.tool
async def paddle_info() -> str:
    """Show Paddle environment, API connectivity, and configuration status."""
    try:
        client = await _get_client()
        env = client.environment
        write = "enabled" if os.environ.get("PADDLE_WRITE_ENABLED", "").lower() == "true" else "disabled"
        webhook = "configured" if os.environ.get("PADDLE_WEBHOOK_SECRET", "").strip() else "not configured"
        return f"Environment: {env}\nAPI: connected\nWrites: {write}\nWebhook secret: {webhook}"
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_ip_addresses() -> str:
    """Get Paddle IP addresses for webhook firewall allowlisting."""
    try:
        client = await _get_client()
        result = await client.list_ip_addresses()
        return format_ip_addresses(result)
    except PaddleError as e:
        return _error(e)


# ===========================================================================
# Products
# ===========================================================================


@mcp.tool
async def paddle_products(
    status: Annotated[str | None, Field(description="Filter: active or archived")] = None,
    tax_category: Annotated[str | None, Field(description="Filter by tax category")] = None,
    limit: Annotated[int, Field(description="Max results (default 20, max 200)")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination")] = None,
    fields: Annotated[str | None, Field(description="Comma-separated fields to return")] = None,
) -> str:
    """List products. Use fields= to select specific fields for token efficiency."""
    try:
        client = await _get_client()
        result = await client.list_products(status=status, tax_category=tax_category, limit=limit, after=after)
        _ = fields  # Field selection applied in detail views; list view is already concise
        return format_product_list(result, limit)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_product(
    product_id: Annotated[str, Field(description="Product ID (pro_*)")],
    include_prices: Annotated[bool, Field(description="Include associated prices")] = False,
    fields: Annotated[str | None, Field(description="Comma-separated fields to return")] = None,
) -> str:
    """Get product detail. Use fields= to select specific fields."""
    try:
        client = await _get_client()
        include = "prices" if include_prices else None
        result = await client.get_product(product_id, include=include)
        data = result.get("data", result)
        output = format_product_detail(data, fields)
        # Append inline prices if included
        prices = data.get("prices", [])
        if prices:
            output += f"\n\nPrices ({len(prices)}):"
            from paddle_billing_blade_mcp.formatters import _format_price_with_cycle

            for p in prices:
                pid = p.get("id", "?")
                desc = p.get("description", "?")
                prc = _format_price_with_cycle(p)
                st = p.get("status", "?")
                output += f"\n  {pid} | {desc} | {prc} | {st}"
        return output
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_create_product(
    name: Annotated[str, Field(description="Product name")],
    tax_category: Annotated[str, Field(description="Tax category (e.g., standard, digital-goods, saas)")],
    description: Annotated[str | None, Field(description="Product description")] = None,
    image_url: Annotated[str | None, Field(description="Product image URL")] = None,
    custom_data: Annotated[str | None, Field(description="Custom data as JSON string")] = None,
) -> str:
    """Create a new product. Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        body: dict[str, object] = {"name": name, "tax_category": tax_category}
        if description:
            body["description"] = description
        if image_url:
            body["image_url"] = image_url
        if custom_data:
            body["custom_data"] = json.loads(custom_data)
        result = await client.create_product(body)
        return format_product_detail(result.get("data", result))
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_update_product(
    product_id: Annotated[str, Field(description="Product ID (pro_*)")],
    name: Annotated[str | None, Field(description="New name")] = None,
    description: Annotated[str | None, Field(description="New description")] = None,
    status: Annotated[str | None, Field(description="active or archived")] = None,
    tax_category: Annotated[str | None, Field(description="New tax category")] = None,
    image_url: Annotated[str | None, Field(description="New image URL")] = None,
    custom_data: Annotated[str | None, Field(description="Custom data as JSON string")] = None,
) -> str:
    """Update a product. Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        body: dict[str, object] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if status is not None:
            body["status"] = status
        if tax_category is not None:
            body["tax_category"] = tax_category
        if image_url is not None:
            body["image_url"] = image_url
        if custom_data is not None:
            body["custom_data"] = json.loads(custom_data)
        result = await client.update_product(product_id, body)
        return format_product_detail(result.get("data", result))
    except PaddleError as e:
        return _error(e)


# ===========================================================================
# Prices
# ===========================================================================


@mcp.tool
async def paddle_prices(
    product_id: Annotated[str | None, Field(description="Filter by product ID")] = None,
    status: Annotated[str | None, Field(description="Filter: active or archived")] = None,
    limit: Annotated[int, Field(description="Max results")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination")] = None,
) -> str:
    """List prices. Filter by product_id to see prices for a specific product."""
    try:
        client = await _get_client()
        result = await client.list_prices(product_id=product_id, status=status, limit=limit, after=after)
        return format_price_list(result, limit)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_price(
    price_id: Annotated[str, Field(description="Price ID (pri_*)")],
    fields: Annotated[str | None, Field(description="Comma-separated fields to return")] = None,
) -> str:
    """Get price detail. Use fields= to select specific fields."""
    try:
        client = await _get_client()
        result = await client.get_price(price_id)
        return format_price_detail(result.get("data", result), fields)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_create_price(
    product_id: Annotated[str, Field(description="Product ID (pro_*)")],
    description: Annotated[str, Field(description="Price description (e.g., 'Monthly')")],
    amount: Annotated[str, Field(description="Amount in cents (e.g., '2900' for $29.00)")],
    currency_code: Annotated[str, Field(description="ISO 4217 currency code (e.g., USD)")],
    interval: Annotated[
        str | None, Field(description="Billing interval: day, week, month, year (omit for one-time)")
    ] = None,
    frequency: Annotated[
        int | None, Field(description="Billing frequency (e.g., 1 for monthly, 3 for quarterly)")
    ] = None,
    trial_interval: Annotated[str | None, Field(description="Trial period interval")] = None,
    trial_frequency: Annotated[int | None, Field(description="Trial period frequency")] = None,
) -> str:
    """Create a new price. Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        body: dict[str, object] = {
            "product_id": product_id,
            "description": description,
            "unit_price": {"amount": amount, "currency_code": currency_code},
        }
        if interval:
            body["billing_cycle"] = {"interval": interval, "frequency": frequency or 1}
        if trial_interval:
            body["trial_period"] = {"interval": trial_interval, "frequency": trial_frequency or 1}
        result = await client.create_price(body)
        return format_price_detail(result.get("data", result))
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_update_price(
    price_id: Annotated[str, Field(description="Price ID (pri_*)")],
    description: Annotated[str | None, Field(description="New description")] = None,
    status: Annotated[str | None, Field(description="active or archived")] = None,
) -> str:
    """Update a price. Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        body: dict[str, object] = {}
        if description is not None:
            body["description"] = description
        if status is not None:
            body["status"] = status
        result = await client.update_price(price_id, body)
        return format_price_detail(result.get("data", result))
    except PaddleError as e:
        return _error(e)


# ===========================================================================
# Customers
# ===========================================================================


@mcp.tool
async def paddle_customers(
    status: Annotated[str | None, Field(description="Filter: active or archived")] = None,
    search: Annotated[str | None, Field(description="Search by name or email")] = None,
    limit: Annotated[int, Field(description="Max results")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination")] = None,
) -> str:
    """List or search customers."""
    try:
        client = await _get_client()
        result = await client.list_customers(status=status, search=search, limit=limit, after=after)
        return format_customer_list(result, limit)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_customer(
    customer_id: Annotated[str, Field(description="Customer ID (ctm_*)")],
    fields: Annotated[str | None, Field(description="Comma-separated fields to return")] = None,
) -> str:
    """Get customer detail."""
    try:
        client = await _get_client()
        result = await client.get_customer(customer_id)
        return format_customer_detail(result.get("data", result), fields)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_create_customer(
    email: Annotated[str, Field(description="Customer email address")],
    name: Annotated[str | None, Field(description="Customer name")] = None,
    locale: Annotated[str | None, Field(description="Locale (e.g., en)")] = None,
) -> str:
    """Create a new customer. Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        body: dict[str, object] = {"email": email}
        if name:
            body["name"] = name
        if locale:
            body["locale"] = locale
        result = await client.create_customer(body)
        return format_customer_detail(result.get("data", result))
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_update_customer(
    customer_id: Annotated[str, Field(description="Customer ID (ctm_*)")],
    name: Annotated[str | None, Field(description="New name")] = None,
    email: Annotated[str | None, Field(description="New email")] = None,
    status: Annotated[str | None, Field(description="active or archived")] = None,
    locale: Annotated[str | None, Field(description="New locale")] = None,
) -> str:
    """Update a customer. Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        body: dict[str, object] = {}
        if name is not None:
            body["name"] = name
        if email is not None:
            body["email"] = email
        if status is not None:
            body["status"] = status
        if locale is not None:
            body["locale"] = locale
        result = await client.update_customer(customer_id, body)
        return format_customer_detail(result.get("data", result))
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_customer_credit(
    customer_id: Annotated[str, Field(description="Customer ID (ctm_*)")],
) -> str:
    """Get customer credit balance."""
    try:
        client = await _get_client()
        result = await client.get_credit_balance(customer_id)
        return format_credit_balance(result)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_customer_portal(
    customer_id: Annotated[str, Field(description="Customer ID (ctm_*)")],
) -> str:
    """Create a customer portal session URL. Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        result = await client.create_portal_session(customer_id)
        data = result.get("data", result)
        urls = data.get("urls", {})
        general_url = urls.get("general", {}).get("overview", "?")
        return f"Portal URL: {general_url}"
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_customer_addresses(
    customer_id: Annotated[str, Field(description="Customer ID (ctm_*)")],
    address_id: Annotated[str | None, Field(description="Address ID to get specific address")] = None,
    limit: Annotated[int, Field(description="Max results")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination")] = None,
) -> str:
    """List customer addresses, or get a specific address by ID."""
    try:
        client = await _get_client()
        if address_id:
            result = await client.get_address(customer_id, address_id)
            data = result.get("data", result)
            parts = [f"ID: {data.get('id', '?')}", f"Country: {data.get('country_code', '?')}"]
            for f in ("first_line", "second_line", "city", "region", "postal_code"):
                if v := data.get(f):
                    parts.append(f"{f.replace('_', ' ').title()}: {v}")
            parts.append(f"Status: {data.get('status', '?')}")
            return "\n".join(parts)
        result = await client.list_addresses(customer_id, limit=limit, after=after)
        return format_address_list(result, limit)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_create_address(
    customer_id: Annotated[str, Field(description="Customer ID (ctm_*)")],
    country_code: Annotated[str, Field(description="ISO 3166-1 alpha-2 country code")],
    postal_code: Annotated[str | None, Field(description="Postal/ZIP code")] = None,
    city: Annotated[str | None, Field(description="City")] = None,
    region: Annotated[str | None, Field(description="State/region")] = None,
    first_line: Annotated[str | None, Field(description="Address line 1")] = None,
) -> str:
    """Create a customer address. Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        body: dict[str, object] = {"country_code": country_code}
        if postal_code:
            body["postal_code"] = postal_code
        if city:
            body["city"] = city
        if region:
            body["region"] = region
        if first_line:
            body["first_line"] = first_line
        result = await client.create_address(customer_id, body)
        data = result.get("data", result)
        return f"Created address: {data.get('id', '?')} | {country_code}"
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_update_address(
    customer_id: Annotated[str, Field(description="Customer ID (ctm_*)")],
    address_id: Annotated[str, Field(description="Address ID (add_*)")],
    country_code: Annotated[str | None, Field(description="New country code")] = None,
    postal_code: Annotated[str | None, Field(description="New postal code")] = None,
    city: Annotated[str | None, Field(description="New city")] = None,
    region: Annotated[str | None, Field(description="New region")] = None,
    status: Annotated[str | None, Field(description="active or archived")] = None,
) -> str:
    """Update a customer address. Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        body: dict[str, object] = {}
        if country_code is not None:
            body["country_code"] = country_code
        if postal_code is not None:
            body["postal_code"] = postal_code
        if city is not None:
            body["city"] = city
        if region is not None:
            body["region"] = region
        if status is not None:
            body["status"] = status
        result = await client.update_address(customer_id, address_id, body)
        data = result.get("data", result)
        return f"Updated address: {data.get('id', '?')}"
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_customer_businesses(
    customer_id: Annotated[str, Field(description="Customer ID (ctm_*)")],
    business_id: Annotated[str | None, Field(description="Business ID to get specific business")] = None,
    limit: Annotated[int, Field(description="Max results")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination")] = None,
) -> str:
    """List customer businesses, or get a specific business by ID."""
    try:
        client = await _get_client()
        if business_id:
            result = await client.get_business(customer_id, business_id)
            data = result.get("data", result)
            parts = [
                f"ID: {data.get('id', '?')}",
                f"Name: {data.get('name', '?')}",
                f"Status: {data.get('status', '?')}",
            ]
            if tax := data.get("tax_identifier"):
                parts.append(f"Tax ID: {tax}")
            return "\n".join(parts)
        result = await client.list_businesses(customer_id, limit=limit, after=after)
        return format_business_list(result, limit)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_create_business(
    customer_id: Annotated[str, Field(description="Customer ID (ctm_*)")],
    name: Annotated[str, Field(description="Business name")],
    tax_identifier: Annotated[str | None, Field(description="Tax/VAT ID")] = None,
    company_number: Annotated[str | None, Field(description="Company registration number")] = None,
) -> str:
    """Create a customer business. Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        body: dict[str, object] = {"name": name}
        if tax_identifier:
            body["tax_identifier"] = tax_identifier
        if company_number:
            body["company_number"] = company_number
        result = await client.create_business(customer_id, body)
        data = result.get("data", result)
        return f"Created business: {data.get('id', '?')} | {name}"
    except PaddleError as e:
        return _error(e)


# ===========================================================================
# Subscriptions
# ===========================================================================


@mcp.tool
async def paddle_subscriptions(
    status: Annotated[str | None, Field(description="Filter: active, canceled, past_due, paused, trialing")] = None,
    customer_id: Annotated[str | None, Field(description="Filter by customer ID")] = None,
    price_id: Annotated[str | None, Field(description="Filter by price ID")] = None,
    limit: Annotated[int, Field(description="Max results")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination")] = None,
) -> str:
    """List subscriptions with optional filters."""
    try:
        client = await _get_client()
        result = await client.list_subscriptions(
            status=status, customer_id=customer_id, price_id=price_id, limit=limit, after=after
        )
        return format_subscription_list(result, limit)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_subscription(
    subscription_id: Annotated[str, Field(description="Subscription ID (sub_*)")],
    include: Annotated[
        str | None, Field(description="Include: next_transaction, recurring_transaction_details")
    ] = None,
    fields: Annotated[str | None, Field(description="Comma-separated fields to return")] = None,
) -> str:
    """Get subscription detail."""
    try:
        client = await _get_client()
        result = await client.get_subscription(subscription_id, include=include)
        return format_subscription_detail(result.get("data", result), fields)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_update_subscription(
    subscription_id: Annotated[str, Field(description="Subscription ID (sub_*)")],
    items: Annotated[str | None, Field(description='Items JSON array: [{"price_id": "pri_*", "quantity": 1}]')] = None,
    proration_billing_mode: Annotated[
        str | None, Field(description="prorated_immediately, prorated_next_billing_period, full_immediately, etc.")
    ] = None,
    custom_data: Annotated[str | None, Field(description="Custom data as JSON string")] = None,
) -> str:
    """Update a subscription. Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        body: dict[str, object] = {}
        if items:
            body["items"] = json.loads(items)
        if proration_billing_mode:
            body["proration_billing_mode"] = proration_billing_mode
        if custom_data:
            body["custom_data"] = json.loads(custom_data)
        result = await client.update_subscription(subscription_id, body)
        return format_subscription_detail(result.get("data", result))
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_subscription_lifecycle(
    subscription_id: Annotated[str, Field(description="Subscription ID (sub_*)")],
    action: Annotated[str, Field(description="Action: pause, resume, or cancel")],
    effective_from: Annotated[
        str | None, Field(description="When: immediately, next_billing_period, or ISO date")
    ] = None,
    confirm: Annotated[bool, Field(description="Must be true for cancel action")] = False,
) -> str:
    """Pause, resume, or cancel a subscription. Cancel requires confirm=true. Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    if action == "cancel":
        if err := require_confirm(confirm, "Cancel subscription"):
            return err
    try:
        client = await _get_client()
        body: dict[str, object] = {}
        if effective_from:
            body["effective_from"] = effective_from

        if action == "pause":
            result = await client.pause_subscription(subscription_id, body or None)
        elif action == "resume":
            result = await client.resume_subscription(subscription_id, body or None)
        elif action == "cancel":
            result = await client.cancel_subscription(subscription_id, body or None)
        else:
            return f"Error: Unknown action '{action}'. Use pause, resume, or cancel."

        data = result.get("data", result)
        return f"Subscription {data.get('id', subscription_id)}: {action}d (status: {data.get('status', '?')})"
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_activate_subscription(
    subscription_id: Annotated[str, Field(description="Subscription ID (sub_*)")],
) -> str:
    """Activate a trialing subscription. Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        result = await client.activate_subscription(subscription_id)
        data = result.get("data", result)
        return f"Activated subscription: {data.get('id', subscription_id)} (status: {data.get('status', '?')})"
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_subscription_charge(
    subscription_id: Annotated[str, Field(description="Subscription ID (sub_*)")],
    items: Annotated[str, Field(description='Charge items JSON array: [{"price_id": "pri_*", "quantity": 1}]')],
    effective_from: Annotated[str, Field(description="When to charge: immediately or next_billing_period")],
) -> str:
    """Create a one-time charge on a subscription. Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        body: dict[str, object] = {
            "items": json.loads(items),
            "effective_from": effective_from,
        }
        result = await client.charge_subscription(subscription_id, body)
        return format_subscription_detail(result.get("data", result))
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_preview_subscription(
    subscription_id: Annotated[str, Field(description="Subscription ID (sub_*)")],
    items: Annotated[str | None, Field(description="New items as JSON array")] = None,
    proration_billing_mode: Annotated[str | None, Field(description="Proration mode")] = None,
) -> str:
    """Preview a subscription update without persisting changes."""
    try:
        client = await _get_client()
        body: dict[str, object] = {}
        if items:
            body["items"] = json.loads(items)
        if proration_billing_mode:
            body["proration_billing_mode"] = proration_billing_mode
        result = await client.preview_subscription_update(subscription_id, body)
        return format_subscription_detail(result.get("data", result))
    except PaddleError as e:
        return _error(e)


# ===========================================================================
# Transactions
# ===========================================================================


@mcp.tool
async def paddle_transactions(
    status: Annotated[
        str | None, Field(description="Filter: draft, ready, billed, paid, completed, canceled, past_due")
    ] = None,
    customer_id: Annotated[str | None, Field(description="Filter by customer ID")] = None,
    subscription_id: Annotated[str | None, Field(description="Filter by subscription ID")] = None,
    created_after: Annotated[str | None, Field(description="Filter: created after ISO date")] = None,
    created_before: Annotated[str | None, Field(description="Filter: created before ISO date")] = None,
    limit: Annotated[int, Field(description="Max results")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination")] = None,
) -> str:
    """List transactions with optional filters."""
    try:
        client = await _get_client()
        result = await client.list_transactions(
            status=status,
            customer_id=customer_id,
            subscription_id=subscription_id,
            created_after=created_after,
            created_before=created_before,
            limit=limit,
            after=after,
        )
        return format_transaction_list(result, limit)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_transaction(
    transaction_id: Annotated[str, Field(description="Transaction ID (txn_*)")],
    include: Annotated[
        str | None, Field(description="Include: address, adjustments, business, customer, discount")
    ] = None,
    fields: Annotated[str | None, Field(description="Comma-separated fields to return")] = None,
) -> str:
    """Get transaction detail."""
    try:
        client = await _get_client()
        result = await client.get_transaction(transaction_id, include=include)
        return format_transaction_detail(result.get("data", result), fields)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_create_transaction(
    items: Annotated[str, Field(description='Items as JSON array: [{"price_id": "pri_*", "quantity": 1}]')],
    customer_id: Annotated[str | None, Field(description="Customer ID")] = None,
    address_id: Annotated[str | None, Field(description="Address ID")] = None,
    currency_code: Annotated[str | None, Field(description="ISO 4217 currency")] = None,
) -> str:
    """Create a transaction. Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        body: dict[str, object] = {"items": json.loads(items)}
        if customer_id:
            body["customer_id"] = customer_id
        if address_id:
            body["address_id"] = address_id
        if currency_code:
            body["currency_code"] = currency_code
        result = await client.create_transaction(body)
        return format_transaction_detail(result.get("data", result))
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_preview_transaction(
    items: Annotated[str, Field(description='Items as JSON array: [{"price_id": "pri_*", "quantity": 1}]')],
    customer_id: Annotated[str | None, Field(description="Customer ID")] = None,
    address_id: Annotated[str | None, Field(description="Address ID")] = None,
    currency_code: Annotated[str | None, Field(description="ISO 4217 currency")] = None,
) -> str:
    """Preview transaction pricing without creating it."""
    try:
        client = await _get_client()
        body: dict[str, object] = {"items": json.loads(items)}
        if customer_id:
            body["customer_id"] = customer_id
        if address_id:
            body["address_id"] = address_id
        if currency_code:
            body["currency_code"] = currency_code
        result = await client.preview_transaction(body)
        return format_transaction_detail(result.get("data", result))
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_invoice_pdf(
    transaction_id: Annotated[str, Field(description="Transaction ID (txn_*)")],
) -> str:
    """Get invoice PDF download URL for a completed transaction."""
    try:
        client = await _get_client()
        result = await client.get_invoice_pdf(transaction_id)
        data = result.get("data", result)
        url = data.get("url", "?")
        return f"Invoice PDF: {url}"
    except PaddleError as e:
        return _error(e)


# ===========================================================================
# Adjustments & Discounts
# ===========================================================================


@mcp.tool
async def paddle_adjustments(
    transaction_id: Annotated[str | None, Field(description="Filter by transaction ID")] = None,
    action: Annotated[str | None, Field(description="Filter: credit, refund, chargeback")] = None,
    limit: Annotated[int, Field(description="Max results")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination")] = None,
) -> str:
    """List adjustments (refunds, credits, chargebacks)."""
    try:
        client = await _get_client()
        result = await client.list_adjustments(transaction_id=transaction_id, action=action, limit=limit, after=after)
        return format_adjustment_list(result, limit)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_adjustment(
    adjustment_id: Annotated[str, Field(description="Adjustment ID (adj_*)")],
) -> str:
    """Get a single adjustment by ID (refund, credit, or chargeback record)."""
    try:
        client = await _get_client()
        result = await client.get_adjustment(adjustment_id)
        return format_adjustment_detail(result)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_create_adjustment(
    transaction_id: Annotated[str, Field(description="Transaction ID (txn_*)")],
    action: Annotated[str, Field(description="Action: refund or credit")],
    reason: Annotated[str, Field(description="Reason for adjustment")],
    items: Annotated[str | None, Field(description="Items as JSON array for partial adjustment")] = None,
    adjustment_type: Annotated[str, Field(description="full or partial")] = "full",
) -> str:
    """Create an adjustment (refund or credit). Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        body: dict[str, object] = {
            "transaction_id": transaction_id,
            "action": action,
            "reason": reason,
            "type": adjustment_type,
        }
        if items:
            body["items"] = json.loads(items)
        result = await client.create_adjustment(body)
        data = result.get("data", result)
        return f"Created adjustment: {data.get('id', '?')} | {action} | {data.get('status', '?')}"
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_discounts(
    status: Annotated[str | None, Field(description="Filter: active or archived")] = None,
    limit: Annotated[int, Field(description="Max results")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination")] = None,
) -> str:
    """List discounts."""
    try:
        client = await _get_client()
        result = await client.list_discounts(status=status, limit=limit, after=after)
        return format_discount_list(result, limit)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_discount(
    discount_id: Annotated[str, Field(description="Discount ID (dis_*)")],
    fields: Annotated[str | None, Field(description="Comma-separated fields to return")] = None,
) -> str:
    """Get discount detail."""
    try:
        client = await _get_client()
        result = await client.get_discount(discount_id)
        return format_discount_detail(result.get("data", result), fields)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_create_discount(
    amount: Annotated[str, Field(description="Discount amount (cents for flat, percentage value for percentage)")],
    description: Annotated[str, Field(description="Discount description")],
    discount_type: Annotated[str, Field(description="Type: flat, flat_per_seat, or percentage")],
    currency_code: Annotated[str | None, Field(description="Currency for flat discounts (e.g., USD)")] = None,
    code: Annotated[str | None, Field(description="Coupon code")] = None,
    recur: Annotated[bool | None, Field(description="Apply to recurring payments")] = None,
    usage_limit: Annotated[int | None, Field(description="Max number of uses")] = None,
) -> str:
    """Create a discount. Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        body: dict[str, object] = {"amount": amount, "description": description, "type": discount_type}
        if currency_code:
            body["currency_code"] = currency_code
        if code:
            body["code"] = code
        if recur is not None:
            body["recur"] = recur
        if usage_limit is not None:
            body["usage_limit"] = usage_limit
        result = await client.create_discount(body)
        return format_discount_detail(result.get("data", result))
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_update_discount(
    discount_id: Annotated[str, Field(description="Discount ID (dis_*)")],
    description: Annotated[str | None, Field(description="New description")] = None,
    status: Annotated[str | None, Field(description="active or archived")] = None,
    amount: Annotated[str | None, Field(description="New amount")] = None,
) -> str:
    """Update a discount. Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        body: dict[str, object] = {}
        if description is not None:
            body["description"] = description
        if status is not None:
            body["status"] = status
        if amount is not None:
            body["amount"] = amount
        result = await client.update_discount(discount_id, body)
        return format_discount_detail(result.get("data", result))
    except PaddleError as e:
        return _error(e)


# ===========================================================================
# Payment Methods
# ===========================================================================


@mcp.tool
async def paddle_payment_methods(
    customer_id: Annotated[str, Field(description="Customer ID (ctm_*)")],
    limit: Annotated[int, Field(description="Max results")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination")] = None,
) -> str:
    """List customer payment methods."""
    try:
        client = await _get_client()
        result = await client.list_payment_methods(customer_id, limit=limit, after=after)
        return format_payment_method_list(result, limit)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_delete_payment_method(
    customer_id: Annotated[str, Field(description="Customer ID (ctm_*)")],
    payment_method_id: Annotated[str, Field(description="Payment method ID (paymtd_*)")],
    confirm: Annotated[bool, Field(description="Must be true to confirm deletion")] = False,
) -> str:
    """Delete a customer payment method. Requires confirm=true and PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    if err := require_confirm(confirm, "Delete payment method"):
        return err
    try:
        client = await _get_client()
        await client.delete_payment_method(customer_id, payment_method_id)
        return f"Deleted payment method: {payment_method_id}"
    except PaddleError as e:
        return _error(e)


# ===========================================================================
# Notifications & Events
# ===========================================================================


@mcp.tool
async def paddle_notification_settings(
    limit: Annotated[int, Field(description="Max results")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination")] = None,
) -> str:
    """List notification settings (webhook destinations)."""
    try:
        client = await _get_client()
        result = await client.list_notification_settings(limit=limit, after=after)
        return format_notification_setting_list(result, limit)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_create_notification_setting(
    destination: Annotated[str, Field(description="Webhook URL or email address")],
    subscribed_events: Annotated[str, Field(description="Comma-separated event types (e.g., subscription.created)")],
    setting_type: Annotated[str, Field(description="Type: url or email")] = "url",
    description: Annotated[str | None, Field(description="Description")] = None,
) -> str:
    """Create a notification setting. Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        body: dict[str, object] = {
            "destination": destination,
            "subscribed_events": [e.strip() for e in subscribed_events.split(",")],
            "type": setting_type,
        }
        if description:
            body["description"] = description
        result = await client.create_notification_setting(body)
        data = result.get("data", result)
        return f"Created notification setting: {data.get('id', '?')} | {destination}"
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_delete_notification_setting(
    setting_id: Annotated[str, Field(description="Notification setting ID (ntfset_*)")],
    confirm: Annotated[bool, Field(description="Must be true to confirm deletion")] = False,
) -> str:
    """Delete a notification setting. Requires confirm=true and PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    if err := require_confirm(confirm, "Delete notification setting"):
        return err
    try:
        client = await _get_client()
        await client.delete_notification_setting(setting_id)
        return f"Deleted notification setting: {setting_id}"
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_notifications(
    notification_setting_id: Annotated[str | None, Field(description="Filter by notification setting ID")] = None,
    status: Annotated[str | None, Field(description="Filter: delivered, failed, needs_retry, not_attempted")] = None,
    limit: Annotated[int, Field(description="Max results")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination")] = None,
) -> str:
    """List notifications."""
    try:
        client = await _get_client()
        result = await client.list_notifications(
            notification_setting_id=notification_setting_id, status=status, limit=limit, after=after
        )
        return format_notification_list(result, limit)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_notification(
    notification_id: Annotated[str, Field(description="Notification ID (ntf_*)")],
    include_logs: Annotated[bool, Field(description="Include delivery logs")] = False,
) -> str:
    """Get notification detail, optionally with delivery logs."""
    try:
        client = await _get_client()
        result = await client.get_notification(notification_id)
        output = format_notification_detail(result.get("data", result))
        if include_logs:
            logs = await client.get_notification_logs(notification_id)
            log_items = logs.get("data", [])
            if log_items:
                output += f"\n\nDelivery Logs ({len(log_items)}):"
                for log_entry in log_items[:10]:
                    status_val = log_entry.get("response_code", "?")
                    attempted = log_entry.get("attempted_at", "?")
                    output += f"\n  {format_datetime(attempted)} | HTTP {status_val}"
        return output
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_replay_notification(
    notification_id: Annotated[str, Field(description="Notification ID (ntf_*)")],
) -> str:
    """Replay a notification. Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        result = await client.replay_notification(notification_id)
        new_id = result.get("data", {}).get("notification_id", "?")
        return f"Replayed notification: {notification_id} (new ID: {new_id})"
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_events(
    limit: Annotated[int, Field(description="Max results")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination")] = None,
) -> str:
    """List events (billing event log)."""
    try:
        client = await _get_client()
        result = await client.list_events(limit=limit, after=after)
        return format_event_list(result, limit)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_event_types() -> str:
    """List all event types Paddle can emit (used to populate webhook subscriptions)."""
    try:
        client = await _get_client()
        result = await client.list_event_types()
        return format_event_type_list(result)
    except PaddleError as e:
        return _error(e)


# ===========================================================================
# Webhooks & Security
# ===========================================================================


@mcp.tool
async def paddle_verify_webhook(
    body: Annotated[str, Field(description="Raw webhook request body (JSON string)")],
    signature: Annotated[str, Field(description="Paddle-Signature header value (ts=...;h1=...)")],
    secret: Annotated[
        str | None, Field(description="Webhook secret (defaults to PADDLE_WEBHOOK_SECRET env var)")
    ] = None,
) -> str:
    """Verify a webhook HMAC-SHA256 signature and parse the event."""
    webhook_secret = secret or os.environ.get("PADDLE_WEBHOOK_SECRET", "").strip()
    if not webhook_secret:
        return "Error: No webhook secret provided. Set PADDLE_WEBHOOK_SECRET or pass secret= parameter."
    result = PaddleClient.verify_webhook_signature(body, signature, webhook_secret)
    return format_webhook_verification(result)


@mcp.tool
async def paddle_parse_event(
    body: Annotated[str, Field(description="Webhook or event payload (JSON string)")],
) -> str:
    """Parse a webhook/event payload and extract type and key fields. No verification."""
    try:
        event = json.loads(body)
        return format_event_detail(event)
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON: {e}"


# ===========================================================================
# Reports
# ===========================================================================


@mcp.tool
async def paddle_reports(
    limit: Annotated[int, Field(description="Max results")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination")] = None,
) -> str:
    """List reports."""
    try:
        client = await _get_client()
        result = await client.list_reports(limit=limit, after=after)
        return format_report_list(result, limit)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_create_report(
    report_type: Annotated[
        str, Field(description="Report type: transactions, transaction_line_items, products_prices, discounts")
    ],
    filters: Annotated[str | None, Field(description="Filters as JSON string")] = None,
) -> str:
    """Create a report. Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        body: dict[str, object] = {"type": report_type}
        if filters:
            body["filters"] = json.loads(filters)
        result = await client.create_report(body)
        data = result.get("data", result)
        return f"Created report: {data.get('id', '?')} | {report_type} | status={data.get('status', '?')}"
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_report_csv(
    report_id: Annotated[str, Field(description="Report ID (rep_*)")],
) -> str:
    """Get CSV download URL for a completed report."""
    try:
        client = await _get_client()
        result = await client.get_report_csv(report_id)
        data = result.get("data", result)
        url = data.get("url", "?")
        return f"CSV download URL: {url}"
    except PaddleError as e:
        return _error(e)


# ===========================================================================
# Simulations
# ===========================================================================


@mcp.tool
async def paddle_simulations(
    limit: Annotated[int, Field(description="Max results")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination")] = None,
) -> str:
    """List simulations."""
    try:
        client = await _get_client()
        result = await client.list_simulations(limit=limit, after=after)
        return format_simulation_list(result, limit)
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_create_simulation(
    event_type: Annotated[str, Field(description="Event type to simulate (e.g., subscription.created)")],
    notification_setting_id: Annotated[str, Field(description="Notification setting to send simulation to")],
    name: Annotated[str | None, Field(description="Simulation name")] = None,
) -> str:
    """Create a simulation. Requires PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        body: dict[str, object] = {
            "type": event_type,
            "notification_setting_id": notification_setting_id,
        }
        if name:
            body["name"] = name
        result = await client.create_simulation(body)
        data = result.get("data", result)
        return f"Created simulation: {data.get('id', '?')} | {event_type}"
    except PaddleError as e:
        return _error(e)


@mcp.tool
async def paddle_run_simulation(
    simulation_id: Annotated[str, Field(description="Simulation ID (sim_*)")],
    confirm: Annotated[bool, Field(description="Must be true to run")] = False,
) -> str:
    """Run a simulation. Sends test webhook events. Requires confirm=true and PADDLE_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    if err := require_confirm(confirm, "Run simulation"):
        return err
    try:
        client = await _get_client()
        result = await client.run_simulation(simulation_id)
        data = result.get("data", result)
        return f"Simulation run started: {data.get('id', '?')} | status={data.get('status', '?')}"
    except PaddleError as e:
        return _error(e)


# ===========================================================================
# Entry point
# ===========================================================================


def main() -> None:
    """Run the Paddle Blade MCP server."""
    if TRANSPORT == "http":
        from starlette.middleware import Middleware

        from paddle_billing_blade_mcp.auth import BearerAuthMiddleware, get_bearer_token

        bearer = get_bearer_token()
        logger.info("PaddleBlade HTTP on %s:%s (auth=%s)", HTTP_HOST, HTTP_PORT, "on" if bearer else "off")
        mcp.run(transport="http", host=HTTP_HOST, port=HTTP_PORT, middleware=[Middleware(BearerAuthMiddleware)])
    else:
        mcp.run(transport="stdio")
