# Промпты для Codex — по одному за раз

> Порядок строгий. Следующий промпт даём **только** после моего ревью предыдущего.
> Ветка одна на всю задачу: `feat/fbs-kiz-manual-binding`.
> `frontend/` не трогаем ни в одной задаче — окно и кнопку делает владелец сам.

Общая шапка (Codex её уже знает из `AGENTS.md`, но повторяем в каждом промпте):

```
Проект: /Users/deniscivkunov/Projects/WMS  (единственная копия, на Десктопе работать запрещено)
Ветка: feat/fbs-kiz-manual-binding (создай от etalon, если её нет)
Слои backend не смешивать: роуты — app/api, логика — app/services, модели — app/models.
Гейт перед коммитом: cd backend && ruff check . && mypy . && pytest
Коммит маленький и связный, только по своей задаче. Несвязанный рефакторинг не тащить.
frontend/ не трогать вообще.
```

---

## KIZ-01 · Миграция

```
Прочитай tasks/fbs-kiz-manual-binding/TASK.md целиком, дальше работай по §4.1–4.3.

Сделай одну alembic-миграцию и правки моделей:

1. backend/app/models/fbs_order.py, FbsOrderMarking — добавь:
   - tenant_id: FK tenants.id, NOT NULL, index. В миграции backfill из fbs_orders по order_id,
     затем set NOT NULL.
   - source: String(16), NOT NULL, server_default 'operator'
   - created_by_user_id: FK users.id, nullable, ondelete SET NULL
   - created_at: timestamptz, server_default now(), NOT NULL
2. Партиальный уникальный индекс:
   CREATE UNIQUE INDEX uq_fbs_order_markings_tenant_kind_value
     ON fbs_order_markings (tenant_id, kind, value)
     WHERE meta_status <> 'rejected';
   В alembic — op.create_index(..., postgresql_where=...). Существующий
   uq_fbs_order_markings_order_kind_value не трогай.
3. backend/app/models/marking_code.py, MarkingCode — source: String(16), NOT NULL,
   server_default 'pool'.
4. backend/app/models/packaging_task.py, PackagingTaskLine — qty_marking_external: Integer,
   NOT NULL, default 0, server_default '0'.

Требования:
- downgrade должен полностью откатывать (индекс, колонки).
- Прогони upgrade и downgrade на тестовой БД, приложи вывод в отчёт.
- Логику нигде не меняй — это чисто схема.

Готово, когда: гейт зелёный, upgrade/downgrade прошли, коммит один.
```

---

## KIZ-02 · Поиск заказа по стикеру

```
Зависит от KIZ-01. Работай по tasks/fbs-kiz-manual-binding/TASK.md §5.1.

Создай backend/app/services/fbs_kiz_service.py и backend/app/api/fbs_kiz.py.
Роутер подключи в app/main.py рядом с fbs_marking.

GET /operations/fbs-orders/kiz/lookup?supply_id={uuid}&sticker={raw}
Доступ: require_fbs_operator_access (как в app/api/fbs_marking.py).

Матч стикера ТОЛЕРАНТНЫЙ, по очереди, первое совпадение выигрывает:
  1) FbsOrder.sticker_code
  2) FbsOrder.wb_barcode
  3) склейка partA+partB, если она хранится
Входную строку перед матчем чистим: strip, убрать пробелы, \r, \n, ﻿.
Ищем ТОЛЬКО среди заказов переданной поставки — стикер из другой поставки считается ненайденным.

Ответ 200:
{ order_id, wb_order_id,
  product: { name, image_url, barcode, seller_article },
  current_kiz: { masked, meta_status, from_pool } | null,
  needs_confirmation: bool,   # true если current_kiz != null
  can_bind: bool, block_reason: string|null }
masked — последние 6 символов кода с многоточием впереди.
from_pool — у связанного MarkingCode source == 'pool'.

Ошибки: 404 sticker_not_found; 409 order_frozen (статусы бери из
FBS_ORDER_MARKING_FROZEN_STATUSES / FBS_ORDER_MARKING_WRITE_STATUSES в fbs_marking_service).
Конверт ошибки — как в fbs_marking.py через envelope_from_exc.

Тесты: backend/tests/test_fbs_kiz.py — матч по каждому из трёх полей, мусорная строка → 404,
стикер чужой поставки → 404, замороженный заказ → 409, заказ с существующим КИЗ →
needs_confirmation=true.

Готово, когда: гейт зелёный, эндпоинт в openapi, тесты покрывают перечисленное.
```

---

## KIZ-02a · Нормализация скана

