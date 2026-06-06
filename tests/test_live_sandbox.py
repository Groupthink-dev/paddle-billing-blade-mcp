"""Live sandbox e2e regression for the DD-385 live-hardening fixes.

Gated on a real Paddle SANDBOX key + ``PADDLE_ENVIRONMENT=sandbox``. When those
are absent the whole module is skipped, so CI mock runs are unaffected.

SAFETY: sandbox only. The module refuses to run unless ``validate_environment``
resolves to ``sandbox-api.paddle.com``. Every object created here is ``zz-``
prefixed and torn down (products archived in a fixture finalizer; archiving a
product cascades to its prices).

These assertions FAIL against the pre-fix code:
  * ``paddle_ip_addresses`` printed the literal key ``ipv4_cidrs`` instead of CIDRs.
  * transaction line items showed ``$0.00`` because the amount was read from a
    non-existent top-level ``total`` key instead of ``line_items[].totals.total``.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator

import pytest

from paddle_billing_blade_mcp.client import PaddleClient
from paddle_billing_blade_mcp.models import format_money, validate_environment

pytestmark = pytest.mark.e2e

_HAVE_SANDBOX = bool(os.environ.get("PADDLE_API_KEY")) and os.environ.get("PADDLE_ENVIRONMENT", "").lower() == "sandbox"

skip_no_sandbox = pytest.mark.skipif(
    not _HAVE_SANDBOX,
    reason="requires PADDLE_API_KEY + PADDLE_ENVIRONMENT=sandbox",
)

_IPV4_CIDR_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}/\d{1,2}\b")


@pytest.fixture(autouse=True)
def _clean_env() -> None:
    """Override the conftest autouse env-scrubber — live tests need the real key."""
    return None


@pytest.fixture(scope="module")
def sandbox_guard() -> None:
    """Hard-fail if we are not pointed at the Paddle sandbox."""
    url = validate_environment()
    assert url == "https://sandbox-api.paddle.com", f"refusing to run live tests against {url}"


@pytest.fixture
async def live_client(sandbox_guard: None) -> PaddleClient:
    return PaddleClient()


@pytest.fixture
async def zz_product_price(live_client: PaddleClient) -> Iterator[dict[str, str]]:
    """Create a zz- product + price; archive the product on teardown (cascades)."""
    created_products: list[str] = []
    product = await live_client.create_product({"name": "zz-dd385-live-product", "tax_category": "standard"})
    product_id = product["data"]["id"]
    created_products.append(product_id)
    price = await live_client.create_price(
        {
            "product_id": product_id,
            "description": "zz-dd385-live-price",
            "unit_price": {"amount": "1800", "currency_code": "USD"},
        }
    )
    price_id = price["data"]["id"]

    yield {"product_id": product_id, "price_id": price_id}

    # Teardown: archive every created product (archiving cascades to its prices).
    for pid in created_products:
        try:
            await live_client.update_product(pid, {"status": "archived"})
        except Exception:  # noqa: BLE001 - best-effort cleanup; never fail teardown
            pass


@skip_no_sandbox
@pytest.mark.asyncio
async def test_ip_addresses_lists_real_cidrs() -> None:
    """Defect #1: GET /ips renders CIDR strings, not the literal 'ipv4_cidrs' key."""
    # Import here so module collection never constructs a client at import time.
    import paddle_billing_blade_mcp.server as server

    server._client = None
    out = await server.paddle_ip_addresses()
    payload = out.split("\n\n_meta:")[0]
    assert _IPV4_CIDR_RE.search(payload), f"expected at least one IPv4 CIDR, got: {payload!r}"
    assert "ipv4_cidrs" not in payload, "must not leak the literal wire key"


@skip_no_sandbox
@pytest.mark.asyncio
async def test_preview_transaction_line_item_nonzero(zz_product_price: dict[str, str]) -> None:
    """Defect #2: a previewed line item shows a non-zero money amount."""
    import json

    import paddle_billing_blade_mcp.server as server

    server._client = None
    out = await server.paddle_preview_transaction(
        items=json.dumps([{"price_id": zz_product_price["price_id"], "quantity": 1}]),
    )
    payload = out.split("\n\n_meta:")[0]
    assert "Line Items" in payload, f"no line items in preview output: {payload!r}"
    line_items_section = payload.split("Line Items")[1]
    assert "$0.00" not in line_items_section, f"line item rendered $0.00 (pre-fix bug): {line_items_section!r}"
    assert "$18.00 USD" in line_items_section, f"expected $18.00 line item, got: {line_items_section!r}"


class TestThreeDecimalMoneyMatrix:
    """Defect #4: 3-decimal currencies divide by 1000 with 3dp; others unchanged."""

    def test_bhd(self) -> None:
        assert format_money("1000", "BHD") == "1.000 BHD"

    def test_kwd(self) -> None:
        assert format_money("2500", "KWD") == "2.500 KWD"

    def test_omr(self) -> None:
        assert format_money("12345", "OMR") == "12.345 OMR"

    def test_usd_unchanged(self) -> None:
        assert format_money("2900", "USD") == "$29.00 USD"

    def test_jpy_unchanged(self) -> None:
        assert format_money("1000", "JPY") == "¥1000 JPY"
