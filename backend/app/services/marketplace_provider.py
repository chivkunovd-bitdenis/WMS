from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Protocol


class MarketplaceProviderError(Exception):
    def __init__(
        self,
        marketplace: str,
        status_code: int | None,
        payload: Mapping[str, object] | None = None,
        *,
        code: str | None = None,
    ) -> None:
        self.marketplace = marketplace
        self.status_code = status_code
        self.payload = dict(payload or {})
        self.code = code or f"{marketplace}_upstream_error"
        super().__init__(self.code)

    @property
    def is_account_blocked(self) -> bool:
        return (
            self.marketplace == "ozon" and self.status_code == 403 and self.payload.get("code") == 7
        )


def provider_error_message(error: MarketplaceProviderError) -> str:
    if error.is_account_blocked:
        return "Кабинет Ozon заблокирован. Обратитесь в поддержку Ozon."
    if error.marketplace == "ozon":
        if error.status_code in {401, 403}:
            return "Ozon отклонил данные подключения."
        if error.status_code == 429:
            return "Ozon временно ограничил частоту запросов."
        return "Ozon временно недоступен."
    return "Маркетплейс временно недоступен."


@dataclass
class MarketplaceBackoff:
    _blocked_until: dict[str, float] = field(default_factory=dict)

    @staticmethod
    def now() -> float:
        return monotonic()

    def record_rate_limit(self, marketplace: str, *, retry_after_seconds: float) -> None:
        delay = max(0.0, retry_after_seconds)
        self._blocked_until[marketplace] = max(
            self._blocked_until.get(marketplace, 0.0),
            self.now() + delay,
        )

    def remaining_seconds(self, marketplace: str, *, now: float | None = None) -> float:
        current = self.now() if now is None else now
        return max(0.0, self._blocked_until.get(marketplace, 0.0) - current)


class MarketplaceTransport(Protocol):
    async def call(
        self,
        *,
        client_id: str,
        api_key: str,
        path: str,
        payload: Mapping[str, object],
    ) -> object: ...

    async def fetch_orders(self, *, client_id: str, api_key: str) -> list[dict[str, Any]]: ...

    async def fetch_statuses(
        self,
        *,
        client_id: str,
        api_key: str,
        order_ids: Sequence[str],
    ) -> list[dict[str, Any]]: ...

    async def fetch_order_labels(
        self,
        *,
        client_id: str,
        api_key: str,
        posting_numbers: Sequence[str],
    ) -> list[dict[str, Any]]: ...

    async def publish_stocks(
        self,
        *,
        client_id: str,
        api_key: str,
        stocks: Sequence[Mapping[str, object]],
    ) -> None: ...

    async def dispatch_unload(
        self,
        *,
        client_id: str,
        api_key: str,
        document_id: str,
    ) -> None: ...

    async def create_supply(
        self,
        *,
        client_id: str,
        api_key: str,
        name: str,
        posting_numbers: Sequence[str],
    ) -> dict[str, Any]: ...

    async def deliver_supply(
        self,
        *,
        client_id: str,
        api_key: str,
        supply_id: str,
    ) -> None: ...

    async def fetch_supply_qr(
        self,
        *,
        client_id: str,
        api_key: str,
        supply_id: str,
    ) -> bytes: ...


