"""Tests for formatters.py — token-efficient output formatting."""

from __future__ import annotations

from paddle_billing_blade_mcp.formatters import (
    format_adjustment_list,
    format_billing_cycle,
    format_billing_period,
    format_credit_balance,
    format_customer_detail,
    format_customer_list,
    format_date,
    format_datetime,
    format_discount_detail,
    format_discount_list,
    format_event_detail,
    format_event_list,
    format_ip_addresses,
    format_notification_list,
    format_pagination,
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
    select_fields,
)
from tests.conftest import (
    SAMPLE_CUSTOMER,
    SAMPLE_PRICE,
    SAMPLE_PRODUCT,
    SAMPLE_SUBSCRIPTION,
    SAMPLE_TRANSACTION,
    make_list_response,
)

# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


class TestDateHelpers:
    def test_format_datetime(self) -> None:
        assert format_datetime("2026-03-15T14:30:00Z") == "2026-03-15 14:30"

    def test_format_datetime_none(self) -> None:
        assert format_datetime(None) == "?"

    def test_format_datetime_with_offset(self) -> None:
        assert format_datetime("2026-03-15T14:30:00+00:00") == "2026-03-15 14:30"

    def test_format_date(self) -> None:
        assert format_date("2026-03-15T14:30:00Z") == "2026-03-15"

    def test_format_date_none(self) -> None:
        assert format_date(None) == "?"

    def test_format_billing_cycle_monthly(self) -> None:
        assert format_billing_cycle({"interval": "month", "frequency": 1}) == "monthly"

    def test_format_billing_cycle_yearly(self) -> None:
        assert format_billing_cycle({"interval": "year", "frequency": 1}) == "yearly"

    def test_format_billing_cycle_quarterly(self) -> None:
        assert format_billing_cycle({"interval": "month", "frequency": 3}) == "every 3 months"

    def test_format_billing_cycle_none(self) -> None:
        assert format_billing_cycle(None) == "one-time"

    def test_format_billing_period(self) -> None:
        result = format_billing_period(
            {
                "starts_at": "2026-03-01T00:00:00Z",
                "ends_at": "2026-03-31T23:59:59Z",
            }
        )
        assert result == "2026-03-01 to 2026-03-31"

    def test_format_billing_period_none(self) -> None:
        assert format_billing_period(None) == "?"


# ---------------------------------------------------------------------------
# Field selection
# ---------------------------------------------------------------------------


class TestSelectFields:
    def test_returns_all_when_none(self) -> None:
        data = {"id": "1", "name": "test", "status": "active"}
        assert select_fields(data, None) == data

    def test_filters_to_requested(self) -> None:
        data = {"id": "1", "name": "test", "status": "active", "extra": "x"}
        result = select_fields(data, "name,status")
        assert result == {"id": "1", "name": "test", "status": "active"}

    def test_always_includes_id(self) -> None:
        data = {"id": "1", "name": "test"}
        result = select_fields(data, "name")
        assert "id" in result

    def test_handles_whitespace(self) -> None:
        data = {"id": "1", "name": "test", "status": "active"}
        result = select_fields(data, " name , status ")
        assert "name" in result
        assert "status" in result


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class TestPagination:
    def test_has_more_with_cursor(self) -> None:
        meta = {
            "pagination": {
                "has_more": True,
                "estimated_total": 50,
                "next": "https://api.paddle.com/products?after=pro_xyz",
            }
        }
        result = format_pagination(meta, 20)
        assert "30 more" in result
        assert 'after="pro_xyz"' in result

    def test_no_more(self) -> None:
        meta = {"pagination": {"has_more": False, "estimated_total": 5}}
        assert format_pagination(meta, 5) == ""

    def test_none_meta(self) -> None:
        assert format_pagination(None, 0) == ""


# ---------------------------------------------------------------------------
# List formatters
# ---------------------------------------------------------------------------


class TestProductList:
    def test_formats_products(self) -> None:
        resp = make_list_response([SAMPLE_PRODUCT])
        result = format_product_list(resp)
        assert "pro_abc123" in result
        assert "Pro Plan" in result
        assert "active" in result

    def test_empty(self) -> None:
        assert format_product_list({"data": []}) == "No products found."

    def test_pagination_hint(self) -> None:
        resp = make_list_response([SAMPLE_PRODUCT], has_more=True)
        result = format_product_list(resp)
        assert "more" in result


