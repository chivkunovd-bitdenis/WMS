# WMS-652: узкая адаптация backup fixture после контракта

Контракт сохранён и опубликован **до** адаптации:
`030d75c01549b32a67ed4af405fea984b5974025` (`WMS-652: контракт тестов`).
После него новый test file неизменён. Только17 строк добавлены к setup
`backend/tests/test_prod_deploy_backup.py`; семь параметров и все23 исходных
assertions сохранены, что проверяет frozen AST-digest контроль.

В искусственном repo появился управляемый `scripts/ci/verify_server_process_ci.py`.
Он записывает exact вызов в существующий trace, принимает только ожидаемый
синтетический SHA и поддерживает refused/unavailable/wrong-sha. Штатный shell
`prod-update.sh` запускается без изменения. Никакого real CI/network/Docker/
production эта fixture не вызывает; старые Docker/git/curl границы сохраняются.
Это подстановка внешнего CI-ответа для backup-order теста. Логика настоящего
production verifier отдельно остаётся под прежним принятым frozen контрактом.

Адресная команда из корня постоянной worktree:

```sh
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -q -n 0 backend/tests/test_prod_deploy_backup.py backend/tests/test_prod_deploy_backup_gate_boundary.py --tb=short --junitxml=docs/evidence/WMS-652/backup-fixture-boundary-20261007/targeted-green.xml
```

**15 PASS**:7 прежних backup variants,2 прежних workflow bootstrap variants,
6 новых checks (пять actual shell boundaries и сохранность старых assertions).
Negative paths failed/unavailable/wrong-sha/missing заканчиваются до любого
Docker, backup directory и API stop. Positive проверяет gate раньше topology/
build и исполняет неизменённые backup/permissions/listener assertions.
Raw JUnit/журнал сохранены. Targeted Ruff и mypy двух test files PASS.

`negative-control.py` читает защищённый shell и меняет только **временную копию**:
добавляет `|| true` после CI-вызова. Frozen tests по этой копии дают3 точных RED
на `assert outcome.returncode != 0`, positive accepted остаётся PASS. В каждом
ошибочном продолжении trace показывает выполненный gate и30 synthetic Docker
calls. Это доказывает, что контракт ловит обход/игнорирование отказа, а не просто
ставит always-success stub. Raw результат — `negative-control.json`.
Точный защищённый shell в checkout не записывался и SHA256 не изменился.

Diff по product, scripts/ci, scripts/deploy, workflows и guards относительно
`f6066d68bd198794602a6e8916612d0d3b32460f` пуст. Тесты517/663/постоянная policy
не затронуты. Нового полного CI и deployment в этой работе нет.

**Это результат исполнения узкой технической дельты, не независимое ревью и
не приёмка.** Текущая сессия — замещающий тестировщик/исполнитель fixture change;
свою дельту она не принимает. Ведущий передаёт оба коммита отдельной Sol6.1 роли
для независимого ревью и delta acceptance перед новым полным CI.