@dataclass
class FakeMarketplaceTransport:
    orders: list[dict[str, Any]] = field(default_factory=list)
    statuses: list[dict[str, Any]] = field(default_factory=list)
    order_labels: list[dict[str, Any]] = field(default_factory=list)
    created_supply_id: str = "ozon-fake-supply"
    supply_qr: bytes = b""
    errors: dict[str, MarketplaceProviderError] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)
    endpoint_responses: dict[str, object] = field(default_factory=dict)
    endpoint_response_queues: dict[str, list[object]] = field(default_factory=dict)
    endpoint_calls: list[tuple[str, dict[str, object]]] = field(default_factory=list)
    published_stocks: list[dict[str, object]] = field(default_factory=list)

    async def call(
        self,
        *,
        client_id: str,
        api_key: str,
        path: str,
        payload: Mapping[str, object],
    ) -> object:
        _ = client_id, api_key
        self.endpoint_calls.append((path, dict(payload)))
        if error := self.errors.get(path):
            raise error
        queue = self.endpoint_response_queues.get(path)
        if queue:
            value = queue.pop(0)
            if isinstance(value, MarketplaceProviderError):
                raise value
            return value
        return self.endpoint_responses.get(path, {})

    async def fetch_orders(self, *, client_id: str, api_key: str) -> list[dict[str, Any]]:
        _ = api_key
        self.calls.append(("fetch_orders", client_id))
        if error := self.errors.get("fetch_orders"):
            raise error
        return list(self.orders)

    async def fetch_statuses(
        self,
        *,
        client_id: str,
        api_key: str,
        order_ids: Sequence[str],
    ) -> list[dict[str, Any]]:
        _ = api_key, order_ids
        self.calls.append(("fetch_statuses", client_id))
        if error := self.errors.get("fetch_statuses"):
            raise error
        return list(self.statuses)

    async def publish_stocks(
        self,
        *,
        client_id: str,
        api_key: str,
        stocks: Sequence[Mapping[str, object]],
    ) -> None:
        _ = api_key
        self.calls.append(("publish_stocks", client_id))
        self.published_stocks.extend(dict(stock) for stock in stocks)
        if error := self.errors.get("publish_stocks"):
            raise error

    async def dispatch_unload(
        self,
        *,
        client_id: str,
        api_key: str,
        document_id: str,
    ) -> None:
        _ = client_id, api_key
        self.calls.append(("dispatch_unload", document_id))
        if error := self.errors.get("dispatch_unload"):
            raise error

    async def fetch_order_labels(
        self,
        *,
        client_id: str,
        api_key: str,
        posting_numbers: Sequence[str],
    ) -> list[dict[str, Any]]:
        _ = api_key, posting_numbers
        self.calls.append(("fetch_order_labels", client_id))
        if error := self.errors.get("fetch_order_labels"):
            raise error
        return list(self.order_labels)

    async def create_supply(
        self,
        *,
        client_id: str,
        api_key: str,
        name: str,
        posting_numbers: Sequence[str],
    ) -> dict[str, Any]:
        _ = api_key, name, posting_numbers
        self.calls.append(("create_supply", client_id))
        if error := self.errors.get("create_supply"):
            raise error
        return {"id": self.created_supply_id}

    async def deliver_supply(
        self,
        *,
        client_id: str,
        api_key: str,
        supply_id: str,
    ) -> None:
        _ = api_key
        self.calls.append(("deliver_supply", supply_id))
        if error := self.errors.get("deliver_supply"):
            raise error

    async def fetch_supply_qr(
        self,
        *,
        client_id: str,
        api_key: str,
        supply_id: str,
    ) -> bytes:
        _ = api_key
        self.calls.append(("fetch_supply_qr", supply_id))
        if error := self.errors.get("fetch_supply_qr"):
            raise error
        return self.supply_qr


