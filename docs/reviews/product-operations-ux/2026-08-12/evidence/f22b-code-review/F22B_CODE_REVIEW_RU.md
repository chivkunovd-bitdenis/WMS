# F22b Code Review: lease datetime fix

Дата: 2026-08-13, Europe/Moscow.
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
Роль: independent Code Review Agent.
Review commit: `3329aa6d270363fe1c6f4227996c51fc8c32fd57` (`Fix FBS stock sync lease datetime comparison`).
Статус: `CODE_REVIEW_PASSED`.

Код не редактировался. Проверка выполнена только для F22b lease datetime fix после browser QA failure с ошибкой:

`TypeError: can't compare offset-naive and offset-aware datetimes`.

## Scope

Проверены файлы из задания:

- `backend/app/services/fbs_stock_sync_service.py`
- `backend/tests/test_fbs_stock_sync.py`

Также прочитаны обязательные правила:

- `AGENTS.md`
- `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`

Секреты, deploy, Railway/GitHub variables, внешние панели и кабинеты ключей не открывались и не изменялись.

## Findings

Blockers не найдено.

Фикс действительно убирает Python-side сравнение naive/aware datetime. В `_try_acquire_lease()` условие lease остается в SQL `UPDATE ... WHERE lease_until IS NULL OR lease_until <= now`, но SQLAlchemy больше не пытается синхронизировать identity map через Python-evaluate: на statement добавлен `execution_options(synchronize_session=False)`. Именно эта Python-side синхронизация могла сравнить загруженный SQLite-naive `binding.lease_until` с aware `now` и упасть до выполнения полезного сценария.

DB atomic lease semantics сохранены. Захват lease по-прежнему выполняется одним conditional `UPDATE` по `binding.id` и истекшему/null `lease_until`, затем проверяется `returning(FbsWarehouseBinding.id)`: если строка не вернулась, синхронизация считается busy и внешний PUT не начинается. После успешного UPDATE код вручную выставляет `binding.lease_until = new_lease_until` и коммитит, поэтому локальный ORM-объект остается согласованным без Python-side evaluation.

Safe-zero поведение не ослаблено. Коммит не меняет `_build_publish_plan()`, расчет availability, blocked targets или публикацию batch-ей. Нулевой или неизвестный FBS-пул остается заблокированным через `ERROR_UNSAFE_ZERO_BLOCKED` / `ERROR_UNSAFE_STOCK_UNKNOWN`, не попадает в `publish_targets` и не уходит в Wildberries PUT. Значение `result.products_zeroed` по-прежнему не используется как путь автоматического зануления.

Регрессионный тест meaningful. Новый `test_try_acquire_lease_handles_naive_loaded_lease_until` воспроизводит важную SQLite-особенность: timezone column может вернуться в Python как naive datetime. Тест кладет в `lease_until` истекшее naive значение, вызывает `_try_acquire_lease()` и проверяет не только отсутствие crash, но и успешный lease acquisition с aware UTC значением после фикса.

Остаточный риск: тест покрывает direct helper path `_try_acquire_lease`, а не полный live browser positive path. Для Code Review этого достаточно, но по gate-протоколу это не заменяет повторный Browser Product QA.

## Commands

Read-only / targeted:

```bash
pwd && git rev-parse --show-toplevel && git status --short
sed -n '1,220p' AGENTS.md
sed -n '1,260p' docs/WMS_FEATURE_GATE_PROTOCOL_RU.md
git show --stat --oneline --decorate --no-renames 3329aa6d270363fe1c6f4227996c51fc8c32fd57
git show --no-ext-diff --unified=80 --no-renames 3329aa6d270363fe1c6f4227996c51fc8c32fd57 -- backend/app/services/fbs_stock_sync_service.py backend/tests/test_fbs_stock_sync.py
nl -ba backend/app/services/fbs_stock_sync_service.py | sed -n '105,260p'
nl -ba backend/app/services/fbs_stock_sync_service.py | sed -n '260,700p'
nl -ba backend/tests/test_fbs_stock_sync.py | sed -n '820,940p'
pytest tests/test_fbs_stock_sync.py
```

Targeted tests:

```text
tests/test_fbs_stock_sync.py ..................... [100%]
21 passed in 7.40s
```

## Verdict

`CODE_REVIEW_PASSED`

Можно возвращать F22b в независимый Browser Product QA rerun. Code Review не является browser approval.
