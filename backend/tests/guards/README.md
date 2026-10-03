# Защищённые backend-проверки

WMS-652, задание B: владелец 03.10.2026 утвердил G-STOCK-1…8 из раздела 1
`docs/reviews/WMS-652-guards-draft.md`. Здесь восемь тестов реальных сервисов,
по файлу на процесс; `stock_helpers.py` содержит измерения и подготовку данных,
а `stock_seeds.py` — используемые функции создания тестовых данных.
Внешние WB-вызовы заменены тестовыми ответами. Д2/Д4 WMS-632 в этой базе уже
исправлены: сценарии проходят без xfail. Доказательства красных мутаций —
`docs/evidence/wms652/stock-guards-proof.md`.

Запуск из backend: `/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python
-m pytest -n auto tests/guards -q`; затем тот же Python `-m ruff check tests/guards`.
Манифест защищает все файлы внутри guards, включая функции подготовки данных.
Импорты из обычных `tests.test_*` запрещены статической проверкой охраны.
Вне манифеста остаются фикстуры `backend/tests/conftest.py`: явно используемая
`db_session` и автоматически применяемые `isolated_withdrawal_gate` и
`isolated_login_rate_limit`. `monkeypatch` — встроенная фикстура pytest.
Изменение общих фикстур требует проверки влияния на достоверность охраны.
Проверяемые операции не подменяются.
