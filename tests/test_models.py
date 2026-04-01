"""Tests for models.py — gates, money formatting, env validation, scrubbing."""

from __future__ import annotations

import pytest

from paddle_billing_blade_mcp.models import (
    format_money,
    get_environment_name,
    is_write_enabled,
    require_confirm,
    require_write,
    scrub_secrets,
    validate_environment,
)

# ---------------------------------------------------------------------------
# Environment validation
# ---------------------------------------------------------------------------


class TestValidateEnvironment:
    def test_sandbox(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PADDLE_ENVIRONMENT", "sandbox")
        assert validate_environment() == "https://sandbox-api.paddle.com"

    def test_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PADDLE_ENVIRONMENT", "production")
        assert validate_environment() == "https://api.paddle.com"

    def test_missing_raises(self) -> None:
        with pytest.raises(ValueError, match="PADDLE_ENVIRONMENT must be"):
            validate_environment()

    def test_invalid_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PADDLE_ENVIRONMENT", "staging")
        with pytest.raises(ValueError, match="staging"):
            validate_environment()

    def test_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PADDLE_ENVIRONMENT", "Sandbox")
        assert validate_environment() == "https://sandbox-api.paddle.com"

    def test_whitespace_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PADDLE_ENVIRONMENT", "  production  ")
        assert validate_environment() == "https://api.paddle.com"


class TestGetEnvironmentName:
    def test_returns_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PADDLE_ENVIRONMENT", "sandbox")
        assert get_environment_name() == "sandbox"

    def test_empty_when_unset(self) -> None:
        assert get_environment_name() == ""


# ---------------------------------------------------------------------------
# Write gate
# ---------------------------------------------------------------------------


class TestWriteGate:
    def test_disabled_by_default(self) -> None:
        assert not is_write_enabled()
        err = require_write()
        assert err is not None
        assert "disabled" in err

    def test_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PADDLE_WRITE_ENABLED", "true")
        assert is_write_enabled()
        assert require_write() is None

    def test_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PADDLE_WRITE_ENABLED", "True")
        assert is_write_enabled()

    def test_non_true_is_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PADDLE_WRITE_ENABLED", "yes")
        assert not is_write_enabled()


# ---------------------------------------------------------------------------
# Confirm gate
# ---------------------------------------------------------------------------


class TestConfirmGate:
    def test_no_confirm_returns_error(self) -> None:
        err = require_confirm(False, "Cancel subscription")
        assert err is not None
        assert "confirm=true" in err
        assert "Cancel subscription" in err

    def test_confirm_true_returns_none(self) -> None:
        assert require_confirm(True, "Cancel subscription") is None


# ---------------------------------------------------------------------------
# Money formatting
# ---------------------------------------------------------------------------


class TestFormatMoney:
    def test_usd(self) -> None:
        assert format_money("2900", "USD") == "$29.00 USD"

    def test_zero(self) -> None:
        assert format_money("0", "USD") == "$0.00 USD"

    def test_gbp(self) -> None:
        assert format_money("1050", "GBP") == "£10.50 GBP"

    def test_jpy_zero_decimal(self) -> None:
        assert format_money("1000", "JPY") == "¥1000 JPY"

    def test_unknown_currency(self) -> None:
        result = format_money("500", "XYZ")
        assert "5.00" in result
        assert "XYZ" in result

    def test_invalid_amount(self) -> None:
        assert format_money("invalid", "USD") == "invalid USD"

    def test_eur(self) -> None:
        assert format_money("9900", "EUR") == "€99.00 EUR"


# ---------------------------------------------------------------------------
# Secret scrubbing
# ---------------------------------------------------------------------------


class TestScrubSecrets:
    def test_scrubs_paddle_key(self) -> None:
        text = "Error with key pdl_sdbx_abc123_xyz"
        result = scrub_secrets(text)
        assert "pdl_" not in result
        assert "****" in result

    def test_scrubs_bearer_token(self) -> None:
        text = "Authorization: Bearer my_secret_token"
        result = scrub_secrets(text)
        assert "my_secret_token" not in result
        assert "****" in result

    def test_leaves_clean_text(self) -> None:
        text = "Everything is fine"
        assert scrub_secrets(text) == text

    def test_scrubs_live_key(self) -> None:
        text = "key=pdl_live_abcdef123"
        result = scrub_secrets(text)
        assert "pdl_live" not in result
