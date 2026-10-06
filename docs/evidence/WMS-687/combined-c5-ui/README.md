# WMS-687: совместная C5, промежуточный результат

CUA выполнена на точном **provisional integration SHA05da854733eb35584c096b9995b52ae8aafe6877**, worktree night1007-integration. Это согласованная ведущим совместная сцена reviewed687+684/586; известный backend PDF pagination defect255char/128line ещё открыт. **Финальная приёмка WMS-687 пока не объявляется**, окончательный C5-verdict требует технического PASS соседнего исправления и сверки неизменности проверенных frontend blobs. Данная роль не принимает WMS-684/586 и не выпускает provisional SHA.

Проверен настоящий `FfInboundRequestView`, штатная muiTheme и тот же настоящий `FbsStockDialogContainer`, с искусственными GET-данными. Сцена использует предыдущий acceptance687 harness; добавлены две normal export fixture и один demo-короб. Корректный искусственный unsigned claims payload задаёт только тестовые tenant/user для существующего локального recovery store; он не является credential и не используется во внешних системах. Product/tests/guards не менялись.

## Фактическая совместимость

- В завершённой приёмке и возврате с длинными названиями выбор обеих строк показывает «Задать остаток» в том же контексте, рядом остаются «Печать накладной», «Акт приёмки · Excel», «PDF», «Сохранить», «Закрыть». На обычной ширине1440 кнопки читаются и не перекрывают друг друга; прежнее сокращение длинного товарного названия многоточием сохранено. Screenshots01/04.
- Нажатия Excel/PDF отправляют обычные GET acceptance-act.xlsx/pdf именно текущего документа, не открывают stockdialog и не сбрасывают выбор. Ответы — явно отдельные synthetic artifacts, созданные actual current backend helper на двух обычных synthetic строках (5513xlsx/16505pdf). Они не являются результатом живого API/данными текущей БД и не доказывают исправление граничной PDF pagination. Получение файлов в Downloads отдельно не подтверждалось в этой среде.
- «Задать остаток» открывает ту же существующую форму для2товаров: сохранённые публикацияtrue, unitsvalue7, складWB↔ФФ. «Отмена» закрывает её, выбранные товары и соседние действия остаются. Screenshots02/05. Новых режимов, полей или форм нет; сохранение/внешняя передача в этом узком C5 не запускались, эти сценарии уже имеют отдельную приёмку687.
- «Короба и грузоместа» → прежняя «Печать» → прежний размер58×40. Внутри самой QA-сцены iframe.print перехвачен app-owned test-safe control, поэтому физическая/системная печать не запускается. Реальный product print helper сформировал HTML с barcode INB-C5-DEMO-687 и реквизитами «Короб№1», «Селлер WMS-687», «Приёмка687от07.10.2026». Встроенный QA iframe показывает именно этот HTML; mock-only mark-label-printed и reload не потеряли выбранные строки/stockentry/Excel/PDF. Screenshots03/06 и обаDOM. Это preview-совместимость и сохранность фронтового вызова, не бумага и не факт нанесения.

Первый print-preview попытался писать durable storage с прежним bare fixture-token и дал `.replace` на отсутствующихJWTclaims. Прямой helper со сценовым barcode прошёл, а source inboundDraftPersistence подтвердил точную причину. Исправлен только QA token payload; productкод/поведение не менялись. После этого штатный путь печати прошёл до mock technical mark/reload. Этот сбой не скрыт и не выдан за продуктовый fix.

Проверка390px общегоstockdialog уже ранее записала тот же baseline дефектcatalog; здесь дополнительных переделок нет. Сканы/права/реальные остатки не перепроверялись без новых причин. Backend586 extremePDF, physicalprinter, native download receipt, marketplace transmission и production не принимаются по этой сцене.

## Передача

Сохранены6screenshots,2DOM,точныйQA source и representative syntheticPDF/XLSX. `tested-source-blobs.json` содержит неизменяемые gitblob идентификаторы проверенных frontend путей для сравнения с финальным technicallyPASSED candidate. При совпадении UIsource не требуется повторять этот же проход; при изменении frontend нужен адресный новый C5.

Воспроизведение: fixturemain/index положить в frontend/.agent-runs/wms687-browser, artifacts normal-act.pdf/xlsx рядом; existingVite4687, `/.agent-runs/wms687-browser/index.html?operation=inbound` или return. Все неизвестные API routes отклоняются. Собственный browser tab закрыт; никакихWB/productionwrites. Отдельный финальный C5-verdict появится после переданного технического PASS и source-blob equality, а не по времени ожидания.
