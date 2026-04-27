"""Paddle Billing API client.

Async wrapper over ``httpx.AsyncClient`` with typed exceptions,
error classification, and credential scrubbing. No SDK dependency —
direct REST API calls for full control over response shaping.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Any

import httpx

from paddle_billing_blade_mcp.models import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    scrub_secrets,
    validate_environment,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PaddleError(Exception):
    """Base exception for Paddle client errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AuthError(PaddleError):
    """Authentication failed — invalid or expired API key."""


class NotFoundError(PaddleError):
    """Requested resource not found."""


class RateLimitError(PaddleError):
    """Rate limit exceeded — back off and retry."""


class ValidationError(PaddleError):
    """Request validation failed — invalid parameters."""


class ConflictError(PaddleError):
    """Conflict — e.g., concurrent modification or duplicate operation."""


class ConnectionError(PaddleError):  # noqa: A001
    """Cannot connect to Paddle API."""


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

_STATUS_TO_ERROR: dict[int, type[PaddleError]] = {
    401: AuthError,
    403: AuthError,
    404: NotFoundError,
    409: ConflictError,
    422: ValidationError,
    429: RateLimitError,
}


def _classify_http_error(status_code: int, body: dict[str, Any]) -> PaddleError:
    """Map HTTP status code and response body to a typed exception."""
    error_data = body.get("error", {})
    detail = error_data.get("detail", "")
    code = error_data.get("code", "")
    message = scrub_secrets(f"{code}: {detail}" if code else detail or f"HTTP {status_code}")

    exc_cls = _STATUS_TO_ERROR.get(status_code, PaddleError)
    return exc_cls(message, status_code=status_code)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class PaddleClient:
    """Async Paddle Billing API client.

    Uses ``httpx.AsyncClient`` for direct REST API access. All methods are
    async — no thread wrapping needed.

    Args:
        api_key: Paddle API key. Defaults to ``PADDLE_API_KEY`` env var.
        environment: "sandbox" or "production". Defaults to ``PADDLE_ENVIRONMENT`` env var.
    """

    def __init__(
        self,
        api_key: str | None = None,
        environment: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("PADDLE_API_KEY", "").strip()
        if not self._api_key:
            raise AuthError("PADDLE_API_KEY environment variable is required.")

        if environment:
            os.environ["PADDLE_ENVIRONMENT"] = environment
        self._base_url = validate_environment()
        self._env_name = os.environ.get("PADDLE_ENVIRONMENT", "").strip().lower()

        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "X-Paddle-Client": "paddle-billing-blade-mcp",
                "X-Paddle-Client-Version": "0.1.0",
            },
            timeout=30.0,
        )

    @property
    def environment(self) -> str:
        """Current environment name."""
        return self._env_name

    # ------------------------------------------------------------------
    # Core HTTP methods
    # ------------------------------------------------------------------

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Execute an HTTP request with error handling and credential scrubbing."""
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.ConnectError as e:
            raise ConnectionError(scrub_secrets(str(e))) from e
        except httpx.TimeoutException as e:
            raise ConnectionError(f"Request timed out: {scrub_secrets(str(e))}") from e
        except httpx.HTTPError as e:
            raise PaddleError(scrub_secrets(str(e))) from e

        if response.status_code == 204:
            return {}

        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError):
            if response.is_success:
                return {"raw": response.text}
            raise PaddleError(f"HTTP {response.status_code}: non-JSON response", status_code=response.status_code)

        if not response.is_success:
            raise _classify_http_error(response.status_code, body)

        return body  # type: ignore[no-any-return]

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET request with optional query parameters."""
        # Filter out None values from params
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        return await self._request("GET", path, params=clean_params)

    async def _post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """POST request with optional JSON body."""
        clean_body = {k: v for k, v in (body or {}).items() if v is not None}
        return await self._request("POST", path, json=clean_body)

    async def _patch(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """PATCH request with optional JSON body."""
        clean_body = {k: v for k, v in (body or {}).items() if v is not None}
        return await self._request("PATCH", path, json=clean_body)

    async def _delete(self, path: str) -> dict[str, Any]:
        """DELETE request."""
        return await self._request("DELETE", path)

    def _paginate_params(self, limit: int, after: str | None) -> dict[str, Any]:
        """Build pagination query parameters."""
        params: dict[str, Any] = {"per_page": min(limit, MAX_LIMIT)}
        if after:
            params["after"] = after
        return params

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    async def list_products(
        self,
        status: str | None = None,
        tax_category: str | None = None,
        include: str | None = None,
        limit: int = DEFAULT_LIMIT,
        after: str | None = None,
    ) -> dict[str, Any]:
        """List products."""
        params = self._paginate_params(limit, after)
        if status:
            params["status"] = status
        if tax_category:
            params["tax_category"] = tax_category
        if include:
            params["include"] = include
        return await self._get("/products", params)

    async def get_product(self, product_id: str, include: str | None = None) -> dict[str, Any]:
        """Get a product by ID."""
        params: dict[str, Any] = {}
        if include:
            params["include"] = include
        return await self._get(f"/products/{product_id}", params or None)

    async def create_product(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create a product."""
        return await self._post("/products", body)

    async def update_product(self, product_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Update a product."""
        return await self._patch(f"/products/{product_id}", body)

    # ------------------------------------------------------------------
    # Prices
    # ------------------------------------------------------------------

    async def list_prices(
        self,
        product_id: str | None = None,
        status: str | None = None,
        include: str | None = None,
        limit: int = DEFAULT_LIMIT,
        after: str | None = None,
    ) -> dict[str, Any]:
        """List prices."""
        params = self._paginate_params(limit, after)
        if product_id:
            params["product_id"] = product_id
        if status:
            params["status"] = status
        if include:
            params["include"] = include
        return await self._get("/prices", params)

    async def get_price(self, price_id: str, include: str | None = None) -> dict[str, Any]:
        """Get a price by ID."""
        params: dict[str, Any] = {}
        if include:
            params["include"] = include
        return await self._get(f"/prices/{price_id}", params or None)

    async def create_price(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create a price."""
        return await self._post("/prices", body)

    async def update_price(self, price_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Update a price."""
        return await self._patch(f"/prices/{price_id}", body)

    # ------------------------------------------------------------------
    # Customers
    # ------------------------------------------------------------------

    async def list_customers(
        self,
        status: str | None = None,
        search: str | None = None,
        limit: int = DEFAULT_LIMIT,
        after: str | None = None,
    ) -> dict[str, Any]:
        """List/search customers."""
        params = self._paginate_params(limit, after)
        if status:
            params["status"] = status
        if search:
            params["search"] = search
        return await self._get("/customers", params)

    async def get_customer(self, customer_id: str) -> dict[str, Any]:
        """Get a customer by ID."""
        return await self._get(f"/customers/{customer_id}")

    async def create_customer(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create a customer."""
        return await self._post("/customers", body)

    async def update_customer(self, customer_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Update a customer."""
        return await self._patch(f"/customers/{customer_id}", body)

    async def get_credit_balance(self, customer_id: str) -> dict[str, Any]:
        """Get customer credit balance."""
        return await self._get(f"/customers/{customer_id}/credit-balances")

    async def create_portal_session(self, customer_id: str) -> dict[str, Any]:
        """Create a customer portal session."""
        return await self._post(f"/customers/{customer_id}/portal-sessions")

    # ------------------------------------------------------------------
    # Addresses
    # ------------------------------------------------------------------

    async def list_addresses(
        self, customer_id: str, limit: int = DEFAULT_LIMIT, after: str | None = None
    ) -> dict[str, Any]:
        """List customer addresses."""
        params = self._paginate_params(limit, after)
        return await self._get(f"/customers/{customer_id}/addresses", params)

    async def get_address(self, customer_id: str, address_id: str) -> dict[str, Any]:
        """Get a customer address."""
        return await self._get(f"/customers/{customer_id}/addresses/{address_id}")

    async def create_address(self, customer_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Create a customer address."""
        return await self._post(f"/customers/{customer_id}/addresses", body)

    async def update_address(self, customer_id: str, address_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Update a customer address."""
        return await self._patch(f"/customers/{customer_id}/addresses/{address_id}", body)

    # ------------------------------------------------------------------
    # Businesses
    # ------------------------------------------------------------------

    async def list_businesses(
        self, customer_id: str, limit: int = DEFAULT_LIMIT, after: str | None = None
    ) -> dict[str, Any]:
        """List customer businesses."""
        params = self._paginate_params(limit, after)
        return await self._get(f"/customers/{customer_id}/businesses", params)

    async def get_business(self, customer_id: str, business_id: str) -> dict[str, Any]:
        """Get a customer business."""
        return await self._get(f"/customers/{customer_id}/businesses/{business_id}")

    async def create_business(self, customer_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Create a customer business."""
        return await self._post(f"/customers/{customer_id}/businesses", body)

    async def update_business(self, customer_id: str, business_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Update a customer business."""
        return await self._patch(f"/customers/{customer_id}/businesses/{business_id}", body)

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    async def list_subscriptions(
        self,
        status: str | None = None,
        customer_id: str | None = None,
        price_id: str | None = None,
        limit: int = DEFAULT_LIMIT,
        after: str | None = None,
    ) -> dict[str, Any]:
        """List subscriptions."""
        params = self._paginate_params(limit, after)
        if status:
            params["status"] = status
        if customer_id:
            params["customer_id"] = customer_id
        if price_id:
            params["price_id"] = price_id
        return await self._get("/subscriptions", params)

    async def get_subscription(self, subscription_id: str, include: str | None = None) -> dict[str, Any]:
        """Get a subscription by ID."""
        params: dict[str, Any] = {}
        if include:
            params["include"] = include
        return await self._get(f"/subscriptions/{subscription_id}", params or None)

    async def update_subscription(self, subscription_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Update a subscription."""
        return await self._patch(f"/subscriptions/{subscription_id}", body)

    async def preview_subscription_update(self, subscription_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Preview a subscription update (no persistence)."""
        return await self._patch(f"/subscriptions/{subscription_id}/preview", body)

    async def activate_subscription(self, subscription_id: str) -> dict[str, Any]:
        """Activate a trialing subscription."""
        return await self._post(f"/subscriptions/{subscription_id}/activate")

    async def pause_subscription(self, subscription_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Pause a subscription."""
        return await self._post(f"/subscriptions/{subscription_id}/pause", body)

    async def resume_subscription(self, subscription_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Resume a paused subscription."""
        return await self._post(f"/subscriptions/{subscription_id}/resume", body)

    async def cancel_subscription(self, subscription_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Cancel a subscription."""
        return await self._post(f"/subscriptions/{subscription_id}/cancel", body)

    async def charge_subscription(self, subscription_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Create a one-time charge on a subscription."""
        return await self._post(f"/subscriptions/{subscription_id}/charge", body)

    async def preview_subscription_charge(self, subscription_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Preview a one-time subscription charge (no persistence)."""
        return await self._post(f"/subscriptions/{subscription_id}/charge/preview", body)

    # ------------------------------------------------------------------
    # Transactions
    # ------------------------------------------------------------------

    async def list_transactions(
        self,
        status: str | None = None,
        customer_id: str | None = None,
        subscription_id: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        include: str | None = None,
        limit: int = DEFAULT_LIMIT,
        after: str | None = None,
    ) -> dict[str, Any]:
        """List transactions."""
        params = self._paginate_params(limit, after)
        if status:
            params["status"] = status
        if customer_id:
            params["customer_id"] = customer_id
        if subscription_id:
            params["subscription_id"] = subscription_id
        if created_after:
            params["created_at[GT]"] = created_after
        if created_before:
            params["created_at[LT]"] = created_before
        if include:
            params["include"] = include
        return await self._get("/transactions", params)

    async def get_transaction(self, transaction_id: str, include: str | None = None) -> dict[str, Any]:
        """Get a transaction by ID."""
        params: dict[str, Any] = {}
        if include:
            params["include"] = include
        return await self._get(f"/transactions/{transaction_id}", params or None)

    async def create_transaction(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create a transaction."""
        return await self._post("/transactions", body)

    async def preview_transaction(self, body: dict[str, Any]) -> dict[str, Any]:
        """Preview a transaction (no persistence)."""
        return await self._post("/transactions/preview", body)

    async def get_invoice_pdf(self, transaction_id: str) -> dict[str, Any]:
        """Get invoice PDF download URL for a transaction."""
        return await self._get(f"/transactions/{transaction_id}/invoice")

    # ------------------------------------------------------------------
    # Adjustments
    # ------------------------------------------------------------------

    async def list_adjustments(
        self,
        transaction_id: str | None = None,
        action: str | None = None,
        limit: int = DEFAULT_LIMIT,
        after: str | None = None,
    ) -> dict[str, Any]:
        """List adjustments."""
        params = self._paginate_params(limit, after)
        if transaction_id:
            params["transaction_id"] = transaction_id
        if action:
            params["action"] = action
        return await self._get("/adjustments", params)

    async def get_adjustment(self, adjustment_id: str) -> dict[str, Any]:
        """Fetch a single adjustment by ID via the list endpoint with id filter.

        Paddle's API does not expose ``GET /adjustments/{id}``; the canonical
        path is to list with the ``id`` query parameter and unwrap the first
        result. The shape returned matches a single-item list response.
        """
        return await self._get("/adjustments", {"id": adjustment_id})

    async def create_adjustment(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create an adjustment (refund/credit/chargeback)."""
        return await self._post("/adjustments", body)

    # ------------------------------------------------------------------
    # Discounts
    # ------------------------------------------------------------------

    async def list_discounts(
        self,
        status: str | None = None,
        limit: int = DEFAULT_LIMIT,
        after: str | None = None,
    ) -> dict[str, Any]:
        """List discounts."""
        params = self._paginate_params(limit, after)
        if status:
            params["status"] = status
        return await self._get("/discounts", params)

    async def get_discount(self, discount_id: str) -> dict[str, Any]:
        """Get a discount by ID."""
        return await self._get(f"/discounts/{discount_id}")

    async def create_discount(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create a discount."""
        return await self._post("/discounts", body)

    async def update_discount(self, discount_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Update a discount."""
        return await self._patch(f"/discounts/{discount_id}", body)

    # ------------------------------------------------------------------
    # Payment Methods
    # ------------------------------------------------------------------

    async def list_payment_methods(
        self, customer_id: str, limit: int = DEFAULT_LIMIT, after: str | None = None
    ) -> dict[str, Any]:
        """List customer payment methods."""
        params = self._paginate_params(limit, after)
        return await self._get(f"/customers/{customer_id}/payment-methods", params)

    async def delete_payment_method(self, customer_id: str, payment_method_id: str) -> dict[str, Any]:
        """Delete a customer payment method."""
        return await self._delete(f"/customers/{customer_id}/payment-methods/{payment_method_id}")

    # ------------------------------------------------------------------
    # Notification Settings
    # ------------------------------------------------------------------

    async def list_notification_settings(self, limit: int = DEFAULT_LIMIT, after: str | None = None) -> dict[str, Any]:
        """List notification settings."""
        params = self._paginate_params(limit, after)
        return await self._get("/notification-settings", params)

    async def get_notification_setting(self, setting_id: str) -> dict[str, Any]:
        """Get a notification setting."""
        return await self._get(f"/notification-settings/{setting_id}")

    async def create_notification_setting(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create a notification setting."""
        return await self._post("/notification-settings", body)

    async def update_notification_setting(self, setting_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Update a notification setting."""
        return await self._patch(f"/notification-settings/{setting_id}", body)

    async def delete_notification_setting(self, setting_id: str) -> dict[str, Any]:
        """Delete a notification setting."""
        return await self._delete(f"/notification-settings/{setting_id}")

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    async def list_notifications(
        self,
        notification_setting_id: str | None = None,
        status: str | None = None,
        limit: int = DEFAULT_LIMIT,
        after: str | None = None,
    ) -> dict[str, Any]:
        """List notifications."""
        params = self._paginate_params(limit, after)
        if notification_setting_id:
            params["notification_setting_id"] = notification_setting_id
        if status:
            params["status"] = status
        return await self._get("/notifications", params)

    async def get_notification(self, notification_id: str) -> dict[str, Any]:
        """Get a notification by ID."""
        return await self._get(f"/notifications/{notification_id}")

    async def get_notification_logs(self, notification_id: str) -> dict[str, Any]:
        """Get delivery logs for a notification."""
        return await self._get(f"/notifications/{notification_id}/logs")

    async def replay_notification(self, notification_id: str) -> dict[str, Any]:
        """Replay a notification."""
        return await self._post(f"/notifications/{notification_id}/replay")

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def list_events(self, limit: int = DEFAULT_LIMIT, after: str | None = None) -> dict[str, Any]:
        """List events."""
        params = self._paginate_params(limit, after)
        return await self._get("/events", params)

    async def list_event_types(self) -> dict[str, Any]:
        """List all available event types."""
        return await self._get("/event-types")

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    async def list_reports(self, limit: int = DEFAULT_LIMIT, after: str | None = None) -> dict[str, Any]:
        """List reports."""
        params = self._paginate_params(limit, after)
        return await self._get("/reports", params)

    async def get_report(self, report_id: str) -> dict[str, Any]:
        """Get a report by ID."""
        return await self._get(f"/reports/{report_id}")

    async def create_report(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create a report."""
        return await self._post("/reports", body)

    async def get_report_csv(self, report_id: str) -> dict[str, Any]:
        """Get CSV download URL for a report."""
        return await self._get(f"/reports/{report_id}/download-url")

    # ------------------------------------------------------------------
    # Simulations
    # ------------------------------------------------------------------

    async def list_simulations(self, limit: int = DEFAULT_LIMIT, after: str | None = None) -> dict[str, Any]:
        """List simulations."""
        params = self._paginate_params(limit, after)
        return await self._get("/simulations", params)

    async def get_simulation(self, simulation_id: str) -> dict[str, Any]:
        """Get a simulation by ID."""
        return await self._get(f"/simulations/{simulation_id}")

    async def create_simulation(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create a simulation."""
        return await self._post("/simulations", body)

    async def run_simulation(self, simulation_id: str) -> dict[str, Any]:
        """Run a simulation."""
        return await self._post(f"/simulations/{simulation_id}/runs")

    # ------------------------------------------------------------------
    # IP Addresses
    # ------------------------------------------------------------------

    async def list_ip_addresses(self) -> dict[str, Any]:
        """Get Paddle IP addresses for webhook allowlisting."""
        return await self._get("/ips")

    # ------------------------------------------------------------------
    # Webhook Verification
    # ------------------------------------------------------------------

    @staticmethod
    def verify_webhook_signature(
        raw_body: str,
        signature_header: str,
        webhook_secret: str,
    ) -> dict[str, Any]:
        """Verify a Paddle webhook HMAC-SHA256 signature and parse the event.

        The Paddle-Signature header format is: ts=timestamp;h1=hash

        Returns:
            Dict with 'valid' bool and parsed event data if valid.
        """
        try:
            # Parse signature header: ts=1234;h1=abc123
            parts = dict(part.split("=", 1) for part in signature_header.split(";"))
            ts = parts.get("ts", "")
            h1 = parts.get("h1", "")

            if not ts or not h1:
                return {"valid": False, "error": "Invalid signature header format"}

            # Compute expected signature: HMAC-SHA256(secret, ts:body)
            signed_payload = f"{ts}:{raw_body}"
            expected = hmac.new(
                webhook_secret.encode("utf-8"),
                signed_payload.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(expected, h1):
                return {"valid": False, "error": "Signature mismatch"}

            # Parse and return event data
            event = json.loads(raw_body)
            return {
                "valid": True,
                "event_type": event.get("event_type"),
                "event_id": event.get("event_id"),
                "occurred_at": event.get("occurred_at"),
                "data": event.get("data"),
            }
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            return {"valid": False, "error": scrub_secrets(str(e))}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()
