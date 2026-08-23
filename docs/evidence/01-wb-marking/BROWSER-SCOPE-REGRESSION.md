# 01-wb-marking — browser scope regression

Проверяемый commit: `5c3b0dd8d4fa7b3b894f896999604de0f39b4e5e`.

Карточка не меняет интерфейс. Проверка подтверждает, что существующие экраны FBS открываются на локальном стенде без новых элементов, колонок или действий.

## Автоматическая проверка

- `frontend/tests-e2e/wb-marking-stand.spec.ts`: `1 passed` (`13.2s`).
- ESLint для stand-теста: PASS.
- Local Docker stand: API `/health` — `ok`, FF web — HTTP 200.
- S-03 `/app/ff/fbs`: корневой элемент `fbs-orders-screen` видим.
- S-14 `/app/ff/packaging`: корневой элемент `ff-packaging-page` видим.
- S-15 `/app/ff/packaging/pending-marking`: корневой элемент `ff-pending-marking-page` видим.
- В commit `5c3b0dd8` нет изменений `frontend/src`; добавлен только stand-тест.

## Инварианты геометрии

- S-14: PASS, нарушений 0.
- S-15: PASS, нарушений 0.
- S-03: одно ранее существовавшее нарушение R-32 — кнопки в одном ряду имеют высоту `34/40`. Карточка 01 не меняет этот экран и не должна расширять scope ради чужой геометрии.

## Независимое ревью

Sol-review: PASS, findings 0. Возвращать backend в разработку не требуется. Ревью подтвердило fail-closed обработку неполного ответа WB, сохранность привязки КИЗ при `required`/replacement mismatch, идемпотентность `wb_orphaned`, изоляцию tenant/seller, ограниченный retry после 429 и отсутствие UI-изменений.

## Скриншоты

- `s03-fbs.png`
- `s14-packaging.png`
- `s15-pending-marking.png`

## Живой browser judge

Вердикт: PASS.

В живой вкладке на локальном stand `:15173` подтверждено:

- S-03 сохранил штатную таблицу и фильтры, новых элементов нет;
- S-14 сохранил штатный экран упаковки, новых колонок нет;
- S-15 сохранил штатное пустое состояние;
- card frontend diff отсутствует;
- ранее существовавший R-32 на S-03 не относится к карточке 01.
