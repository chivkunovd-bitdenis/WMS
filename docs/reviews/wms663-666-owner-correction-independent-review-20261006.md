# WMS-663 / WMS-666 / WMS-662: независимое ревью новой коррекции владельца

## Текущее техническое заключение

**TECHNICAL PASS** на конечном продукте `1fe678d9abb4ed06afc79eba41461e3215978d5b`: выявленные F1/F2/F3 исправлены и узко перепроверены. Кодовых блокеров для стендового показа новой дельты663/666/662 не выявлено. **VISUAL PENDING:** реальную геометрию нового стенда reviewer не проверял и визуальный PASS не ставит. Общий CI нового кандидата, стендовый runtime и бумага остаются отдельными доказательствами; production/main/реальное применение675 не выполнялись.

Независимый reviewer: `gpt-6.1-sol`, effort `high`. Reviewer не писал новую продуктовую дельту и не изменял её тесты. Ниже сохранены первые findings и точная повторная проверка, без стирания истории.

## Область и первоначальное состояние

Ревью новой продуктовой дельты, а не повтор ранее принятого пакета. База runtime: `585877bedf948faf7e38d14acc7e89acbf4feab3`; эталон интерфейса для разрешённого отката: `727575a0fd47dec56f34b38b987925686626c2b9`. Первый сохранённый продуктовый SHA: `d4d1c658839d1cdbb8b9e50509f046a30bf5ffa3`; непосредственный родитель `c82808d37300cb1f90f9f0cdb19233ae41806aa7`. Тесты до кода: `4c38e1b9cc45437abec32d2c55ff1f2b40135138`. Аналитическая граница отката: `c395a68d3f2477fba8eda923f967dd69c7ca5b28`, `docs/reviews/wms663-666-frontend-rollback-scope-20261006.md`.

**Первый вердикт на d4d1: FINDINGS / исправление и узкая повторная проверка ожидались. Итоговый PASS на этом первом SHA не ставился.** Разработчик ещё сохраняет отдельные изменения геометрии666 и отката662; они не выдаются за проверенную часть первого663 SHA. Ревьюер не реализовывал эту новую дельту, не меняет продукт/тесты и не управляет общим релизным Git. Запись только этого отчёта в общий checkout прямо поручена ведущим; commit/push отчёта выполняет ведущий.

## Прочитанный контекст

Свежий `origin/etalon:AGENTS.md` (`4b298efc95be7b4b6b7fe5665be9f3671f1fe747`), обе библиотеки целиком (`owner-cases.md`, 104 строки; `failure-cases.md`, 359 строк), актуальное уточнение владельца в requirements663/666, пофайловый аудит отката и контракт нового тестировщика. Проверяются только новые one-batch backend, один control в Коробах, baseline geometry/wording/Link correction. Старые чипы списка588, QR681, stock и общая печать должны сохраниться.

## Первые технические замечания на d4d1c6588

### F1: прерванная подготовка до SET навсегда блокирует первую запись

Новый `save_absent_exemplar_documents` (строки713–723 в exactSHA) отправляет любой `choice.all_required_absent=True` в resume. Штатный claim сначала сохраняет `preparing`, `in_flight`, версию и этот choice до внешнего вызова. Если процесс прервётся до checkpoint SET, после истечения lease существующий `resume_exemplar_document_check` (485–496) корректно освобождает прерванную подготовку: `editable`, `in_flight=False`, version+1. Однако новый batch-choice остаётся true. Следующий явный POST вновь попадает только в resume и никогда не доходит до первого SET; UI также считает намерение выбранным.

Это чтение конкретного нового code path, а не сообщение о живой внешней записи. Независимый тестировщик получил штатную последовательность `claim_exemplar_write(kind=documents, choice=all_required_absent)` → истёкшая lease → новая DB-сессия/GET → явное действие актуальной версии. Требуется восстановить возможность первого SET для подготовки, которая ещё не checkpoint-ила SET. Потерянный ответ после фактического SET остаётся отдельным случаем: только STATUS, без повторной записи. Код и ожидания ревьюер не правит.

