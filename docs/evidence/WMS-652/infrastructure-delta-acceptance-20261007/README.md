# WMS-652: совокупная инфраструктурная приёмка после R1, 07.10.2026

**Четыре инфраструктурных исправления приняты на `972da18be97cab8c41b14b0aa00a3d30773e4492`.
Окончательный SOURCE/pin, успешный полный CI и выпуск ещё не приняты.**

Это та же отдельная замещающая сессия аналитика Sol6.1/high
`01a11390-1014-76a0-9302-fbe0fd46ed1f`; исходный аналитик недоступен.
Тестировщик01a11370 и разработчик — другие сессии. Аналитик не автор native/peer/
raster/CDP контрактов или реализации. Постоянная ветка
`codex/wms652-infrastructure-acceptance-20261007`; принято одно совокупное
инфраструктурное изменение в рамках исходных требований652 и полного CI→production.

Независимый3850c37895eec94dc391ea46136f416271404845 принял первые три исправления.
Четвёртое после прежнего блокирующего bef38 R1 имеет **Technical PASS; R1 CLOSED**
в опубликованном `7c4670975d7e70cbbfe28fb0cd4ee66f39018007`:
[точный отчёт](https://github.com/chivkunovd-bitdenis/WMS/blob/7c4670975d7e70cbbfe28fb0cd4ee66f39018007/docs/evidence/WMS-652/cdp-cancellation-source-review-20261007/r1-rereview.md).
Он прочитан через git show из этого объекта, после trustedhandoff pending:false.
Ревью source на972da и принятие registry-дельты не являются finalSOURCEpin approval.

Приняты только: устаревшее reference-ожидание d618→ранееaccepted25eb; добавление
%j в одно CryptoPro test title при прежних входах/assertions/числе случаев;
полное AST-представление с одним fixed063digest/23asserts/7params/5controls;
конечная CDP-fixture обработка первой известной отмены с сохранённым nativepayload.
Unknown/ambiguous/duplicate/competing/othererror/navigation-only/timeout остаются
строгими отказами. Оригинальный listener/errors.length, timers и все43 бизнес-
тела/маршруты/asserts/delays/IDs сохранены. Нет accepted/submitted/receipt/retry.

Frozen130130→910 до первого кода; отдельный d024 CDP6/7 до307873. Прежний5/helper
prefix неизменен. BEFORE5PASS/2targetRED0skip → AFTER7PASS0skip/syntaxPASS.
Точная одна reply guard теперь проверяет monotonic ambiguity до retirement.
[Таблица requirement→realtestref→actualverdict](../../../requirements/WMS-652.md#совокупная-приёмка-четырёх-инфраструктурных-исправлений--07102026)
содержит все семь имён и границу actual-class controlled WebSocket/timers.
Сохранённые targeted3/37/preservationPASS и отрицательные контроли не повторялись.

Native explicit-abort37552021494 дал наблюдённую связь FetchID/NetworkID, actual
AbortError/canceled:true/netERR_ABORTED и первый native-32602 того же ID. Raw17members/
44events/0drop приняты5c6; unknown-ID та же ошибка остаётся отказом; nav-only
fulfillment былSUCCESS. **Оригинальная историческая CI команда/ID/cause UNKNOWN**.
Ни этот контроль, ни новая фикстура не объявляются ретроспективным объяснением.

Последний wholeCI37548248403 attempt1 eab/testedmergeac845 FAILED743s/12m23.
4631 exactcollection=2316+2315, union/no duplicates;4432PASS/198regularXMLskip/
1preservationmetadataFAIL. RequiredPG после failedshard не выполнен. Frontend1566
имеет одинduplicate group2PASS, strictparser верноRED; Mac110exactPASS/204mandatory
uniquePASS не целыйproof. Old672all11PASS0skip328.855s, remaining6/new12PASS.
Browser43=42PASS1FAIL на strictCDPerror после предшествующих businessasserts;
actualfull43 послеpatch не запускался и остаётся доказательством NEXTcommonCI.
Успешная fullCI цель10–15 минут не подтверждена failed12m23.

[source-probe.py](source-probe.py) выполнен один раз как офлайн-подсчёт неизменяемых
Git-объектов и сохранённых receipts, без тестов или собственного технического ревью.
[source-probe.json](source-probe.json) закрепляет все230 текущих hashes,22suites/1180IDs,
семь exactrefs, preserved old230/22/1178 и installed229/21/1173, input identities.
От3151 меняются только frozen test53c54d… и browser24f146…; workflow/report прежние.
Приложение25eb неизменно, исключённый product_scope инфраструктурный `.test.ts`
меняет только принятое имя. Requirements672/517 и чужие разделы бэклога не тронуты.

Mainconfig8df23716626451e026d74137494e835e3cb081b7 установлена на исторический
SOURCE9dae4b19f6d4dca554200e08282579414a110848/BASE4b298; checker04527 прежний.
Strict9checks/no bypass, environment exactetalon и negativecanaries уже
установлены/проверены сохранёнными readbacks. Новые230/1180 hashes требуют отдельной
finalSOURCE-проверки и новой mainconfig до одного следующего полного CI.
Затем обычный etalonmerge/pushCI, staging и подтверждённый deployedSHA.
Production8f11d912/stagingcc8e неизменны по сохранённой передаче; liveaudit не было.
Softwaredeploy FIRST, бумага/517/подписи/provider условия отдельно после него.

В этом этапе не было тестов/сборки/браузера/fullCI/деплоя/секретов/новых агентов.
Изменены только652requirements, её раздел бэклога и этот каталог доказательств.
Заполненная приёмка подготовленной инфраструктуры не закрывает всю652 или release.
