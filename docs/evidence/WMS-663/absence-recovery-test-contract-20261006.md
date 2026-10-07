# Два конкретных замечания ревью: тесты до исправления

База продукта — `d4d1c658839d1cdbb8b9e50509f046a30bf5ffa3`.
Собственный постоянный checkout `.worktrees/wms653-scope-attribution-20261006`,
ветка `codex/wms663-pre-set-recovery-contract-20261006`.
Отдельный тестировщик — фактический Sol 6.1. Сценарии согласованы напрямую с
ревьюером priority_662 и разработчиком priority_663; второй добавлен только после
отдельного поручения ведущего. Новая общая матрица не запускалась.

Новый файл `backend/tests/test_wms663_absent_pre_set_recovery_contract.py` содержит
ровно два теста. Прежний контракт из пяти cases и runtime не изменены.

Первый использует штатный `claim_exemplar_write` с реальным
`choice={'all_required_absent':True}`. Через штатный checkpoint меняется только
срок lease, затем новая DB session читает interrupted preparing. Ожидаются
editable/version2 и отсутствие выбранного, но ещё не отправленного намерения.
Новый явный вызов текущей версии должен отправить первый полный SET ровно один раз.
Тест затем теряет ответ этого SET; новый restart/repeat разрешает только STATUS,
не второй SET. Невозможное pending-состояние вручную не выдумывается.

Второй сначала реально отправляет batch и получает exact matching accepted
readback. Затем вызывается существующий `_scan`/`submit_marking` для экземпляра81:
допускаются один document SET и один настоящий KIZ SET. Поля документов и weight
проверяются на равенство; mark действительно добавлен. Новый GET в новой DB session
читает полный последний payload с реальными requirement flags и должен сохранить
absence_selected=true. Повтор выбора не делает третий SET, только STATUS.

## Фактический RED

Команда из backend:
`/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -n 0 -q tests/test_wms663_absent_pre_set_recovery_contract.py`.

На exact d4d1: **2 FAIL**, 0.97 s, 6 известных deprecation warnings.
Первый отказ: recovered уже editable/version2, но absence_selected=True вместоFalse.
Второй: batch принят, настоящий marking SET выполнен, полный readback принят,
но absence_selected=False вместоTrue. Это целевые assertions, не collection или
environment errors. Первый сценарий отдельно ранее дал 1FAIL за0.74s по тому же месту.

Оставшиеся после этих точек assertions ещё не достигнуты на RED, их PASS не заявлен.
Ruff нового файла PASS. Разработчик получает сохранённый test commit до исправления.
Своих runtime изменений, новых статусов/таблиц, полного CI и product review нет.
