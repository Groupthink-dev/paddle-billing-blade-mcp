"""Tests for server.py — MCP tool integration tests with mocked client."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

# We need to import the module to reset _client between tests
import paddle_billing_blade_mcp.server as server_module
from paddle_billing_blade_mcp.server import (
    paddle_adjustments,
    paddle_create_product,
    paddle_customer,
    paddle_customer_credit,
    paddle_customers,
    paddle_delete_payment_method,
    paddle_discount,
    paddle_discounts,
    paddle_events,
    paddle_info,
    paddle_invoice_pdf,
    paddle_ip_addresses,
    paddle_notification_settings,
    paddle_notifications,
    paddle_parse_event,
    paddle_payment_methods,
    paddle_product,
    paddle_products,
    paddle_reports,
    paddle_simulations,
    paddle_subscription,
    paddle_subscription_lifecycle,
    paddle_subscriptions,
    paddle_transaction,
    paddle_transactions,
    paddle_update_product,
)
from tests.conftest import (
    SAMPLE_CUSTOMER,
    SAMPLE_PRODUCT,
    SAMPLE_SUBSCRIPTION,
    SAMPLE_TRANSACTION,
    make_detail_response,
    make_list_response,
)


@pytest.fixture(autouse=True)
def _reset_client() -> None:
    """Reset the lazy client singleton between tests."""
    server_module._client = None


@pytest.fixture
def mock_client(sandbox_env: None) -> AsyncMock:
    """Provide a mocked PaddleClient and patch _get_client to return it."""
    mock = AsyncMock()
    mock.environment = "sandbox"

    async def fake_get_client() -> AsyncMock:
        return mock

    patcher = patch("paddle_billing_blade_mcp.server._get_client", side_effect=fake_get_client)
    patcher.start()
    yield mock
    patcher.stop()


# ---------------------------------------------------------------------------
# Meta tools
# ---------------------------------------------------------------------------


class TestMetaTools:
    @pytest.mark.asyncio
    async def test_paddle_info(self, mock_client: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
        result = await paddle_info()
        assert "sandbox" in result
        assert "connected" in result

    @pytest.mark.asyncio
    async def test_paddle_ip_addresses(self, mock_client: AsyncMock) -> None:
        mock_client.list_ip_addresses.return_value = {"data": [{"ipv4_cidr": "1.2.3.4/32"}]}
        result = await paddle_ip_addresses()
        assert "1.2.3.4/32" in result


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


class TestProductTools:
    @pytest.mark.asyncio
    async def test_list_products(self, mock_client: AsyncMock) -> None:
        mock_client.list_products.return_value = make_list_response([SAMPLE_PRODUCT])
        result = await paddle_products()
        assert "pro_abc123" in result
        assert "Pro Plan" in result

    @pytest.mark.asyncio
    async def test_get_product(self, mock_client: AsyncMock) -> None:
        mock_client.get_product.return_value = make_detail_response(SAMPLE_PRODUCT)
        result = await paddle_product(product_id="pro_abc123")
        assert "Pro Plan" in result

    @pytest.mark.asyncio
    async def test_create_product_blocked(self, mock_client: AsyncMock) -> None:
        result = await paddle_create_product(name="Test", tax_category="standard")
        assert "disabled" in result

    @pytest.mark.asyncio
    async def test_create_product_allowed(self, mock_client: AsyncMock, write_env: None) -> None:
        mock_client.create_product.return_value = make_detail_response(SAMPLE_PRODUCT)
        result = await paddle_create_product(name="Pro Plan", tax_category="standard")
        assert "Pro Plan" in result

    @pytest.mark.asyncio
    async def test_update_product_blocked(self, mock_client: AsyncMock) -> None:
        result = await paddle_update_product(product_id="pro_123", name="New Name")
        assert "disabled" in result


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------


class TestCustomerTools:
    @pytest.mark.asyncio
    async def test_list_customers(self, mock_client: AsyncMock) -> None:
        mock_client.list_customers.return_value = make_list_response([SAMPLE_CUSTOMER])
        result = await paddle_customers()
        assert "ctm_abc123" in result

    @pytest.mark.asyncio
    async def test_get_customer(self, mock_client: AsyncMock) -> None:
        mock_client.get_customer.return_value = make_detail_response(SAMPLE_CUSTOMER)
        result = await paddle_customer(customer_id="ctm_abc123")
        assert "alice@example.com" in result

    @pytest.mark.asyncio
    async def test_customer_credit(self, mock_client: AsyncMock) -> None:
        mock_client.get_credit_balance.return_value = {
            "data": [{"currency_code": "USD", "balance": {"available": "5000", "reserved": "0", "used": "0"}}]
        }
        result = await paddle_customer_credit(customer_id="ctm_abc123")
        assert "$50.00 USD" in result


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------


class TestSubscriptionTools:
    @pytest.mark.asyncio
    async def test_list_subscriptions(self, mock_client: AsyncMock) -> None:
        mock_client.list_subscriptions.return_value = make_list_response([SAMPLE_SUBSCRIPTION])
        result = await paddle_subscriptions()
        assert "sub_abc123" in result

    @pytest.mark.asyncio
    async def test_get_subscription(self, mock_client: AsyncMock) -> None:
        mock_client.get_subscription.return_value = make_detail_response(SAMPLE_SUBSCRIPTION)
        result = await paddle_subscription(subscription_id="sub_abc123")
        assert "sub_abc123" in result
        assert "active" in result

    @pytest.mark.asyncio
    async def test_cancel_requires_write(self, mock_client: AsyncMock) -> None:
        result = await paddle_subscription_lifecycle(subscription_id="sub_123", action="cancel", confirm=True)
        assert "disabled" in result

    @pytest.mark.asyncio
    async def test_cancel_requires_confirm(self, mock_client: AsyncMock, write_env: None) -> None:
        result = await paddle_subscription_lifecycle(subscription_id="sub_123", action="cancel", confirm=False)
        assert "confirm=true" in result

    @pytest.mark.asyncio
    async def test_cancel_succeeds(self, mock_client: AsyncMock, write_env: None) -> None:
        mock_client.cancel_subscription.return_value = make_detail_response({"id": "sub_123", "status": "canceled"})
        result = await paddle_subscription_lifecycle(subscription_id="sub_123", action="cancel", confirm=True)
        assert "cancel" in result.lower()

    @pytest.mark.asyncio
    async def test_pause_no_confirm_needed(self, mock_client: AsyncMock, write_env: None) -> None:
        mock_client.pause_subscription.return_value = make_detail_response({"id": "sub_123", "status": "paused"})
        result = await paddle_subscription_lifecycle(subscription_id="sub_123", action="pause")
        assert "pause" in result.lower()


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------


class TestTransactionTools:
    @pytest.mark.asyncio
    async def test_list_transactions(self, mock_client: AsyncMock) -> None:
        mock_client.list_transactions.return_value = make_list_response([SAMPLE_TRANSACTION])
        result = await paddle_transactions()
        assert "txn_abc123" in result

    @pytest.mark.asyncio
    async def test_get_transaction(self, mock_client: AsyncMock) -> None:
        mock_client.get_transaction.return_value = make_detail_response(SAMPLE_TRANSACTION)
        result = await paddle_transaction(transaction_id="txn_abc123")
        assert "txn_abc123" in result

    @pytest.mark.asyncio
    async def test_invoice_pdf(self, mock_client: AsyncMock) -> None:
        mock_client.get_invoice_pdf.return_value = {"data": {"url": "https://paddle.com/invoice.pdf"}}
        result = await paddle_invoice_pdf(transaction_id="txn_abc123")
        assert "invoice.pdf" in result


# ---------------------------------------------------------------------------
# Adjustments & Discounts
# ---------------------------------------------------------------------------


class TestAdjustmentDiscountTools:
    @pytest.mark.asyncio
    async def test_list_adjustments(self, mock_client: AsyncMock) -> None:
        mock_client.list_adjustments.return_value = make_list_response([])
        result = await paddle_adjustments()
        assert "No adjustments" in result

    @pytest.mark.asyncio
    async def test_list_discounts(self, mock_client: AsyncMock) -> None:
        mock_client.list_discounts.return_value = make_list_response([])
        result = await paddle_discounts()
        assert "No discounts" in result

    @pytest.mark.asyncio
    async def test_get_discount(self, mock_client: AsyncMock) -> None:
        mock_client.get_discount.return_value = make_detail_response(
            {
                "id": "dis_123",
                "description": "20% off",
                "type": "percentage",
                "status": "active",
                "amount": "20",
            }
        )
        result = await paddle_discount(discount_id="dis_123")
        assert "20%" in result


# ---------------------------------------------------------------------------
# Payment methods
# ---------------------------------------------------------------------------


class TestPaymentMethodTools:
    @pytest.mark.asyncio
    async def test_list_payment_methods(self, mock_client: AsyncMock) -> None:
        mock_client.list_payment_methods.return_value = make_list_response([])
        result = await paddle_payment_methods(customer_id="ctm_123")
        assert "No payment methods" in result

    @pytest.mark.asyncio
    async def test_delete_requires_write(self, mock_client: AsyncMock) -> None:
        result = await paddle_delete_payment_method(customer_id="ctm_123", payment_method_id="paymtd_456", confirm=True)
        assert "disabled" in result

    @pytest.mark.asyncio
    async def test_delete_requires_confirm(self, mock_client: AsyncMock, write_env: None) -> None:
        result = await paddle_delete_payment_method(
            customer_id="ctm_123", payment_method_id="paymtd_456", confirm=False
        )
        assert "confirm=true" in result


# ---------------------------------------------------------------------------
# Notifications & Events
# ---------------------------------------------------------------------------


class TestNotificationEventTools:
    @pytest.mark.asyncio
    async def test_list_notifications(self, mock_client: AsyncMock) -> None:
        mock_client.list_notifications.return_value = make_list_response([])
        result = await paddle_notifications()
        assert "No notifications" in result

    @pytest.mark.asyncio
    async def test_list_events(self, mock_client: AsyncMock) -> None:
        mock_client.list_events.return_value = make_list_response([])
        result = await paddle_events()
        assert "No events" in result

    @pytest.mark.asyncio
    async def test_list_notification_settings(self, mock_client: AsyncMock) -> None:
        mock_client.list_notification_settings.return_value = make_list_response([])
        result = await paddle_notification_settings()
        assert "No notification settings" in result


# ---------------------------------------------------------------------------
# Reports & Simulations
# ---------------------------------------------------------------------------


class TestReportSimulationTools:
    @pytest.mark.asyncio
    async def test_list_reports(self, mock_client: AsyncMock) -> None:
        mock_client.list_reports.return_value = make_list_response([])
        result = await paddle_reports()
        assert "No reports" in result

    @pytest.mark.asyncio
    async def test_list_simulations(self, mock_client: AsyncMock) -> None:
        mock_client.list_simulations.return_value = make_list_response([])
        result = await paddle_simulations()
        assert "No simulations" in result


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


class TestWebhookTools:
    @pytest.mark.asyncio
    async def test_parse_event(self, mock_client: AsyncMock) -> None:
        payload = json.dumps(
            {
                "event_type": "subscription.created",
                "event_id": "evt_abc",
                "occurred_at": "2026-03-15T14:30:00Z",
                "data": {"id": "sub_123", "status": "active"},
            }
        )
        result = await paddle_parse_event(body=payload)
        assert "subscription.created" in result
