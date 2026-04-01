"""Shared constants, types, and gates for Paddle Blade MCP server."""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

DEFAULT_LIMIT = 20
MAX_LIMIT = 200  # Paddle API max per_page
MAX_BODY_CHARS = 50_000

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

BASE_URLS: dict[str, str] = {
    "sandbox": "https://sandbox-api.paddle.com",
    "production": "https://api.paddle.com",
}

# Entity ID prefixes for validation/display
ENTITY_PREFIXES: dict[str, str] = {
    "pro_": "product",
    "pri_": "price",
    "ctm_": "customer",
    "add_": "address",
    "biz_": "business",
    "sub_": "subscription",
    "txn_": "transaction",
    "adj_": "adjustment",
    "dis_": "discount",
    "ntf_": "notification",
    "ntfset_": "notification_setting",
    "evt_": "event",
    "rep_": "report",
    "sim_": "simulation",
    "paymtd_": "payment_method",
    "dsgp_": "discount_group",
    "ctok_": "client_token",
}

# Currency symbols for human-readable money formatting
CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "AUD": "A$",
    "CAD": "C$",
    "NZD": "NZ$",
    "HKD": "HK$",
    "SGD": "S$",
    "JPY": "¥",
    "CNY": "¥",
    "CHF": "CHF ",
    "SEK": "kr",
    "NOK": "kr",
    "DKK": "kr",
    "INR": "₹",
    "BRL": "R$",
    "KRW": "₩",
    "MXN": "MX$",
    "PLN": "zł",
    "THB": "฿",
    "TRY": "₺",
}

# Zero-decimal currencies (amount is already in major units)
ZERO_DECIMAL_CURRENCIES: set[str] = {"JPY", "KRW", "VND"}


# ---------------------------------------------------------------------------
# Environment validation
# ---------------------------------------------------------------------------


def validate_environment() -> str:
    """Validate PADDLE_ENVIRONMENT and return the base URL.

    Raises:
        ValueError: If PADDLE_ENVIRONMENT is missing or invalid.
    """
    env = os.environ.get("PADDLE_ENVIRONMENT", "").strip().lower()
    if env not in BASE_URLS:
        raise ValueError(
            f"PADDLE_ENVIRONMENT must be 'sandbox' or 'production', got '{env or '(empty)'}'. "
            "This is required to prevent accidental operations against the wrong environment."
        )
    return BASE_URLS[env]


def get_environment_name() -> str:
    """Return the current environment name (sandbox/production)."""
    return os.environ.get("PADDLE_ENVIRONMENT", "").strip().lower()


# ---------------------------------------------------------------------------
# Write gate
# ---------------------------------------------------------------------------


def is_write_enabled() -> bool:
    """Check if write operations are enabled via env var."""
    return os.environ.get("PADDLE_WRITE_ENABLED", "").lower() == "true"


def require_write() -> str | None:
    """Return an error message if writes are disabled, else None."""
    if not is_write_enabled():
        return "Error: Write operations are disabled. Set PADDLE_WRITE_ENABLED=true to enable."
    return None


# ---------------------------------------------------------------------------
# Confirm gate (for destructive operations)
# ---------------------------------------------------------------------------


def require_confirm(confirm: bool, action: str) -> str | None:
    """Return an error message if confirm is False for a destructive operation.

    This is a second gate beyond require_write() for operations that are
    difficult or impossible to reverse (cancel subscription, delete payment method).
    """
    if not confirm:
        return f"Error: {action} requires confirm=true. This action may be difficult to reverse."
    return None


# ---------------------------------------------------------------------------
# Money formatting
# ---------------------------------------------------------------------------


def format_money(amount: str, currency_code: str) -> str:
    """Format a Paddle money amount for human-readable output.

    Paddle stores amounts as string cents (e.g., "2900" for $29.00).
    Zero-decimal currencies (JPY, KRW, VND) are already in major units.

    Examples:
        format_money("2900", "USD") -> "$29.00 USD"
        format_money("1000", "JPY") -> "¥1000 JPY"
        format_money("0", "USD") -> "$0.00 USD"
    """
    try:
        cents = int(amount)
    except (ValueError, TypeError):
        return f"{amount} {currency_code}"

    symbol = CURRENCY_SYMBOLS.get(currency_code, "")

    if currency_code in ZERO_DECIMAL_CURRENCIES:
        return f"{symbol}{cents} {currency_code}"

    major = cents / 100
    return f"{symbol}{major:.2f} {currency_code}"


# ---------------------------------------------------------------------------
# Token scrubbing
# ---------------------------------------------------------------------------

# Patterns that indicate Paddle API keys or secrets
_SCRUB_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"pdl_[a-zA-Z0-9_]+"),  # Paddle API keys (pdl_sdbx_*, pdl_live_*)
    re.compile(r"Bearer\s+[^\s]+", re.IGNORECASE),  # Bearer tokens
]


def scrub_secrets(text: str) -> str:
    """Remove API keys and tokens from text to prevent leakage."""
    result = text
    for pattern in _SCRUB_PATTERNS:
        result = pattern.sub("****", result)
    return result