### F2: последующий штатный КИЗ стирает видимое сохранённое отсутствие и разрешает повтор SET

Новое `document_view.absence_selected` вычисляется только по текущему `choice.all_required_absent`. Существующий `submit_marking` начинает запись через `claim_exemplar_write(kind=marking, choice=...)`, который заменяет choice, сохраняя существующие choices. Поэтому после accepted batch → штатного КИЗ → GET новый boolean становится false, хотя сохранённое намерение отсутствия и актуальные документы остаются. UI `selected()` сразу доверяет явному false и не смотрит required absent-флаги; галка сбрасывается. Следующий explicit absent POST также не видит прежний batch-choice и может сделать второй SET отсутствия.

Новое поле и новая retry-граница должны учитывать сохранённый выбор, переживающий существующий маршрут маркировки. Требуется отдельный regression: batch accepted с точным полным readback → существующий submit_marking → GET/reopen absence_selected=true → повтор absent только STATUS, без третьего SET. Два допустимых SET здесь — первый документный и последующий маркировочный. Свежие изменения кабинета нельзя перезаписывать старой историей documents.

## Проверки и ограничения на этом этапе

Точные immutable blobs первого productSHA прочитаны через Git. Новый API использует существующий operator access и document_order tenant-check до выбора учётной записи; новый Workspace mount находится только в Ozon Коробах, row mount удалён. Полный posting payload строится через существующие snapshot validation, mark merge и durable send; эти наблюдения не заменяют проверки двух найденных recovery-путей и итогового нового UI.

Разработчик сообщил новые backend5 PASS и frontend6 PASS с ещё не реализованным отдельным wording-case; это авторские результаты, не независимый повтор ревьюера. Ревьюер пока не запускал новую DB/матрицу тестов, не выполнял внешний SET, браузер, печать, CI или deploy. Нет заявления о приёмке всех экранов, бумаги или документа Ozon.

## Следующий шаг

Отдельный тестировщик сохраняет два regression до исправления; разработчик исправляет findings и публикует окончательные productSHA666/662/663. Ревьюер проверяет исправленные конкретные code paths и конечный ограниченный diff, сохраняет точные результаты/визуальные evidence и только затем формулирует итоговый вердикт. История F1/F2 остаётся в отчёте.

## Отдельные RED-контракты замечаний до исправления

Тестировщик опубликовал однофайловый test-only `2afefa04e1b921ba94c40ba17887ee987a7c2589`; proof `f660fbe5f545c5519f7d81212c976d5f8c3d281d`, `docs/evidence/WMS-663/absence-recovery-test-contract-20261006.md`. Ревьюер прочитал точный новый файл `test_wms663_absent_pre_set_recovery_contract.py` и proof. На первом productSHA фактически получены **2 FAIL / 0.97 s** по целевым assertions, а не сборке/окружению: F1 editable/version2 ещё имеет absence_selected=true; F2 accepted batch и настоящий marking SET уже выполнены, но последующий полный readback имеет absence_selected=false. Это результаты отдельного тестировщика; независимый запуск reviewer ещё не выполнен.

Оба теста используют существующие реальные сервисы. F1 начинает штатный claim, меняет только lease через штатный checkpoint и продолжает новой DB session; после разрешённого первого SET теряет его ответ и требует STATUS-only без второго SET. F2 получает exact matching batch readback, выполняет существующий `_scan`/submit_marking, проверяет документы/weight и добавленную mark, затем перечитывает полный marked payload и запрещает третий SET. Прежние пять guards сохранены. Тесты зафиксированы до runtime-исправления.

## Прочитанные отдельные frontend-коммиты, пока без итогового PASS