class OzonMarketplaceProvider:
    marketplace = "ozon"

    def __init__(self, *, transport: MarketplaceTransport) -> None:
        self.transport = transport
        self._blocked_error: MarketplaceProviderError | None = None

    def _raise_if_blocked(self) -> None:
        if self._blocked_error is not None:
            raise self._blocked_error

    def _remember_blocked(self, error: MarketplaceProviderError) -> None:
        if error.is_account_blocked:
            self._blocked_error = error

    async def call(
        self,
        *,
        client_id: str,
        api_key: str,
        path: str,
        payload: Mapping[str, object],
    ) -> object:
        """Call one typed Seller API operation through the provider boundary.

        Mutations are deliberately never retried here. Read retry policy belongs
        to the Ozon FBS process service, where the operation semantics are known.
        """
        self._raise_if_blocked()
        try:
            return await self.transport.call(
                client_id=client_id,
                api_key=api_key,
                path=path,
                payload=payload,
            )
        except MarketplaceProviderError as error:
            self._remember_blocked(error)
            raise

    async def fetch_orders(self, *, client_id: str, api_key: str) -> list[dict[str, Any]]:
        self._raise_if_blocked()
        try:
            return await self.transport.fetch_orders(client_id=client_id, api_key=api_key)
        except MarketplaceProviderError as error:
            self._remember_blocked(error)
            raise

    async def fetch_statuses(
        self,
        *,
        client_id: str,
        api_key: str,
        order_ids: Sequence[str],
    ) -> list[dict[str, Any]]:
        self._raise_if_blocked()
        try:
            return await self.transport.fetch_statuses(
                client_id=client_id,
                api_key=api_key,
                order_ids=order_ids,
            )
        except MarketplaceProviderError as error:
            self._remember_blocked(error)
            raise

    async def publish_stocks(
        self,
        *,
        client_id: str,
        api_key: str,
        stocks: Sequence[Mapping[str, object]],
    ) -> None:
        self._raise_if_blocked()
        try:
            await self.transport.publish_stocks(
                client_id=client_id,
                api_key=api_key,
                stocks=stocks,
            )
        except MarketplaceProviderError as error:
            self._remember_blocked(error)
            raise

    async def dispatch_unload(
        self,
        *,
        client_id: str,
        api_key: str,
        document_id: str,
    ) -> None:
        self._raise_if_blocked()
        try:
            await self.transport.dispatch_unload(
                client_id=client_id,
                api_key=api_key,
                document_id=document_id,
            )
        except MarketplaceProviderError as error:
            self._remember_blocked(error)
            raise

    async def fetch_order_labels(
        self,
        *,
        client_id: str,
        api_key: str,
        posting_numbers: Sequence[str],
    ) -> list[dict[str, Any]]:
        self._raise_if_blocked()
        try:
            return await self.transport.fetch_order_labels(
                client_id=client_id,
                api_key=api_key,
                posting_numbers=posting_numbers,
            )
        except MarketplaceProviderError as error:
            self._remember_blocked(error)
            raise

    async def create_supply(
        self,
        *,
        client_id: str,
        api_key: str,
        name: str,
        posting_numbers: Sequence[str],
    ) -> dict[str, Any]:
        self._raise_if_blocked()
        try:
            return await self.transport.create_supply(
                client_id=client_id,
                api_key=api_key,
                name=name,
                posting_numbers=posting_numbers,
            )
        except MarketplaceProviderError as error:
            self._remember_blocked(error)
            raise

    async def deliver_supply(
        self,
        *,
        client_id: str,
        api_key: str,
        supply_id: str,
    ) -> None:
        self._raise_if_blocked()
        try:
            await self.transport.deliver_supply(
                client_id=client_id,
                api_key=api_key,
                supply_id=supply_id,
            )
        except MarketplaceProviderError as error:
            self._remember_blocked(error)
            raise

    async def fetch_supply_qr(
        self,
        *,
        client_id: str,
        api_key: str,
        supply_id: str,
    ) -> bytes:
        self._raise_if_blocked()
        try:
            return await self.transport.fetch_supply_qr(
                client_id=client_id,
                api_key=api_key,
                supply_id=supply_id,
            )
        except MarketplaceProviderError as error:
            self._remember_blocked(error)
            raise


class WildberriesMarketplaceProvider:
    """Thin dispatch boundary; existing WB functions remain the implementation."""

    marketplace = "wb"

    def __init__(
        self,
        *,
        fetch_orders: Callable[..., Awaitable[list[dict[str, Any]]]],
        fetch_statuses: Callable[..., Awaitable[list[dict[str, Any]]]],
        publish_stocks: Callable[..., Awaitable[None]],
    ) -> None:
        self.fetch_orders = fetch_orders
        self.fetch_statuses = fetch_statuses
        self.publish_stocks = publish_stocks
