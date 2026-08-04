# 00 — Триаж

- **Задача:** Склады/офисы продавца WB FBS + отдельный marketplace-токен.
- **Тип:** feature
- **Размер:** S
- **GitHub Issue:** нет
- **Зачем:** Нужен токен «Маркетплейс» и officeId/warehouseId для поставок; intake уже временно сидит на supplies_token.

## Маршрут (feature S)
- [x] 0 триаж
- [x] 1 анализ
- [x] 🔒 ГЕЙТ 1 — наследует эпик + модераторские уточнения
- [ ] 2 контракт (кратко — S, но есть DoD в TASK)
- [x] 3 тест-дизайн (из TASK)
- [ ] 4 код
- [ ] 5 ревью
- [ ] 6 док

## Затрагивает
backend: credentials model + migration, wildberries_client (v3 warehouses/offices), service, api `/operations/fbs-sellers/...`, wire intake to prefer marketplace_token.