`6b6ff12c1b670b3914d64528a471dea90680c5c4` меняет только Workspace/Assembly: optional Size/Available-KIZ слоты согласованы между текущими supplies; возвращён прежний flex и убраны Ozon-only flexWrap/useFlexGap, подпись снова «упаковано»; отсутствующий Ozon QR занимает невидимый слот штатной ширины кнопки, без новой QR-кнопки/задания. `a853239214de613d1cadc9945092c98f7186f9a7` удаляет только добавленный status chip/Stack в Составе и возвращает Link непосредственно в TableCell. Delta `FbsAssemblyTaskRows.tsx` от727 доa853 пустая: прежние чипы588 не удалены. Авторские 44 frontend PASS, 74 backend PASS/1 PG skip и tsc/build PASS не приписаны reviewer. Реальная геометрия и окончательный исправленный663 SHA ещё ожидаются; итоговый PASS не поставлен.

### F3: заказ без требуемых документов мешает общей галке показать завершённый выбор

На первом663 SHA UI `checked` (OzonDocumentsAbsence69) требует selected=true для каждого orderId поставки. У заказаB с полным подтверждённым составом экземпляров, но без требуемых ГТД/РНПТ, batch no-choices ветка758–761 очищает batch-choice и возвращает absence_selected=false. Поэтому в поставке[A с requiredГТД, B без обоих требований] после успешного выбора всех документовA общая галка остаётся indeterminate; повтор снова подготавливаетB, которому absent вообще не требуется.

Это конкретная новая multiorder-агрегация, сообщённая автору/ведущему как P2. Нужно отличать отсутствие требований в полном известном snapshot от пустого/неизвестного products: последнее не является доказательством отсутствия требований и не разрешает убрать явное техническое получение экземпляров. Новый DOM-case и продуктовый fix ожидаются; reviewer не выполнял живой SET и не меняет тесты. Unknown/rejected частичный результат должен остаться различимым.

Ведущий уточнил границу заключения: после исправления технических findings отдельно дать вердикт о наличии кодовых блокеров для стендового показа. Реальную geometry GREEN он получит на exact staged candidate отдельно; source/DOM assertions не выдаются за визуальный PASS. После предъявления реального geometry proof окончательное узкое заключение дополняется без повторного ревью старого пакета.

## Узкая независимая перепроверка F1/F2 на d01e0b888

Точный опубликованный runtime-fix: `d01e0b8885e85004dffac4d6c1e27e8d39bb8a90`, только `backend/app/services/ozon_exemplar_documents_service.py` (+21/-4). Тестовый контракт двух замечаний `2afefa04e1b921ba94c40ba17887ee987a7c2589` присутствует до fix в ancestry.

Ревьюер самостоятельно запустил ровно два новых regressions и пять исходных owner-batch guards: `python -m pytest -n 0 -q tests/test_wms663_owner_absent_batch_contract.py tests/test_wms663_absent_pre_set_recovery_contract.py`. Результат **7 PASS, 0 skip**, 1.16s, exit0 (6 прежних deprecation warnings). До/после запуска исходники service и обоих тестовых файлов сверены с immutable d01e blobs и сохранены неизменными; это не прогон общей74/76 матрицы и не CI. Логи/точная команда: `.worktrees/wms653-scope-independent-review-20261006/.agent-runs/wms663-owner-independent-review-20261006/backend-seven.{log,json}`.

**F1 CLOSED:** освобождение истёкшей preparing lease очищает только unsent batch-choice; версия повышается и старый preparer fenced, первый новый явный SET разрешён. После checkpoint SET неизвестный исход по-прежнему читается STATUS-only; retry не создаёт второй SET. Snapshot/реальные документы не стираются.

**F2 CLOSED:** новый helper получает intent из существующих choices и requirement flags snapshot, переживающих маркировочный claim. Ответ и batch retry-guard используют одинаковое вычисление. Существующий `_scan`/submit_marking действительно отправляет marking payload с сохранёнными документами/weight; subsequent GET сохраняет выбранную галку, дополнительного absence SET нет. Нового независимого bool/store/реестра не введено.

