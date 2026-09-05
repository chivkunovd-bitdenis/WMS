"""Форма запросов и ответов Ozon: то, что сломалось бы на живом кабинете.

Проверено 03.09.2026 боевым ключом кабинета «ИП Горячкина Т.И.»: девять
читающих методов приняли ровно то тело, которое строит наш код, и наши модели
разобрали их ответы целиком. Здесь закреплены два места, где до этой проверки
код не работал бы вовсе, — оба нашлись только потому, что запрос собирали
нашими же моделями, а не руками.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.schemas import ozon_fbs_api as api

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def test_new_orders_request_can_be_built_with_a_real_date() -> None:
    """Запрос новых заказов Ozon обязан собираться настоящей датой.

    В спеке Ozon `cutoff_from`/`cutoff_to` объявлены шаблоном
    " YYYY-MM-DDThh:mm:ss.mcsZ" — это подсказка человеку, а не регулярное
    выражение. Скопированная в модель буквально, она делала поле непроходимым:
    вызов «забрать новые заказы» падал бы валидацией ещё до выхода в сеть.
    """
    request = api.OzonPostingV4PostingFbsUnfulfilledListRequest(
        limit=100,
        filter=api.OzonPostingV4PostingFbsUnfulfilledListRequestFilter(
            cutoff_from=(NOW - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            cutoff_to=NOW.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        ),
    )
    # Сериализуем ровно так, как боевой код: ozon_fbs_process_service._payload.
    body = request.model_dump(by_alias=True, exclude_none=True)
    assert body["filter"]["cutoff_from"].startswith("2026-09-02T")
    assert body["limit"] == 100


def test_posting_list_request_can_be_built_with_a_real_date() -> None:
    request = api.OzonPostingV4PostingFbsListRequest(
        limit=100,
        filter=api.OzonPostingV4PostingFbsListRequestFilter(
            since=(NOW - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            to=NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        ),
    )
    body = request.model_dump(by_alias=True, exclude_none=True)
    assert body["filter"]["to"] == "2026-09-03T12:00:00Z"


def test_posting_with_scheduled_tariff_change_is_parsed() -> None:
    """Ответ с плановой сменой тарифа не должен ронять разбор всего списка.

    Тот же шаблон стоял и в модели ответа. Одно поле `next_tariff_starts_at` с
    настоящей датой отвергало весь ответ целиком — со всеми отправлениями в нём.
    """
    parsed = api.OzonPostingV4PostingFbsUnfulfilledListResponse.model_validate(
        {
            "count": 1,
            "has_next": False,
            "cursor": "",
            "postings": [
                {
                    "posting_number": "12345-0001-1",
                    "tariffication": {
                        "current_tariff_rate": 5,
                        "next_tariff_starts_at": "2026-09-10T00:00:00Z",
                    },
                }
            ],
        }
    )
    assert parsed.postings[0].tariffication.next_tariff_starts_at == "2026-09-10T00:00:00Z"