class TestPriceList:
    def test_formats_prices(self) -> None:
        resp = make_list_response([SAMPLE_PRICE])
        result = format_price_list(resp)
        assert "pri_abc123" in result
        assert "$29.00 USD" in result
        assert "monthly" in result

    def test_empty(self) -> None:
        assert format_price_list({"data": []}) == "No prices found."


class TestCustomerList:
    def test_formats_customers(self) -> None:
        resp = make_list_response([SAMPLE_CUSTOMER])
        result = format_customer_list(resp)
        assert "ctm_abc123" in result
        assert "alice@example.com" in result

    def test_empty(self) -> None:
        assert format_customer_list({"data": []}) == "No customers found."


class TestSubscriptionList:
    def test_formats_subscriptions(self) -> None:
        resp = make_list_response([SAMPLE_SUBSCRIPTION])
        result = format_subscription_list(resp)
        assert "sub_abc123" in result
        assert "active" in result
        assert "$29.00 USD" in result

    def test_empty(self) -> None:
        assert format_subscription_list({"data": []}) == "No subscriptions found."


class TestTransactionList:
    def test_formats_transactions(self) -> None:
        resp = make_list_response([SAMPLE_TRANSACTION])
        result = format_transaction_list(resp)
        assert "txn_abc123" in result
        assert "completed" in result
        assert "$29.00 USD" in result

    def test_empty(self) -> None:
        assert format_transaction_list({"data": []}) == "No transactions found."


class TestAdjustmentList:
    def test_formats(self) -> None:
        adj = {
            "id": "adj_abc123",
            "transaction_id": "txn_def456",
            "action": "refund",
            "totals": {"total": "1000"},
            "currency_code": "USD",
            "status": "approved",
            "created_at": "2026-03-15T10:00:00Z",
        }
        resp = make_list_response([adj])
        result = format_adjustment_list(resp)
        assert "adj_abc123" in result
        assert "refund" in result

    def test_empty(self) -> None:
        assert format_adjustment_list({"data": []}) == "No adjustments found."


class TestDiscountList:
    def test_formats(self) -> None:
        dis = {
            "id": "dis_abc123",
            "description": "20% off",
            "type": "percentage",
            "status": "active",
            "amount": "20",
            "code": "SAVE20",
        }
        resp = make_list_response([dis])
        result = format_discount_list(resp)
        assert "dis_abc123" in result
        assert "20%" in result
        assert "SAVE20" in result

    def test_empty(self) -> None:
        assert format_discount_list({"data": []}) == "No discounts found."


class TestNotificationList:
    def test_formats(self) -> None:
        ntf = {
            "id": "ntf_abc123",
            "type": "subscription.created",
            "status": "delivered",
            "occurred_at": "2026-03-15T14:30:00Z",
        }
        resp = make_list_response([ntf])
        result = format_notification_list(resp)
        assert "ntf_abc123" in result
        assert "subscription.created" in result

    def test_empty(self) -> None:
        assert format_notification_list({"data": []}) == "No notifications found."


class TestEventList:
    def test_formats(self) -> None:
        evt = {
            "event_id": "evt_abc123",
            "event_type": "subscription.activated",
            "occurred_at": "2026-03-15T14:30:00Z",
        }
        resp = make_list_response([evt])
        result = format_event_list(resp)
        assert "evt_abc123" in result
        assert "subscription.activated" in result

    def test_empty(self) -> None:
        assert format_event_list({"data": []}) == "No events found."


class TestPaymentMethodList:
    def test_formats(self) -> None:
        pm = {
            "id": "paymtd_abc123",
            "type": "card",
            "card": {"type": "visa", "last4": "4242", "expiry_month": 12, "expiry_year": 2028},
        }
        resp = make_list_response([pm])
        result = format_payment_method_list(resp)
        assert "paymtd_abc123" in result
        assert "****4242" in result

    def test_empty(self) -> None:
        assert format_payment_method_list({"data": []}) == "No payment methods found."


class TestReportList:
    def test_formats(self) -> None:
        rep = {
            "id": "rep_abc123",
            "type": "transactions",
            "status": "ready",
            "created_at": "2026-03-15T10:00:00Z",
        }
        resp = make_list_response([rep])
        result = format_report_list(resp)
        assert "rep_abc123" in result
        assert "transactions" in result

    def test_empty(self) -> None:
        assert format_report_list({"data": []}) == "No reports found."