Это закрывает технические findings F1/F2. **F3 ещё OPEN до test/fix и точной узкой перепроверки; технический PASS всей коррекции и реальный geometry PASS не поставлены.** Ранее прочитанная frontend geometry/Link delta остаётся отдельно; авторские tsc/build и76PASS/1PGskip не объявляются независимым выполнением reviewer.

## F3: самостоятельный тестовый контракт до UI-fix

Тестировщик сохранил ровно один новый DOM-case `68c3bd3052e201c16b8f9a1d0fe1282cc91615c3`; proof `cdd84eaaba2a76fd6ecae6321f525dcf54fc3f75`, `docs/evidence/WMS-663/required-order-checkbox-test-contract-20261006.md`. Ревьюер прочитал точный файл/proof. На исходном d4d1 фактически **1 FAIL / 1.31s**: extra POST наB с expected_version7, хотя его полный snapshot явно не требует ГТД/РНПТ. Opening GET-only уже прошёл; последующие checked/no-partial/reopen assertions ещё не достигнуты на RED и не приписываются ему как PASS. Runtime и прежние cases не изменены. Fix ожидается после этого контракта.

Отдельный обязательный артефакт новой API-ручки передан разработчику: FBS OpenAPI export пока не содержит `/ozon-exemplar-documents/absent`; существующий `test_exported_fbs_openapi_file_matches_live_schema` проверяет точное равенство path-объектов. Нужно штатное обновление exporter без изменения теста или старых endpoints. Это проверка опубликованного API-артефакта новой дельты, не новое продуктовое требование.

## F3 CLOSED: точная completeness-дельта и независимый целевой GREEN

Окончательный runtime-fix `1fe678d9abb4ed06afc79eba41461e3215978d5b` добавляет только вычисление requirements_complete из уже прочитанных FbsOrderProduct и snapshot: точное множество SKU, отсутствие повторов SKU, точные количества экземпляров, уникальные положительные реальные ID. Новых SQL/внешних calls, сохранённого bool, таблиц/статусов нет. UI исключает posting из общего выбора/POST только при requirements_complete===true и явных false обоих требований у полного списка экземпляров. False/undefined и неполный состав не превращаются в отсутствие требований.

До этого кода сохранён отдельный контракт `f938b2dba65c2d2f8605e78b087eb2076b5e8fda`; fixture annotation `a08c98f77d9f39d0ed7991bb8fd6f19f21ebef62` также присутствует до fix. Самостоятельный reviewer-прогон: backend `test_wms663_requirements_completeness_contract.py` **3 PASS**, 1.46s, 0skip; Node20.20.2/Vitest frontend required-orders + incomplete-requirements **3 PASS**, 3.12s, 0skip. Полный состав против missingSKU/missingQuantity, истинно не требующий документовB и false/undefined completeness защищены фактическими assertions. Исходники и тестовые blobs до/после проверены на точное совпадение с immutable1fe. Прежние7 backend PASS наd01 и авторская общая44матрица не повторялись. Логи/команды: `.worktrees/wms653-scope-independent-review-20261006/.agent-runs/wms663-owner-independent-review-20261006/f3-backend.{log,json}` и `f3-frontend.{log,json}`.

## Фактическое независимое ревью owner-supersessions старых UI-контрактов

Reviewer `gpt-6.1-sol`, effort `high`, отдельная от автора кода и тестов сессия. Исходный опубликованный runtime/test source для обеих замен: **`585877bedf948faf7e38d14acc7e89acbf4feab3`**. Прямое поручение владельца закреплено в `4c9e1238c85a50a9238bc109651c79cac5f10e03`, `docs/reviews/wms663-666-frontend-rollback-scope-20261006.md`, blob `664aa8ea5e279c04f9b6219a8440142fd7bc142a`; его смысл соответствует прочитанному аудитуc395. Это semantic owner override, а не косметическая fixture correction.

