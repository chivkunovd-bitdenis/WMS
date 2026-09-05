"""Одна точка, где решается: провайдер Ozon боевой или локальный.

До этого модуля выбор транспорта был размазан по десяти местам, и все десять
жёстко создавали ``FakeMarketplaceTransport``. Переключить модуль на живые
вызовы конфигом было нельзя в принципе — только правкой кода в десяти файлах.

Теперь решение принимается здесь и ровно по одному признаку — настройке
``ozon_live_api_enabled``. Пока она выключена (умолчание), поведение системы
не меняется ни на шаг: те же фейки, те же ошибки, те же тесты. Как только её
включат, все десять точек уходят в кабинет одновременно, а не по одной.

Аргумент ``blocked_operation`` сохраняет прежнюю локальную семантику: в
автоопросе и в отгрузке фейк намеренно отвечает «403, код 7» на конкретной
операции, чтобы локальный путь не выглядел успешным. Это поведение остаётся
в точности прежним при выключенном флаге.
"""

from __future__ import annotations

from app.core.settings import settings
from app.services.marketplace_provider import (
    FakeMarketplaceTransport,
    MarketplaceProviderError,
    MarketplaceTransport,
    OzonMarketplaceProvider,
)
from app.services.ozon_marketplace_transport import HttpxOzonMarketplaceTransport


def ozon_live_api_enabled() -> bool:
    return bool(settings.ozon_live_api_enabled)


def build_ozon_transport(*, blocked_operation: str | None = None) -> MarketplaceTransport:
    if ozon_live_api_enabled():
        return HttpxOzonMarketplaceTransport()
    if blocked_operation is None:
        return FakeMarketplaceTransport()
    return FakeMarketplaceTransport(
        errors={blocked_operation: MarketplaceProviderError("ozon", 403, {"code": 7})}
    )


def build_ozon_provider(*, blocked_operation: str | None = None) -> OzonMarketplaceProvider:
    """Return the provider every Ozon call site should use instead of building its own."""
    return OzonMarketplaceProvider(
        transport=build_ozon_transport(blocked_operation=blocked_operation)
    )
