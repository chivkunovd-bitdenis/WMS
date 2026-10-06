# WMS-676: журнал продолжения приоритетного выпуска, 6 октября 2026

Прямое поручение владельца: в первую очередь довести WMS-662, 663, 666, 517 и 675, по одному исполнителю Sol 6.1 на задачу, параллельно. Полные тесты и CI выполнить после общей интеграции. Сохранить уже готовые задачи и утренние исправления 681/683. Никаких повторных полных циклов для неизменного кода и ревью документов. Это журнал исполнения существующих задач, не новый бэклог и не заявление о готовности.

## Точки продолжения

База общего кандидата: origin/etalon 4b298efc95be7b4b6b7fe5665be9f3671f1fe747. Ветка codex/priority-five-release-20261006, одноимённый worktree внутри WMS/.worktrees. Product-кода ещё не объединено. Production при последней прямой проверке 8f11d912351e8de7633b4abcf74d195badaeb254; его WMS-683 необходимо сохранить отдельно от etalon.

- 662: native /root/priority_662, worktree wms662-scoped-integration-20261006, исходный HEAD259a36854462e5dc794c9ee8eefa5a7e3d5acc68. Независимая проверка интеграции, затем приёмка.
- 663: native /root/priority_663, исходный worktree wms662-663-priority HEADbda4a1faaaa21c518c1ef9580787b8cdd719fe08. Подготовка scoped интеграции; одна ограниченная попытка подтвердить публичную схему Ozon, внешняя проверка с оператором остаётся честно открытой.
- 666: native /root/priority_666, исходный worktree wms666-unified-fbs-packing HEAD3ae3d3427d6791f0a329bb570803630f9895d5b8. Подготовка scoped интеграции и точного остатка для общего staging/принтера.
- 517: CLI Sol6.1 high, session91208, persistent thread01a110f1-6c2a-71b2-84e0-564eb653b6c0, исходный worktree wms517-sales-report-contract HEADdd5cb7a629bbadcbb3fcd76be64110d86ab44bc6. Совместимая дельта и штатный путь полного свежего набора проданных КИЗ.
- 675: CLI Sol6.1 high, session25667, persistent thread01a110f1-70ef-7412-8700-0945d5c23e92, worktree wms675-live-reconciliation-20261006 HEADdf3e17614. Свежие подтверждения Ozon и точный план недостающего учёта, без самовольного применения.

CLI запущены с --json и --output-last-message. Живой поток сохраняется в /Users/deniscivkunov/Projects/WMS/.agent-runs/priority-five-20261006/{517,675}-events.jsonl, финалы в {517,675}-result.txt, manifest.json и исходные prompts рядом. Это вспомогательные локальные журналы; код и доказательства исполнители обязаны сохранять commit+push в своих постоянных ветках. Не публиковать сырые полные логи или секреты.

Каждый исполнитель ведёт docs/reviews/wmsNNN-priority-progress-20261006.md в своей ветке. При обрыве сначала прочитать прогресс/Git и проверить живой процесс, затем продолжать сохранённую сессию, не создавать дубль. Native сообщения приходят ведущему автоматически; CLI контролируются чтением новых agent_message из сохранённого потока и статусом процесса.

## Следующая граница

Получить конечные SHA пяти исполнителей и точные остающиеся внешние действия. Передать одному интегратору общий кандидат и принятые дельты, включая уже готовую группу и обязательный hotfix683. После объединения провести требуемые независимые проверки изменений и отдельную приёмку, целевые тесты вместе, полный CI точного итогового SHA, общий staging. Не путать программную готовность с подписью Виталика, физической бумагой или исправленным учётом Bambook. Один production выпуск, без отдельных выкладок задач.

## Интеграция 1 — production hotfix WMS-683