```
Зависит от KIZ-02. Работай по tasks/fbs-kiz-manual-binding/TASK.md §5.5.
Правь только backend/app/services/fbs_kiz_service.py и тесты.

Контекст: мы мультиарендные, у каждого ФФ свой сканер и свои настройки. Нельзя предполагать
ничего про железо. Поэтому клиент шлёт строку как есть, а чинит её сервер — одинаково для веба
и будущего ТСД.

Сделай normalize_scanned_cis(raw: str) -> tuple[str, list[str]] (значение, hints):

1. Срезать AIM-префиксы символики в начале: ]d2, ]d1, ]Q1, ]Q3, ]C1 → hint "aim_prefix".
2. Восстановить разделитель GS (\x1d): часть сканеров не умеет его печатать и подставляет
   ~ | # либо литералы <GS> {GS} \x1d. Приводить к \x1d → hint "gs_substitute".
   ВАЖНО: заменяй только в позициях, где по GS1 ожидается разделитель (после полей переменной
   длины), а не любое вхождение символа — в крипто-хвосте эти символы легитимны.
3. Починить раскладку: если строка содержит кириллицу, применить обратное отображение
   ЙЦУКЕН→QWERTY (детерминированная таблица, включая знаки препинания и цифровой ряд)
   → hint "keyboard_layout". Если после починки строка перестала быть похожа на КИЗ —
   вернуть исходную и не ставить hint.
4. Срезать хвостовые \r \n и пробелы.

Плюс is_probably_cis(value) -> bool: строка начинается с AI 01 + 14 цифр, содержит AI 21,
длина в разумных границах. Используется вызывающей стороной для ошибки not_a_kiz.

Плюс scan_debug(raw) -> dict: длина, первые и последние 8 символов, невидимые символы
показаны как <GS>. Нужен, чтобы по телефону понять, что за сканер у ФФ.

Тесты: по одному на каждую строку таблицы из §5.5 плюс комбинация «кириллица + подставленный GS
одновременно». Чистый корректный КИЗ должен проходить без единого hint.

Готово, когда: гейт зелёный.
```

---

## KIZ-03 · Валидация пары без сохранения

```
Зависит от KIZ-02. Работай по §5.2. Правь только fbs_kiz_service.py и fbs_kiz.py.

POST /operations/fbs-orders/kiz/validate, body { order_id, value }.
Проверяет и НИЧЕГО не пишет в БД:
  - заказ существует, не заморожен → иначе 409 order_frozen
  - значение непустое после нормализации (preserve_scan_raw_value из fbs_marking_service)
  - код не привязан к другому заказу: ищем в fbs_order_markings по (tenant_id, kind='sgtin', value)
    среди строк с meta_status <> 'rejected' → 409 duplicate_kiz с context
    { wb_order_id, created_at } того заказа
  - код не занят в пуле: MarkingCode по (tenant_id, cis_code) со статусом, отличным от available
    → тоже duplicate_kiz
200 { ok: true }

Тест обязателен: после вызова validate количество строк в fbs_order_markings и marking_codes
не изменилось.

Готово, когда: гейт зелёный, тесты на дубль/заморозку/чистый случай есть.
```

---

## KIZ-04 · Проведение пачки

```
Зависит от KIZ-03. Работай по §5.3. Правь только fbs_kiz_service.py и fbs_kiz.py.

POST /operations/fbs-orders/kiz/commit
body { pairs: [{ order_id, value, confirmed: bool }], idempotency_key }
200 [ { order_id, status: "ok"|"error", code, message } ]  — построчно, порядок как во входе.

КАЖДАЯ пара обрабатывается в своей транзакции: падение одной не откатывает остальные.

Алгоритм по паре:
1. Перепроверки из KIZ-03.
2. Если у заказа уже есть маркировка kind='sgtin' и confirmed != true →
   status="error", code="needs_confirmation", ничего не пишем.
3. Если confirmed=true и старая маркировка есть — погасить её той же процедурой, что в KIZ-05
   (вынеси в общую функцию, не дублируй).
4. Создать MarkingCode: source='external_fbs', status='applied', applied_at=now,
   seller_id и product_id из заказа, packaging_task_line_id — строка упаковки по этому товару
   в задании упаковки поставки, cis_code = значение. pool_id, import_batch_id,
   label_artifact_pdf = NULL.
5. record_event(..., event_type='applied') с оператором и номером документа задания.
6. Создать FbsOrderMarking: source='operator', created_by_user_id, marking_code_id.
7. Отправить в WB и синхронизировать статусы — ПЕРЕИСПОЛЬЗУЙ логику
   scan_order_metadata из fbs_marking_service (put_marketplace_order_meta, обработка
   WildberriesBusinessError → meta_validation_fail, _sync_order_meta_from_wb). Не пиши заново.
8. Инкремент PackagingTaskLine.qty_marking_external на 1.

Тесты: три пары, WB отклоняет вторую → первая и третья сохранены, вторая вернула
meta_validation_fail; повтор без confirmed на заказе с КИЗ → needs_confirmation и БД не тронута;
успешная пара → проверить обе созданные записи, событие и счётчик.

Готово, когда: гейт зелёный, тест частичного успеха есть.
```

