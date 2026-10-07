# WMS-652/WMS-662: ограниченная приёмка инфраструктуры общего выпуска

**Software PASS; общий выпуск не принят.** Та же отдельная замещающая сессия
Sol6.1/high `01a11390-1014-76a0-9302-fbe0fd46ed1f` продолжила приёмку652;
исходный аналитик652 недоступен. Эта сессия определила R52/приняла4fef,
но не писала новые PID/exact-pair тесты, fixture, checker или продукт.
Текущий источник — `d5a3d5391c6a030a4d075bf18cea00c09c2ec178`.

[Независимый review](../../../reviews/wms652-batch-exact-fixture-review-20261007.md)
`e70b2f89b00d4f656a0c61029d1fe1f4eb95c0ee`, импорт
`07b49705462eeb2f4da934b1a946afe751a82b43`, blob
`b566e9896a7571ce46cde3ffe385c3800867b66e` дал PASS обоим полным fixture-файлам
и двум точным парам. [Source probe и реальные XML IDs](source-probe.json)
связывают текущие защищённые Git-объекты с проверенным3867 источником;
технический аудит/тесты/CI не повторялись.

| Требование → проверка | Сохранённые фактические результаты | Приёмка |
|---|---|---|
| R53/R45/R46 → C69 | Frozen8d16 до fixture1 target assertion RED/1 positive PASS; после4661782 PASS0skip/error. COPY setdefault ловится preservation assertion RED. Первый proven wait219/209 сохранён до release, после recycled PID живой цикл продолжает наблюдаться301/302. | Подтверждено; controlled actual-class contract, native PG отдельно ниже |
| R53/R45/R49 → C70 | Frozen937b до checker3 target assertion RED/3 negative PASS; после10 literal data lines6 PASS0skip/error. COPY bypass даёт3 meaningful negative RED. Реальные5 function names, параметр legacy-format/batch-pid и exact6 XML IDs записаны в JSON. | Подтверждено; synthetic review fixtures в replay отделены от actual independent review |

BatchSchedule изменён только внутри класса9 insert/6 delete; вне класса и21
business assertions, distinct-two-writer условие, delays/timeouts не изменены.
Checker после удаления двух literal dictionary entries сохраняет весь прежний
AST/algorithm/schema/старые пары/ownerUI. Продукт текущего кандидата совпадает
с ранее принятым `1cf85fc500bc6ee7a5f4ef283b250c4bf59c5333`; новая миграция не нужна.

Actual ledger `353b711dd10297ae86f9cd8184de52d99c33df5a` сохраняет обе исторические
коррекции c466→5feca (a6fc→cefb) и200617→466178 (eb225→03d744), пустые companion
lists и review bindings на actual07b497/b566. Owner_supersessions retained verbatim.
Его JSON совпадает с independently approved complete fixture_corrections template.
По явной передаче интегратора actual full document gate BASE4b на353 PASS,
AGENTS/CLAUDE равны; это не повторялось и не названо окончательным d5a3 CI.
Прежний0b12 source PASS/standalone или legacy-array ledger REJECTED сохранён;
отклонённая форма не выдаётся за принятую.

[Native comparison37563300572](../all-pg-comparison-37563300572/README.md), attempt1,
exactb568bfdddd8b106799428ce81451b406ffe9860b SUCCESS02:42:59–02:47:00UTC:
16 exact native outcomes exit0/37requiredPG и30nativeLinux PASS0skip/error/duplicate.
Оригинальные batch/steady-state по1 PASS с219/209 и225/224,659/537 по1 PASS,
fresh upgrade/downgrade/upgrade PASS. Это закрывает эффективность fixture;
isolated collector/workflow никогда не интегрирован в ordinary candidate.
Synthetic675 quantity не определяет production repair quantity.

Prepared238files/22suites/1192IDs/backend-fbs627 сохраняет старые233/1184 и235/1186,
619+PID2+pair6 в прежнем backend-all.xml/exact:false;230 normal/8 executable blobs.
Последний common37561608930 наa09/merge4a118 остаётся FAILED779s/12m59:
обе части4635 exactunion/4437PASS198ordinaryXMLskip;619requiredFBS PASS0skip,
Stock4 и исторический SQLite victim PASS. Исторический locker UNKNOWN.
Frontend1566/204required/Mac110/print11+6/new12/CDP7/browser43/6735/guards20/
scope51/Windows29 PASS относятся кa09, а не к окончательному новому SOURCE.
R51/C65 успешная цель полного CI10–15 минут ещё не измерена.

Main configuration6bd/pinb815 — установленная прежняя база; stagecc8e/prod8f11
не изменены. Следуют отдельные final SOURCE/pin, fresh common/etalon push CI,
staging и обычный production с exactSHA/runtime. Ручные Mac/подписи/бумага/
provider conditions после softwaredeploy; доступность Виталия не новый blocker.
Новые проверки, код, policy/workflow/ledger, внешние действия и deploy аналитик
не выполнял. Все прочие backlog sections сохранены побайтно.
