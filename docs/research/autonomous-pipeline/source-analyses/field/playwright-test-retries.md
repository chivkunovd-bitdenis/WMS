# Playwright — retries не равны чистому успеху

## 1–2. Ссылка и доказательность

[Playwright Test retries](https://playwright.dev/docs/test-retries), official docs, проверено 2026-08-24. E1 для описываемого механизма framework; не полевой incident.

## 3–5. Задача и happy path

Playwright Test запускает тест в worker. При failure worker отбрасывается, создаётся новый, а failed test повторяется до `retries`; это изолирует состояние между попытками. Без failure: test passed и retries не используются.

## 6–13. Переходы и решения

Переходы детерминированы: fail + attempts left → new worker/retry; pass first attempt → `passed`; fail then pass → `flaky`; fail all → `failed`. Число retries конфигурируется кодом/config (в том числе CI); модель ничего не решает. Reporter сохраняет итоговую классификацию; source не задаёт prompts, Git/PR, scope или product acceptance. Trace/screenshot относятся к отдельной конфигурации. Контроль loop — конечный retries count; recovery только свежий worker, а не диагностика причины.

## 14. Слабости

Retry способен скрыть timing defect и не объясняет, какие failures ретраить. `flaky` — результат конкретного запуска, не диагноз. Browser runtime crash и test assertion failure будут одинаково «fail», если controller не добавит классификацию.

## 15–16. WMS-применимость и вердикт

Адаптировать для browser gate: максимум один диагностический rerun на новом worker; сохранить оба результата и пометить `flaky`, не выпустить автоматически как clean browser-approved. Взять строгую terminal taxonomy; не позволять модели выбирать число попыток на ходу.

## 17. Evidence

- [Retry semantics и worker discard](https://playwright.dev/docs/test-retries#retries) .
- [Passed/flaky/failed status](https://playwright.dev/docs/test-retries#retries) .
