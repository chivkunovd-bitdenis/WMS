# WMS-652: выпуск06.10.2026 остановлен до защиты существующих FBS

**Последние прямые уточнения владельца, после 19:08 UTC.** В ответ на запрос установки
независимой защиты в main владелец сказал «Да, я разрешаю». Повторное разрешение
для этой согласованной установки не требуется; проверенные файлы и конкретный pin
сначала готовятся и принимаются. Это не разрешает неподтверждённый production.
Обычный полный CI должен целиться в10–15 минут без удаления сценариев; предыдущий
успешный37493512332 занимал1085s backend, из них965s Pytest. Структура БД уже
создаётся один раз на worker; сейчас готовится проверяемое разделение полного
набора на две параллельные части с точным объединением результатов.

**517 остаётся здесь и в текущем выпуске, не в следующем чате.** Владелец прямо
потребовал довести и Mac-скрипт Виталика, и штатный вывод КИЗ. Обнаружен старый
fixed80 helper; новые R26/R27/SC17/SC18 в517 требуют актуального полного серверного
набора. Отдельный тестировщик готовит контракт до исправления. Нужна реальная
подпись Виталика и конечный результат ЧЗ для завершения всей задачи, их нельзя
зачесть по коду/CI. Вопрос о доступности Виталика задан; ответа пока нет.

