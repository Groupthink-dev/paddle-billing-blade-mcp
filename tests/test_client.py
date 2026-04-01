"""Tests for client.py — PaddleClient, error hierarchy, webhook verification."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from paddle_billing_blade_mcp.client import (
    AuthError,
    ConflictError,
    ConnectionError,
    NotFoundError,
    PaddleClient,
    PaddleError,
    RateLimitError,
    ValidationError,
    _classify_http_error,
)

# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestClientConstruction:
    def test_requires_api_key(self) -> None:
        with pytest.raises(AuthError, match="PADDLE_API_KEY"):
            PaddleClient()

    def test_requires_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PADDLE_API_KEY", "pdl_sdbx_test")
        with pytest.raises(ValueError, match="PADDLE_ENVIRONMENT"):
            PaddleClient()

    def test_creates_with_env(self, sandbox_env: None) -> None:
        client = PaddleClient()
        assert client.environment == "sandbox"

    def test_creates_with_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PADDLE_ENVIRONMENT", "sandbox")
        client = PaddleClient(api_key="pdl_sdbx_test")
        assert client.environment == "sandbox"


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


class TestErrorClassification:
    def test_401_is_auth(self) -> None:
        err = _classify_http_error(401, {"error": {"code": "unauthorized", "detail": "bad key"}})
        assert isinstance(err, AuthError)

    def test_404_is_not_found(self) -> None:
        err = _classify_http_error(404, {"error": {"code": "not_found", "detail": ""}})
        assert isinstance(err, NotFoundError)

    def test_409_is_conflict(self) -> None:
        err = _classify_http_error(409, {"error": {"code": "conflict", "detail": ""}})
        assert isinstance(err, ConflictError)

    def test_422_is_validation(self) -> None:
        err = _classify_http_error(422, {"error": {"code": "validation", "detail": "bad field"}})
        assert isinstance(err, ValidationError)

    def test_429_is_rate_limit(self) -> None:
        err = _classify_http_error(429, {"error": {"code": "rate_limit", "detail": ""}})
        assert isinstance(err, RateLimitError)

    def test_500_is_base(self) -> None:
        err = _classify_http_error(500, {"error": {"code": "server_error", "detail": "oops"}})
        assert isinstance(err, PaddleError)
        assert not isinstance(err, AuthError)

    def test_scrubs_secrets_in_error(self) -> None:
        err = _classify_http_error(401, {"error": {"code": "auth", "detail": "key pdl_sdbx_abc invalid"}})
        assert "pdl_sdbx" not in str(err)


# ---------------------------------------------------------------------------
# HTTP method tests (mocked httpx)
# ---------------------------------------------------------------------------


@pytest.fixture
def client(sandbox_env: None) -> PaddleClient:
    """Create a PaddleClient with sandbox env."""
    return PaddleClient()


class TestHttpMethods:
    @pytest.mark.asyncio
    async def test_get_success(self, client: PaddleClient) -> None:
        mock_response = httpx.Response(
            200,
            json={"data": [{"id": "pro_123"}], "meta": {}},
            request=httpx.Request("GET", "https://test"),
        )
        with patch.object(client._http, "request", new_callable=AsyncMock, return_value=mock_response):
            result = await client._get("/products")
            assert result["data"][0]["id"] == "pro_123"

    @pytest.mark.asyncio
    async def test_get_filters_none_params(self, client: PaddleClient) -> None:
        mock_response = httpx.Response(
            200,
            json={"data": []},
            request=httpx.Request("GET", "https://test"),
        )
        with patch.object(client._http, "request", new_callable=AsyncMock, return_value=mock_response) as mock_req:
            await client._get("/products", {"status": "active", "type": None})
            _, kwargs = mock_req.call_args
            assert kwargs["params"] == {"status": "active"}

    @pytest.mark.asyncio
    async def test_post_success(self, client: PaddleClient) -> None:
        mock_response = httpx.Response(
            200,
            json={"data": {"id": "pro_new"}},
            request=httpx.Request("POST", "https://test"),
        )
        with patch.object(client._http, "request", new_callable=AsyncMock, return_value=mock_response):
            result = await client._post("/products", {"name": "Test"})
            assert result["data"]["id"] == "pro_new"

    @pytest.mark.asyncio
    async def test_delete_204(self, client: PaddleClient) -> None:
        mock_response = httpx.Response(
            204,
            request=httpx.Request("DELETE", "https://test"),
        )
        with patch.object(client._http, "request", new_callable=AsyncMock, return_value=mock_response):
            result = await client._delete("/something")
            assert result == {}

    @pytest.mark.asyncio
    async def test_error_response(self, client: PaddleClient) -> None:
        mock_response = httpx.Response(
            404,
            json={"error": {"code": "not_found", "detail": "Not found"}},
            request=httpx.Request("GET", "https://test"),
        )
        with patch.object(client._http, "request", new_callable=AsyncMock, return_value=mock_response):
            with pytest.raises(NotFoundError):
                await client._get("/products/pro_missing")

    @pytest.mark.asyncio
    async def test_connection_error(self, client: PaddleClient) -> None:
        with patch.object(
            client._http, "request", new_callable=AsyncMock, side_effect=httpx.ConnectError("connection refused")
        ):
            with pytest.raises(ConnectionError):
                await client._get("/products")

    @pytest.mark.asyncio
    async def test_timeout_error(self, client: PaddleClient) -> None:
        with patch.object(client._http, "request", new_callable=AsyncMock, side_effect=httpx.ReadTimeout("timeout")):
            with pytest.raises(ConnectionError, match="timed out"):
                await client._get("/products")


# ---------------------------------------------------------------------------
# Resource method tests
# ---------------------------------------------------------------------------


class TestResourceMethods:
    @pytest.mark.asyncio
    async def test_list_products(self, client: PaddleClient) -> None:
        mock_response = httpx.Response(200, json={"data": [], "meta": {}}, request=httpx.Request("GET", "https://test"))
        with patch.object(client._http, "request", new_callable=AsyncMock, return_value=mock_response) as mock_req:
            await client.list_products(status="active", limit=10)
            args, kwargs = mock_req.call_args
            assert args[0] == "GET"
            assert "/products" in args[1]
            assert kwargs["params"]["status"] == "active"
            assert kwargs["params"]["per_page"] == 10

    @pytest.mark.asyncio
    async def test_get_product(self, client: PaddleClient) -> None:
        mock_response = httpx.Response(
            200, json={"data": {"id": "pro_123"}}, request=httpx.Request("GET", "https://test")
        )
        with patch.object(client._http, "request", new_callable=AsyncMock, return_value=mock_response) as mock_req:
            await client.get_product("pro_123", include="prices")
            args, _ = mock_req.call_args
            assert "pro_123" in args[1]

    @pytest.mark.asyncio
    async def test_create_product(self, client: PaddleClient) -> None:
        mock_response = httpx.Response(
            200, json={"data": {"id": "pro_new"}}, request=httpx.Request("POST", "https://test")
        )
        with patch.object(client._http, "request", new_callable=AsyncMock, return_value=mock_response) as mock_req:
            await client.create_product({"name": "Test", "tax_category": "standard"})
            args, kwargs = mock_req.call_args
            assert args[0] == "POST"
            assert kwargs["json"]["name"] == "Test"

    @pytest.mark.asyncio
    async def test_list_subscriptions(self, client: PaddleClient) -> None:
        mock_response = httpx.Response(200, json={"data": [], "meta": {}}, request=httpx.Request("GET", "https://test"))
        with patch.object(client._http, "request", new_callable=AsyncMock, return_value=mock_response) as mock_req:
            await client.list_subscriptions(customer_id="ctm_123")
            _, kwargs = mock_req.call_args
            assert kwargs["params"]["customer_id"] == "ctm_123"

    @pytest.mark.asyncio
    async def test_cancel_subscription(self, client: PaddleClient) -> None:
        mock_response = httpx.Response(
            200, json={"data": {"id": "sub_123", "status": "canceled"}}, request=httpx.Request("POST", "https://test")
        )
        with patch.object(client._http, "request", new_callable=AsyncMock, return_value=mock_response) as mock_req:
            await client.cancel_subscription("sub_123", {"effective_from": "immediately"})
            args, _ = mock_req.call_args
            assert "cancel" in args[1]

    @pytest.mark.asyncio
    async def test_list_transactions_with_dates(self, client: PaddleClient) -> None:
        mock_response = httpx.Response(200, json={"data": [], "meta": {}}, request=httpx.Request("GET", "https://test"))
        with patch.object(client._http, "request", new_callable=AsyncMock, return_value=mock_response) as mock_req:
            await client.list_transactions(created_after="2026-01-01", created_before="2026-03-31")
            _, kwargs = mock_req.call_args
            assert kwargs["params"]["created_at[GT]"] == "2026-01-01"
            assert kwargs["params"]["created_at[LT]"] == "2026-03-31"

    @pytest.mark.asyncio
    async def test_delete_payment_method(self, client: PaddleClient) -> None:
        mock_response = httpx.Response(204, request=httpx.Request("DELETE", "https://test"))
        with patch.object(client._http, "request", new_callable=AsyncMock, return_value=mock_response) as mock_req:
            await client.delete_payment_method("ctm_123", "paymtd_456")
            args, _ = mock_req.call_args
            assert args[0] == "DELETE"
            assert "paymtd_456" in args[1]


# ---------------------------------------------------------------------------
# Webhook verification
# ---------------------------------------------------------------------------


class TestWebhookVerification:
    def _sign(self, body: str, secret: str, ts: str = "1234567890") -> str:
        signed_payload = f"{ts}:{body}"
        h1 = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
        return f"ts={ts};h1={h1}"

    def test_valid_signature(self) -> None:
        body = json.dumps(
            {
                "event_type": "subscription.created",
                "event_id": "evt_123",
                "occurred_at": "2026-03-15T14:30:00Z",
                "data": {"id": "sub_abc"},
            }
        )
        secret = "whsec_test_secret_123"
        sig = self._sign(body, secret)
        result = PaddleClient.verify_webhook_signature(body, sig, secret)
        assert result["valid"] is True
        assert result["event_type"] == "subscription.created"

    def test_invalid_signature(self) -> None:
        body = '{"event_type": "test"}'
        result = PaddleClient.verify_webhook_signature(body, "ts=123;h1=invalid", "secret")
        assert result["valid"] is False
        assert "mismatch" in result.get("error", "").lower()

    def test_malformed_header(self) -> None:
        result = PaddleClient.verify_webhook_signature("{}", "garbage", "secret")
        assert result["valid"] is False

    def test_missing_ts(self) -> None:
        result = PaddleClient.verify_webhook_signature("{}", "h1=abc", "secret")
        assert result["valid"] is False
