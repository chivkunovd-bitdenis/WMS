# Clicker evidence — 01-wb-marking

## Пройденные проверки

- S-03 `/app/ff/fbs`: маршрут открыт, `fbs-orders-screen` видим, штатные таблица и фильтры сохранены.
- S-14 `/app/ff/packaging`: маршрут открыт, `ff-packaging-page` видим, новых колонок и действий нет.
- S-15 `/app/ff/packaging/pending-marking`: маршрут открыт, `ff-pending-marking-page` видим, штатное пустое состояние сохранено.

Targeted Playwright: `1 passed` (`13.2s`). Скриншоты сохранены в `docs/evidence/01-wb-marking/`.

## Инварианты

- S-14: PASS, нарушений 0.
- S-15: PASS, нарушений 0.
- S-03: обнаружен ранее существовавший R-32 (`34/40` высоты кнопок). В карточке 01 нет diff в `frontend/src`, поэтому это не регрессия карточки и не основание расширять её scope.

Боевой прод и живой кабинет Wildberries не использовались.