**Последний приоритет владельца: release BLOCKED.** Прежний manual GO отменён. До доказанной обязательной защиты действующих FBS-кнопок, подбора и непрерывной QR-печати выпуск не состоится;23:00 — прежний ориентир, не разрешение обходить это условие. [Актуальная карта и заключение652](../../requirements/WMS-652.md#единая-карта-действующих-шагов-источники-ab-и-приёмка-checkpoint). Ни main, ни production этим документом не разрешены.

Первоначальное поручение до нового приоритета: два отдельных Astra-аудита половин готового пакета,
проверка соседних процессов и фактического CI, выяснение истории тестов до кода,
параллельно требования следующей ночной очереди. Выпуск не раньше20:00UTC
(23:00Москва, 07.10 00:00Тбилиси). Это контрольная точка перед итоговым CI.

## Проверенный результат

Исходный f68a7a93 / CI37493512332 не пригоден к выпуску без следующей дельты.
[AstraA](astra-a.md) воспроизвела отсутствие явного повтора после отказа Ozon663;
[AstraB](astra-b.md) нашла неисполнявшиеся PG/browser/PDF проверки и пробелы
постоянной охраны. Других новых воспроизведённых продуктовых дефектов не найдено.

663: отдельный frozenконтракт fe1d37d90 (до кода, meaningful RED), разработчик
7f9a2ec9/d716cc69, независимая AstraA e18802ab9 DELTA PASS, заменяющий аналитик
dde8d6349 PASS C-RETRY1–6. При интеграции исходные product/testcommits сохранены
merge-историей. Продукт отличается отf68 только сервисом документов и существующей
галкой: новый явный повтор определённого отказа без дубля неизвестного/принятого.

В обязательный CI включены25PG и22browser/PDF случая. Настройка прошла два
независимых статических review. Итоговый LinuxCI этого общего SHA ещё должен
закончиться; зелёный исторический run не переносится. XML/TAP/JSON запрещают
пропуски, ошибки и иной состав. Mainfrontend может показать3 старых PDFskip,
но те же реальные PDF дополнительно обязаны исполниться отдельным job5/5.

C11 исправленной упаковки на фактическом стендеcc8e уже имела приёмку90c4,
но requirements отстала. Ведущий дополнительно открыл четыре реальные контекста;
[заменяющий аналитик](../../evidence/WMS-666/staging-c11-release-20261006/analyst-acceptance.md)
согласовал доказательства и документ. Исходное заключение07673 импортировано в
разрешённый каталог evidence; immutable scope test не менялся,11PASS локально.
Физическая бумага666/672, настоящая подпись517 и SET в Ozon не объявляются выполненными.

В пакете662/663/666/517/675/653/657/659/660/667/669/670/672/673 и процесс652;
прежние681/683/656 сохранены.651 в коде нет: поздний документ ограничения фронта
сохраняет «упаковано». Не возвращать её под видом пропущенного исправления без
разрешения существующего противоречия старой постановки и позднего scope.

## Границы автоматической защиты

Значимые новые тесты существуют, но не все перенесены в неизменяемую охрану.
B3/B4 остаются открытой652: многоссылочные ячейки, browser-e2e promotion,
классификация660, устаревшие ссылки672, scopeпоsubject, freezeпоsuffix,
comment-only reference и сокращённыйhotfix путь. Всё сохранено в требованиях и
каноническом бэклоге. Не объявлять будущий ночной конвейер полностью защищённым.
Историческая рекомендация ручного выпуска отозвана новым прямым условием владельца. Ручная проверка точного SHA/jobs/заключений не заменяет обязательную сохранённую защиту и отказ выпуска при RED/missing/skipped. Текущий выпуск BLOCKED; выполненные без новых оснований неизменные проверки повторять не требуется.

## Почему ночной выпуск не состоялся

Ночные handoff в `.worktrees/night-ready-acceptance-1006/docs/reviews/` сохраняют
FULL-HANDOFF-NIGHT-2026-10-06.md и night-release-continuation-20261006.md:
старые ветки разошлись с актуальным etalon, scopedинтеграция требовала отдельной
работы;662 имела реальные взаимные блокировки,672 срыв большой серииdecode;
документные/fixture поправки приводили к дополнительным проходам; окружение
теряло место на диске, браузер/модель местами были недоступны. У прежнего фонового
job5beb52dad9529727 (создан04.10, завершён05.10 — это предшествующий цикл, не вся
ночь05→06) статусdone сосуществовал с release_error конфликтов бэклога и отсутствием
выпуска. Такой статус не является успехом релиза. Работа была, результата вproduction
не было; организация интеграции и подтверждения результата не выдержала.

История ролей в A/B неоднородна. Большинство основных задач имеют отдельные
контракты до кода и независимые проверки; срочные681/683/656 имели разрешённые
сокращения,675 incidenttest добавлен после accountingкода, частьfixtures исправлялась
отдельно с доказательствами. Нельзя задним числом объявить все задачи идеальной
канонической цепочкой, либо сказать, что вся работа сделана без тестов.

## Следующая ночная очередь и вопросы

Требования658/654/681/671/679/680/684/586 обновлены в опубликованной ветке
codex/night-requirements-20261006, SHA3f8275d51; канонический бэклог там сохранён.
Обращение33 связано с671 как отдельное действие из выбранных строк приёмки,
без нового дублирующего номера. Это постановки, не новая разработка.

Ожидаются ответы владельца:658 точный пример импорта/неправильной этикетки;
671 выбранные строки или весь фильтр;33 только приёмки либо также возвраты;
683 действительно приоритет отменённых заказов Машнина (ошибочный дубльномера)
или сохранность уже выпущенного добавления заказов в WB. Отсутствие ответа не
считать одобрением варианта.679 требует техпроверки официального FBW API/XLSX,
не вопроса владельцу о существовании API. Сохранённое исследование включено вветку.

517 имеет код отбора действительно проданных КИЗ, но реальная Macподпись и вывод
не подтверждены.675 тестовая восстановительная дельта26 не означает ремонтproduction:
после выпуска нужно заново прочитать точную поставку/учёт и применить только свежую
доказанную недостающую дельту, без повторных расходов/начислений.

## Дальнейшая передача

Продолжать в `.worktrees/release-ci-final-20261006`, ветка
codex/release-ci-final-20261006, общий PR387. Перед новым запуском смотреть живой
CI текущего head. Production не выкатывать до выполнения нового обязательного условия652, независимо от времени; main не менять. Production
исходно8f11d912351e8de7633b4abcf74d195badaeb254, stagingcc8e.
Не подменять smoke и очереди настоящей бумагой/подписью/внешней приёмкой.

## Текущий аналитический checkpoint защиты

Единая карта652 содержит конкретные шаги списка, группового создания/добавления, ручного/скан-подбора и возврата, коробов, технического QR/КИЗ, очереди и восстановления печати, статусов и учёта. Exact источники A54152/Bb6f34 подтверждают отдельные полезные тесты и мутации, но выявляют отсутствующие экранные связи и незащищённые проверки. Фазовый PG-контракт bcb2 принят отдельно по C62 после независимого actualPG1 PASS/0 SKIP; C63 anti-weakening и полный requiredCI не приняты. Ни карта, ни этот узкий PASS не разрешают выпуск.

## Последний ограниченный checkpoint652: подтверждения и остаток

Сведённая карта действий остаётся каноном. На sourceef991 есть33 exact saved browser GREEN: реальный выбор/создание/partial retry/add-existing и QR→КИЗ→следующий заказ в трёх входах. Независимый ef56 подтвердил full CIS из PNG, реальное нажатие и business RED, но remount selection idempotency ещё требует узкого теста. Шесть существующих concurrency cases независимо PASS на PostgreSQLd618; это не новый fullCI. Registry9768 содержит176files/586 IDs как bootstrap, а не уже установленную trusted protection. Platform/attempt delta26fb принята отдельным review; root сообщает94 infrastructure PASS и30 POSIX native cases на macOS. Ни число, ни локальные результаты не заменяют exact requiredCI/Linux/Windows.

Два P1 независимого anchor переданы прежнему разработчику; servergate independent review ещё ожидается. Main anchor/mandatory checks/current-base не включены. В requirements652 C53 переклассифицирована «руками» как аналитическая смысловая сверка; C54–58/C60/C63 привязаны к реальным частичным проверкам, C62 очищена от скобочного комментария в testref. C59 — настоящий открытый блокер, без фиктивной ссылки; там сохранён brief testwriter по whole-candidate scope независимо от subject и геометрии/доступности критичных FBS элементов. R41–50 не ослаблены. Общая приёмка652/выпуск остаются BLOCKED, предыдущий manual GO не действует. По ночной очереди новых ответов нет.


## Актуальные решения владельца после 19:13 UTC

Владелец явно разрешил установить независимую защиту в main и потребовал обычный
полный CI за10–15мин без сокращения тестов. Старое «main не менять/ждать разрешения»
выше заменено этим разрешением только для подготовленной независимой защиты.

517 остаётся в текущем выпуске. После нового прямого уточнения владельца выпуск
программного исправления **не ждёт Виталика/подписи/его Mac**: Виталик проверит после
выкладки. Нужны исправленный динамический Mac-helper, проверенный обычный WMS вывод,
CI и установленная версия. Реальное внешнее завершение не выдавать за выполненное.
Контракт109 сценариев сохранён отдельно136ce395f до кода: старыйhelper78PASS31FAIL;
исторический контракт106PASS воспроизведён. Отдельный разработчик работает над
четырьмя scripts/ops файлами; старую ветку665 целиком не переносить.

## Checkpoint общей интеграции19:50UTC

[Точный handoff и registry](../../evidence/WMS-652/process-gates-20261006/integration-handoff.md):222files/1146suite IDs, Mac110PASS, geometry43 сохранены, независимые reviews Mac/CI/geometry приняты. Предыдущая строка об ожидании доступности Виталика устарела: владелец требует сначала softwaredeploy, затем личный Mac/подпись. Приёмка новой дельты поручена отдельному замещающему Sol аналитику. Main только checker/workflow045272b51; SOURCEpin/rules/canary/fullCI/deploy ещё не объявлены. Production прежний8f11d912.

19:52UTC: actual71contracts+45subtestsPASS; обязательныеruleset24431521readback9checks/stricttrue/nobypass сохранены вevidence. Источникpin проходит отдельную boundedпроверку последобавлениязащитыcollectionfixture.

## Checkpoint 19:58 UTC: действующая защита перед полным CI

Программная приёмка замещающего аналитика d2eb5c739800efe78b17b24a87ded70db314d7b9 сохранена в общей ветке a223aec02: C59 и SC17 приняты. Ручная подпись и проверка Mac SC18 остаются после деплоя. SOURCE0151a555ac429957d0eee591317cc4326e909dfd отдельно одобрен94aba396:222 защищённых файла и1146 идентификаторов сценариев; все прежние210 файлов и955 сценариев сохранены. Точная пара BASE4b298efc95be7b4b6b7fe5665be9f3671f1fe747 / SOURCE0151 установлена через обычный main PR389, merge SHA4e7b8abf12077e9e100730c6557507dc20a665b2. Единственная дельта main — четыре строки process_bootstrap.json; приложение main не менялось.

[Настоящая отрицательная проба](../../evidence/WMS-652/process-gates-20261006/actual-negative-canary.json): PR390 с head54fdd77296c42e2401c09bd221eafc9a43441141 удалил защищённое утверждение C62 и обновил хеш кандидата. Установленный workflow run37522705204 дал обязательной process-integrity результат FAILURE от GitHub Actions app15368, а PR получил mergeStateBLOCKED. Проверяющий код из установленного main дополнительно прочитал настоящие данные GitHub и подтвердил причину Candidate changed a protected baseline digest. PR закрыт без слияния; повреждённый тест в выпуск не включён. Повторное чтение ruleset24431521 подтвердило active, девять checks, stricttrue и отсутствие обхода правил.

Полный CI точного общего кандидата ещё ожидается. Production8f11d912 не изменён; до20:00UTC выпуск запрещён.

## Checkpoint 20:08 UTC: общий CI остановил выпуск на C5 печати

PR387 HEADf6066d68bd198794602a6e8916612d0d3b32460f, run37523087363 attempt1. Print-regressions завершился FAILURE:10PASS/1FAIL. Замороженный C5 на ошибке декодирования299 не дождался точного сообщения; сохранённый настоящий экран показал общий текст «Не удалось напечатать этикетки.», отметок печати0. Это зарегистрированный сбой, его причина ещё не установлена. Источник, ожидания и таймаут теста не ослаблены, повтор без разбора не запускается. Последующая новая browser43 команда была skipped и поэтому не подтверждена. [Сырые доказательства](../../evidence/WMS-652/common-ci-37523087363/README.md) сохранены вGit84452f0c5.

Frontend, backend-checks, Windows, backlog и охрана прошли; полные backend shards продолжаются. Успех отдельных jobs не разрешает общий release. Staging остаётсяcc8e6a019559343ac404e168a92ad36137255672; read-only Railwaymetadata подтвердил этот SHA у WMS/web/wms-worker/wms-beat. Живое SSH-чтение подтвердило production /opt/wms8f11d912351e8de7633b4abcf74d195badaeb254, четыре appservice running и здоровые db/redis. Никакого deploy/675repair/signature не было.

## Checkpoint20:22UTC: полный отказ и две отдельные технические линии

Full run37523087363 завершился FAILURE за796s. Обе raw receipts/XML сохранены:4625 exact union,0 intersection,4420 PASS,7 FAIL,198 JUnit skip (один pytest xfail). Все семь backend FAIL — старый backup test fixture без нового server verifier. Backend aggregator отказал, process-proof skipped. C5 diagnosis6b2b5dce подтверждает native Error boundary defect, но actual CI primary cause ещё неизвестна.

Ведущий поручил отдельному Sol разработчику один диагностический Linux/Chrome141 запуск только неизменённого C5 с exception/decode/image telemetry; этот запуск не является полным CI или выпуском. Отдельный testwriter исправляет только техническую backup fixture после нового test-first boundary контракта, сохраняя все семь старых вариантов и assertions; собственную дельту он не принимает. Source pin0151, policy, приложение, staging и production пока не менялись.

ENOSPC прервал сохранение этого checkpoint до измененияGit. После разрешённой адресной очистки одного остановленного synthetic WMS652 Chrome profile и двух завершённых чистых worktrees (Mac7a2fa31 и review1bd1d85, уже сохранены вremote/общейветке) свободно2.0GiB; код и доказательства не потеряны. Рабочий main checkout сокращён sparse checkout до checker/workflow/config, всеmainGitданные4e7b8abf сохранены. Пользовательский браузер, секреты и посторонние worktrees не затронуты.

## Checkpoint 20:40 UTC: backup fixture принята, C5 остаётся блокером

Отдельный test-first контракт030d75c01549b32a67ed4af405fea984b5974025 сохранён до технической fixture дельтыd736a02427c916979b2117ebecc1ace10dc9cc07. Независимый Sol review/техническая приёмка68de0bef6d78acf55aa517b16de4e440d68dc3c4 подтвердили15 PASS /0 skips: семь прежних backup вариантов, два bootstrap варианта и шесть новых boundary проверок. Прежние23 assertions и frozen новый контракт неизменны. Synthetic внешний CI verifier позволяет принятому exact SHA дойти до backup, а failed/unavailable/wrong-sha/missing останавливают настоящий shell до Docker. Продуктовый deploy shell и реальный verifier не изменены.

[Подготовленная добавочная охрана](../../evidence/WMS-652/process-gates-20261006/backup-registry-prepared.json) содержит224 файла/1161 suite IDs; все прежние222 хеша и1146 IDs сохранены. Это ещё не одобренный новый SOURCEpin: main продолжает доверять0151/BASE4b298. Общий PR387 остаётсяf606 и его failed run37523087363 не заменён новым full CI.

Один разрешённый диагностический run37527056184 attempt1 действительно выполнил неизменённый C5 в Linux/Chrome141 на b44ef10777f8d63555229d575558c6c9a5f3affd. Ошибка150 дошла с правильным сообщением; исправленный повтор затем получил native EncodingError на label227 (cumulative decode387), хотя PNG7675 bytes полностью декодируется независимо в836×356 pixels. Та же cross-realm ошибка дошла до экранного catch и превратилась в общий текст;0 POST/transfer. Фаза299 не достигнута. Причина внутри image decode/cache Chrome ещё не доказана; изменение окна32→16 предложено, но не реализовано и не объявлено PASS. Нужны отдельный контракт до продуктового исправления, review/приёмка и отдельно одобренная миграция замороженного product scope перед новым полным CI. Stagingcc8e и production8f11d912 не изменены.

## Checkpoint 20:55 UTC: bounded Linux сравнение не разрешило выпуск

Отдельный additive test-first05a7d08a65e135256fa69e8bf84519e95bcdef96 включён до двухфайлового productfix9e757a02cefa0cd1f7a95d272944e0b7c2b0660a. Новая exact7 Node suite подключена отдельным rawTAP к прежнему print artifact/process-proof; прежние C5/11 и scope51 сохранены. Подготовленная policy227files/1168IDs/19suites включает closure, но не стала установленным SOURCEpin. Независимый source-only reviewf0053194f93c72c1de91b5a6abd22dc62ec7eaa2 не нашёл дефекта в cross-realm сообщении, строгом all-success порядке и окне16; эффективность оставил непроверенной.

[Actual comparison37529471517](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37529471517), attempt1, HEAD68207fee941e7682adbc1c0ac31f366aeeff044c на точных product/test bytes9e: Node7 PASS/0 skips, неизменённый C5 FAILURE86.75s в Linux/Chrome141/Node24.21. Ветка diagnostic CI в общий кандидат не переносилась. Первая ошибка150 и исправленный повтор завершились300 readiness/marks/renderTape. Ошибка299 достигнута правильно, но исправленный повтор получил native EncodingError на retrylabel231/cumulative531; загруженный PNG836×356 прошёл независимую CRC/pixel проверку. Экран сохранил точное native сообщение,0transfer/0iframe. Поэтому окно16 недостаточно; source-only PASS не объявляется успешным исправлением ресурса или полной приёмкой.

Повтор полного CI, миграция fixed product reference d618, новый main SOURCEpin, staging и production не выполнялись. PR387 по-прежнему f606 с failed full run37523087363. Следующая коррекция остаётся ограниченной воспроизводимым C5, после code нужны independent review и отдельная аналитическая приёмка.

## Checkpoint21:04UTC: независимое ограничение production environment установлено

Владелец отдельно потребовал CI у входа в любой production deploy, независимо от ветки. [Live environment proof](../../evidence/WMS-652/process-gates-20261006/production-entry-protection.md) зафиксировал прежний production branchpolicy:null и исправление только deployment protection metadata: custom policies, ровно одна веткаetalon типаbranch, rule62185902. Повторное чтение подтвердило эту настройку и сохранённое пустое reviewer/wait configuration. Секреты не читались/не менялись. Это действующее независимое ограничение environment job из candidate/main/tag ветки; выполненный отрицательный deploy canary не заявляется.

Actual etalon4b298 уже проверяет exact CI metadata доSSH черезverify_ci.py; candidate усиливает это доrawmandatorycaseproof иservergate передDocker. Эти новые части пока не установлены вetalon/production из-за C5 FAILURE. Альтернативные directSSH пути иsecret scope не исследованы, обещание абсолютной защиты всех путей не даётся. Приложение иproduction8f11d912 не изменены.

Production environment negative canary subsequently executed as separately authorized: standalone branchcodex/wms652-prod-env-negative-canary-20261007, head9f2127a549440d438909426c0650f2a511127a09, run37531081039 attempt1. Harmless echo-only job112500324116 was rejected with0executedsteps and GitHub annotation identifying branch restriction. No action/credentials/SSH/deploy step existed, noPR/main merge occurred. Actualrawmetadata and workflow are preserved inproduction-env-canary-* evidence.

## Checkpoint21:12UTC: peer-drain контракт зафиксирован до механизма

Отдельный тестировщик опубликовал a0e4409300d4897234c501474de2bfe45478e488 на currentcode9e до новой реализации; controlled async heldpeers и synchronous decode throw дали2 целевых RED на преждевременном удалении источника. Старые7 nativeerror checks заново PASS в этом precode запуске; прежние11/C5 и numeric-independent ожидания сохранены. Independent bounded contract/wiring review2fd8c1749710d5b6b9dffcf9aa80c865a38c67ee с уточнением9e2939f828101f1fcb672c725c65378ec0339997 не нашёл замечаний. Новая raw672-peer-drain.tap exact2 suite подключена к прежнему print artifact/proof; prepared policy228files/1170IDs/20suites, old1168 IDs сохранены. Review/evidence включены в commonf0e15976c.

Это доказанный controlled lifecycle дефект, но не доказательство причины nativeChromeFAIL: saved actual299cleanup имеет11outerunfinished peers, nativepending в прежней telemetry не измерено;150 с15unfinished peers прошёл исправленный повтор. Разработчик активен в прежней отдельной Sol сессии, выполняет только drain active cohort/rethrow firsterror после frozenконтракта; numeric tuning, native bypass и новая слепая CI попытка не разрешены. Новый productfix/LINUXcheck ещё не объявлены. Scope/mainSOURCEpin остаются прежними, PR387/fullCI/staging/production не изменены.

## Checkpoint21:17UTC: active cohort механизм и один bounded Linux запуск

Product47817f76589701ea36ba1f8b30fca84b6a136208 опубликован после frozena0e: только utility10insertions/1deletion, async active promises захватывают synchronous throw, Promise.all catch ждёт allSettled уже начатого cohort и повторно бросает тот же первый error. Окно16, yield, strict all-success и non-handoff не изменены. Local2+7 PASS/0skip, typecheck/build PASS из docs-only69065b3db93b1036c6c399c1bebe8fe71527e68b включены в commonafbda45a3 вместе с точным preparedhash. Независимое ревью новой реализации и приёмка ещё требуются.

Разрешённый один actual Linux comparison37532767928 attempt1 запущен с standalonecef4cffd5d6bd1b76e691c596b87c9ad719e7d4f: product и пять frozen source/test paths сравниваются с47817, команды2peer+7native+ONLYoldC5, Linux141/Node24.21, прежние assertions/timeouts/420seconds, mute/noexternalnetwork. Observation-only adapter добавляет native fulfillment/pending counters, чтобы не смешивать внешнюю готовность с настоящим native completion. Сокращённый diagnostic CI не входит в общий кандидат. Result ещё не объявлен. Никакого fullCI/refmigration/mainpin/deploy после прежнего FAILURE нет.

## Checkpoint21:31UTC: native pending измерено; основной C5 всё ещё FAILURE

Actual37532767928 attempt1 завершён FAILURE на unchangedC5 за70.15s, setup/upload/source-byte guards PASS, peer2+native7 PASS/0skip. [Полные raw доказательства](../../evidence/WMS-672/peer-drain-linux-comparison-20261007/comparison-result.md) опубликованы отдельным978e5fd484411d2b707822774eb17c0889469ae1:39 docs files, все38 manifest members включая14 rejectedPNG проверены и включены в common. Diagnostic workflow/config/adapter не перенесены.

Fixture1: известная ошибка150 дошла правильно, cleanup измерил nativePending0/removedFramePending0; correctedretry300 readiness/300POST/renderTape PASS,459native fulfilled/0rejected/0pending. Fixture2: первая подготовка получила14 native EncodingError227–240 ДО injection299/retry;240started,226fulfilled,14rejected. Изображения836×356 complete, все14PNG CRC/pixel valid; после allSettled cleanup nativePending0/removedFramePending0,0POST/transfer. C5 ожидание299alert line308 отказало. Same nativeFrameId3: firststart→error510ms, firstcohortend→error469ms, поэтому простой довод «ещё не прошло250ms» не подтверждается.

Peer-drain controlled defect исправлен, но он не закрывает Chrome отказ валидных изображений. Нет новой правки/dispatch, numeric tuning или native bypass. Следующий разбор должен искать подтверждённые CC cache budget/lock/DecodeResult данные в bounded native lane; source/ref/pin migration, отдельная аналитическая приёмка и fullCI ещё не приняты. Production8f11d912/stagingcc8e/PR387f606/mainpin0151 не изменены.

## Checkpoint21:36UTC: следующий различающий diagnostic план

Владелец/ведущий разрешили существующему Sol разработчику bounded causal measurement без нового ожидания разрешения. План не меняет product47817 или frozen2/7/C5: один Linux/Chrome141 C5 с browser CDP tracecc.debug/decode-worker/memory-infra, bounded32MiB gzip stream, background numeric dumps без forcedGC, usertiming markers и backend metadata. Данные должны отличить отказ reservation/cache budget/locks от настоящего decode-worker отказа и проверить cache key/резервации/освобождения на момент ошибки. Пока конкретный standalone ref ещё не получен и dispatch не выполнен. Trace timing perturbation/отсутствие нужных полей означали бы inconclusive, а не PASS. Единственный dispatcher остаётся интегратором.

Верх README теперь ведёт к актуальным installedmain/rules/environment иC5 checkpoint; старые формулировки о неизменных main/product сохранены как история прежней стадии. Source/ref/pin/fullCI/deploy ожидают доказанной коррекции и отдельных review/приёмки.

## Checkpoint21:41UTC: различающий CC cache trace dispatched один раз

После source/scope проверки опубликованного standalone d82ba1c435b5a5e2101c50bfee3534679c79673d/refcodex/wms672-c5-cache-trace интегратор выполнил один разрешённый dispatch37535645145 attempt1. Product47817 и пять frozenfiles побайтно сохранены,2+7 Node checks затем unchangedC5, Linux141/Node24.21/mute/noexternalnetwork/старыеtimeouts. CDP наблюдение не вставляет decode waits, retry, fallback или GC; trace32MiB gzip/parser128MiB. Исходная backgrounddump идея уточнена ДО запуска: exact141 allowlist исключает CCcache providers, поэтому применяются light numeric dumps250ms и AddBudget/RemoveBudget/worker events.

Result ещё pending. DecodeResult enum не записывается напрямую; только no-loss/непустойtarget/однозначныйcachekey/нетreservationworkerприизмереннойsaturation могут обосновать admission refusal. Математическая гипотеза256MiB не считается причиной по226успехам:225/226 оказываются на разных сторонах предполагаемой границы, нужны actual target/storage/reuse данные. Trace может менять timing, отсутствиеполей/переполнение/неповторениеFAIL остаётся inconclusive. Диагностический CI/adapter/config не входят в общийrelease; дополнительного fullCI/refpin/deploy нет.

## Checkpoint 21:49 UTC: trace overflow не установил причину cache отказа

Run 37535645145, attempt1, повторил C5 FAILURE: peer2/native7 PASS, ошибка150 и её corrected300 PASS, injection299 достигнута, затем correctedretry получила native EncodingError на valid labels235–240 с pending0 и без передачи. Полный [отчёт и raw trace](../../evidence/WMS-672/cache-trace-linux-20261007/comparison-result.md) опубликован developer73e8049ff501d053ebf89d284c5fb43c860f412d и включён в common723862c61. Все38 manifest members проверены; три HTML snapshots сжаты losslessgzip и исходные SHA после распаковки совпадают.

Измерение причины inconclusive: dataLossOccurred=true, maxUsage0.9966; из86644 trace events66487 принадлежат React/Vite blink.user_timing и заполнили буфер до native C5. Native markers/image allocation snapshots отсутствуют, остались только22 ранних GetTask keys16×16. Softwarebackend подтверждён,13 light providercallbacks есть, но отсутствие поздних cache событий при overflow не доказывает admission/worker причину. Никакой product правки/dispatch по этому результату не было.

Разработчик готовит конкретную observation-only коррекцию capture: исключить шумную blink.user_timing и связать epoch wallTime с несколькими поддерживаемыми CDP clock-sync markers, сохранив bounded32MiB и cc/cache/light memory данные. Перед новым dispatch требуется проверяемый standalone ref и scope; новый run ещё не запущен. FullCI/pin/ref/deploy остаются заблокированы неизменённым C5.
