# WMS-652 · обязательные receipts 654,672 и promotion

WMS-654 принят отдельно на c6ffee0e и интегрирован10630bf24. На combined models через isolated loopback PostgreSQL выполнены ровно C8+C4False/True:3PASS0SKIP, raw `docs/evidence/WMS-654/combined-postgres-20261007.xml`. CI отдельной командой создаёт isolated `wms_test_654_combined`, выполняет эти же3cases и пишет `release-postgres/654.xml`; existing backend artifact+exact-attempt process download включает файл. Policy exact:true требует все3IDs.

Остальные genuine654backend cases получены из настоящей pytest collection и зарегистрированы в existing required `backend-all.xml`, который CI исполняет полными неизменёнными shards; PG-only C4 туда не добавлены, потому что там SQLite и skip. 20 genuine654frontend cases прошли адресно (`654-frontend.json`) и зарегистрированы в existing required `frontend-all.json`; три frozen test source files hash-protected. Product/tests/expectations не менялись. Test.each шаблоны в requirements остаются; matcher требует отдельного последующего до-code контракта поддержки подстановок.

C5a672: exact frozen test ce615a, real command независимого reviewer `--config tests-e2e/wms672-dom.config.ts -t 'C5a 33 labels'`. На combined product PASS1, старые6INCOMPLETE DRAFT JSdom cases исключены именованным фильтром и честно присутствуют skipped в raw `wms672-c5a.json`. Они не выданы за исполненные. Все accepted11+6 native Linux browser cases сохраняются в своих exact suites. Новая required suite требует именно passed C5a со source hash и реальным JSON; exact:false допускает необязательные draft entries, не пропускает required C5a failure/skip. Existing19suite formats/exact/caseIDs сохранены.

Promotion: настоящий guard JUnit producer дополнен frozen `test_promote_guards.py`, policy требует все5cases, включая прежние move/rejection. Raw `ci-shards.xml`29PASS0SKIP плюс54subtests. До этого broad unittest discovery исполнял promoter, но его JUnit receipt не сохранялся; wiring исправлена до final SOURCE freeze.

Main pin, etalon и deploy не менялись. Final product P/source S пока pending; это подготовка обязательного CI, не full-CI readiness.