База этапа `4b325876eb607bea5cba5b9547e9fe02becfce89`.
Включён ancestry `8f11d912351e8de7633b4abcf74d195badaeb254`, его parent
`f7b1ae2c6` уже находится в etalon. Продукт и исходные тесты hotfix перенесены
автоматически. Единственный конфликт — добавление секций канонического бэклога:
сохранён весь текущий бэклог и добавлена только исходная секция WMS-683.
Тесты и CI не запускались. Следующий шаг — включить scoped WMS-662/666 и готовые
651/667/669/672/673; 517/663 ожидают финальных scoped SHA.

## Интеграция 2 — WMS-662

База этапа `56dd434676ac9a06e6deb9dcfee5492bfeeb11ab`; сохранён источник `23190047674c1ea3c0ecf1bcaeebc76dea625110` с контрактом до кода,
продуктом, proofs и независимым PASS. Единственный конфликт в бэклоге разрешён
добавлением исходной принятой секции 662 при сохранении всех текущих секций.
Продукт объединился автоматически; QR681, ошибки653 и hotfix683 сохраняются.
Отдельная приёмка интеграции выполняется параллельно другим аналитиком.
Следующий шаг — WMS-666 и оставшиеся готовые дельты. Общие тесты/CI ещё не запускаются.

## Интеграция 3 — WMS-666

База `685366ac9e97e44afbb900e698be1b94abdbdad1`; включён scoped источник `1a1ec824661c8501d79a1c026e74267e24a01d96` с полной историей
контрактов и reviewed correction ledger. Бэклог и общий supply workspace
объединились автоматически. Известный frozen scope-тест с фиксированным `0f1460b02`
не исправляется интегратором: отдельный тестировщик выполнит точную коррекцию.
C11 (настоящий общий стенд) и C12 (бумага) остаются открытыми. Сохранённые доказательства
не выдаются за новые прогоны. Предыдущий полный diff check выявил whitespace только
в неизменённых logs/patches WMS-662; они сохранены побайтно, проверка product/tests
и новых integration docs прошла. Следующий шаг — готовые 651/667/669/672/673.

## Интеграция 4 — WMS-651

База `022b242fd52c4470e217c76fa0d067a005b6b617`; источник `70bddc65ab39473a4560d791bd96d6b78acb648e` объединён автоматически, в том числе supply workspace с новой упаковкой/статусами. Сохранены исходная приёмка и доказательства. Следующий шаг — WMS-667. Тесты/CI ждут сведения всех дельт.

## Интеграция 5 — WMS-667

База `bd825cf58172abfc4f5ba64046f631afeeb01ed2`; включён принятый источник `9cc133d6a4883e0c76a7147794f4a8e557c29d20`. Продукт/тесты объединились автоматически. Конфликт добавления секций бэклога решён сохранением всех текущих задач и исходной секции667. Следующий шаг —669 и672/673. Общие тесты/CI ещё не выполнялись.

## Интеграция 6 — WMS-669

База `f60a4c0af3cafd04a4d70135ffc9ea0f21eda213`; источник `79b842ef692ab794d55be25049f3e181e3515539` включён с контрактами и корректировками. Продукт/тесты без конфликтов; объединены только независимые секции бэклога. Следующий шаг — scoped672/673. Общие тесты/CI остаются будущим общим этапом.

## Интеграция 7 — WMS-672/WMS-673

База `fa311770fcc41516cbfd168faee7c982be6d8920`; scoped reviewed источник `a13b59f0e326da56af0a0ee55cdbcfdbc590043c` объединён автоматически, включая supply workspace. Сохранены новые допечатки и чтение label context, исходные contracts/corrections и интеграционные доказательства. Интегратор не корректирует frozen ожидания. Следующий шаг — включить scoped517 и663 после конечныхSHA и зафиксировать карту сохранности всего продукта. Общие тесты/CI ещё не запускались.

## Интеграция 8 — независимая приёмка WMS-662

База `6c01a6dece601e9297929a41d4b1bb216db65908`; заключение отдельного аналитика `0fa4ea9542e41e8bcf498e1cd8a4967752c63246` включено без конфликтов. Это четыре документальных файла, продукт662 остался неизменён. Ранее готовые 651/667/669/672/673 уже включены. Следующий шаг — scoped517/663 и свежий675proof/план. Полный CI/общие тесты не запускались.

