"""Shared fixtures for paddle-billing-blade-mcp tests."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure a clean env for every test — no real API keys leak."""
    monkeypatch.delenv("PADDLE_API_KEY", raising=False)
    monkeypatch.delenv("PADDLE_ENVIRONMENT", raising=False)
    monkeypatch.delenv("PADDLE_WRITE_ENABLED", raising=False)
    monkeypatch.delenv("PADDLE_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("PADDLE_MCP_API_TOKEN", raising=False)


@pytest.fixture
def sandbox_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up sandbox env vars for client construction."""
    monkeypatch.setenv("PADDLE_API_KEY", "pdl_sdbx_test_key_123")
    monkeypatch.setenv("PADDLE_ENVIRONMENT", "sandbox")


@pytest.fixture
def write_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable write operations."""
    monkeypatch.setenv("PADDLE_WRITE_ENABLED", "true")


# ---------------------------------------------------------------------------
# Sample Paddle API responses
# ---------------------------------------------------------------------------

SAMPLE_PRODUCT: dict[str, Any] = {
    "id": "pro_abc123",
    "name": "Pro Plan",
    "description": "Professional subscription",
    "type": "standard",
    "status": "active",
    "tax_category": "standard",
    "created_at": "2026-03-15T10:00:00Z",
    "updated_at": "2026-03-15T10:00:00Z",
}

SAMPLE_PRICE: dict[str, Any] = {
    "id": "pri_abc123",
    "product_id": "pro_abc123",
    "description": "Monthly",
    "unit_price": {"amount": "2900", "currency_code": "USD"},
    "billing_cycle": {"interval": "month", "frequency": 1},
    "status": "active",
    "created_at": "2026-03-15T10:00:00Z",
}

SAMPLE_CUSTOMER: dict[str, Any] = {
    "id": "ctm_abc123",
    "email": "alice@example.com",
    "name": "Alice Smith",
    "status": "active",
    "locale": "en",
    "created_at": "2026-03-15T10:00:00Z",
    "updated_at": "2026-03-15T10:00:00Z",
}

SAMPLE_SUBSCRIPTION: dict[str, Any] = {
    "id": "sub_abc123",
    "customer_id": "ctm_abc123",
    "status": "active",
    "currency_code": "USD",
    "collection_mode": "automatic",
    "items": [
        {
            "price": {
                "id": "pri_abc123",
                "description": "Monthly",
                "unit_price": {"amount": "2900", "currency_code": "USD"},
                "billing_cycle": {"interval": "month", "frequency": 1},
            },
            "quantity": 1,
        }
    ],
    "current_billing_period": {
        "starts_at": "2026-03-01T00:00:00Z",
        "ends_at": "2026-03-31T23:59:59Z",
    },
    "next_billed_at": "2026-04-01T00:00:00Z",
    "started_at": "2026-01-01T00:00:00Z",
}

SAMPLE_TRANSACTION: dict[str, Any] = {
    "id": "txn_abc123",
    "customer_id": "ctm_abc123",
    "subscription_id": "sub_abc123",
    "status": "completed",
    "currency_code": "USD",
    "origin": "subscription_recurring",
    "collection_mode": "automatic",
    "details": {
        "totals": {
            "subtotal": "2900",
            "tax": "0",
            "discount": "0",
            "grand_total": "2900",
        },
        "line_items": [
            {
                "product": {"name": "Pro Plan"},
                "quantity": 1,
                "total": "2900",
            }
        ],
    },
    "billed_at": "2026-03-15T10:00:00Z",
    "created_at": "2026-03-15T10:00:00Z",
}

SAMPLE_PAGINATION_META: dict[str, Any] = {
    "pagination": {
        "per_page": 20,
        "has_more": True,
        "estimated_total": 50,
        "next": "https://sandbox-api.paddle.com/products?after=pro_xyz",
    }
}

SAMPLE_NO_MORE_META: dict[str, Any] = {
    "pagination": {
        "per_page": 20,
        "has_more": False,
        "estimated_total": 2,
    }
}


def make_list_response(items: list[dict[str, Any]], has_more: bool = False) -> dict[str, Any]:
    """Build a Paddle list API response."""
    meta = SAMPLE_PAGINATION_META if has_more else SAMPLE_NO_MORE_META
    return {"data": items, "meta": meta}


def make_detail_response(data: dict[str, Any]) -> dict[str, Any]:
    """Build a Paddle detail API response."""
    return {"data": data}