class TestSimulationList:
    def test_formats(self) -> None:
        sim = {
            "id": "sim_abc123",
            "type": "subscription_creation",
            "status": "active",
            "notification_setting_id": "ntfset_def456",
        }
        resp = make_list_response([sim])
        result = format_simulation_list(resp)
        assert "sim_abc123" in result
        assert "subscription_creation" in result

    def test_empty(self) -> None:
        assert format_simulation_list({"data": []}) == "No simulations found."


# ---------------------------------------------------------------------------
# Detail formatters
# ---------------------------------------------------------------------------


class TestProductDetail:
    def test_formats(self) -> None:
        result = format_product_detail(SAMPLE_PRODUCT)
        assert "ID: pro_abc123" in result
        assert "Name: Pro Plan" in result
        assert "Status: active" in result

    def test_field_selection(self) -> None:
        result = format_product_detail(SAMPLE_PRODUCT, fields="name,status")
        assert "Name: Pro Plan" in result
        assert "ID: pro_abc123" in result  # id always included
        assert "Description" not in result


class TestPriceDetail:
    def test_formats(self) -> None:
        result = format_price_detail(SAMPLE_PRICE)
        assert "ID: pri_abc123" in result
        assert "$29.00 USD" in result
        assert "monthly" in result


class TestCustomerDetail:
    def test_formats(self) -> None:
        result = format_customer_detail(SAMPLE_CUSTOMER)
        assert "ID: ctm_abc123" in result
        assert "alice@example.com" in result


class TestSubscriptionDetail:
    def test_formats(self) -> None:
        result = format_subscription_detail(SAMPLE_SUBSCRIPTION)
        assert "ID: sub_abc123" in result
        assert "active" in result
        assert "$29.00 USD/month" in result
        assert "Next Billed" in result


class TestTransactionDetail:
    def test_formats(self) -> None:
        result = format_transaction_detail(SAMPLE_TRANSACTION)
        assert "ID: txn_abc123" in result
        assert "Total: $29.00 USD" in result
        assert "Pro Plan" in result


class TestDiscountDetail:
    def test_percentage(self) -> None:
        d = {
            "id": "dis_abc123",
            "description": "20% off",
            "type": "percentage",
            "status": "active",
            "amount": "20",
            "code": "SAVE20",
        }
        result = format_discount_detail(d)
        assert "20%" in result
        assert "SAVE20" in result


# ---------------------------------------------------------------------------
# Special formatters
# ---------------------------------------------------------------------------


class TestCreditBalance:
    def test_formats(self) -> None:
        resp = {
            "data": [
                {
                    "currency_code": "USD",
                    "balance": {"available": "5000", "reserved": "0", "used": "1000"},
                }
            ]
        }
        result = format_credit_balance(resp)
        assert "$50.00 USD" in result
        assert "$10.00 USD" in result

    def test_empty(self) -> None:
        assert format_credit_balance({"data": []}) == "No credit balance."


class TestWebhookVerification:
    def test_valid(self) -> None:
        result = format_webhook_verification(
            {
                "valid": True,
                "event_type": "subscription.created",
                "event_id": "evt_123",
                "occurred_at": "2026-03-15T14:30:00Z",
            }
        )
        assert "Valid webhook" in result
        assert "subscription.created" in result

    def test_invalid(self) -> None:
        result = format_webhook_verification({"valid": False, "error": "Signature mismatch"})
        assert "Invalid webhook" in result
        assert "Signature mismatch" in result


class TestEventDetail:
    def test_formats(self) -> None:
        data = {
            "event_type": "subscription.activated",
            "event_id": "evt_abc123",
            "occurred_at": "2026-03-15T14:30:00Z",
            "data": {"id": "sub_abc123", "status": "active"},
        }
        result = format_event_detail(data)
        assert "subscription.activated" in result
        assert "sub_abc123" in result


class TestIpAddresses:
    def test_formats_dict(self) -> None:
        data = {"data": [{"ipv4_cidr": "34.194.127.46/32"}]}
        result = format_ip_addresses(data)
        assert "34.194.127.46/32" in result

    def test_formats_str(self) -> None:
        data = {"data": ["34.194.127.46/32"]}
        result = format_ip_addresses(data)
        assert "34.194.127.46/32" in result

    def test_empty(self) -> None:
        assert format_ip_addresses({"data": []}) == "No IP addresses returned."