## Интеграция 9 — WMS-517 принятый продукт

База `1c1a1185261579d5f0e7cd516244b4fd52857440`; scoped источник `e93f9efba99032028444d7149268f1860dddd379` включён автоматически. Сохранён отдельный tests-before-code28671d78c и принятые blobs15тестов/6product; старый checker652 не перенесён. Исполнитель517 сейчас дочитывает WB events по штатному read-onlyGET, новые proof/helper будут включены отдельным опубликованнымSHA. Старое сообщение об отсутствии доступа не переносится как текущий факт. Следующий шаг —663 и финальные docs/helpers517/675. Общие тесты/CI ещё не запускаются.

## Интеграция 10 — WMS-663

База `69299ff9f755f5e00bf94e091544851549da8cd1`; scoped source `15d33af129a5608d7c7bf133ac5cfb29cce3a88f` включён с ancestry исходных контрактов/коррекций/ревью. Product663 и supply workspace объединились автоматически. Конфликты: независимая секция663 бэклога; analysis add/add, где входящая версия является прежней плюс исторический access-probe раздел, поэтому сохранён весь superset. Текущую675сверку этот исторический отказ не заменяет. Из663 перенесены только нужные принятые652fixture-governance дополнения, свежий checker не заменён старой смешанной веткой. C17UNKNOWN403 и C19operator остаются честно открытыми. Следующий шаг — конечные helper/proof517/675 и отдельная коррекция scope666. Общие тесты/CI ещё не выполнялись.

## Интеграция 11 — статическая карта сохранности

Точная сверенная версия `08e0d33ddb54dfa5f0712a316d879032441206dc`.
Собственная карта `priority-five-preservation-20261006.json` подтверждает ancestry
всех десяти включений и 131 путь продукта/контрактов/runner. Все уникальные пути
совпадают побайтно с соответствующим опубликованным источником. 66 etalon paths
вне разрешённых дельт также совпадают побайтно. Unexpected drift: отсутствует.
Единственный общий product path — FfFbsSupplyWorkspace.tsx, куда автоматически
объединены 662/666/651/672-673/663; его независимо проверит другой исполнитель.
Статическое чтение подтверждает сохранённые QR681 guards, Ozon QR disabled,
FbsStatusChip конкретного заказа, надпись «Обработано»651, документы663 и единый
scanner666. Это проверка интегратора, не независимое ревью/приёмка всего пакета.

Последние доступные product deltas включены. Отдельному тестировщику663 передан
этот SHA для frozen scope666 correction в своём worktree. Ожидаются опубликованные
helper/proof517 и read-only proof/план675; новыйruntime662 в675 не дублируется.
Общие тесты, полный CI, браузер Mac, внешние записи, merge main/etalon и deploy
не выполнялись. Каждый этап опубликован с [skip ci].

## Интеграция 12 — WMS-517 свежий полный набор и helper

База `9252ad203592d338ff6aba5ff1f129397d350f85`; включён конечный источник `e09eb757c1879bd87c43c276a514e65b4da07e9b` без конфликтов. Принятый product517 не изменён. Добавлены штатный read-only helper,84 подтверждённыхsold из246актуальных кандидатов и инструкции Виталику наMac. Подпись и отправка не выполнены и не объявляются выполненными. Parent организует короткое независимое ревью новогоhelper отдельно от уже идущего общегоproductreview08e0d33dd. Старый блокер чтения не переносится как текущий. Следующий шаг — новые realOzoncards/proofs675 и scope666 correction; общие тесты/CI ещё не запускались.

## Интеграция 13 — WMS-675 операционный источник

База `8fa213151859c82d8db27439a31da9b707f2729e`; источник `749b80cb85e3a15344c23fe83012d38af1ae99d4` включён без конфликтов:40операционных evidence/collector файлов, applicationruntime не добавлен. Отдельный исполнитель уже получил31realOzoncards и сохраняет свежийproof; ждём егоSHA перед актуальным675заключением. Исторические no-reader замечания в исходных proofs не выдаются за нынешний блокер. Текущий документWMS-675 отсутствует после намеренного scoped исключения663; финальный675документ должен быть явно включён с честным текущим вердиктом. Production ремонт/списание этим этапом не выполняется. Следующий шаг — scope666correction и свежий675SHA. Общие тесты/CI пока не запускались.

