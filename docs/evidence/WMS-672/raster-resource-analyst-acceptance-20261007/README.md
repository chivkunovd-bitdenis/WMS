# WMS-672 / WMS-652: ограниченная приёмка замещающего аналитика, 07.10.2026

**Программная native bulk-decode дельта принята; точный product-reference25eb
одобрен для миграции интегратором. Выпуск и окончательная защита ещё не завершены.**

Исходный аналитик недоступен. Приёмку выполняет отдельный Sol6.1/high по прямому
поручению владельца; он не автор контрактов или исправлений. Постоянная ветка
`codex/wms672-raster-analyst-acceptance-20261007`, база`050544fb3bcb7aae87dbc0d60c5b6ae429b9acb8`.
Прочитаны свежие origin/etalon AGENTS, аналитический навык, исходный запрос/R1–R7,
последние уточнения652, прежние finish reports и полное reviewerbfba. Новых
агентов, модельных вызовов, runtime-тестов, сборок, браузера, сети/провайдеров,
физической печати, установок или чтения секретов/авторизации не было.

Таблица requirement→test→actual verdict и заключение находятся в
[WMS-672](../../../requirements/WMS-672.md#последняя-ограниченная-программная-приёмка--07102026);
bounded current state — в [WMS-652](../../../requirements/WMS-652.md#последнее-ограниченное-состояние-защиты--07102026).
Исторические FAIL/частичные вердикты сохранены. Functional-finish59a2 уже закрыл
C7/C10/C11; повторной приёмки неизменённых областей нет. C12 — после выкладки.

Принят продукт`25ebc6fe13384a55cf1f2b7e5e4054bb862d002d`; от d618 меняются ровно существующий обработчик ошибки
экрана и утилита печати. Непустая настоящая причина cross-realm отказа сохранена,
пустое/некорректное сообщение даёт прежнюю общую ошибку. Уже начатые16 peers завершаются
до очистки с той же первой причиной. Текущие исходные изображения временно
готовят1px неперекрывающийся raster в том же iframe; точные styles/HTML/CSS/PNG
возвращаются до handoff/error. Нет нового fallback/bypass/quota/sleep/retry.
Frozen native7/peer2/raster3 зафиксированы до кода; прежние7/2/11 неизменны.

Saved Linux37545334001 attempt1 diagnosticb3adc/product25eb,
Chrome141.0.7390.37/Node24.21.0:12 Node PASS0skip и **весь неизменённый C5 PASS83.784s**,
оба150/299 отказа без ранних передач/отметок, исправленные300 retries,
independent renderTape300 и все отметки. Другие10 browser cases не повторялись.
[Полное независимое ревью](../raster-resource-independent-review-20261007/review.md)
в`bfba7536566962de5c6bb16667b3ce80420d6302` не нашло блокирующего дефекта; independently229hashes/21suites/1173IDs
подтверждены, прежние228/20/1170 сохранены. В исходном manifest37 Linux artifacts;
в этом каталоге они не копируются и не редактируются, [acceptance.json](acceptance.json)
закрепляет прочитанные Git-input identities и точные два product blobs.

Positive retained prefix:299 original и299 scaled Add/Remove pairs balanced,
peak55; первые16 full-key→scaled→UnrefRemove происходят6.790–10.001ms до следующей
группы; reviewer реконструировал213 ранних цепочек. Источники141 поддерживают
интерпретацию, но14 source snapshots имеют разные границы accounting. Privatequota
не измерена. Wholetrace lateoverflow/dataLoss=true остаётся ограничением:
no-loss/whole-run completeness/мгновенное освобождение всех ресурсов не заявлены.
Эта граница не требует нового C5/capture или возврата исходного PASS в FAIL.

Одобрена **только** миграция ссылки`d61805978b3e7878d1056c99b4e6e0823edf49a5`→`25ebc6fe13384a55cf1f2b7e5e4054bb862d002d`.
Интегратор изменяет workflowref/digest, сохраняя frozen51 и существующий скрипт;
отдельный reviewer проверяет финальный SOURCE. Текущий CLI намеренно отвергает
эти2 app-пути относительно d618; в этом документальном этапе миграция не активирована.

Installed main04527 checker/workflow+config4e7b, старые BASE4b298/SOURCE0151,
strict9checks/no bypass и negativeprotectedcanary390 FAIL подтверждены saved receipts.
Production environment exactetalon установлен, harmless37531081039 denied steps[]
до echo. Это установленные metadata-барьеры, не принятие finalSOURCE/deployedprotection.
Prepared229/1173 требует финальной SOURCE-приёмки/config/fullPRCI/etalonCI и выкладки.
Oldfull37523087363 FAILED13m16; backup fixture отдельно15PASS и C5PASS не заменяют
новый wholeCI. Успешная цель fullCI10–15 минут не доказана. Production8f11d912 и
stagingcc8e по сохранённой передаче неизменны; live audit не выполнялся.
Softwaredeploy FIRST; бумага/517/подписи Виталия после него, без нового ожидания/вопроса.
