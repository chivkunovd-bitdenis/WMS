# Проверки исходной версии

База: `001b93e00e3f76e29c7b3f658e082fe2c201b2d1` = обновлённый origin/etalon.
До продуктовых изменений в backend выполнено:

```text
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -q -n 2 tests/test_ozon_delivery_confirmation.py tests/test_fbs_pr140_shipment_write_off.py
17 passed, 18 warnings in 13.25s
```

Использована локальная тестовая SQLite по штатному conftest.py.
Результат подтверждает существующие сценарии проведения и списания,
но не новый контракт обратной синхронизации или состояние production.