## Интеграция 14 — WMS-675 живые ответы Ozon

База `b0f9c3e07cbe97102604531281549ef986631579`; source `5b5da992a6cd766eb250ab83f4575fc8b11cdf22` включён без конфликтов. Сохранены31HTTP200,26положительных подтверждений передачи,4отмены и1ожидающийposting. Эти внешние факты не подменяются локальнымdone. Исходный исполнитель675сверяет свежиеledger/остаток/резерв и сохраняет точныйmissingdeltaплан и текущийrequirements675/backlog; планнеприменяется. Продуктобщейсборки08e0неизменен. Далее —финальный675документ,scope666correction и независимоеревью/приёмкаhelper517. Общие тесты/CI ещё не выполнялись.

## Новое основание WMS-662 — реальные подстатусы675

Точная версия `7cf8de3432f9c7568cb14959dc79a101d1d41beb` и сохранённые31livecards
выявили новый случай вне прежних приёмки/ревью. В `ozon_proves_handoff`
(`backend/app/services/fbs_observed_handoff_service.py`,218–229) allowlist подстатусов
отвергает delivering/posting_in_pickup_point9 и delivering/posting_on_way_to_city6.
Текущий код принимает только11delivered/posting_received из26положительных,
пропускает15. Все4cancel и1awaiting остаются FALSE. Это лично проверено выполнением
только неизменённого pure ASTclassifier на сохранённых JSON, без imports,
внешних операций или applicationmutation; exactрезультат сохранён рядом
в `wms662-live675-classifier-gap-20261006.json`.

Отдельный тестировщик сначала сохраняет RED-контракт этих двух реальных подстатусов;
интегратор не меняет product до testcommit. После него минимальныйfixallowlist,
целевые контрактные тесты и узкое независимое повторное ревью новогоcase.
Полученный отдельный productreview08e0PASS8e301dda остаётся фактом своего снимка,
а не доказательством новогоcase. Scope666correction0455cd0a также ожидает
отдельногоreviewPASS; ledgerPENDING не подменяется GREENтестом.

Обновлённая статическая карта на7cf8de343 сохраняет13sourceancestries,
132sourcepaths и66untouchedetalons; unexpecteddrift отсутствует.

## Интеграция 15 — независимое ревью общего product

База `5f1ec9a26e1f453e1e894184f6442330e9a3d9bd`; независимыйreport `8e301ddaf542d4823bcc14363e318f409fdc0935` включён без конфликтов. PASS относится кproduct08e0d33dd и сохранённым тогда cases. Новые реальные подстатусы662/675отдельно открыты; они будут закрыты контрактомдоfix и узким новымreview. Runtimeнеизменён. Общие тесты/CI ещё не выполнялись.

## Сохранённые сессии оставшихся этапов

Независимое CLI-ревьюproduct08e0d33dd: persistent thread
`01a110fb-c252-7011-b64e-d9267447d9de`, завершеноPASS;report8e301dda включён.
Исходный исполнитель675возобновлён в persistent thread
`01a110f1-70ef-7412-8700-0945d5c23e92`, execsession46309; JSONL
`.agent-runs/priority-five-20261006/675-plan-events.jsonl` хранит продолжение
scopedledgerrefresh и exactплана/docs675. Сырой поток здесь не копируется.
При обрыве продолжать эту сессию по сохранённому шагу, не создавать дубль.

Продуктовая граница нового662case: R2/официальная сохранённая таблица признают
точную карточку Ozon со status=delivering доказательством передачи; новые
положительные подстатусы подтверждены свежимиответами, а не guessedenum.
Awaiting/cancelled/unknownнерасширяются. Дождаться отдельногоREDtestcommit,
внести минимальныйfixдвухподстатусов, получить отдельныйузкийreview отparent.
Послеscope666reviewedcorrection и текущих675docs — общие проверки и PR/полныйCI
точногоитоговогоSHA, которые координирует ведущий.

