# WMS-652 · сохранённая постоянная защита при promotion

Контракт отдельного тестировщика: `90cf5e8f49e5eee1070c914b19ed87de4fa49353`, импорт `787908cfd`. До product изменения локально 5 cases: 3 PASS, 2 FAIL (`red.log`): original удалялся, а три ссылки склеивались. Ожидания тестировщика не изменены.

После изменения `promote_guards.py` все 5 cases PASS (`green.log`). Registered original сохраняется только если committed PROCESS policy и original bytes совпадают с HEAD, SHA-256 совпадает с policy и named case существует в её обязательном report suite. Используется тот же schema/local-file validator, что и обязательный process proof. Само наличие имени пути не считается защитой. При отсутствующем case/изменённых bytes/несохранённой policy/symlink — отказ без mutation (`negative-probes.json`).

Полностью registered задача — idempotent без изменения original/document/policy/manifest. Unprotected legacy move/import rewrite сохраняются. Несколько references `<br>`/`;` разбираются отдельно, а при legacy move записываются каноническими `<br>`, сохраняя все имена. Пустая active `навсегда` ссылка остаётся ошибкой.

Policy включает три новые cases в existing `ci-shards.xml` и обновляет только два изменённых process-contract source hashes; прежние 1146 cases и их report/format/exact сохранены. Всего текущая policy содержит 1164 cases/19 suites/225 protected paths. Final accepted product P / protection SOURCE S пока не frozen, main/etalon/deploy не менялись. До S нужно зарегистрировать genuine forever cases новых принятых задач с raw CI receipts; после etalon policy становится BASE, и protected originals нельзя переносить/переписывать.
