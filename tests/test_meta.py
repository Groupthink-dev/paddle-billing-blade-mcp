"""CONV-29 ``_meta`` audit-tail envelope tests (S-AUD-001).

Every successful tool return carries the canonical ``_meta: {...}`` JSON tail;
gate / error returns do not.
"""

from __future__ import annotations

import json
import re
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

import paddle_billing_blade_mcp.server as server_module
from paddle_billing_blade_mcp.server import (
    paddle_create_product,
    paddle_ip_addresses,
    paddle_products,
)
from tests.conftest import SAMPLE_PRODUCT, make_detail_response, make_list_response

_META_RE = re.compile(r"\n\n_meta: (\{.*\})\s*$", re.DOTALL)


def _split_meta(out: str) -> tuple[str, dict[str, Any]]:
    """Split a tool output into (payload, parsed_meta_json). Asserts presence."""
    m = _META_RE.search(out)
    assert m is not None, f"expected a _meta tail, got: {out!r}"
    return out[: m.start()], json.loads(m.group(1))


def _assert_no_meta(out: str) -> None:
    assert _META_RE.search(out) is None, f"did not expect a _meta tail, got: {out!r}"


@pytest.fixture(autouse=True)
def _reset_client() -> None:
    server_module._client = None


@pytest.fixture
def mock_client(sandbox_env: None) -> AsyncMock:
    mock = AsyncMock()
    mock.environment = "sandbox"

    async def fake_get_client() -> AsyncMock:
        return mock

    patcher = patch("paddle_billing_blade_mcp.server._get_client", side_effect=fake_get_client)
    patcher.start()
    yield mock
    patcher.stop()


class TestMetaPresence:
    @pytest.mark.asyncio
    async def test_read_list_carries_meta(self, mock_client: AsyncMock) -> None:
        mock_client.list_products.return_value = make_list_response([SAMPLE_PRODUCT])
        payload, meta = _split_meta(await paddle_products())
        assert "pro_abc123" in payload
        assert meta["matched_total"] == 1
        assert meta["returned"] == 1

    @pytest.mark.asyncio
    async def test_read_ip_addresses_carries_meta(self, mock_client: AsyncMock) -> None:
        mock_client.list_ip_addresses.return_value = {"data": {"ipv4_cidrs": ["1.2.3.4/32", "5.6.7.8/32"]}}
        _, meta = _split_meta(await paddle_ip_addresses())
        assert meta["matched_total"] == 2

    @pytest.mark.asyncio
    async def test_write_success_carries_meta_with_target(self, mock_client: AsyncMock, write_env: None) -> None:
        mock_client.create_product.return_value = make_detail_response(SAMPLE_PRODUCT)
        _, meta = _split_meta(await paddle_create_product(name="Pro Plan", tax_category="standard"))
        assert meta["target_id"] == "pro_abc123"
        assert meta["rows_affected"] == 1


class TestMetaAbsence:
    @pytest.mark.asyncio
    async def test_write_gate_has_no_meta(self, mock_client: AsyncMock) -> None:
        # Writes disabled -> gate refusal, no meta tail.
        _assert_no_meta(await paddle_create_product(name="X", tax_category="standard"))