## Интеграция 16 — отдельный RED-контракт WMS-662

База `8e64e14e8ea39adbe122191e209a329b7513b920`; test-onlysource `c466c65b850dd87481be5da88b99bcfaa4087414` включён ancestrymerge доproductfix. Одинновыйфайл с двумянастоящимиcards675; отдельныйтестировщик сохранил2positiveFAIL/10negative-or-receivedPASS. Текущиеcontracts иruntimeнеизменены. Теперьминимальныйfixдвухподстатусов и одинцелевойпрогон12cases; ожиданиянеизменять. Общие тесты/CI ещё не выполнялись.

## WMS-662 минимальный fix после RED

Контрактc466c65b включён и опубликован отдельнымmerge127884ce9 доfix.
Изменён только `ozon_proves_handoff`: добавлены двастроковых allowlist значения
posting_in_pickup_point иposting_on_way_to_city, без правок NEGATIVE, primary
statuses, scope/quantities, синхронизации, бухгалтерии и frozen test.
Собственныйцелевойpytest:12PASS,6existingdeprecationwarnings,0.05s;Ruffцелевого
модуляPASS. Факты команды/исходныйtestblob сохранены в
`wms662-live675-fix-verification-20261006.json`. Это узкийGREEN, полныйCIне заявлен.
Интегратор теперь автор этихдвухстрок и не подменяет их независимыйreview;
parent назначает отдельнуюсессию на точный опубликованныйfixSHA.
Следующийшаг —517helperreview/SC13docs,scope666reviewedledger иcurrent675docs,
затемобщиепроверки по поручению ведущего.

## Интеграция 17 — WMS-517 независимое заключение

База `b4043c0df9fee0419bdfe85167bbd645f820de9c`; source `85c2f5e0e24af84548e7ff74e193b3ac423d3f82` включён автоматически,4docs. Отдельныйreviewновогоhelper иSC13приёмкаfreshsoldсохранены; исходныйproductreviewнеповторялся. Новый662fixb4043c0dfпереданparentнаузкоенезависимоеревью. Scope666reviewedledger иcurrent675docsещёожидаются. Дополнительное675поручение: прочитать штатныеstockpublicationsideeffects восстановления, безновыхsuppressрежимов/monkeypatch.

## Интеграция 18 — принятая совместимость staging migration history

База `7f9d720ee47db130eaa9ef63df8325566c70dcd1`. Включена ancestry staging `727575a0fd47dec56f34b38b987925686626c2b9` и reviewedcompat
`c775941f373b89a9eaca70d0056673ff27a0dafa` через oursmerge, сохраняющий всё нынешнее runtime/tests/checker.
Затем восстановлены ровно9acceptedmigrationfiles из `7f7e922b16d8f2fa08816f8446e7a53a1d24ac74`;
каждый blob совпал также со staging727575a0. Исходные migration тела/revision IDs
не редактировались. Отчёт независимогоAstrareview сохранён исходнымфайлом.
НовыеDDL,DBmigration,stamp,downgrade иотдельныйdeployне выполняются.
Послеcommitкандидат станетdescendantstaging, возможенобычныйfastforwardбезforce.
Следующийшаг —локальнаяread-onlyпроверкаграфа/offlineплана, затемдожать675docs,
scope666ledger иузкий662reviewпередобщимteststage/CI.

## Проверка графа и side effects675 сохранены

Дляe45822aed локальнаяAlembicScriptDirectoryпроверка дала199revisions,
единственныйhead20261003_0001 и0upgrade шагов от действующейstagingrevision.
Staging727575a0являетсяancestor. Backendapp/tests,frontendsrc,currentchecker
иAGENTS/CLAUDE совпали побайтно с7f9d720ee. Это offline/read-only, безDB/DDL.
Proof: `priority-five-staging-graph-check-20261006.json`.