---

## KIZ-05 · Отмена КИЗ

```
Зависит от KIZ-04. Работай по §5.4. Правь только fbs_kiz_service.py и fbs_kiz.py.

DELETE /operations/fbs-orders/{order_id}/kiz

Порядок строгий:
1. Проверить, что заказ не заморожен → иначе 409 order_frozen.
2. delete_marketplace_order_meta (backend/app/services/wildberries_fbs_client.py:554),
   key='sgtin'. Если WB вернул ошибку — НИЧЕГО не менять, вернуть 502 wb_*.
3. Удалить строку fbs_order_markings.
4. Связанный MarkingCode: status='void', событие 'voided' с причиной
   «отмена оператором» (или «заменён внешним КИЗ», если вызвано из KIZ-04).
5. Счётчики: если гасим код с source='external_fbs' — qty_marking_external -= 1 (не ниже нуля).
   Если гасим код из пула (source='pool') — qty_marking_printed НЕ трогаем, этикетка физически
   напечатана, это расход.

Тест обязателен: WB отвечает ошибкой → ни одна запись не изменилась.

Готово, когда: гейт зелёный.
```

---

## KIZ-06 · Принцип «печатаем только ненапечатанное»

```
Зависит от KIZ-01. Работай по tasks/fbs-kiz-manual-binding/TASK.md §1.4 и §4.2/§4.4.
Это самая важная задача в наборе — читай §1.4 внимательно.

Смысл: отсканированный чужой КИЗ должен закрывать заказ ровно так же, как напечатанный из пула.

Три правки:

1. backend/app/services/marking_code_service.py, assert_packaging_line_marking_done (~:2159):
   сравнивать qty_marking_printed + qty_marking_external с qty_done(line).
2. backend/app/services/marking_code_service.py, _lines_needing_marking и все места, где
   считается остаток к печати (print_codes_for_packaging_line, превью печать-всего,
   _preview_all_lines_print): remaining = qty_need_pack(line) - qty_marking_printed
   - qty_marking_external. Найди ВСЕ такие места, их несколько.
3. backend/app/services/fbs_marking_service.py, build_order_metadata (~:308): в каждый элемент
   states добавь "source": mark.source (для отсутствующей маркировки — None). Фронт по этому полю
   отличает КИЗ, внесённый оператором, от напечатанного нами.
4. backend/app/services/fbs_workspace_service.py, _build_marking_pool (~:442): из needing_orders
   исключить заказы, у которых уже есть маркировка kind='sgtin' с meta_status <> 'rejected'.
   Иначе плашка «не хватает Честных знаков» и orders_without_code врут.

Обязательный тест — сценарий целиком:
  строка упаковки на 150 шт одного товара; 100 заказов получили внешний КИЗ
  (qty_marking_external=100); печать-всего должна выдать 50; после ручной печати 10 —
  следующая печать-всего выдаёт 40; assert_packaging_line_marking_done не срабатывает;
  _build_marking_pool возвращает shortage=0 при 50 доступных кодах в пуле.

Готово, когда: гейт зелёный, сценарий покрыт одним тестом.
```

---

## KIZ-07 · Аудит выборок пула

```
Зависит от KIZ-04 и KIZ-06. Работай по §4.3.

Внешние коды теперь живут в marking_codes с source='external_fbs' и статусом 'applied'.
Проверь, что они не искажают отчётность пула.

1. Найди ВСЕ выборки MarkingCode, которые показывают инвентарь, остатки, разбивку по статусам
   или ленту расхода: marking_code_service.py (_pool_status_counts, инвентарь, ledger),
   app/api/marking_codes.py, marking_low_stock_service.py.
2. Для каждой определи: искажает её внешний код или нет. Выборки, фильтрующие
   status == available, безопасны — обоснуй это явно, не правь.
3. Там, где искажает, добавь фильтр source == 'pool'.
4. В отчёт — таблица «файл:строка → вердикт (безопасно / поправлено)». Ничего не правь без
   обоснования: цель не «добавить фильтр везде», а не сломать существующие цифры.

Готово, когда: гейт зелёный, отчёт со списком в описании коммита.
```
