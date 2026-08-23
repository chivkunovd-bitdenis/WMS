# Короба и грузоместа в каталоге

Проверено 23.08.2026 на чистой ветке от `origin/etalon`.

- `python3 -m pytest -q backend/tests/test_inbound_package_catalog.py` — 3 passed.
- `npm run build` — успешно.
- ESLint изменённых файлов — успешно.
- `npx playwright test tests-e2e/catalog-box-lookup.spec.ts --project=chromium` — 2 passed.
- Основной браузерный сценарий: внутренний ШК короба введён в поиск каталога, нужный короб автоматически раскрыт, товар и текущий остаток показаны.
- Защита от гонки: запоздавшая ошибка предыдущего скана не заменяет результат следующего успешного скана.

Скриншот живого Chromium: `catalog-box-open.png`.

В базовой ветке `origin/etalon` нет `scripts/ui/invariants.js` и `scripts/ui/ui_guard.py`, поэтому эти два отсутствующих репозиторных инструмента не запускались.