По поручениюparent прочитан штатный662recovery: расход/снятиеreserve планируют
обычнуюsellerstockpublication; suppress/monkeypatch не добавлен. Точный
sideeffects разбор6products и существующего billedquantityreuse сохранён
в `wms675-existing-recovery-side-effects-20261006.md`. Нового live repair нет.
Кодpublishercallback не гарантирует толькоoutercommit из-за savepoints;
эта граница записана без создания нового пользовательского запрета.

## Интеграция 19 — узкий662reviewPASS

База `082922a8ecb857d656f2cf6ee9a9521e35cb06b3`; независимыйreport `17e50faa3d13981b123ef7b093b2f97aefee9016` включён без конфликтов. Новыйcaseдвухживыхподстатусов наfixb4043c0df проверенотдельнойсессиейPASS. Самоинтеграторэтотрезультатнеподменял. Следующийшаг —current675requirements/plan53299b0b иreviewedscope666ledger, затемобщиетесты/CIточногоSHA.

## Интеграция 20 — WMS-675 currentrequirements/exactplan

База `d10b8ca786b912794c23912b1bdca13b42a3173c`; source `53299b0b7567a6f1b4c67b46fe4da8d0a039f36b` включён, восстановлентекущийrequirements675. Единственныйконфликтдобавленияbacklog675решён сохранениемвсехпрежнихсекций иточнойновой675. FreshSQL: missing26,reserve16→1;11facts/22chargesпереиспользуются,ожидаются15newfacts/30newcharges. Планнеприменён. Исходный675исполнительсейчасубираетизплана custom suppression и явноучитываетнормальнуюфоновуюstockpublication послеобщегопроверенногодеплоя. Этоещёdoccommit, runtimeне меняется. Scope666узкийP2fix30aea1fb проходитreview; ledgerPASSещёожидается. Подготовкаобщеготестовогоэтапаидёт, ни CI ни deployне запущены.

## Интеграция 21 — реальный scope666 PASS ledger

База `47afb0768b853d619d1790548d521a45c3d46b81`; конечныйreviewedsource `ef8aae5c469e94bcc44fd4acbdcbbf1ba80e817f` включёнбезконфликтов.
Actualcontract30aea1fbf/review2c24d7bb,обеcanonicalrefs записаныAstrahighPASS;
староеprovenance/FINDINGS сохранены. Runtime/checker неизменены. Всеproductdelta
и новыеузкиеreviews теперьвключены; общийтестовыйэтап начинается.

Предварительныйdocgateна47afb0768 нашёл реальные2стыкаимен:WMS651C5/R5scanner
иWMS657C2pickingprint. Не найдено точноезаявленноеимя в существующемtestfile.
Неослабленныетесты/ожидания интеграторомнеизменяются; parentполучилточныеошибки
для отдельнойсверкиexistingsemanticcoverage иcanonicaltestref/ledger.
PR/fullCI запускаются послеисправленияреальныхgateошибок,не ждуткосметики.
675ещёсохраняетdoc-onlyplan с обычнойstockpublication.

## Финальная граница общего CI

База `acd0523e9986e89149959319c74fd355c659d22e`; окончательный675source `ced5a713e56d3bb4fe2c310d3813306f08446ce2` включёнбезконфликтов.
Толькоexisting662послеобщегопроверенногодеплоя с normalstockpublication;
customsuppression/override удалены изплана, новыйruntimeнесоздавался.
Missing26/reserve16→1 с reuse11facts/22charges остаютсяпланом, не mutation.

Отдельныйтестировщик663 прочиталexisting651C5/R5 и657C2 наacd0523e9:
все прежние scan/data/immutabilityassertions сохранены. По прямойкомандеparent
исправлены ТОЛЬКО2точныеtestref ссылки вrequirements651/657. Тесты, ожидания,
correctionledger и checker не менялись. 65711-колоночныйtest ужеявляется
разрешённой673semanticmigration с дополнительнымЦветом. Дополнительноедокревью
не назначается. Послеgate/diff проверок этотcommit публикуется БЕЗ skip-ci,
создаётся общийPR и запускаетсяfullCIточногоSHA. Merge/deploy/repairне выполняются.