**WMS-662 exact final test correction `667a136a2760ff62fc181f47772290a8388587c6`: PASS.** Файл `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms662.c19.dom.test.tsx`, before `04379c221c29e9a70ae195ff3d834e1855b375de`, after `eda2d0d82663c76a3042e3a161fb47f164ad4f08`. Прочитан весь точный diff: отменены только две soft-проверки текста нового composition chip и использовавшийся ими visibleText helper. Вместо них проверяются отсутствие нового chip и прежний history Link непосредственно в TD. Остальные navigation/picking/history/reopen/read-only assertions и запрет внешних writes/печати сохранены. Это выполняет прямой откат нового оформления владельцем; не означает отмену учётного поведения662 и не разрешает изменение backend-контракта.

**WMS-663 exact final test correction `23b222dede4869ae6035c55175f5d14f6a6af5f4`: PASS.** Исходный source тот же полный585; опубликованный переход `35ac50caa77f1ca5eb1905a23a730e1dee1e2f45` → final23b прочитан вместе с новым конечным файлом. Before после исторической fixture chain: `7b41916c43bf144d9fdeb7772d415bdf5535ff05`; промежуточный blob `87d14b74cbfa4f7f119bb0c6374929259fed5dc5`; final `e177548bb5a728cad63b32528071c1c5ac9995e1`. Старый C16 строковых форм отменён прямым поручением, а не сохранён под видом равнозначности. Новые семь cases проверяют отсутствие row UI, одну галку в Ozon Коробах/WB boundary, GET-only open, точные текущие order/version явного POST, persisted unknown intent/reopen/no repeat, существующий error alert/доступное закрытие и прежнее «упаковано». Final23b связывает error assertion с существующим supply alert; новых панелей не требует. Старые backend документы/marks/weight/tenant/unknown guards не изменены. Эти разрешения относятся строго к названным полным SHA/blobs, а не к будущим правкам ожиданий.

## Фактическое независимое ревью точной F3 fixture-дельты

**`a08c98f77d9f39d0ed7991bb8fd6f19f21ebef62`: PASS**, reviewer `gpt-6.1-sol`, effort `high`. Source `68c3bd3052e201c16b8f9a1d0fe1282cc91615c3`; единственный путь `frontend/src/screens/v2/OzonDocumentsAbsence.required-orders.dom.test.tsx`; before blob `5a508673b78388e44c903fe503fd76f3e48a7cde`, after blob `d96fd44965a7f0b8806d87fe3d4f88243cad1f5e`. Ровно одна строка полного, известного по контракту B получает `requirements_complete:true`. Ни один assertion, запрос, порядок действий или контроль A не изменён. Это annotation знания полного no-documents fixture; неизвестные/partial ответы защищены отдельными до-кода f938 negative cases и самостоятельно дали GREEN на1fe. Не разрешается переносить true на partial/undefined данные.

## Граница технического PASS и дальнейшей приёмки

Новая runtime-дельта прочитана на exactSHA; прежние чипы588 не изменены, новый composition chip удалён, row-document runtime mount отсутствует, stock/continuous-print/QR681 исходники не затронуты этой коррекцией. Новый endpoint экспортирован штатным `c7c079262fa39289554542e93d0134b103835746`; diff добавляет только путь/body, авторские четыре existing OpenAPI tests PASS и tsc/build не приписаны самостоятельному reviewer-прогону.

Технический verdict позволяет показать этот кандидат на стенде, но не подтверждает визуальную геометрию. Ведущий отдельно выполняет настоящую geometry-проверку exact установленного кандидата; она должна быть предъявлена перед визуальным заключением. Приёмка аналитиком, новый полный CI/деплой и физическая бумага не заменены этим code-review. Отдельный process-checker8b находится в следующем узком ревью; его вердикт здесь пока не поставлен.
