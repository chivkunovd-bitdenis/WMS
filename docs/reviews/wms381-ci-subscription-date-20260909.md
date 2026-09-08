# WMS-381 — стабильная дата в тестах подписки

CI run34282219436 для head2e908fafcc65fd3e489b8712b9484ecd5f4e90ce завершился
одним падением: test_subscription_endpoint_reports_days_left ожидал12 дней,
получил11. Прогон проходил 08.09.2026 после21:00UTC, когда по Москве уже09.09.
Тест строил paid_until от date.today(), сервис использует today_msk().

Сравнение с зелёным ad116f0d: backend tree в обоих коммитах идентичен,
`a66fd4096e6b41a764590cc7cbf931ef441e3e99`; diff .github/workflows пуст.
Это исправление зависимости тестовых предпосылок от времени запуска.
Production-логика подписки, её московская дата и конфигурация CI не менялись.

Изменён только backend/tests/test_subscription.py: явная fixture
subscription_today возвращает фиксированную дату2026-09-09 и через monkeypatch
подставляет её в subscription_service.today_msk на время каждого API-теста.
Три API-теста рассчитывают paid_until от этой же даты. Два существующих
арифметических теста уже задают today явно и не изменены. Новых сценариев,
пропусков, ослабленных assertions и граничного набора не добавлено.

Проверки из backend в .worktrees/wms396-stage:

- ruff check tests/test_subscription.py — passed.
- mypy tests/test_subscription.py — success, 1 source file.
- pytest -n auto tests/test_subscription.py — 5 passed за6.62с,
  Python3.14.3/macOS; warnings сторонних SWIG типов.
- git diff --check — passed.

Полный набор и ручной retry CI не запускались. Канон обновляет координатор
параллельно; этот commit содержит только назначенный test-файл и отчёт.
Источник CI: https://github.com/chivkunovd-bitdenis/WMS/actions/runs/34282219436.
