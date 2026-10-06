# WMS-676: регистрация тестового адаптера, замечание F4

Исправлено только подключение существующего адаптера тестовой среды.
`tools/support_agent/tests/conftest.py` регистрирует
`tests.test_install_model_migration_races` через `pytest_plugins`, поэтому
его autouse fixture `frozen_metadata` доступна прежнему модулю при обычном
запуске pytest. Код установщика, адаптер и замороженные утверждения не менялись.
Fallback в production не добавлен.

Основание RED — независимое ревью `astra-review-21bc89.md`: обычный запуск
обоих модулей давал 8 failed / 12 passed, отдельный прежний модуль —
8 failed / 3 passed. Этот воспроизведённый RED принят как достаточное
основание исправления тестового процесса по прямому поручению владельца.

Проверено из `tools/support_agent` без флага `-p` и без установки пакетов:

```sh
python3 -m pytest -q tests/test_install_model_migration.py tests/test_install_model_migration_races.py
# 20 passed in 11.40s
python3 -m pytest -q tests/test_install_model_migration.py
# 11 passed in 0.85s
python3 -m pytest -q tests/test_model_migration.py tests/test_llm_router.py tests/test_pipeline_chat.py tests/test_runner_and_safety.py tests/test_install_model_migration.py tests/test_install_model_migration_races.py
# 127 passed in 14.42s
```

Ruff для изменённого conftest и `git diff --check` прошли.
`git diff e009c3fc0 -- tools/support_agent/tests/test_install_model_migration.py`
пуст: прежний замороженный модуль сохранён без изменений.

Область изменения ограничена регистрацией тестового окружения и этим отчётом.
Отчёт независимого ревью сохранён отдельным коммитом ревьюера и не включается
в коммит разработчика. Независимое ревью данного изменения, приёмка, полный CI
и установка в этой работе не выполнялись; ведущий проверяет итоговый diff.
Рабочая служба, production, Telegram и настройки авторизации не затрагивались.