## Реальныйbackloggate восстановлен без новогоproductscope

ПослеdocgatePASS backloggate нашёл11 отсутствующих headings из ужеизвестных
stagingancestry (433/593–597/599/617/618) иscoped672/673. Восстановленыихточные
номера/названия по исходнымGitдокументам, с provenanceJSON ирабочимиссылками
наисторическиеснимки. Старые задачи явно помеченыhistoricalancestry-only:
новыйruntime/seed/DDLизнихнепереносится.672/673 связанысактуальнымиrequirements;
672полнаяприёмкачестнонеобъявлена,673сохраняетпринятие. Никакихновыхзадач,
тестов,checkerпослаблений илиизмененийproductизэтойвосстановительнойправкинет.

## PR387 и первый реальный CI

PR https://github.com/chivkunovd-bitdenis/WMS/pull/387 создан иattach_artifact
выполнен. ПолныйCI37460067342 запущенна066a5e95c08b9e91c7957e205b35b58ad16e2ab0.
Backlog/documentCIgatePASS; frontendtypecheck/CAdESprofilePASS.
Backend остановилсядоMypy/Pytest на15Ruffstyleerrors тольков2testfiles.
ЛокальныйfullRuffвоспроизвёлровноих; форматированиеисправлено, обаPythonAST
до/послепобайтноравны,assertions/состав/условиянеизменны. Proofсохранён.
ПослеформатированияfullRuffPASS;fullMypyPASS(563sourcefiles);целевые662/672
14pytestPASS(18existingdeprecationwarnings,7.34s);docgatePASS.
Этоне полныйCI-PASS: новыйcommitобновляетPR и запускает следующийfullCI.

Составпакетаизsource-map:662/663/666/517код+675operationalproof/plan;
651/667/669/672/673explicitmerges;653/657/659/660/670вetalonbaseсохранены;
681QRhotfixbaseи683productionhotfixancestryсохранены. Этообщийпакет,
а неотдельныйвыпускпяти. Новые незавершённые658/674/671/654 и681systemic
неподключались. Полнаявнешняяприёмка/бумага/подпись/apply не объявлены.
675functionalisolatedDBtest сохраняется тем же исполнителем и будетвключён
следующимSHA; самплан26единицневыдаётсязадоказанное проведениетестовойDB.

## Первый frontend CI — реальные failures

CI37460067342на066a5e95c завершёнFAIL. Backlog/guardsPASS. Frontend1517PASS,
8testFAIL+1suiteFAIL в6files: sizeevalharness,2QR681assemblyselectors,
oldWMS514sourceguard,2WMS636oldscannerselectors,2WMS666mixed/standaloneprintcases,
scope666historymissing. Точнаягруппа переданаparent; ожиданиянескрываются/неослабляются.
Дляruntime/fixtureразбораparentвыделяетотдельногоисполнителя.

Scope666 требуетoriginalcontract0e078 вGit, а стандартныйfrontendcheckout
CIбылshallow. Backend/frontendcheckouts теперьfetch-depth0, какdoc/guardjobs;
никакихskip/relax тестамне добавлено. Это исправление runnerконтекста.
НовыйCI37460722630идётна5ddd09aacпослеформатирования; онневыдаётсязаPASS.
Этотworkflowfixсохранитсяследующимкоммитом, когдавключаетсяfrontfixили675test,
чтобынеcancelполезныйbackendпрогонещёоднимнемедленнымheadupdate.

## CI corrections grouped before next push · 06.10.2026

Current integration: `4982e8fd6` includes live read-only663 source `5fb403a702f31edb5ba8508f3229fda803e6b904` and functional675 source `f98960a1e3d8adcc52264aafdad715f63e2397c5`. The conflict in requirements675 retained the newer ordinary recovery/publication plan `ced5a713e56d3bb4fe2c310d3813306f08446ce2` and added actual isolated testDB acceptance. No runtime change. Independent675 review `c3c6ee210fc92958e84ee58d86c4a606f54cba6c` is included as its exact report-only commit.

