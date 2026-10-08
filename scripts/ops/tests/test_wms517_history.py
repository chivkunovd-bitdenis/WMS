"""Focused owner-requested archive checks; only vendor I/O is simulated."""

import json
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from app.services import wb_sales_report as sales


class ArchiveTests(unittest.IsolatedAsyncioTestCase):
    def finance(self, **changes):
        row = dict(
            srid="owned",
            rrdId=100,
            sellerOperName="Продажа",
            docTypeName="Продажа",
            quantity=1,
            retailAmount="1093.12",
            currency="RUB",
            nmId=1,
            sku="abc",
            saleDt=(datetime.now(UTC) - timedelta(days=120)).isoformat(),
        )
        return row | changes

    async def read(self, finance=None, operational=None, age=180):
        self.requests = []
        finance = [[self.finance()], 204] if finance is None else list(finance)
        operational = [] if operational is None else operational
        now = datetime.now(UTC)
        order = sales.SalesOrder(uuid.uuid4(), "owned", now - timedelta(days=age))
        count = 0

        def handle(request):
            nonlocal count
            self.requests.append(request)
            if request.url.path == sales.SALES_SOURCE:
                value = operational if count == 0 else []
                count += 1
            else:
                self.assertEqual(request.url.path, sales.FINANCE_SOURCE)
                self.assertEqual(request.method, "POST")
                value = finance.pop(0)
            if isinstance(value, int):
                return httpx.Response(value)
            return httpx.Response(200, json=value)

        client = httpx.AsyncClient
        with (
            patch.object(
                sales.httpx,
                "AsyncClient",
                side_effect=lambda **kw: client(
                    transport=httpx.MockTransport(handle), **kw
                ),
            ),
            patch.object(
                sales,
                "get_decrypted_marketplace_token",
                AsyncMock(return_value="fixture"),
            ),
            patch.object(sales, "_wait_slot", AsyncMock()),
            patch.object(sales.settings, "celery_broker_url", None),
            patch.object(sales.settings, "withdrawal_environment", "sandbox"),
        ):
            return await sales.read_sales_report(
                SimpleNamespace(commit=AsyncMock()),
                tenant_id=uuid.uuid4(),
                seller_id=uuid.uuid4(),
                orders=[order],
            )

    async def test_old_sale_all_pages_and_exact_amount(self):
        report = await self.read()
        self.assertEqual(sales.sale_cost(report.by_rid["owned"]), 109312)
        self.assertFalse(report.coverage_missing)
        bodies = [json.loads(r.content) for r in self.requests if r.method == "POST"]
        self.assertEqual([b["rrdId"] for b in bodies], [0, 100])
        self.assertLess(
            bodies[0]["dateFrom"],
            (datetime.now(UTC) - timedelta(days=90)).date().isoformat(),
        )
        evidence = report.evidence(SimpleNamespace(id=uuid.uuid4(), wb_rid="owned"))
        self.assertEqual(evidence["source"], sales.FINANCE_SOURCE)
        self.assertEqual(evidence["price_field"], "retailAmount")
        self.assertEqual(evidence["raw_sale"]["retailAmount"], "1093.12")

    async def test_financial_return_excludes_sale(self):
        r = await self.read(
            finance=[
                [
                    self.finance(),
                    self.finance(
                        rrdId=101, sellerOperName="Возврат", docTypeName="Возврат"
                    ),
                ],
                204,
            ]
        )
        self.assertFalse(r.by_rid)
        self.assertFalse(r.coverage_missing)

    async def test_recent_return_excludes_archive_sale(self):
        row = dict(
            srid="owned",
            saleID="R1",
            date=datetime.now(UTC).isoformat(),
            lastChangeDate=datetime.now(UTC).isoformat(),
        )
        self.assertFalse((await self.read(operational=[row])).by_rid)

    async def test_foreign_rows_and_fees_do_not_authorize(self):
        r = await self.read(
            finance=[
                [
                    self.finance(srid="foreign"),
                    self.finance(rrdId=101, sellerOperName="Доставка"),
                ],
                204,
            ]
        )
        self.assertFalse(r.by_rid)

    async def test_unavailable_archive_not_empty_success(self):
        with self.assertRaisesRegex(sales.WbSalesError, "history_incomplete_http_403"):
            await self.read(finance=[403])

    async def test_failed_second_page_not_partial_success(self):
        with self.assertRaisesRegex(sales.WbSalesError, "history_incomplete_http_500"):
            await self.read(finance=[[self.finance()], 500])

    async def test_stalled_cursor_fails(self):
        with self.assertRaisesRegex(sales.WbSalesError, "stalled_cursor"):
            await self.read(finance=[[self.finance()], [self.finance()]])

    async def test_ambiguous_sales_do_not_authorize(self):
        r = await self.read(finance=[[self.finance(), self.finance(rrdId=101)], 204])
        self.assertFalse(r.by_rid)

    async def test_wrong_quantity_price_is_not_invented(self):
        r = await self.read(finance=[[self.finance(quantity=2)], 204])
        with self.assertRaises(sales.WbPriceDataError):
            sales.sale_cost(r.by_rid["owned"])

    async def test_recent_orders_do_not_require_finance_permission(self):
        r = await self.read(age=20)
        self.assertFalse(r.by_rid)
        self.assertTrue(all(q.method == "GET" for q in self.requests))

    async def test_no_sale_after_archive_start_is_not_coverage_error(self):
        r = await self.read(finance=[204])
        self.assertFalse(r.coverage_missing)
        self.assertFalse(r.by_rid)

    async def test_missing_pre2024_history_is_not_called_complete(self):
        r = await self.read(finance=[204], age=2000)
        self.assertTrue(r.coverage_missing)
        body = json.loads([q for q in self.requests if q.method == "POST"][0].content)
        self.assertEqual(body["dateFrom"], "2024-01-29")


if __name__ == "__main__":
    unittest.main()
