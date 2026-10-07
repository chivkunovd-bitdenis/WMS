# WMS-652: контракт серверного CI в старой backup fixture

Отдельный замещающий тестировщик Sol6.1 вместо недоступной прежней тестовой
сессии. Предыдущая программная приёмка этой сессии не используется как ревью
или приёмка собственной новой дельты. Источник до изменения:
`f6066d68bd198794602a6e8916612d0d3b32460f`; именованная ветка
`codex/wms652-backup-fixture-boundary-20261007` в прежней постоянной worktree.

Прочитаны текущие origin/etalon AGENTS, требования652 и test-writer skill.
Полный CI37523087363 остановился на семи старых backup variants: в искусственном
repo отсутствует новый accepted `scripts/ci/verify_server_process_ci.py`.
Прочитаны оба raw shard logs; все семь failures относятся к этому отсутствию,
а не к реальной ошибке production pg_dump. Product gate уже имеет отдельный
принятый frozen контракт и независимое ревью; здесь он не изменяется.

Новый файл `backend/tests/test_prod_deploy_backup_gate_boundary.py` использует
старый backup harness и наблюдает настоящий subprocess неизменённого shell.
Пять случаев требуют exact `--sha` CI boundary до каждого Docker-вызова:
accepted; failed; unavailable; wrong-sha; missing. Отказ обязан оставить ноль
Docker-вызовов, отсутствие backup directory и отсутствие остановки API.
Missing проверяет именно отсутствие gate file. Положительный случай также
исполняет все прежние backup assertions. Шестой случай фиксирует прежние семь
параметров и все23 assertions через AST digest, включая порядок/режимы доступа.

До fixture adaptation: **4 целевых FAIL,2 PASS**, без import/collection errors.
Positive fail содержит точное `can't open file ...verify_server_process_ci.py`;
failed/unavailable/wrong-sha не находят обязательный boundary trace, поскольку
файл ещё отсутствует. Missing и сохранность прежних assertions проходят.
Raw JUnit и журнал — `contract-red.xml`/`contract-red.log` рядом.

После фиксации этого контракта допустима только техническая адаптация старой
fixture: добавить controllable synthetic server-CI CLI внутри искусственного
repo, с exact SHA, trace и явными отрицательными исходами. Это управляемая внешняя
граница для проверки backup shell, а не подмена production verifier или
always-success обход. Все прежние7 variants/23 assertions и shell остаются.
Ожидания нового контракта после его commit не изменяются. Нужны targeted GREEN,
meaningful negative control и отдельное независимое ревью/приёмка другой роли.
CI/policy/product/runtime/секреты в этой работе не меняются.