675 test is collected by ordinary full pytest with no skip and now has an explicit serial PostgreSQL CI step on a newly created loopback database `wms_test_675_incident`; standard conftest and server identity guards remain. The test uses real accounting/reservation/billing services; live external calls cannot occur.

CI2 on `5ddd09aac4df17e7ecdefaf1625462c05f8039ce`: Ruff/Mypy/guards passed, backend pytest running; frontend fixture incompatibilities and raw662 contract formatting caused failures. Formatting AST is identical; its actual Sol review and strict one-file correction provenance are coordinated with original tester663. No Ruff exclusions or checker scope relaxation. The narrow652 reviewer-model compatibility change will follow independent RED regressions. The next single push waits for the coordinated fixture/correction sources.

## Narrow process correction and functional validation · 06.10.2026

Exact checker-only correction `f263064f4c5735a477b91bd92bea982c9eeceaf5` follows separate tester source `2e94cf5f04a7863cf8abbe028126a6e48f8aee95`. Before code: 3 RED /67 PASS reproduced locally. After code:61 generic +9 exact fixture tests PASS, preserving all negative scope/SHA/blob/model/effort controls. Only actual Sol6.1 high joins historical Astra high; no product refactor or guard allowance. Independent narrow review assigned by leading agent.

Isolated formatting provenance662 `5feca959614667eb95e56a85e7b94efa497feeff` is retained by tree-identical ours merge `09dfb3c7ec4a591929e9db8c974c12c92b0772aa`; final662 blob identical to current formatted candidate. Original tester records the single-file ledger only after actual review artifact.

Shared675 incident test on integrated tree:1 SQLite PASS in3.12s; full backend Ruff PASS. Dedicated PostgreSQL step is retained for common CI; independent reviewer separately confirmed2 SQLite+2 PostgreSQL PASS without skips. Progress waits only for concrete fixture corrections/ledgers and exact narrow review reports before one grouped push.

## CI2 backend failure facts and integrated corrections · 06.10.2026

CI2 `37460722630` completed FAILURE on `5ddd09aac4df17e7ecdefaf1625462c05f8039ce`:4366 PASS,13 FAIL,2 ERROR,196 SKIP/1 XFAIL. New groups: generated OpenAPI missing2endpoint663paths;11 old475/537 cases assert one WB add but e2e mock pre-read claims orders already present;653scope evaluates whole package and rejects9 accepted stagingcompat migrations;2 realPG662 contracts incorrectly collected underSQLite. Separate executors own475/537 and653scope correction, expectations preserved.

Workflow/API correction `c884171aca6cbf72bc9ae6cc46d37cfa6afd7381`: two frozen662 contracts run unchanged in separate idlePG16services on exact55466/batch and55468/steady/userwms_test, serially with required asyncpg driver. OrdinarySQLite routing excludes only these two files, both mandatory below without skip/xfail. GeneratedAPI adds exactly2accepted663paths (`ozon-exemplar-documents` and `/prepare`),92existing path definitions unchanged; exporter also retains current accepted schema definitions. ExistingOpenAPI contract passed in local targeted run.

Actual narrow652 model review `74890bb821d3a881c16b2806c964ca8676d0b832` included report-only as `6f0dab804`, exactf263 PASS81/81. Historical676 C8 reference changed to current equivalent allowedmodel testcase and latest rule documented explicitly; original history retained. Fresh `git fetch origin etalon` still confirms base `4b298efc95be7b4b6b7fe5665be9f3671f1fe747`. No new base changes to merge.

Document integration gate discovered that historical514/636 tables use ID rather than required current header Проверка. Current supplement now links only independently accepted test harness maintenance, with truthful12/7existingtestsPASS and actual58/58review report; original product requirements/old acceptance not fabricated or replaced.676 renamedSol model testcase reference was aligned with newly authorized652 R40. Next gate rerun includes actual662/666correction ledgers.
