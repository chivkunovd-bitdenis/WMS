# TASKLOG

## TASK-112 — 2026-07-09 — Этикетка ШК: фикс сплющенной строки ИП (не trim)

- Баг: на проде «ИП Горячкина Т И» визуально сплющена и почти касается названия (фото с красной рамкой). PR #94 (обрезка низа) баг не закрыл.
- What changed: `printProductThermalLabel.ts` — `labelTextFontScale` (потолок роста шрифта), line-height 1.35, min-height seller, gap/margin от цифр, убран `-webkit-line-clamp`; превью диалога синхронизировано; BUGLOG BUG-5; скрипт proof `verify-seller-line-height.mts`.
- What did NOT change: политика trim снизу остаётся как страховка на 58×40; native PDF ЧЗ.
- Verification: unit 12 passed; Playwright metrics gap seller/name > 1.5px на всех размерах.

## TASK-111 — 2026-07-09 — Этикетка ШК ВБ: построчная обрезка снизу + фикс «слипания» ИП

- Баг: на 58×40 / 60×40 строка ИП (напр. «ИП Горячкина Т И») визуально «слипалась» — буквы наезжали друг на друга, потому что нижние строки (название с `-webkit-line-clamp`) сжимались в flex вместо обрезки.
- What changed: `frontend/src/utils/printProductThermalLabel.ts` — текстовые строки (ИП → название → артикул → детали → отзыв) собираются в список; по расчёту высоты под штрихкодом нижние строки убираются по одной; обязательный минимум — ИП (если есть) + название + артикул; CSS: `flex-shrink: 0`, `overflow: hidden` на `.body`, зазор 0,5 мм, явный `line-height`; футер «оставьте отзыв» внутри обрезаемого блока (уходит первым на низких форматах). Проброс `labelSize` в `buildProductLabelSectionHtml` и ленту ЧЗ+ШК.
- What did NOT change: штрихкод, native PDF ЧЗ-артефакты, размеры этикеток в `labelSize.ts`.
- Verification: `npm run test:unit -- src/utils/printProductThermalLabel.test.ts` — 10 passed; `npm run build` green.

## TASK-110 — 2026-07-08 — Упаковка МП: одна строка на товар (убрана привязка к ячейке)

- Баг: в отгрузке на МП было 2 товара, но на вкладке «Упаковка» показывалось 3 строки. Причина — строки задания на упаковку строились из подбора (pick allocations) по ключу «товар + ячейка склада» (`packaging_task_service.sync_lines_from_pick_allocations`); если один товар подбирали из двух разных ячеек, на упаковке появлялись две строки для этого товара, а ячейка на UI не показывалась — визуально «лишний товар из ниоткуда».
- What changed: `backend/app/services/packaging_task_service.py::sync_lines_from_pick_allocations` — теперь агрегирует подбор по `product_id` (суммирует количество со всех ячеек) и всегда пишет строку в единую сортировочную ячейку задания, т.е. **одна строка = один товар**, независимо от ячеек. Дополнительно консолидирует уже существующие в БД задвоенные строки одного товара (сложение `qty_packed_in_task`/`qty_confirmed_packed`/`qty_marking_printed`, удаление дублей) — чинит и уже испорченные старые задания, не только новые.
- What did NOT change: обычные (не-МП) задания на упаковку (`create_manual_task`, приёмка) — там ячейка остаётся значимой для реального списания остатков и логика не тронута; `sync_lines_from_unload_plan` (план до подбора) уже и раньше был «один товар = одна строка».
- Verification: новый регрессионный тест `test_marketplace_unload_packaging_one_row_per_product_across_cells` (`backend/tests/test_marketplace_unload_and_discrepancy_acts.py`) — подбирает 1 товар из 2 разных ячеек + второй товар из третьей ячейки, проверяет, что на вкладке «Упаковка» ровно 2 строки (по числу товаров), с корректной суммой количества. Без фикса тест воспроизводит баг (3 строки вместо 2) — проверено откатом изменения и повторным прогоном. Полные гейты: `ruff check .` — чисто, `mypy .` — чисто, `pytest` — 345 passed.

## TASK-109 — 2026-07-08 — Убрана «печать пачками» для ленты (ЧЗ и ШК)

- Проблема: HTML-fallback печати ленты (когда native PDF ЧЗ не собрался) резал секции по 20 штук и открывал отдельный диалог «Печать пачками» с кнопками «Печатать пачку N/Повторить/Готово» — лишний шаг, которого никто не просил ни для ЧЗ, ни для ШК.
- What changed: `MarkingPrintDialog.deliverTape` — HTML fallback печатает все секции одним заданием (`printTapeSections`) независимо от длины; удалены `PRINT_CHUNK_SIZE`, `ChunkPrintJob`, `chunkJob`/`setChunkJob`, `printChunk`/`finishChunkJob`/`abortChunkJob` и весь диалог «Печать пачками»; удалён e2e-тест `TC-NEW-CHUNK-PRINT-01`, который проверял именно эту убранную механику.
- What did NOT change: native PDF путь печати ЧЗ (`printCzArtifactTape`) — им и раньше печатали одним заданием; логика «Количество этикеток» + «Печатать 2 ШК» из TASK-108.
- Verification: `npm run build` (tsc + vite) green; ручной grep подтвердил отсутствие остаточных ссылок на `chunkJob`/`PRINT_CHUNK_SIZE`/«Печать пачками» в `frontend/`.

## TASK-108 — 2026-07-08 — Печать: ручное кол-во этикеток + ТЗ альбом

- Проблема: в диалоге печати ШК ВБ множитель зависел от кол-ва к упаковке; сводное ТЗ печаталось книжной ориентацией, ШК был в одной строке с артикулами.
- What changed:
  - `MarkingPrintDialog`: поле «Количество этикеток» (ручной ввод, без × qty строки/упаковки); чекбокс «Печатать 2 ШК» (×2); то же в раздельном режиме ШК.
  - `printShipmentPackagingSheet`: `@page size: A4 landscape`; ШК отдельной жирной строкой в шапке карточки.
  - Тесты: vitest `resolveManualWbLabelCount`, e2e double-checkbox и landscape TZ.
- What did NOT change: печать ЧЗ, лента ЧЗ+ШК в одном задании, каталог `printProductBarcodeFromMeta` (pack_units там по-прежнему).
- Deploy: PR #89 → `main` `3074cc6`; Deploy Production run `28937861849` success; smoke `http://194.87.96.144:8088` FF/seller/health HTTP 200.

## TASK-107 — 2026-07-08 — ШК на 70×120: одна наклейка, не две

- Проблема: на 70×120 (и 60×80) ШК масштабировался по `k.h` → высота ~42 мм, контент вылезал на 2-ю физическую этикетку.
- What changed: `uniform` + `object-fit: contain`; тесты на все 4 размера (`printProductThermalLabel.test.ts`).
- Deploy: PR #88 → `main` `45c783e`; prod SSH `prod-update.sh` + `compose down/up` (docker name conflict), FF/health HTTP 200.

## TASK-106 — 2026-07-08 — Приёмка: колонки таблицы + кнопка печати в строке

- Проблема: в таблице приёмки «Заявлено/Принято» уехали вправо с пустотой посередине; иконка печати ШК/ЧЗ в строке пропала (`showPrint={false}` + sticky qty).
- What changed: вернули `FfProductMarkingPrintProvider` + `productId` в строках; убрали sticky у qty-колонок; e2e guard на кнопку печати.
- What did NOT change: «Печать накладной» в шапке; логика скана/коробов.
- Deploy: PR #87 → `main` `4627aba`; prod `194.87.96.144:8088` — `prod-update.sh` (SSH, без ожидания CI), FF/health HTTP 200, bundle `ff-qlw_kW4p.js`.

## TASK-105 — 2026-07-08 — Hotfix: кнопка «Печать» молчит (native PDF)

- Проблема: после PR #84 при печати ЧЗ диалог закрывался, окно печати не открывалось.
- Root cause: `printPdfBlob` fire-and-forget + 0×0 iframe; user gesture терялся после async fetch.
- What changed: Promise в `printPdfBlob`, off-screen iframe, `beginPrintUserGesture()` по клику, HTML fallback при сбое native PDF.
- Commit: `eacb3ed` (PR pending).

## TASK-104 — 2026-07-08 — Native PDF печать ленты ЧЗ из артефактов селлера

- Проблема: путь PNG→HTML→iframe давал «в точки» DataMatrix и неверную раскладку на высоких наклейках; нужна печать как «открыть PDF селлера и Print».
- What changed:
  - Backend: `merge_label_artifact_pdfs`, `build_label_artifact_tape_pdf`, `POST /operations/marking-codes/label-artifact-tape` — склеивает нарезанные PDF артефакты в порядке ленты (до 500 стр.).
  - Frontend: `printCzArtifactTape` — если лента только ЧЗ и у всех единиц `hasLabelArtifact` → native PDF через `printPdfBlob`; иначе прежний HTML fallback (PNG/генерация). CSS `rotate(90deg)` убран из artifact HTML path.
  - Tests: `test_label_artifact_tape_merges_pdfs_in_order`, `test_merge_label_artifact_pdfs_empty_raises`; vitest `resolveCzArtifactTapeCodeIds`.
- What did NOT change: mixed ЧЗ+ШК лента; WB labels; import/narезка; fallback `buildCzLabelHtml` при отсутствии артефакта.
- Verification: backend pytest 337/337, ruff+mypy ok; frontend vitest 11/11 в `printMarkingCodeLabel.test.ts`, `npm run build` ok.
- Commit: `d7dc69e` (PR #84).

## TASK-103 — 2026-07-08 — Печать ЧЗ строго из PDF селлера + поворот на высоких размерах

- Проблема: ЧЗ-этикетка селлера физически альбомная 60×40. На высоких наклейках (60×80, 70×120) печаталась узкой полосой с большими пустыми полями. 60×40 печатался идеально, т.к. совпадает с размером PDF селлера.
- What changed:
  - Frontend `printMarkingCodeLabel.ts` (артефакт ЧЗ): на высоких размерах (высота/ширина ≥ 1.2 → 60×80, 70×120) картинка селлера поворачивается на 90° (`transform: rotate(90deg)`, бокс = высота×ширина, `object-fit: contain`) — заполняет наклейку по высоте без искажений. На 58×40 / 60×40 — как было (`width/height 100%`, `contain`).
  - Backend `pdf_bytes_to_png`: перед рендером PNG артефакт обрезается по содержимому (`_content_clip_rect`) — убирает белые поля.
- What did NOT change: ШК ВБ и «самодельная» ЧЗ (`buildCzLabelHtml`) — вернул ровно к прод-версии (#79), не трогал; размеры `labelSize.ts`; раздельная печать; нарезка артефактов (`extract_label_artifacts_from_pdf`); API.
- ЧЗ формируем строго из PDF селлера (нарезанный `label_artifact_pdf`); генерация своими силами — только запасной путь при отсутствии артефакта.
- Данные: уже нарезанные артефакты пере-обрабатывать НЕ нужно — раскладка применяется на печати, деплоя фронта достаточно. Пере-нарезка нужна только кодам без артефакта (CSV/многокодовая страница/старый импорт); прод-данные ЧЗ ранее очищены (TASK-101), после повторной загрузки все коды получат правильный артефакт.
- Verification: реальный движок печати Chromium (`page.pdf` в мм) → `output/pdf/_verify/artifact-final-bordered.png` совпадает с эталоном; backend `pytest test_marking_pdf_label_artifact.py` 7/7, ruff+mypy ok; frontend `vitest` 85/85, `npm run build` ok.

## TASK-101 — 2026-07-07 — Хранение оригинальных PDF при импорте ЧЗ

- What changed:
  - PDF-импорт: best-effort сохранение оригинала (ошибка storage **не блокирует** импорт КМ).
  - Backends: S3 (`WMS_S3_*`) или local (`WMS_DATA_DIR`, только dev/tests).
  - Prod compose: local storage off by default, S3 env из `.env`.
  - Script `scripts/wipe_marking_data.py` — dry-run / wipe всех ЧЗ для чистого re-import.
- What did NOT change: prod wipe (нужен ручной запуск); S3 bucket создаётся вручную.
- Verification: `pytest tests/test_marking_pdf_label_artifact.py` 6/6.
- Commit: `1b19b77` (PR #80), deploy fix `PR #81`.
- Prod deploy: GitHub Actions `Deploy Production` run `28866993394` success, 2026-07-07.
- Prod wipe: `scripts/wipe_marking_data.py --apply --confirm WIPE-MARKING` on `194.87.96.144` — было 833 codes / 7 pools; после 0.

## REMINDER — ~2026-07-07 evening — Настроить бэкапы БД на проде

- Owner action: включить автоматические pg_dump / snapshot Postgres (Railway/hosting panel).
- Пока нет — риск потери данных при wipe/миграциях.

## TASK-100 — 2026-07-07 — ЧЗ: split-print refresh + клиентский PDF artifact

- What changed:
  - Frontend: refresh `separate_marking_print_enabled` из `/auth/me` при открытии `MarkingPrintDialog`; inline reprint по клику «Печать ЧЗ» при уже напечатанных КМ; ориентация печати ЧЗ; artifact image на всю наклейку.
  - Backend: `extract_label_artifacts_from_pdf` — crop отдельной этикетки на каждый CIS при PDF-импорте; валидация `is_printable_label_artifact`; endpoint `/label-artifact` не отдаёт multi-CIS страницу.
  - Импорт КМ в БД без изменений: один CIS = одна запись `marking_codes` (видна в разделе ЧЗ), плюс `label_artifact_pdf` при успешном extract.
  - Tests: `test_marking_pdf_label_artifact.py` (single/multi/CSV); e2e `ff-mp-packaging-print`, `ff-separate-marking-print`; unit `labelSize`, `printMarkingCodeLabel`.
- What did NOT change: inbound receiving; mobile/; prod deploy.
- Verification: backend pytest `test_marking_pdf_label_artifact.py` 4/4; frontend vitest + targeted playwright green.
- Branch: `feat/cz-print-split-artifact` from `origin/main@5b4bd9c`.
- Commit: `77170e5` (PR #79 merged to main).
- Prod deploy: GitHub Actions `Deploy Production` run `28858488896` success, 2026-07-07.

## TASK-099 — 2026-07-06 — Приёмка: редактирование после завершения, фикс blur→0, печать ТЗ

- What changed:
  - Backend: `POST .../reopen-receiving` — вернуть заявку в приёмку, сторно остатка в сортировке, повторное завершение пересчитывает остатки.
  - Frontend приёмка: sticky колонки «Заявлено»/«Принято», кнопка «Редактировать» после завершения; BUG-4 — сохранение факта по `event.target` при blur (строка + короб).
  - Печать ТЗ из отгрузки МП: столбец «Кол-во»; `@page size: A4` без принудительного portrait (альбом из диалога печати).
- What did NOT change: состав коробов после reopen; mobile/.
- Verification: backend pytest `test_reopen_receiving_*`; frontend `npm run build`; vitest `printShipmentPackagingSheet`; e2e `inbound-receiving-v2`, `ff-inbound-box-intake`, `ff-mp-shipment-tz-print`.
- Commit: `f62b590` (PR #73) → prod Deploy Production run `28783305890` success.

## TASK-098 — 2026-07-05 — COMPOSER: импорт коробов xlsx + ЧЗ печать из общих корзин (wave 1–3)

- What changed:
  - Backend: `box_import_service` + preview/apply API на приёмке и отгрузке МП; `POST /operations/marking-codes/products/{id}/print` со списанием КМ (в т.ч. общие корзины); `scan-print` и `print-all` → **410 Gone**.
  - Frontend: `BoxImportDialog` на приёмке (`FfInboundRequestView`) и отгрузке МП (`FfSuppliesShipmentsPage`); `MarkingPrintDialog.printCatalogTape` → списывающий POST; `markingAvailable` учитывает shared baskets.
  - Tests: box import service + inbound API; catalog print write-off; write-off invariants (упаковка, каталог, reprint); deprecated endpoints openapi.
- What did NOT change: mobile audit путей печати; prod deploy.
- Verification: backend pytest (composer subset); frontend `npm run build`; e2e `ff-inbound-box-import` 2/2.
- Commit: merge `feat/composer-tasks` → `origin/staging` (Railway auto-deploy).

## TASK-097 — 2026-07-05 — MP упаковка: убрать дубли шапки на вкладке «Упаковка»

- What changed: на вкладке «Упаковка» в карточке отгрузки МП убраны кнопка «Продолжить упаковку» и шапка панели (chip «Черновик», «Упаковка», №, ссылка «Отгрузка»); таблица упаковки и действия без изменений; на странице `/ff/packaging` шапка задания сохранена.
- What did NOT change: summary «План/Распределено/Осталось/Упаковано»; вкладка «Товары»; backend упаковки.
- Verification: `npm run build`; e2e `ff-mp-full-flow`, `ff-mp-tabs` green.

## TASK-096 — 2026-07-05 — Раздельная печать ЧЗ/ШК, пачки, мультивыбор перепечатки, wedge-сканер

- What changed:
  - Backend: флаг тенанта `separate_marking_print_enabled` (модель, миграция, `/auth/me`, `PATCH /tenant/settings`) + pytest.
  - Frontend: галочка «Раздельная печать ЧЗ и ШК ВБ» в настройках FF; `MarkingPrintDialog` — две секции с отдельными размерами и кнопками; печать пачками по 20 этикеток (диалог прогресса); мультивыбор КМ при перепечатке (`code_ids[]`); scoped `labelSize` (`cz` / `label`).
  - Wedge-сканер (`useBarcodeScanner`) на всех FF-формах со сканом: приёмка (общая + добавление строки), наполнение короба приёмки, наполнение короба отгрузки МП, отгрузка МП (добавление строки + привязка WHB-короба).
  - E2e: `ff-separate-marking-print.spec.ts` (раздельный UI + chunk-диалог); обновлён `ff-marking-packaging.spec.ts` (мультивыбор перепечатки).
- What did NOT change: legacy v2 `InboundScreen` (старый shell); mobile/Android WIP в `mobile/`; prod deploy.
- Verification: backend `ruff`/`mypy` + pytest tenant_settings 9/9; frontend `npm run build`; vitest 75/75; e2e `ff-separate-marking-print` 2/2, `ff-marking-packaging` 3/3, `stab-cz-ui-print` + `ff-marking-print-constructor` green.
- Commit: `3f8b043` → pushed `origin/staging` (Railway auto-deploy).

## TASK-095 — 2026-07-02 — Печать ТЗ в отгрузке + выбор размера этикетки в модалках печати

- What changed:
  - Фича A: на экране отгрузки на МП (вкладка «Товары») кнопка «Печать ТЗ» рядом с «Печать накладной» → сводная A4-форма (`printShipmentPackagingSheet.ts`): по каждому товару отгрузки слева фото/артикулы/ШК/размер/состав, справа текст ТЗ из карточки; карточка не рвётся между страницами; нет ТЗ/фото → плейсхолдеры; нет товаров → тост «Нет товаров для печати». ТЗ берётся из уже отдаваемого backend поля `packaging_instructions` каталога (в тип `WbProductCatalogRow` добавлено поле, backend не менялся).
  - Фича B: единый выбор физического размера этикетки (`utils/labelSize.ts` + компонент `LabelSizeSelect`), размеры 58×40 (дефолт, как было зашито), 60×80, 60×40, 70×120; выбор запоминается в localStorage; размер реально задаёт `@page size` и рамку `.label` в `printMarkingCodeLabel.ts` и `printProductThermalLabel.ts`; подключён в `MarkingPrintDialog` (мониторируемый конструктор печати везде) и `ProductBarcodePrintDialog`.
- What did NOT change: логика «Печать накладной»; редактирование текста ТЗ (только отображение); внутренняя вёрстка/размер штрихкода этикетки (сохранён проверенный размер для читаемости сканером — на больших этикетках добавляется поле); backend API.
- Verification: `npm run build` green; vitest 45/45 (новые `labelSize.test.ts`, `printShipmentPackagingSheet.test.ts`, расширен `printMarkingCodeLabel.test.ts`); Playwright `ff-product-barcode-print` (проверка 60×80 → `size: 60mm 80mm`), `ff-mp-shipment-tz-print` (сводная форма с ТЗ) — green; PR #68 CI green → squash merge `eb9561c`; prod Deploy Production run `28608396020` success; smoke `http://194.87.96.144:8088/` FF/seller 200, `/api/health` ok, bundle содержит «Печать ТЗ».

## TASK-094 — 2026-07-01 — Документы FF: display-номера, шапки без техкодов, отгрузка summary

- What changed: backend `display_number` (`№000001`) отдельно от технического `document_number` для приёмки/отгрузки/упаковки + миграция/backfill; UI приёмки/сортировки/упаковки показывает процесс + человеческий номер; отгрузка МП — шапка «Отгрузка №…», один серый summary (План/Распределено/Осталось/Упаковано), убраны дубли итогов и кнопка «Упаковка» в footer.
- What did NOT change: блок «Сборка в короба»; построчные колонки в таблице товаров; prod/VPS deploy.
- Verification: backend targeted pytest 11/11; frontend build + unit; targeted e2e 14/14; Railway staging `202547a` → web+api smoke OK.

## TASK-093 — 2026-06-30 — Фикс печати в сортировке: база = «Принято», множитель в конструкторе

- What changed: сортировка передаёт `qtyNeedPack` (принято) и `source: packaging`; `MarkingPrintDialog` не считает сортировку «каталогом» с qty=1; ШК без ЧЗ: итог = база × множитель.
- What did NOT change: упаковка/отгрузка с `lineId`; каталог (`source: catalog`).
- Verification: e2e print pack green; merged `92789af` (#65); Railway web deploy + smoke OK.

## TASK-092 — 2026-06-30 — Единая печать: MarkingPrintDialog везде, убрана нижняя иконка в приёмке

- What changed: `useFfProductMarkingPrint` + `FfProductMarkingPrintProvider` — один диалог на страницу, Snackbar при ошибке marking-overview; `ProductBarcodePrintButton` без N копий диалога; в «Состав приёмки» иконка печати убрана; сортировка и каталог — тот же поток, что отгрузка.
- What did NOT change: печать накладной; печать ШК ячейки; упаковка/отгрузка (`onPrintClick` + `lineId`); `ProductBarcodePrintDialog` файл остаётся (не монтируется в FF UI).
- Verification: `npm run build`; e2e print pack (`ff-product-barcode-print`, `ff-reception-sorting`, `ff-marking-packaging`, `stab-cz-ui-print`) green.

## TASK-091 — 2026-06-30 — Сортировка: убрать «Упаковать», авто-строки короб/россыпь

- What changed: `FfInboundSortingPanel` — удалена кнопка «Упаковать»; под товаром авто-строки: по одной на каждый короб приёмки + «Россыпь»; источник текстом (не Select); «+ ячейка» только для остатка россыпи; qty короба read-only.
- What did NOT change: раздел «Упаковка»; prod docker.
- Verification: `npm run build`; e2e `ff-reception-sorting`, `ff-sorting-product-centric` 3/3; merged `92848c4` (#63); Railway staging web+WMS SUCCESS; smoke `/` + `/api/health` OK.

## TASK-090 — 2026-06-30 — IN-01: единая модель коробов приёмки + отгрузка, модалка 2×

- What changed: убрана UX-модель «закрыть короб» (приёмка + отгрузка МП); короба редактируются до завершения документа; `FfInboundBoxAddDialog` / `FfMarketplaceUnloadBoxAddDialog` — общий layout `boxFillDialogLayout.ts` (~2× размер, скролл внутри, прямое поле qty без карандаша); факт по строке = Σ коробов + россыпь (`effective_actual_qty`); backend снял блокировки `box_closed` на scan/PUT; GET приёмки грузит `boxes` с линиями явно.
- What did NOT change: API `POST .../close` остаётся для legacy; отдельная кнопка «удалить строку» в приёмке (qty→0 работает); деплой Railway.
- Verification: backend `ruff`/`mypy` + pytest inbound box 19/19; frontend `npm run build`; e2e inbound/mp/stab — green; merged `2d4a48d` (#62); Railway staging web+WMS deploy OK.

## TASK-089 — 2026-06-30 — CZ print: seller PDF page per CIS (not generated template)

- What was wrong: печать собирала «свою» HTML-этикетку из CIS — не совпадала с PDF селлера.
- What changed: при **PDF-импорте** каждая страница сохраняется как PDF-артефакт прямо в `marking_codes.label_artifact_pdf`; CIS по-прежнему в БД. Печать: если у КМ есть артефакт — грузится **PNG из сохранённого PDF** и печатается как есть; иначе fallback (CSV без PDF). API: `GET .../codes/{id}/label-artifact?format=pdf|png`, в ответе печати — `printed_codes[].has_label_artifact`.
- What did NOT change: CSV/TXT импорт без картинки; конструктор ленты `cz`/`label`.
- Verification: backend `ruff`/`mypy` targeted green; `pytest tests/test_marking_pdf_label_artifact.py` 1/1; frontend build + vitest 6/6 + e2e marking 4/4.

## TASK-088 — 2026-06-30 — STAB-IN-FE-03 + handoff 09 + Railway smoke tooling

- What changed: `FfInboundBoxAddDialog` / `FfProductLineCells` — testid на строку товара (фото/sku/название/размер); e2e `STAB-IN-FE-03`; mock WB photo в `wildberries_client.py`; `scripts/railway-staging-smoke.sh`; обновлены `09_STABILIZATION_HANDOFF`, `RAILWAY_STAGING_RU.md`, `SESSION_HANDOFF.md`.
- What did NOT change: Railway project WMS не создан (CLI login ok, `railway link` не выполнен).
- Verification: `npm run test:e2e -- tests-e2e/ff-inbound-box-intake.spec.ts tests-e2e/inbound-receiving-v2.spec.ts` 9/9 passed.

## TASK-087 — 2026-06-30 — STAB-E2E-02: ЧЗ UI + печать (финальный proof)

- What changed: `frontend/tests-e2e/stab-cz-ui-print.spec.ts` — сквозной e2e: товарная строка (фото/название/артикул/размер), карточка пула без threshold, единый конструктор печати с drag ленты, нет «Перепечатки» в навигации.
- What did NOT change: продуктовый UI/API ЧЗ; деплой Railway (только git push ветки `hotfix/deploy-wb-sync-nonfatal`).
- Verification: `npm run test:e2e -- tests-e2e/stab-cz-ui-print.spec.ts` 1/1 passed; push `4a22fc6..` на origin.

## TASK-086 — 2026-06-29 — IN-BE-03: e2e stabilization after primary-accept removal

- What changed: `inbound-boxes-helpers.ts` — `fulfillInboundViaBoxScans` fallback create on closed box; `v2InboundBoxIntakeUi` skip open if box already open; legacy primary-accept tests wait PATCH+POST /boxes. ~25 e2e specs migrated from `primary-accept` to `beginInboundReceivingWithBoxes`; `App.tsx` primary accept → PATCH actual + POST /boxes; `InboundScreen.tsx` statuses `receiving`/`sorting`; backend tests use `effective_actual_qty`.
- What did NOT change: FF inbound UI flow (IN-FE-01); API `/verify` alias kept for legacy callers.
- Verification: backend `ruff+mypy+pytest` 303 passed; frontend `npm run test:e2e` 93 passed (~7m); commit `c27dd0a`.

## TASK-085 — 2026-06-29 — REV-SORT-FE-02: distribution-lines load error handling

- What changed: `FfInboundSortingPanel.tsx` — failed GET не сбрасывает draft; Alert+retry; save/apply disabled until loaded. E2e TC-REV-SORT-FE-02.
- Verification: build + 3 e2e passed; integrate merge; commit `a78b407`.

## TASK-084 — 2026-06-29 — REV-IN-FE-01: manual receiving edit saves loose not total

- What changed: `inboundReceivingHelpers.ts`, `FfInboundRequestView.tsx` — effective total in UI, PATCH loose (`total − box`); e2e TC-NEW-IN-04.
- Verification: build + 4 e2e passed; integrate merge; commit `1bc3702`.

## TASK-083 — 2026-06-29 — REV-CZ-FE-01: multi-pool threshold + navigation race fix

- What changed: per-pool threshold on `HonestSignPoolPage`; multi-pool hint on product page; race fix (poolId reset, loadRequestId, disabled while busy). Commits `a316d79`, `d671ca2`.
- Verification: build + e2e honest-sign green; integrate merge.

## TASK-081 — 2026-06-29 — REV-CZ-TEST-01: tenant/seller isolation CZ tests

- What changed: TC-NEW-CZISO-001..004 in marking inventory/product-code filter tests.
- Verification: pytest 8 passed; integrate merge; commit `44784cd`.

## TASK-075 — 2026-06-29 — IN-FE-01: inbound receiving UI new flow

- What changed: `FfInboundRequestView.tsx` — факт=0, красные строки при расхождении, общий скан `/receiving/scan`, ручная правка через кнопку, модалка короба, одна «Завершить» + модалка расхождений; убраны primary-accept и boxIntakeMode. `FfInboundBoxAddDialog.tsx`, `inboundReceivingHelpers.ts`; `inboundQueues.ts` — статусы `receiving`/`sorting`; e2e `inbound-receiving-v2.spec.ts`.
- What did NOT change: `FfInboundSortingPanel` (SORT-FE-01); legacy e2e с primary-accept (inbound-intake.spec.ts).
- Verification: `npm run build` green; `npx playwright test inbound-receiving-v2.spec.ts` 3 passed; commit `d709506`.

## TASK-074 — 2026-06-29 — OUT-FE-01: unified outbound finish with discrepancy modal

- What changed: `FfSuppliesShipmentsPage.tsx` — одна кнопка «Завершить»; модалка «Есть расхождения, точно провести?» при plan≠fact; `mpHasDiscrepancy` по строкам; кнопка короба «Добавить в короб». `FfMarketplaceUnloadBoxAddDialog.tsx` — заголовок модалки «Добавить в короб».
- What did NOT change: e2e (optional); OUT-FE-02 (колонки/краснота/печать); backend OUT-BE-01 уже на ветке.
- Verification: `npm run build` — не выполнен локально (ENOSPC, диск 100%); IDE lint без ошибок.

## TASK-073 — 2026-06-29 — IN-BE-02: on-demand inbound intake boxes

- What changed: `inbound_intake_box_service.create_open_box` — короб приёмки по требованию (открыт сразу); `INTAKE_STATUSES` включает `submitted`; факт из коробов без primary-accept; тесты `test_inbound_intake_box_ondemand.py`.
- What did NOT change: API эндпоинты (IN-BE-03); `primary_accept_request` всё ещё вызывает `create_boxes_for_request` для legacy.
- Verification: `PYTHONPATH=worktree/backend ruff check . && mypy . && pytest` — 271 passed; commit `27dfe13`.

## TASK-072 — 2026-06-29 — Печать ТЗ на упаковку (A4)

- What changed: кнопка «Печать» в модалке ТЗ (`FfProductsCatalogScreen`, `SellerProductsStockScreen`); утилита `printPackagingInstructions.ts` — A4 с SKU, товаром, селлером, инструкцией и флагом ЧЗ; e2e assert `ff-packaging-print`.
- What did NOT change: API, сохранение ТЗ, печать этикеток/ЧЗ.
- Verification: `npm run test:unit` 26 passed; `npm run build` green; `npm run test:e2e -- ff-products.spec.ts` 2 passed.

## TASK-071 — 2026-06-29 — CZ product-first: PR #52

- Full backlog `CHESTNY_ZNAK_PRODUCT_FIRST_TASKS_RU.md` integrated on `feat/cz-product-first`.
- PR: https://github.com/chivkunovd-bitdenis/WMS/pull/52 → `main`
- Verification: backend 261 pytest; frontend build + 85 e2e passed locally.

## TASK-070 — 2026-06-29 — API-02: is_shared and shared_with on pool responses

- What changed: `marking_codes.py` — `PoolListItemOut` + `linked_products_count`, `is_shared`; `PoolDetailOut` + `shared_with`; API tests personal/shared pools.
- Verification: ruff/mypy/pytest — 261 passed; commit `bbc63fd`; merged → `feat/cz-product-first`.

## TASK-069 — 2026-06-29 — SVC-02 + API-01: pool flags + product-centric API

- SVC-02: `linked_products_count`, `is_shared` on pool rows; commit `50d0e6b`.
- API-01: `/inventory` personal+shared; `GET marking-overview`; commit `20087b1`.
- Merged both → `feat/cz-product-first`.

## TASK-068 — 2026-06-29 — SVC-01: personal inventory + shared baskets

- What changed: `marking_code_service.py` — `personal_available`, `personal_printed`, `shared_baskets` in `list_inventory`; `available_count` = personal (fix double-count shared pools); `test_marking_inventory_personal_shared.py` — 4 pytest cases.
- What did NOT change: API serialization (API-01 followed); frontend screens.
- Verification: `PYTHONPATH=. ruff/mypy/pytest` — 252 passed in worktree; merged `task/SVC-01` → `feat/cz-product-first`.
- Commit: `4768058` on `task/SVC-01`.

## TASK-067 — 2026-06-28 — CD: GitHub Actions deploy + prod PR #49

- What changed: `.github/workflows/deploy.yml` — автодеплой после green CI на `main` (SSH → `prod-update.sh`) + smoke HTTP; `docs/DEPLOY_SERVER_RU.md` — CI/CD секция и secrets; GitHub Secrets `DEPLOY_SSH_*`, `DEPLOY_HTTP_PORT`; deploy key `github-actions-wms-deploy` на сервере.
- What did NOT change: `prod-update.sh` логика; `.env` на сервере; ручной деплой по-прежнему работает.
- Deploy: PR #49 → `main` `6d375ab`; prod `194.87.96.144:8088` — `prod-update.sh`, FF/seller/health HTTP 200. CD PR #50 → `6f3c0ad`; Deploy Production workflow success.
- Commit: `6f3c0ad` (PR #50 merge).

## TASK-066 — 2026-06-28 — FIX-05: ledger/pools abort + BACKEND-01 openapi + docs

- What changed: `HonestSignLedgerPage.tsx`, `HonestSignScreen.tsx`, `HonestSignPoolPage.tsx` — `AbortController` в `load()`/`loadPools()`/`loadLedger()` против stale fetch; `ff-honest-sign-ledger.spec.ts` — e2e экспорт CSV (TC-NEW-LEDGER-04); `test_marking_deprecated_openapi.py` — pytest `deprecated` в OpenAPI; `MASTER_BACKLOG_RU.md` — статусы lane ✅ на `feat/cz-ux-fixes`; `CZ_DUPLICATE_SURFACES_AUDIT_RU.md` — ссылка `docs/` + §4 закрытые POOLS.
- What did NOT change: `FfHonestSignReprintsPage` (FIX-03); packaging/import dialogs; удаление deprecated routes (отдельный тикет).
- Verification: `pytest tests/test_marking_deprecated_openapi.py` 1 passed; marking subset 20 passed; `npm run build` exit 0.

## TASK-065 — 2026-06-28 — FIX-03: FINAL-01 terminology (КМ/ЧЗ)

- What changed: `HonestSignPoolPage.tsx` — export captions «N КМ», CSV status via `codeStatusLabel`; `FfHonestSignReprintsPage.tsx` — «История КМ», hints без «код», `ledgerEventLabel` в drawer; `App.tsx` — placeholder «Загрузка КМ»; `printMarkingCodeLabel.ts` — «Нет КМ для печати»; e2e `ff-marking-packaging.spec.ts` — «К перепечатке: 1 КМ».
- What did NOT change: `markingStatus.ts` (already RU); print/defect sections e2e (FIX-01/04); `HonestSignScreen.tsx` POOLS-03 (FIX-05).
- Verification: `npm run build` exit 0; grep — no «кодов» in exclusive user strings.

## TASK-064 — 2026-06-28 — FIX-01: PRINT-03 merge artifact + print terminology

- What changed: `MarkingPrintDialog.tsx` — убраны дубли MenuItem (ЧЗ/Этикетка/ШК ВБ) в custom-builder; helper-тексты «этикеток» → «ШК ВБ»/«блоков»; `markingPrintPresets.ts` JSDoc; e2e TC-NEW-001 — assert нет «Этикетка» в select и нет `marking-print-request-seller`.
- What did NOT change: PRINT-04/05 backend; `ff-mp-packaging-print.spec.ts` (expect «этикеток» — follow-up); reprint e2e «1 код» (FIX-03).
- Verification: `npm run build` exit 0; playwright `-g "print honest sign codes for line quantity"` exit 0.

## TASK-063 — 2026-06-28 — Queue integration: merge task/* → feat/cz-ux-fixes

- What changed: собран весь ЧЗ UX backlog в одну ветку **`feat/cz-ux-fixes`**: база `task/FINAL-01` + догон LEDGER-05…06, POOLS-01…05, POOLCARD-02, REPRINTS-*, BACKEND-01, PRINT-02/03, FINAL-02/03; конфликты разрешены вручную; `scripts/queue-integrate.sh`; orchestrator/hook — обязательный integrate после verifier; `.gitignore` — `.cursor/state/`, `.cursor/wt/`.
- What did NOT change: `main` (интеграция только в feature-ветке); `task/PACK-01..03` не мержились отдельно (уже в FINAL-01/PACK-09).
- Verification: `npm run build` green; `pytest tests/test_marking_pools_read.py tests/test_print_templates.py` — 14 passed.

## TASK-037 — 2026-06-28 — FINAL-03: docs sync (CHESTNY_ZNAK UX + FIX_TASKS)

- What changed:
  - **`docs/CHESTNY_ZNAK_UX_FIXES_RU.md`** — перенесён из корня; T-A7 закрыт как дубль MP-021/022/023; таблица сверки с `CHESTNY_ZNAK_FIX_TASKS_RU.md`.
  - **`docs/CHESTNY_ZNAK_FIX_TASKS_RU.md`** — ссылка на UX-бэклог и пояснение независимости треков.
  - **`docs/MASTER_BACKLOG_RU.md`**, **`docs/EXECUTION_PLAN_RU.md`**, **`docs/PARALLEL_AGENT_TASKS.md`** — пути и статусы X-1/X-2/X-3, FINAL-03 closed.
- What did NOT change: код приложения; lane-задачи.
- Verification: docs-only diff; ссылки на корневой `CHESTNY_ZNAK_UX_FIXES_RU.md` убраны.
- Commit: `501d055`

## TASK-049 — 2026-06-28 — FINAL-02: аудит дублей поверхностей ЧЗ

- What changed:
  - **`docs/CZ_DUPLICATE_SURFACES_AUDIT_RU.md`:** канон по ленте / списку кодов / импорту; follow-up POOLS-04…06, CROSS-04.
  - **`HonestSignImportPage.tsx`:** редирект `…/import` → список пулов (убрана заглушка-дубль; канон — `MarkingImportDialog`).
  - **`HonestSignPoolPage.tsx`:** `codeStatusLabel` / `ledgerEventLabel` в табах «Коды» и «Лента» + drawer истории.
  - **`MarkingProductCodesDialog.tsx`:** `@deprecated` — не монтируется, канон — таб «Коды» пула.
  - Merge: `task/LEDGER-06`, `task/POOLCARD-03`.
- What did NOT change: POOLS-04 (дашборд+таблица), удаление сироты `MarkingProductCodesDialog`, CROSS-04 (импорт с контекстом пула).
- Verification: `npm run build`; e2e `ff-honest-sign-pool`, `ff-honest-sign-import`. Commit `f048585`.

## TASK-051 — 2026-06-28 — BACKEND-01: deprecate scan-print / print-all / verify-pair

- What changed: `marking_codes.py` — `deprecated=True` + summary on `POST /scan-print`, `/verify-pair`, `/packaging-tasks/{id}/print-all`; comment BACKEND-01 / T-A6 (ORD-44).
- What did NOT change: endpoint behaviour, per-line print (`/packaging-lines/{line_id}/print`), service layer.
- Verification: `ruff check app/api/marking_codes.py`; `mypy app/api/marking_codes.py`; `pytest tests/ -q -k marking` — 50 passed; all three routes `deprecated=True` in OpenAPI. Commit `d82fe3c`.

## TASK-050 — 2026-06-28 — REPRINTS-03: context links on reprint row

- What changed: `FfHonestSignReprintsPage` — колонка «Контекст»: ссылки «Задание» (упаковка с `state.taskId`), «Пул», «История кода» (drawer); API `reprint-requests` отдаёт `packaging_task_id` и `pool_id`; e2e `ff-marking-defect.spec.ts` (TC-NEW-006) проверяет доступность контекста из строки. Сохранён диалог причины отклонения (REPRINTS-02).
- What did NOT change: approve/replace API, навигация ЧЗ вне reprints.
- Verification: `npm run build` + `npm run test:e2e tests-e2e/ff-marking-defect.spec.ts` + `PYTHONPATH=. pytest tests/test_marking_reprint_defect.py tests/test_shift_lead.py` in REPRINTS-03 worktree — green. Commits `320d7c6`, `1c22d6f`.

## TASK-037 — 2026-06-28 — REPRINTS-02: rejection reason field

- What changed: `FfHonestSignReprintsPage` — диалог с полем «Причина отклонения» при reject; текст уходит в API вместо хардкода «Отклонено старшим».
- What did NOT change: approve/replace actions; backend reject endpoint.
- Verification: `npm run build` green in `.cursor/wt/REPRINTS-01`.

## TASK-042 — 2026-06-28 — POOLCARD-02: honest pool codes CSV export

- What changed: `HonestSignPoolPage` — экспорт CSV запрашивает свежий список кодов с сервера (не client-side `filteredCodes`); подписи «N из M» при фильтре по хвосту КМ или статусу; кнопка показывает объём выгрузки.
- What did NOT change: API `/pools/{id}/codes`, локализация статусов (POOLCARD-01), таб «Лента» (POOLCARD-03).
- Verification: `npm run build` in `.cursor/wt/POOLCARD-02/frontend` — green.

## TASK-049 — 2026-06-28 — POOLS-05: unified forecast format

- What changed: `HonestSignScreen` — общий `ForecastLabel` (дата `ДД.ММ` + tooltip `(N дн.)`) в таблице и карточках селлера.
- What did NOT change: расчёт `forecast_days` на бэкенде, POOLS-04 переключатель дашборд/таблица.
- Verification: `npm run build` in POOLS-05 worktree (branch task/POOLS-05) — green. Commit `c32df5d`.

## TASK-042 — 2026-06-28 — POOLS-03: tooltip on disabled upload codes

- What changed: `HonestSignScreen` — кнопка «Загрузить коды» при `sellerIdRequiredForImport` без выбранного селлера обёрнута в MUI `Tooltip` («Выберите селлера») через `span`-обёртку для disabled.
- What did NOT change: empty-state «Загрузить коды», «Догрузить» на карточках пула, e2e.
- Verification: `npm run build` в worktree `.cursor/wt/POOLS-03/frontend` — exit 0.

## TASK-037 — 2026-06-28 — POOLS-01: seller picker via autocomplete

## TASK-037 — 2026-06-28 — POOLS-01: integrate (MarkingSellerPicker retained)

- What changed: merged task/POOLS-01; seller UI stays `MarkingSellerPicker` (CROSS-03) not Autocomplete row from lane branch.
- What did NOT change: e2e helpers `selectMarkingSeller` / ledger waits (HEAD).
- Verification: merge conflict resolution on `feat/cz-ux-fixes`.

## TASK-048 — 2026-06-28 — LEDGER-06: localize ledger events via markingStatus

- What changed: `HonestSignLedgerPage` — фильтр и чипы событий через `ledgerEventLabel` из `markingStatus.ts`; e2e на русские подписи («Импорт», «Печать»).
- What did NOT change: API `event_type` (англ. enum), логика фильтров (LEDGER-02–05).
- Verification: `npm run build` + `npm run test:e2e tests-e2e/ff-honest-sign-ledger.spec.ts` in LEDGER-06 worktree — green. Commit `8c0c350`.
## TASK-042 — 2026-06-28 — LEDGER-05: unified ledger filter triggers

- What changed: убрана кнопка «Применить» на `HonestSignLedgerPage`; текстовые фильтры «Документ» и «Маска КМ» через debounce 400ms (`useDebouncedValue`); select/даты/селлер — немедленный reload через `useEffect`; e2e без кликов по apply.
- What did NOT change: экспорт CSV (LEDGER-04), backend API, CROSS-03 (Autocomplete селлера).
- Verification: `npm run build` in worktree `LEDGER-05`.

## TASK-041 — 2026-06-28 — LEDGER-04: export ledger by filters

- What changed: `GET /operations/marking-codes/ledger/export` — CSV по тем же фильтрам, что и лента (seller, pool, event_type, document, cis_mask, date_from/to); кнопка «Экспорт» на `HonestSignLedgerPage`; восстановлен серверный `cis_mask` (регресс LEDGER-03); pytest `test_ledger_export_csv`, `test_ledger_cis_mask_filter`.
- What did NOT change: LEDGER-05 (единая модель «Применить»), e2e Playwright для экспорта.
- Verification: `PYTHONPATH=. pytest tests/test_marking_pools_read.py`; `npm run build` in worktree `LEDGER-04`.

## TASK-040 — 2026-06-28 — LEDGER-03: date range filter on ledger

- What changed: `HonestSignLedgerPage` — поля «С»/«По» (`type="date"`), query `date_from`/`date_to` на `/operations/marking-codes/ledger`; e2e + pytest `test_ledger_date_range_filter`.
- What did NOT change: экспорт (LEDGER-04), backend API (параметры уже были).
- Verification: `pytest tests/test_marking_pools_read.py::test_ledger_date_range_filter`; `npm run build` in worktree `LEDGER-03`.

## TASK-054 — 2026-06-28 — FINAL-01: unify КМ/ЧЗ UI labels

- What changed: merged PACK-09, PENDING-01, SHARED-01, POOLCARD-01/03, CROSS-01…04, PRINT-05 into `task/FINAL-01`; unified user-visible strings — **КМ** for code instances (pool, ledger, import, defect/reprint, errors), **ЧЗ** for system/requirement (column «ЧЗ», «Печать ЧЗ», product flag, presets, integration). Files: `FfPackagingPage`, `FfPendingMarkingPage`, `MarkingPrintDialog`, `MarkingProductCodesDialog`, `MarkingImportDialog`, `HonestSignScreen`/`PoolPage`/`LedgerPage`, `FfHonestSignReprintsPage`, `readApiErrorMessage`, `ffPermissions`, `App.tsx`.
- What did NOT change: API payloads, `data-testid`, behavior, backend.
- Verification: `npm run build` in FINAL-01 worktree — green (tsc + vite). Commit `c3d05c8`.

## TASK-053 — 2026-06-28 — CROSS-02: unified pending-marking total for badge + worklist

- What changed: shared `frontend/src/utils/pendingMarkingApi.ts` (`fetchPendingMarking`, `pendingMarkingLineCount` → API `total`, `limit=200`); `FfPackagingPage` badge and `FfPendingMarkingPage` chip use the same helper; pending fetch runs even if packaging-tasks list fails; e2e TC-NEW-011 asserts (badge = chip = row count) folded into TC-NEW-007/008.
- What did NOT change: backend `/pending-marking` contract; bulk print (PENDING-01); per-row print flow.
- Verification: `npm run build` — green; `npx playwright test tests-e2e/ff-pending-marking.spec.ts` — 2 passed (10.8s: TC-NEW-007 + TC-NEW-011, TC-NEW-008 + TC-NEW-011). Backend not touched. Commits: `c997485`, `d8ccd35`.
## TASK-052 — 2026-06-28 — PENDING-01: bulk print selected pending rows

- What changed: `FfPendingMarkingPage` — чекбоксы строк, «Печать выбранных (N)», очередь последовательных `MarkingPrintDialog` (каждая лента по своему товару); e2e TC-NEW-008.
- What did NOT change: API pending-marking, построчная кнопка «Печать», контракт total vs rows (CROSS-02).
- Verification: `npm run build` — green; `npx playwright test tests-e2e/ff-pending-marking.spec.ts` (TC-NEW-007, TC-NEW-008) — 2 passed (33.6s); fix `useMarkingCodePrint.close` (close after print while busy blocked queue). Commits: `ea31ed5` (bulk UI), `c93286c` (close fix + per-product header assert), `1dffbba` (e2e asserts distinct packaging-line IDs). Backend `ruff check` — 4 pre-existing issues in unrelated test files (not introduced by PENDING-01).

## TASK-053 — 2026-06-28 — POOLCARD-01: localize pool code statuses

- What changed: `HonestSignPoolPage` — фильтр и чипы статусов кодов через `codeStatusLabel` из `markingStatus.ts`; cherry-pick SHARED-01 (словарь + `MarkingProductCodesDialog`); e2e проверяет «Доступен» в строке и опциях фильтра.
- What did NOT change: лента событий на карточке пула (LEDGER-06), CSV export (англ. enum в файле).
- Verification: `npm run build` in POOLCARD-01 worktree — green. Commit `117b153`. E2E webServer timeout (env), не блокирует сборку.

## TASK-037 — 2026-06-28 — POOLCARD-03: таб «Лента» → превью + ссылка

- What changed:
  - **`HonestSignPoolPage.tsx`:** таб «Лента» показывает компактное превью (5 последних событий, 3 колонки) и кнопку «Вся лента пула» → `/honest-sign/ledger?pool_id=…`; убрана полная таблица с фильтрами/пагинацией (дубль `HonestSignLedgerPage`).
  - **`ff-honest-sign-pool.spec.ts`:** TC-NEW-011 — превью, отсутствие фильтров ленты на карточке, переход на полную ленту.
- What did NOT change: `HonestSignLedgerPage`, API ленты, другие табы карточки пула.
- Verification: `npm run build` green; `playwright test ff-honest-sign-pool.spec.ts` passed.

## TASK-048 — 2026-06-28 — CROSS-01: single KM reprint selection

- What changed:
  - **`MarkingPrintDialog.tsx`:** reprint-ветка — загрузка напечатанных КМ (`printed-codes`), radio-выбор одного кода, `code_ids` в POST print.
  - **`FfPackagingPage.tsx`:** «Повтор»/«Брак» в overflow-меню строки (`…`); `openLinePrint(..., { reprint: true })`.
  - **Backend:** `PrintMarkingCodesIn.code_ids`, фильтр reprint в `print_codes_for_packaging_line`.
  - **Tests:** pytest single reprint в `test_marking_import_and_packaging_print`; e2e TC-NEW-CROSS-01 в `ff-marking-packaging.spec.ts`; defect e2e через меню.
- What did NOT change: первичная печать через конструктор; очередь перепечаток (shift_lead).
- Verification: `pytest tests/test_marking_codes.py::test_marking_import_and_packaging_print` (passed); `npx playwright test … --grep "reprint single"` (passed); `npm run build` (exit 0).
- Commit: `280944b` (feature `b20496f` + e2e proof)

## TASK-041 — 2026-06-28 — PACK-07: block complete with incomplete marking

- What changed: `FfPackagingTaskPanel` — warning + disabled «Завершить упаковку» when `requires_honest_sign` lines have `qty_marking_printed < qty_done` (mirrors `assert_packaging_line_marking_done`); e2e TC-NEW-PKG-07 in `ff-marking-packaging.spec.ts`.
- What did NOT change: server `marking_not_done` gate; print/defect flows (PACK-05/06).
- Verification: `npm run build` green in PACK-07 worktree.

## TASK-037 — 2026-06-28 — PACK-04: packaging page cleanup after removals

- What changed:
  - **`FfPackagingPage.tsx`:** removed orphaned code after PACK-01..03 — `hasHonestSignLines`, `hasPrintedMarkingLines`, print-all (`printAll*`, dialog), verify-pair (`pair*`), unused imports (`printMarkingCodeTape`, `MarkingTapeUnitInput`, `PrintLayout`).
  - Deleted obsolete e2e: `ff-marking-print-all.spec.ts`, `ff-marking-verify-pair.spec.ts`.
  - Row-wise «Печать ЧЗ» / «Повтор» via `openLinePrint` + `useMarkingCodePrint` unchanged.
- What did NOT change: backend endpoints; `MarkingPrintDialog` constructor flow.
- Verification: `npm run build` green; eslint on file — no unused-vars; e2e `ff-marking-print-constructor.spec.ts`.
- Commit: `ac7f312`

## TASK-039 — 2026-06-28 — PRINT-05: per-user print template layout

- What changed:
  - **`print_templates.user_id`:** миграция `20260628_0053`, FK на `users`; per-user «последняя раскладка» (`__user_last__`).
  - **`print_template_service.py`:** `resolve` — сначала раскладка текущего пользователя, затем product/seller/system; `save_user_last_print_layout` (upsert без имени).
  - **`marking_codes.py`:** `user_id` в API; после успешной печати с `layout_json` — авто-сохранение последней раскладки.
  - **`printTemplate.ts`:** поле `user_id` в типе `PrintTemplate`.
  - **`test_print_templates.py`:** user last > seller default; два пользователя; auto-save на print.
- What did NOT change: именованные шаблоны (кнопка «Сохранить») — дополнение; drag-and-drop ленты.
- Verification: `PYTHONPATH=. pytest tests/test_print_templates.py` (6 passed); `npm run build` (exit 0).

## TASK-038 — 2026-06-28 — PRINT-04: pack qty multiplier for WB barcode

- What changed:
  - **`productBarcodePrint.ts`:** `resolvePackUnits` (из `pack_units:N` в ТЗ или `units_in_pack`), `resolveWbBarcodeLabelCount` — qty × pack; печать через умноженное количество.
  - **`ProductBarcodePrintDialog.tsx`:** каталог — поле «Количество ШК ВБ», подсказка «× N шт в упаковке», итог «К печати».
  - **`MarkingPrintDialog.tsx`:** не-ЧЗ упаковка — тот же множитель; `packagingInstructions` в контексте.
  - **`wbProductCatalog.ts`:** `packaging_instructions` / `units_in_pack` в `ProductLineDisplayMeta`.
  - **`productBarcodePrint.test.ts`:** gate qty 3 × pack 5 → 15.
- What did NOT change: ЧЗ-конструктор; backend поля `units_in_pack` (пока парсинг из ТЗ).
- Verification: `npm run test:unit src/utils/productBarcodePrint.test.ts` (3 passed); `npm run build` (exit 0).

## TASK-037 — 2026-06-28 — PRINT-01: non-ЧЗ print qty-only (no constructor)

- What changed:
  - **`MarkingPrintDialog.tsx`:** для товара без ЧЗ — только поле «Количество ШК ВБ» (`marking-print-wb-qty`); пресеты, билдер, превью и сохранение шаблона скрыты; печать с фиксированным layout label×1.
  - **`ff-mp-packaging-print.spec.ts`:** e2e обновлён под qty-only UI (TC-NEW-MP-016).
- What did NOT change: ЧЗ-ветка конструктора; каталог (`ProductBarcodePrintDialog`); множитель «× упаковка» (PRINT-04).
- Verification: `npm run build` (exit 0) в `.cursor/wt/PRINT-01/frontend`.

## TASK-037 — 2026-06-28 — CROSS-03: seller Autocomplete on ledger page

- What changed:
  - **`MarkingSellerPicker.tsx`** — shared MUI Autocomplete for seller selection (search, same testids as POOLS-01).
  - **`HonestSignLedgerPage.tsx`** — replaced seller button row with `MarkingSellerPicker`.
  - **`HonestSignScreen.tsx`** — uses shared picker (unified UX with ledger).
  - **`ff-honest-sign-helpers.ts`** — `selectMarkingSeller` / `selectHonestSignSeller` for e2e.
  - **e2e:** updated honest-sign specs; **TC-NEW-011** — ledger seller autocomplete filters events.
- What did NOT change: ledger filter debounce/export (LEDGER-* lanes); pool link CTA (POOLS-06).
- Verification: `npm run build`; `npm run test:e2e` on ff-honest-sign-ledger/spec/pools (4 passed).
- Commit: `b8b85e4`

## TASK-039 — 2026-06-28 — IMPORT-05: highlight import groups missing title

- What changed:
  - **`MarkingImportDialog.tsx`:** при «Загрузить» с пустым названием — подсветка всех групп без `title` (border/error TextField), `data-testid` `…-title-missing`, скролл к первой; снятие подсветки при вводе названия. Хелперы `isImportGroupTitleMissing`, `gtinsWithMissingTitle`, `findFirstGtinWithMissingTitle`.
  - **`markingImportMerge.test.ts`:** тесты хелперов валидации названия.
- What did NOT change: контекст пула при «Догрузить» (CROSS-04).
- Verification: `npm run test:unit -- markingImportMerge.test.ts`, `npm run build` — green.

## TASK-038 — 2026-06-28 — IMPORT-04: delete uploaded import file chip

- What changed:
  - **`MarkingImportDialog.tsx`:** чипы файлов с `onDelete`; `removeImportFileAt` + `removeFileAt` — удаление файла, пересбор превью по оставшимся; при пустом списке — сброс групп и meta.
  - **`markingImportMerge.test.ts`:** тесты `removeImportFileAt`.
- What did NOT change: подсветка пустого названия (IMPORT-05), контекст пула (CROSS-04).
- Verification: `npm run test:unit -- markingImportMerge.test.ts`, `npm run build` — green.

## TASK-037 — 2026-06-28 — POOLS-06: один CTA на привязку товаров в списке пулов

- What changed:
  - **`HonestSignScreen.tsx`:** убран дублирующий чип «не привязан» в колонке «Пул»; привязка только через кнопку «Привязать» в колонке «Товары» (и пункт меню «Привязать товары»).
- What did NOT change: диалог привязки, меню пула, e2e `ff-honest-sign-pools.spec.ts`.
- Verification: `npm run build` в worktree POOLS-06 — OK. Commit: `e888b73`.

## TASK-036 — 2026-06-28 — CZ-000 barrier: MP commit + feat/cz-ux-fixes + autopilot backlog

- What changed:
  - **CZ-000 done:** MP slice committed `304abf2` on `hotfix/alembic-marking-pools`; branch **`feat/cz-ux-fixes`** created.
  - **Autopilot:** `.cursor/hooks`, `wms-queue.mdc`, `docs/PARALLEL_AGENT_TASKS.md`, `CURSOR_QUEUE_LANES_RU.md`, CZ backlog docs.
  - **`PARALLEL_AGENT_TASKS.md`:** CZ-000 marked done; agents may start PACK/PRINT/… lanes.
- What did NOT change: lane tasks (PACK-01…); orchestrator lives in `~/.cursor/agents/orchestrator.md`.
- Verification: `git status` clean on `feat/cz-ux-fixes`.

## TASK-035 — 2026-06-28 — Queue lanes: files, depends_on, lane scheduling doc

- What changed:
  - **`docs/CURSOR_QUEUE_LANES_RU.md`** — справка для человека и orchestrator (атрибуты lane/files/depends_on, правила параллели, примеры, resume).
  - **`orchestrator.md`**, **`wms-queue.mdc`**, **`QUEUE.md`** — планирование по lanes; ссылка на справку (не alwaysApply).
  - **`.cursor/skills/queue-lanes/SKILL.md`** — короткий указатель на справку.
  - Orchestrator queue: **1 задача = 1 builder**, `parallel_workers` от владельца.
- What did NOT change: содержимое backlog (владелец вставит в QUEUE).
- Verification: docs-only.

## TASK-034 — 2026-06-28 — Backlog autopilot: orchestrator queue mode, QUEUE, stop hook

- What changed:
  - **`~/.cursor/agents/orchestrator.md`** — режим очереди: 4×3 parallel builder, builder→verifier→fix (max 3), ` done` только после verifier.
  - **`backlog-runner.md`** — stub → redirect на orchestrator queue mode.
  - **`.cursor/QUEUE.md`** — очередь (формат: `ID — описание` / `… done` / `… blocked`).
  - **`.cursor/SESSION_HANDOFF.md`** — handoff между пачками.
  - **`.cursor/rules/wms-queue.mdc`** — правила queue mode.
  - **`.cursor/hooks.json` + `continue-queue.sh`** — auto follow-up пока в QUEUE есть открытые задачи.
- What did NOT change: orchestrator (режим одной фичи); backlog tasks — владелец вставит в QUEUE.
- Verification: hook script exits `{}` on empty queue; `chmod +x` on continue-queue.sh.

## TASK-033 — 2026-06-28 — MP-032…034: parallel full-flow e2e, ship UI gate, canonical docs

- What changed:
  - **MP-032:** `ff-mp-full-flow.spec.ts` — TC-NEW-MP-FULL-001: boxes filled **before** packaging complete, then pack → ship from footer.
  - **MP-033:** `FfSuppliesShipmentsPage` — **«Отгружено»** disabled until `linked_packaging_task` done (`mpPackagingComplete`); guard in `requestShipMpUnload`.
  - **MP-034:** docs — superseded banners on `02`/`03`; `MVP_DECISIONS_RU` MP packaging; `DATA_FLOW.md` lifecycle; `01_normalized_process_spec` implementation status; `IMPLEMENTED_PRODUCT_SCENARIOS_*` §17 + updated S16 cases.
- What did NOT change: MP-024…031 (already in REV-FIX / prior tasks); `04_release_implementation_review.md` historical snapshot.
- Verification: e2e `ff-mp-full-flow`, `ff-mp-packaging-gate`, `ff-mp-tabs` — 5 passed; backend pytest batch/ship subset — 9 passed.

## TASK-032 — 2026-06-28 — MP-021…023: единый конструктор печати на упаковке MP

- What changed:
  - **MP-021:** иконка печати на вкладке «Упаковка» MP → `MarkingPrintDialog` (не `ProductBarcodePrintDialog`); печать убрана с вкладки «Товары».
  - **MP-022:** поле «Этикеток на каждый товар»; для товаров без ЧЗ — только пресеты этикеток, без блоков ЧЗ.
  - **MP-023:** `applyLabelsPerProductToLayout` / `countTapeBlocks` — lpp умножает только label-блоки (A-002); полная лента через `printMarkingCodeTape`.
- What did NOT change: MP-024…034 (settings, docs polish).
- Verification: `npm run test:unit -- markingPrintPresets` — 4 passed; e2e `ff-mp-packaging-print` — 1 passed; e2e `ff-mp-full-flow`, `ff-mp-tabs`, `ff-marking-print-constructor`, `ff-marking-packaging` — green; `npm run build` ok.

## TASK-031 — 2026-06-28 — MP-018 + MP-020: модалка pick/scan, главный scan только WHB

- What changed:
  - **MP-018:** модалка «Добавить товары» — dropdown ячейки, scan товара/ячейки/WHB; backend `collect_ready_box_into_open_box` + `kind: ready_box` в scan API; confirm/over-plan для WHB в модалке; убран `packagingGateActive`.
  - **MP-020:** главный scan на «Товарах» — только WHB/INB; товар/ячейка → сообщение «используйте Добавить товары»; e2e TC-NEW-MP-015.
- What did NOT change: MP-021…034 (печать, docs polish).
- Verification: `pytest tests/test_marketplace_unload_tsd_scan_contract.py` — 6 passed; e2e `ff-mp-box-add-modal` — 4 passed; e2e `ff-mp-tabs` — 3 passed; e2e `ff-mp-full-flow` — 1 passed; `npm run build` ok.

## TASK-030 — 2026-06-28 — MP-015…020: batch open boxes, e2e parallel, attach over-plan, WHB scan

- What changed:
  - **MP-015:** подтверждено — `create_boxes_batch` с `closed_at=NULL`; pytest batch green.
  - **MP-016:** e2e `ff-mp-box-add-modal` — 3 короба **без** complete packaging (параллельный flow).
  - **MP-017:** подтверждено — UI всегда `/boxes/batch`; pytest one-by-one + e2e TC-NEW-MP-022 green.
  - **MP-019:** `allow_over_plan` в collect/attach API; UI confirm «Весь короб» + «Больше плана»; pytest `test_marketplace_unload_attach_allow_over_plan`.
  - **MP-020:** главный scan на «Товарах» — только WHB attach; ячейка/товар → модалка короба; кнопка «Закрыть» на строке открытого короба.
- What did NOT change: MP-018 (WHB attach в модалке короба), MP-021…034, MP-020 dedicated e2e (product barcode на главном scan).
- Verification: `pytest -k "batch or attach_allow_over"` — 4 passed; `npm run build` ok; e2e `ff-mp-box-add-modal` + `ff-mp-packaging-gate` — 4 passed.

## TASK-029 — 2026-06-28 — MP-010/011/013: 2 вкладки, короба на «Товарах», footer ship

- What changed:
  - **MP-010:** убраны вкладки `ff-mp-tab-boxes` и `ff-mp-tab-final`; остались только «Товары» и «Упаковка».
  - **MP-011:** блок коробов (`ff-mp-boxes`), сводка распределения, scan/batch — на вкладке «Товары» после confirm.
  - **MP-013:** «Утвердить» / «Отгружено» / «Отменить» — в footer (`ff-mp-footer-bar`); дата/WB/печать на «Товарах».
- What did NOT change: MP-012 (full re-check), MP-015+.
- Verification: `npm run build` ok; e2e `ff-mp-tabs`, `ff-mp-full-flow`, `ff-mp-box-add-modal`, `ff-mp-print-waybill`, `ff-mp-packaging-gate`, `ff-dashboard` — green.

## TASK-029b — 2026-06-28 — MP-014: шапка документа (склад ФФ + дата + WB)

- What changed: `ff-mp-doc-header-fields` — дата (`ff-mp-planned-date`), склад ФФ (`ff-mp-ff-warehouse-name`), WB select/readonly; убрано дублирование с вкладки «Товары».
- Verification: e2e draft test asserts header testids; build green.

## TASK-028 — 2026-06-28 — MP-unload Phase A + frontend unblock (MP-001…009, MP-006…008, MP-012 partial)

- What changed:
  - **MP-001:** статус `collecting` («На сборке») — переход при первом коробе/collect/attach; ship из `collecting`; label в UI.
  - **MP-002/MP-009:** подтверждено — упаковка `done` только через `complete_task`; pytest marking_not_done green.
  - **MP-003:** `PackagingTask` только после confirm; draft без `linked_packaging_task`; GET by-unload → 404 без task.
  - **MP-004:** MP pack — счётчик `qty_packed` без `apply_packaging_convert`.
  - **MP-005:** снят gate упаковки с create/collect/batch коробов (остался на ship).
  - **MP-006/007/008:** UI — убран packaging gate; колонка «На полке упак.» скрыта для MP task; pack без ячейки.
  - **MP-012 (partial):** плашка прогресса не на draft; «Продолжить упаковку» только на вкладке «Упаковка».
- What did NOT change: MP-010…014 (2 вкладки, footer ship), MP-015…034, MP-021…023 (печать).
- Verification: backend `pytest tests/test_packaging_tasks.py` + MP sync/box tests — 12 passed; e2e `ff-mp-packaging-gate.spec.ts`, `ff-mp-tabs.spec.ts` (draft banner) — green; `npm run build` — ok.
- Commit: bdf297e (includes CZ P0/P1 marking fixes in same slice)

## TASK-027 — 2026-06-27 — CI mypy green for outbound-rework PR

- What changed: mypy fixes — optional `storage_location_id` в collect API/services; marking imports (`LAYOUT_BLOCK_CZ`, `STATUS_AVAILABLE`, `EVENT_PRINTED`); rename query param `code_status` (shadow `status`); typed seller scope in print-templates.
- What did NOT change: product behavior; e2e scenarios.
- Verification: `mypy .` — Success; `pytest -q` — 224 passed; PR #47 CI — backend + e2e + pr-quality + tc-coverage all pass.
- Commit: 39268c4

## TASK-026 — 2026-06-27 — REV-FIX-019, 020

- What changed:
  - **REV-FIX-019:** e2e `ff-mp-full-flow.spec.ts` (TC-NEW-MP-FULL-01): seller plan → FF confirm → packaging UI → batch 2 короба → fill → ship full plan; green.
  - **REV-FIX-020:** sanity docs — REQ-001 дополнен DEC-019 (миграция, не block); журнал батчей S03 в `04_release_manifest.md`; manifest S02/S04/S05 → works.
  - **CI fixes:** ruff (duplicate test rename, line length); `complete_task` billing order (finalize before skip guard); `test_staff_packaging_billing` — billing после explicit complete.
- What did NOT change: `04_release_implementation_review.md` (исторический снимок review).
- Verification: `npm run test:e2e -- ff-mp-full-flow.spec.ts` — 1 passed; grep DEC-019 в spec/MVP/manifest — канон «миграция на зону сортировки, toggle не блокируется».
- Commit: e6913ec

## TASK-025 — 2026-06-27 — REV-FIX-014 … 018 (P2)

- What changed:
  - **REV-FIX-014:** зафиксирован MVP — plan total на «Товары» (draft), collect summary/warning только после confirm на «Короба»; комментарии в UI; регрессия ff-mp-tabs green.
  - **REV-FIX-015:** docstring `copy_box` (closed by design); `docs/DATA_FLOW.md` — copy box; pytest `test_marketplace_unload_box_remove_copy_delete` green.
  - **REV-FIX-016:** `PUT .../pick-allocations` помечен `deprecated=True` + docstring admin-only; pytest green.
  - **REV-FIX-017:** cancel → sorting zone в `docs/DATA_FLOW.md`; pytest `-k cancel` green.
  - **REV-FIX-018:** Snackbar `ff-mp-box-add-success-snackbar` «Добавлено N шт» после add в короб; e2e ff-mp-box-add-modal green.
- What did NOT change: REV-FIX-019 (full-flow e2e), REV-FIX-020 (docs — уже в TASK-024).
- Verification: e2e ff-mp-tabs, ff-mp-box-add-modal; pytest copy + cancel + pick_allocations.
- Commit: e6913ec

## TASK-024 — 2026-06-27 — REV-FIX-004, 020, 011–013

- What changed:
  - **REV-FIX-004:** info Alert `ff-settings-address-storage-migration-info` при выключении адресного хранения; e2e green.
  - **REV-FIX-020:** DEC-019 → миграция на зону сортировки в `01_normalized_process_spec.md`, `MVP_DECISIONS_RU.md`, `04_release_manifest.md`.
  - **REV-FIX-011:** subtitle «Отгрузки на МП» без «подбор по ячейкам»; e2e assert.
  - **REV-FIX-012:** Alert `seller-mp-ff-handoff-hint` после «Запланировано»; e2e green.
  - **REV-FIX-013:** `ff-mp-plan-total` на вкладке «Товары» черновика; e2e assert.
- What did NOT change: REV-FIX-014+ (P2 docs/UX).
- Verification: e2e ff-address-storage-setting, ff-mp-tabs, seller-mp-unload green.
- Commit: e6913ec

## TASK-023 — 2026-06-27 — REV-FIX P1 (007–010, 009)

- What changed:
  - **REV-FIX-007:** убран misleading copy «появится после подтверждения»; empty/created states на вкладке упаковки; e2e assert.
  - **REV-FIX-008:** `ff-mp-packaging-progress` виден на draft при `linked_packaging_task`; e2e assert.
  - **REV-FIX-010:** Alert `ff-mp-packaging-gate-alert` на вкладке «Короба» при gate; e2e assert.
  - **REV-FIX-009:** batch API count≥1; UI всегда `/boxes/batch`; batch-create виден при открытых коробах; pytest one-by-one + e2e TC-NEW-MP-022.
- What did NOT change: REV-FIX-003+ (DEC-019 migration), P2 copy/docs.
- Verification: e2e ff-mp-tabs, ff-mp-packaging-gate, ff-mp-box-add-modal (two single-box); pytest create_boxes_batch*.
- Commit: e6913ec

## TASK-022 — 2026-06-27 — REV-FIX P0/P1 (001–006, 002a, 005)

- What changed:
  - **REV-FIX-001:** убран авто-`done` из `_touch_task`; gate `assert_unload_packaging_done` требует `status=done`; pytest explicit complete.
  - **REV-FIX-002:** batch-короба создаются открытыми (`closed_at=NULL`); pytest batch + manual-line.
  - **REV-FIX-002a:** UI — список всех открытых коробов; e2e TC-NEW-MP-021 batch 3 → add на 2-м коробе.
  - **REV-FIX-005:** pytest `marking_not_done` на `POST .../complete`.
  - **REV-FIX-006:** вкладка «Упаковка» enabled при `linked_packaging_task` (draft); e2e draft packaging tab.
- What did NOT change: REV-FIX-007+ (copy, progress на draft, DEC-019 migration).
- Verification: pytest packaging_tasks + batch; e2e ff-mp-box-add-modal + ff-mp-tabs green.
- Commit: e6913ec

## TASK-021 — 2026-06-27 — DEC-012 недопоставка + отмена на сортировку

- What changed: ship с `acknowledge_discrepancy` при распределено < план; UI диалог «Отгрузить неполную»; кнопка «Отменить отгрузку» на FF; cancel возвращает товар на **сортировку** (не на исходные ячейки); pytest partial ship + cancel/sorting.
- What did NOT change: DEC-019 (блок toggle) — по решению владельца не нужен; выключение адресного → перенос на виртуальную ячейку (отдельная задача).
- Verification: pytest ship ack + cancel sorting; build green.
- Commit: e6913ec

## TASK-020 — 2026-06-27 — Селлер plan-only (DEC-015)

- What changed: `_require_ff_execution` — seller 403 на короба/ship/confirm/cancel/pick; GET detail без boxes/pick_allocations/packaging для seller; `SellerMarketplaceUnloadDialog` — status cancelled, `seller-mp-plan-only`; pytest seller guards; e2e TC-NEW-MP-020.
- What did NOT change: FF вкладки; seller plan/unplan/lines draft.
- Verification: pytest seller test; e2e seller-mp-unload green; ruff.
- Commit: e6913ec

## TASK-019 — 2026-06-27 — Отмена отгрузки → откат инвентаря (DEC-016)

- What changed: `POST .../cancel`; `cancel_request` + `rollback_all_collected_for_cancel`; status `cancelled`; pytest partial distribution cancel restores stock and clears reserves/box lines.
- What did NOT change: UI кнопка отмены (FF); seller cancel (403 via TASK-020).
- Verification: pytest `test_marketplace_unload_cancel_partial_distribution_restores_inventory`; ruff.
- Commit: e6913ec

## TASK-018 — 2026-06-27 — API-контракт scan-потока для ТСД

- What changed: `POST .../boxes/{box_id}/scan` — единый flow location→product (`kind` в ответе); код ошибки `plan_limit_exceeded`; `pick/scan` deprecated; doc `docs/API_MP_UNLOAD_SCAN_TSD_RU.md`; pytest `test_marketplace_unload_tsd_scan_contract.py`; UI modal/box scan на один endpoint.
- What did NOT change: мобильный клиент; seller parity.
- Verification: pytest tsd contract + unload suite; e2e ff-mp-box-add-modal (after build).
- Commit: e6913ec

## TASK-017 — 2026-06-27 — E2E tests отгрузки на МП

- What changed: e2e `ff-mp-packaging-gate.spec.ts` (TC-NEW-MP-008) — UI/API gate до упаковки; комментарий TASK-017 в `ff-mp-ship-pick`; ship без ack body (TASK-015).
- What did NOT change: seller-mp-unload UI parity, ff-mp-print-waybill.
- Verification: e2e ff-mp-packaging-gate + ff-mp-ship-pick + ff-mp-tabs + ff-mp-box-add-modal green.
- Commit: e6913ec

## TASK-016 — 2026-06-27 — Backend tests marketplace unload

- What changed: pytest packaging gate before box/batch; ship rejects empty boxes (`distribution_incomplete`); seller test order упаковка→короба; batch test clarifies count=1 validation.
- What did NOT change: pick-allocations admin-only test (legacy admin path).
- Verification: pytest 32 passed (unload + address_storage + seller + packaging).
- Commit: e6913ec

## TASK-015 — 2026-06-27 — Рефактор ship_request после переноса списания

- What changed: `ship_request` без `acknowledge_discrepancy` и без pick_allocations; проверка `distribution_incomplete` по коробам (DEC-010); `wb_mp_warehouse_required` на ship; API ship без body; UI/e2e без ack body; pytest + packaging test через manual-line в короб.
- What did NOT change: seller parity, DEC-012 partial ship path.
- Verification: pytest 25 passed (unload + packaging); e2e ff-mp-ship-pick + ff-mp-tabs.
- Commit: e6913ec

## TASK-014 — 2026-06-27 — Финальная вкладка: печать ШК и gate ship

- What changed: кнопка «Печать всех ШК коробов» на вкладке «Финал»; ship блокируется при `remaining > 0` (UI + без confirm расхождения); pytest `test_marketplace_unload_ship_blocked_when_distribution_incomplete`; e2e ship disabled в `ff-mp-tabs`.
- What did NOT change: refactor ship_request pick_allocations (TASK-015), seller parity.
- Verification: pytest 1 passed; e2e ff-mp-tabs + ff-mp-ship-pick green; `npm run build`.
- Commit: e6913ec

## TASK-013 — 2026-06-27 — Счётчики плана, распределения и упаковки

- What changed: `mpCollectSummary` — план / распределено по коробам / остаток + статус упаковки; предупреждение `ff-mp-collect-warning` при неполном распределении; колонка «Распределено» вместо «Собрано»; e2e asserts в `ff-mp-tabs.spec.ts` (TC-NEW-MP-007).
- What did NOT change: ship validation (TASK-014), backend `picked_qty_by_product` (уже по коробам).
- Verification: `npm run build`; e2e ff-mp-tabs green.
- Commit: e6913ec

## TASK-012 — 2026-06-27 — Вкладочная структура документа отгрузки на МП

- What changed: MUI Tabs в `FfSuppliesShipmentsPage` — «Товары / Упаковка / Короба / Финальная отгрузка»; embed `FfPackagingTaskPanel` вместо `FfPackagingTaskDialog`; финал (дата, склад WB, печать, подтвердить/отгрузить) на вкладке «Финал»; e2e `ff-mp-tabs.spec.ts` (TC-NEW-MP-007).
- What did NOT change: счётчики DEC-010 (TASK-013), ship validation DEC-012 (TASK-014/015), seller parity (`SellerMarketplaceUnloadDialog`).
- Verification: `npm run build`; e2e ff-mp-tabs + ff-mp-box-add-modal + ff-address-storage-mp-ui + ff-mp-ship-pick green.
- Commit: e6913ec


- What changed: `FfMarketplaceUnloadBoxAddDialog` (фото, план/в коробах/доступно, scan ячейки+товара, ручной ввод); кнопка `ff-mp-box-add-products-{boxId}`; `plan_exceeded` в `collect_into_box` (BR-005); gate упаковки по `status === 'done'`; e2e `ff-mp-box-add-modal.spec.ts` (TC-NEW-MP-006).
- What did NOT change: вкладочная структура (TASK-012), счётчики DEC-010 (TASK-013).
- Verification: pytest 26 passed (unload + packaging + address_storage); `npm run build`; e2e `ff-mp-box-add-modal.spec.ts` green.
- Commit: e6913ec

## TASK-010 — 2026-06-27 — Действия короба: remove line, delete empty, copy, print ШК

- What changed: `remove_from_box` (откат on_hand/reserved/pick allocation, DEC-016); `delete_box` (DEC-007, только пустой); `copy_box` (новый короб + collect по allocations, лимит плана BR-005); API `POST .../copy`, `DELETE .../boxes/{id}`, `POST .../lines/{id}/remove`; UI меню короба + печать ШК + удаление строки; pytest `test_marketplace_unload_box_remove_copy_delete`.
- What did NOT change: модалка «Добавить товары» напротив короба (TASK-011), вкладочная структура (TASK-012).
- Verification: pytest 26 passed (unload + address_storage + packaging); `npm run build`.
- Commit: e6913ec

## TASK-009 — 2026-06-27 — Массовое создание N коробов

- What changed: `create_boxes_batch` в `marketplace_unload_box_service`; `POST .../boxes/batch` (count 2–50, закрытые пустые короба с ШК); UI — поле «Кол-во коробов» + кнопка «Создать короба» / «Открыть короб» (count=1); pytest batch.
- What did NOT change: per-box modal add (TASK-011), copy/delete короба (TASK-010).
- Verification: pytest `test_marketplace_unload_create_boxes_batch` + 25 unload tests passed; `npm run build`.
- Commit: e6913ec

## TASK-005 — 2026-06-27 — Удаление «Начать подбор» (legacy flow)

- What changed: убраны кнопка `ff-mp-start-picking`, модалка `ff-mp-picking-dialog`, блок `ff-mp-pick-saved`; `PUT .../pick-allocations` — только `FULFILLMENT_ADMIN`; pytest + e2e TC-NEW-MP-005.
- What did NOT change: сборка через скан в короб (`collect_into_box`); `GET pick-options` (без UI).
- Verification: pytest 24 passed (unload + address_storage + packaging); e2e `ff-address-storage-mp-ui`, `ff-mp-ship-pick` green; `npm run build`.
- Commit: e6913ec

## TASK-004 — 2026-06-27 — Списание остатков при добавлении в короб (DEC-006)

- What changed: `collect_into_box` вызывает `apply_marketplace_unload_pick` + `reduce_reservation_for_collect` в одной транзакции; `FOR UPDATE` на балансе и заявке; `ship_request` без повторного movement; `delete_empty_boxes_for_ship` (DEC-002); pytest + e2e `ff-mp-ship-pick` — остаток уменьшается после collect, не после ship.
- What did NOT change: откат при remove-from-box (TASK-010), отмена/abandon (TASK-019).
- Verification: `pytest tests/test_marketplace_unload_and_discrepancy_acts.py` + `test_marketplace_unload_address_storage.py` — 23 passed.
- Commit: e6913ec

## TASK-007 + TASK-008 — 2026-06-27 — Завершение упаковки и gate коробов

- What changed: `POST .../packaging-tasks/{id}/complete`; reopen task при смене плана отгрузки; блок `create_open_box`/`collect_into_box` до `packaging_not_done`; UI complete panel + disabled box scan; e2e `ff-mp-ship-pick`, `ff-address-storage-mp-ui` — упаковка перед коробами.
- What did NOT change: списание при collect (TASK-004), batch короба (TASK-009).
- Verification: `pytest tests/test_packaging_tasks.py` 8 passed; `test_marketplace_unload_address_storage.py` 2 passed; `npm run build`.
- Commit: e6913ec

## TASK-003 — 2026-06-27 — Скрытие UI ячеек при выкл. адресном хранении

- What changed: `addressStorageEnabled` prop в `FfSuppliesShipmentsPage`, `FfInboundRequestView`, `App.tsx`; скрыты chip ячейки, «Начать подбор», таблица pick_allocations, блок распределения приёмки; scan без шага ячейки; e2e `ff-address-storage-mp-ui.spec.ts`.
- What did NOT change: списание при collect (TASK-004), backend API (TASK-002 уже в `908029c`).
- Verification: `npm run build`; e2e `ff-address-storage-mp-ui.spec.ts` + `ff-address-storage-setting.spec.ts` green.
- Commit: `2cd8062`.

## TASK-001 — 2026-06-27 — Флаг «Адресное хранение» (UI)

- What changed: checkbox на `FfSettingsScreen`, поле `address_storage_enabled` в `Me`/`useAuth`, reload me после PATCH; e2e `ff-address-storage-setting.spec.ts`. Backend/API — в `908029c`.
- What did NOT change: скрытие UI ячеек (TASK-003).
- Verification: e2e settings + build green.
- Commit: `2cd8062` (UI; backend/API в `908029c`).

## TASK-002 — 2026-06-27 — Условная обязательность ячеек в collect/pick API

- What changed: `resolve_collect_storage_location` в `marketplace_unload_collect_service`; флаг `address_storage_enabled` через `tenant_settings_service` (TASK-001 dependency); optional `storage_location_id` в API scan/manual-line/pick-add; `pick_scan` — порядок ячейка→товар при вкл. флаге; pytest `test_marketplace_unload_address_storage.py`.
- What did NOT change: списание при collect (TASK-004), скрытие UI ячеек (TASK-003), inventory movement moment on ship.
- Verification: `ruff` + `mypy` on changed files green; pytest 2 new + `test_marketplace_unload_ship_deducts_stock_by_pick_and_scan` green.
- Commit: `908029c`.

## TASK-78 — 2026-06-26 — ЧЗ T4.1: хранилище кредов селлера

- What changed: таблица `seller_marking_credentials` (шифрованные токены ЧЗ/СУЗ/МП, МЧД, signing_method, edo_route, auto_introduce, auto_emit_limit); API `GET/PATCH /operations/marking-codes/self/credentials` и `/sellers/{id}/credentials`; блок настроек в `SellerSettingsScreen`; pytest + e2e `seller-marking-credentials.spec.ts`.
- What did NOT change: signing-service (T4.2), авто-ввод в оборот (T4.3).
- Verification: `pytest tests/test_marking_credentials_api.py` 4 passed; `npm run build`; e2e `seller-marking-credentials.spec.ts` green.
- Commit: `6840b15`.

## TASK-77 — 2026-06-26 — ЧЗ T3.3–T3.5: прогноз, low-stock, дашборд селлера, триггеры ФФ

- What changed: T3.3 расчёт `consumption_7d`/`forecast_days`, `PUT pools/{id}/threshold`, Celery `marking_low_stock`, KPI и пороги в UI; T3.4 карточки остатков селлера + e2e; T3.5 `notify_ff_portal` при создании приёмки/отгрузки МП.
- What did NOT change: фаза 4 (креды ЧЗ, подпись).
- Verification: pytest forecast+triggers; `npm run build`; e2e `seller-honest-sign-dashboard.spec.ts`.
- Commit: `51876d2`.

## TASK-76 — 2026-06-26 — ЧЗ T3.2: колокольчик и центр уведомлений

- What changed: `NotificationBell` в шапке FF и селлера, страница «Уведомления», API-клиент, e2e seed `/_e2e/seed`, Playwright `ff-notifications.spec.ts`.
- What did NOT change: пороги low-stock (T3.3), дашборд остатков селлера (T3.4), триггеры отгрузок (T3.5).
- Verification: `npm run build`; e2e `ff-notifications.spec.ts` green.
- Commit: `11c1ccd`.

## TASK-75 — 2026-06-26 — ЧЗ T3.1: шина уведомлений

- What changed: таблица `notifications`, сервис `notify`/`notify_ff_portal`, API `GET/POST /operations/notifications` (список, read, read-all), скоуп получателя user/seller/ff_portal.
- What did NOT change: UI колокольчик (T3.2), триггеры low-stock и отгрузок (T3.3–T3.5).
- Verification: `ruff`, `mypy`, `pytest tests/test_notifications.py` — 5 passed.
- Commit: `9c8a449`.

## TASK-74 — 2026-06-26 — ЧЗ T2.4–T2.5: verify-pair и ворклист pending

- What changed: T2.4 `POST verify-pair` (match → `applied` + событие), мини-станция на упаковке; T2.5 `GET pending-marking`, экран «Осталось промаркировать», бейдж на упаковке.
- What did NOT change: фаза 3 (уведомления T3.1).
- Verification: pytest verify_pair + pending; e2e ff-marking-verify-pair + ff-pending-marking.
- Commit: `15e290a`.

## TASK-73 — 2026-06-26 — ЧЗ T2.1–T2.3: shift_lead, брак, очередь перепечатки

- What changed: T2.1 `can_shift_lead`, `require_shift_lead`, nav «Перепечатки»; T2.2 `marking_reprint_requests`, `POST codes/{id}/defect`, кнопка «Брак» на упаковке; T2.3 approve/replace/reject API и кнопки на экране очереди.
- What did NOT change: T2.4 скан-пара «товар=пакет»; колокольчик уведомлений (Э7).
- Verification: pytest reprint_defect + shift_lead; `npm run build`; e2e ff-shift-lead + ff-marking-defect.
- Commits: `78881e7` (T2.1), `f6d78d1` (T2.2), `ff6f9f9` (T2.3).

## TASK-72 — 2026-06-26 — ЧЗ T1.6: рендер ленты по layout

- What changed: `expandLayoutTape` в `markingPrintPresets.ts`; `printMarkingCodeTape` / обновлённый `printMarkingCodeLabels` с блоками `cz` и `label` (58×40); экспорт `buildProductLabelSectionHtml`; вызовы из `MarkingPrintDialog`, `FfPackagingPage` (scan/print-all/строка); vitest `markingPrintPresets.test.ts`; e2e constructor — пресет «Этикетки + ЧЗ», счётчик этикеток в предпросмотре.
- What did NOT change: Фаза 2 (shift_lead, перепечатки).
- Verification: `npm run test:unit` 2 passed; `npm run build`; e2e constructor + print-all green.
- Commit: `a86def6`.

- What changed: `print_all_for_packaging_task` + `POST /operations/marking-codes/packaging-tasks/{id}/print-all` (dry_run, allow_partial); кнопка «Печать всех ЧЗ» и диалог сводки на панели упаковки; pytest `test_marking_print_all.py`; e2e `ff-marking-print-all.spec.ts` (TC-NEW-003).
- What did NOT change: рендер ленты по layout label-блокам (T1.6).
- Verification: pytest print_all 2 passed; `npm run build`; e2e print-all green.
- Commit: `7b33be6`.

## TASK-70 — 2026-06-26 — ЧЗ T1.4: скан-печать

- What changed: `units_to_print` в `print_codes_for_packaging_line` (инкремент `qty_marking_printed`); `scan_print_for_packaging_task` + `POST /operations/marking-codes/scan-print`; поле «Сканируйте товар» на панели упаковки; pytest `test_marking_scan_print.py`.
- What did NOT change: print-all (T1.5), layout-рендер label (T1.6).
- Verification: pytest scan + marking; `npm run build`.
- Commit: `b1e27b1`.

## TASK-69 — 2026-06-26 — ЧЗ T1.3: диалог-конструктор печати

- What changed: `MarkingPrintDialog` — шапка (товар/документ, нужно/доступно), баннер нехватки, «печатать доступные M», пресеты (Парами/Этикетки+ЧЗ/…/Свой), конструктор блоков, предпросмотр 3 единиц, сохранение шаблона, тост «Запросить у селлера»; кнопка «Печать ЧЗ» доступна при available≥1; e2e `ff-marking-print-constructor.spec.ts` (TC-NEW-002).
- What did NOT change: scan-print (T1.4), print-all (T1.5), рендер label-блоков (T1.6).
- Verification: `npm run build`; e2e constructor + packaging.
- Commit: `b1e27b1`.

## TASK-68 — 2026-06-26 — ЧЗ T1.2: печать из пула

- What changed: рефактор `print_codes_for_packaging_line` — коды из пула (`marking_pool_products`), reserve→printed, события с `document_number`, API `{layout_json, copies, allow_partial}`; ответ `{codes, layout, quantity, shortage}` вместо 422 при нехватке; фронт отправляет `layout_json` из шаблона; pytest `test_marking_print_pool.py`, обновлён `test_marking_insufficient_codes`.
- What did NOT change: конструктор ленты Э5 (T1.3), scan-print (T1.4), рендер по layout на фронте (T1.6).
- Verification: pytest marking print 9 passed; `npm run build`.
- Commit: not yet.

## TASK-67 — 2026-06-26 — ЧЗ T1.1: шаблоны печати

- What changed: таблица `print_templates`, модель `PrintTemplate`, сервис `print_template_service.py` (CRUD + резолвер product→seller→системный «Парами»); API `GET/POST/PUT/DELETE /operations/marking-codes/print-templates` и `GET …/print-templates/resolve`; фронт `printTemplate.ts`, диалог печати подтягивает шаблон по товару; pytest `test_print_templates.py`.
- What did NOT change: рефактор печати из пула (T1.2), конструктор ленты Э5 (T1.3), scan-print (T1.4).
- Verification: `ruff`/`mypy` green; pytest print_templates 3 passed; `npm run build`; e2e packaging — по возможности.
- Commit: not yet.

## TASK-66 — 2026-06-26 — ЧЗ T0.4: привязка пул↔товары

- What changed: `set_pool_products` / `add_pool_products` / `remove_pool_products` в `marking_code_service.py`; `PUT /operations/marking-codes/pools/{pool_id}/products` (422 `product_seller_mismatch`); диалог `MarkingPoolProductsDialog` + панель `MarkingPoolProductsPanel` (чипы товаров); e2e seed `POST …/_e2e/pools` при `WMS_AUTO_CREATE_SCHEMA=1`; pytest `test_marking_pool_products.py`, e2e `ff-pool-products-link.spec.ts` (TC-NEW-004).
- What did NOT change: список пулов Э1 (T0.7), импорт в пулы (T0.3), GET ленты/пулов (T0.6).
- Verification: `ruff`/`mypy` green; pytest marking 12 passed; `npm run build`; e2e `ff-pool-products-link.spec.ts` green.
- Commit: `82180c8`.

## TASK-65 — 2026-06-26 — ЧЗ T0.5: журнал marking_code_events

- What changed: таблица `marking_code_events`, модель `MarkingCodeEvent`, константы типов событий; `record_event()` в `marking_code_service.py`; события `imported` при импорте, `printed`/`reprinted` при печати; pytest `test_marking_code_events.py`.
- What did NOT change: API ленты (T0.6), привязка пул↔товары (T0.4), рефактор импорта в пулы (T0.3).
- Verification: `ruff`/`mypy` green; `pytest` 156 passed.
- Deploy: not yet.

## TASK-64 — 2026-06-26 — ЧЗ T0.2: модель пулов и расширение кодов

- What changed: таблицы `marking_pools`, `marking_pool_products`; расширение `marking_codes` (pool_id, serial, crypto_tail, reserved/applied/introduced/transferred/consumed, defective_reason, replaced_by_code_id); константы статусов; дата-миграция backfill пулов для существующих кодов; pytest `test_marking_pools.py`.
- What did NOT change: API, фронт, импорт в пулы (T0.3), события `marking_code_events` (T0.5).
- Verification: `ruff`/`mypy` green; `pytest` 154 passed.
- Deploy: not yet.

## TASK-63 — 2026-06-26 — ЧЗ T0.1: нумерация документов (УПАК/ПРИЕМ/ОТГР)

- What changed: таблица `document_sequences`, колонка `document_number` на `packaging_tasks`, `inbound_intake_requests`, `marketplace_unload_requests`; сервис `document_number_service.py` (атомарный счётчик по МСК); номер при создании упаковки/приёмки/отгрузки; API + UI (упаковка, приёмка, списки отгрузок); pytest + e2e TC-NEW-DOCNUM-01.
- What did NOT change: пулы ЧЗ, импорт кодов, события `marking_code_events` (T0.2+).
- Verification: `ruff`/`mypy` green; `pytest` 152 passed; `npm run build`; e2e `ff-packaging-page.spec.ts` (create from sorting).
- Deploy: not yet.

## TASK-62 — 2026-06-26 — FF каталог: поиск по артикулу и названию

- What changed: в разделе «Каталог» ФФ — строка поиска сверху; фильтрация по `sku_code`, `wb_vendor_code` (артикул продавца) и названию; пустое состояние «ничего не найдено»; e2e TC-NEW-002 в `ff-products.spec.ts`.
- What did NOT change: API `/products/ff-catalog`; фильтр по селлеру и сортировка.
- Verification: `npm run build`; e2e `ff-products.spec.ts` — filter/sort/search.
- Deploy: PR #46 → `main` `4e82c6b`; prod `194.87.96.144:8088` — `prod-update.sh`, HTTP 200.

## TASK-61 — 2026-06-24 — Фикс сброса даты отгрузки в WmsDateField

- What changed: `WmsDateField` не вызывает `onChange(null)` на пустом blur после выбора в календаре; регрессия в `seller-mp-unload.spec.ts` (TC-NEW-DATE-01).
- What did NOT change: API PATCH `planned_shipment_date`; логика сохранения в диалогах селлера и ФФ.
- Verification: `npm run build`; e2e `seller-mp-unload.spec.ts`, `ff-dashboard.spec.ts`.
- Deploy: PR #43 → `main` `fc1a32b`; prod `194.87.96.144:8088` — `prod-update.sh`, HTTP 200.

## TASK-60 — 2026-06-23 — FF навигация: «Каталог»→«Ячейки», «Товары»→«Каталог»

- What changed: подписи в сайдбаре ФФ и заголовки экранов — раздел складов/ячеек «Ячейки», раздел товаров селлеров «Каталог»; подсказки в приёмке/сортировке и текст ошибки ТЗ упаковки.
- What did NOT change: маршруты (`/app/catalog`, `/app/ff/products`), `data-testid`, кабинет селлера («Товары»).
- Verification: `npm run build`; e2e `admin-shell-layout.spec.ts`, `ff-products.spec.ts`.

## TASK-59 — 2026-06-23 — FF каталог: все товары селлеров, не только с движениями

- What changed: `GET /products/ff-catalog` возвращает все товары тенанта (как `linked-wb-catalog`), а не только с `InventoryMovement`; остатки в UI по-прежнему из `inventory-balances/summary` (0 для непринятых).
- What did NOT change: приватный WB-каталог селлера; эндпоинт `linked-wb-catalog` (оставлен для приёмки/хуков).
- Verification: `pytest tests/test_products_wb_catalog.py::test_ff_catalog_lists_all_tenant_products`; e2e `ff-products.spec.ts` — filter/sort passed.
- Deploy: PR #45 → `main` `7146d77`; prod `194.87.96.144:8088` — `prod-update.sh`, WB sync 8/8 sellers ok (~307 SKU updated).

## TASK-58 — 2026-06-18 — Печать ШК в каталоге товаров ФФ и после закрытия приёмки

- What changed: в разделе «Товары» ФФ — кнопка печати этикетки 58×40 (как на приёмке/упаковке); после «Завершить пересчёт» в разделе «Сортировка» таблица состава приёмки с печатью ШК остаётся видимой; общий компонент `ProductBarcodePrintButton`.
- What did NOT change: API печати; логика этикетки 58×40.
- Verification: `npm run build`; e2e `ff-reception-sorting.spec.ts`, `ff-product-barcode-print.spec.ts` — green.
- Deploy: PR #42 → `main` `a8a840a`; prod `194.87.96.144:8088` — `prod-update.sh`, все контейнеры Up, bundle `ff-ZMw0qrUp.js`.

## TASK-57 — 2026-06-16 — Селлер: изоляция каталога по магазину + деплой

- What changed: обычные селлеры всегда видят только свой `seller_id` (JWT-делегирование игнорируется); менеджеры — allowlist (`vitalik`/`vitaliy`/`виталий`, `denmark`/`denmarks`, `WMS_SHOP_MANAGER_EMAILS`, флаг БД); фронт перезагружает каталог при смене активного магазина; WB-импорт ищет баркод только в рамках селлера; pytest `test_seller_wb_catalog_isolation.py`, `test_seller_shop_allowlist.py`.
- What did NOT change: FF-каталог «все селлеры» для админа; логика переключения магазинов у менеджеров.
- Verification: pytest seller isolation 15 passed; PR #40 CI green; `npm run build`.
- Deploy: merge PR #40 → `main` `ee5095c`; prod `194.87.96.144:8088` — `prod-update.sh`, все контейнеры Up, seller/api HTTP 200. WB re-sync прерван (OOM); при необходимости вручную: `./scripts/deploy/sync-all-wb-products.sh`.

## TASK-56 — 2026-06-16 — Честный знак: импорт кодов и печать из упаковки

- What changed: модуль ЧЗ — `marking_codes` / `marking_code_imports` в БД; флаг `requires_honest_sign` у товара; загрузка CSV/PDF селлером или админом ФФ; остатки в разделах «Честный знак» (FF + seller); в задании на упаковке кнопка «Печать ЧЗ» на всё `qty_need_pack` строки, галочка «в 2 экземплярах», повторная печать без списания новых кодов; печать DataMatrix 58×40 (`bwip-js`); блок отгрузки на МП при `marking_not_done`; миграция `20260616_0041`; pytest `test_marking_codes.py`; e2e `ff-marking-packaging.spec.ts`.
- What did NOT change: отчётность в ГИС МТ / API ЧЗ; парсинг PDF-сетки на листе (только постраничный текст + CSV).
- Verification: `ruff check . && mypy . && pytest` (129 passed); `npm run build`; `npx playwright test tests-e2e/ff-marking-packaging.spec.ts`.

## TASK-55 — 2026-06-15 — Портал селлера: переключение между магазинами (Vitality)

- What changed: менеджер-магазинов (email с «vitalik», `WMS_SHOP_MANAGER_EMAILS` или `users.can_manage_seller_shops`) — в сайдбаре раздел «Магазины» с чекбоксами (все селлеры тенанта кроме своего и тестовых `@example.com` / `e2e-*`); после включения — переключатель «Активный магазин»; API `PUT /auth/seller-shops`, `POST /auth/switch-seller`; JWT `seller_id` = активный магазин; все seller API (отгрузки, приёмки, товары, WB) работают от лица выбранного магазина; миграция `20260615_0040`; pytest `test_seller_shop_switch.py`.
- What did NOT change: обычные селлеры без флага — только свой магазин; админ FF не затронут.
- Verification: `pytest tests/test_seller_shop_switch.py`; `npm run build`.

## TASK-54 — 2026-06-14 — Этикетка 58×40 и колонка ШК: баркод WB + размер

- What changed: на этикетке 58×40 в блоке деталей снова печатается «Размер: …»; под штрихкодом — только цифры ШК (баркод WB, не артикул/sku); в колонке «ШК» строк товаров (приёмка, упаковка, отгрузка) — баркод сверху, «Размер: …» снизу; e2e `ff-product-barcode-print.spec.ts` обновлён.
- What did NOT change: отдельная колонка «Размер» в каталоге товаров; логика импорта WB.
- Verification: `npm run build`; `npx playwright test tests-e2e/ff-product-barcode-print.spec.ts`.
- Deploy: commit `476d2aa`, prod `/opt/wms` — `git pull` + rebuild `web` only, `:8088` OK.

## TASK-53 — 2026-06-14 — WB: отдельный товар на каждый размер + фильтр ИП при отгрузке ФФ

- What changed: импорт WB — один `Product` на каждый баркод из `sizes[].skus` (`sku_code` вида `ART/S`, поля `wb_barcode`, `wb_chrt_id`, `wb_size`); при multi-size старый merged SKU → `OLD/…` + `[OLD]` в названии; миграция `20260614_0039`; post-deploy `./scripts/deploy/sync-all-wb-products.sh` (в `prod-update.sh`) — полная загрузка карточек по **всем** селлерам с content-токеном; UI «Товары» — колонка «Размер»; отгрузка на МП (ФФ) — выбор селлера (ИП) перед созданием.
- What did NOT change: строки `OLD/…` не удаляются (остатки/история на них); одна snapshot-карточка WB на nmID.
- Verification: `pytest tests/test_wildberries_legacy_old_mark.py tests/test_wildberries_product_import_sizes.py`; `npm run build`.
- Deploy: `prod-update.sh` → migrate + `python -m app.cli.sync_all_wb_products` в контейнере api.

## TASK-52 — 2026-06-14 — Дубликаты селлеров: очистка prod + атомарное создание

- What changed: prod — удалены 6 пустых дублей «ИП Герус Д.В.» (оставлен один с `gerus_denis@mail.ru`); бэкенд — `POST /sellers/with-account` (селлер + учётка в одной транзакции, откат при `email_taken`); UI `SellersScreen` — один запрос вместо двух; pytest `test_create_seller_with_account_*`; e2e sellers-create / auth-dual / auth-portal-mismatch.
- What did NOT change: отдельные `POST /sellers` и `POST /auth/seller-accounts` (для тестов/API); остальные селлеры (Denmarcs, Виталик и т.д.).
- Verification: `pytest tests/test_sellers.py` — 4 passed; `npm run build` — OK; prod SQL — 1 «ИП Герус Д.В.».
- Deploy: код ещё не на проде — нужен `git pull` + rebuild.

## TASK-51 — 2026-06-11 — Остатки селлера: остаток vs резерв vs отгрузка

- What changed: бэкенд — резерв МП/outbound только по ячейкам (не «Сортировка»); UI селлера — колонки «В ячейках», «Остаток» (На ФФ − резерв), «К отгрузке» (только ячейки); тест `test_available_matches_mp_reserve_only_after_putaway`, e2e `seller-available-stock`.
- What did NOT change: списание при ship/pick МП; экран товаров ФФ.
- Verification: `pytest tests/test_inventory_balances_summary.py`; `npm run build`.

## TASK-50 — 2026-06-11 — Биллинг сотрудников за упаковку

- What changed: ставка за ед. (₽) в настройках сотрудников; расчёт ЗП по завершённым заданиям (только `qty_packed_in_task`, снимок ставки при завершении); фильтр по месяцу (МСК); право «Упаковка» в матрице доступа; API `PATCH /auth/staff-accounts/{id}/packaging-rate`; миграция `0038`.
- What did NOT change: биллинг селлеров (литр‑день), выплаты/бухгалтерия.
- Verification: `ruff` / `mypy` / `pytest tests/test_staff_packaging_billing.py`; `npm run build`; e2e `ff-staff-packaging-billing.spec.ts`; PR #37 CI green; prod `194.87.96.144:8088` commit `b646463`.
- Commit: b646463 (squash PR #37).

## TASK-49 — 2026-06-11 — Упаковка: таблица создания задания как в приёмке

- What changed: диалог «Создать задание на упаковку» — ширина `min(1200px, 96vw)` как у `WbProductPickerDialog` в приёмке; те же отступы таблицы; фиксированные ширины колонок количества; `minWidth: 180` у «Наименование» в `FfProductLineCells` (не ломается посимвольно).
- What did NOT change: API упаковки, логика создания задания.
- Verification: `npm run build` — OK.
- Commit: 405025f.

## TASK-48 — 2026-06-11 — Отдельный favicon и марка для портала селлера

- What changed: `frontend/public/favicon-seller.svg` — бирюзовый «магазин» (отличается от фиолетовой «коробки» FF); `seller/index.html` → `/favicon-seller.svg`; `WmsBrandMark` с `portal="seller"` в шапке селлера и на экране входа; `deploy/Caddyfile.http` — исключение favicon-seller из no-cache SPA.
- What did NOT change: favicon FF (`/favicon.svg`), API, бизнес-логика.
- Verification: `npm run build` — OK.

## TASK-47 — 2026-06-11 — Брендинг WMS: favicon и марка в UI

- What changed: `frontend/public/favicon.svg` — вместо розовой молнии (оцифровка) иконка коробки в цвете темы; `WmsBrandMark` в шапке FF/селлера и на экране входа; заголовки вкладок `WMS · Фулфилмент` / `WMS · Селлер`.
- What did NOT change: API, бизнес-логика.
- Verification: `npm run build`; CI green PR #34; prod deploy `194.87.96.144:8088` commit `4caef80` — `curl /favicon.svg` → коробка `#5b21b6`.
- Commit: 4caef80 (squash PR #34).

## TASK-46 — 2026-06-11 — Seller SPA: no-cache на :8088 (Caddyfile.http)

- What changed: `deploy/Caddyfile.http` — `Cache-Control: no-cache` для seller/FF HTML (как в `frontend/deploy/Caddyfile`), чтобы после деплоя браузер не держал старый `seller-*.js`.
- What did NOT change: логика `SellerMarketplaceUnloadDialog` (на сервере уже `seller-mp-add-products`).
- Verification: после merge — `curl -I http://194.87.96.144:8088/seller/` → no-cache; hard refresh у селлера → кнопка «Добавить товары».

## TASK-45 — 2026-06-11 — WbProductPickerDialog: FF приёмка и отгрузка на МП

- What changed: `SellerWbProductPickerDialog` → ядро `WbProductPickerDialog` с `variant="ff"` (`FfProductLineCells`, печать ШК); подключено в `FfInboundRequestView` и `FfSuppliesShipmentsPage`. Пропсы `applyLabel`, `renderTrailingHeadCells` / `renderTrailingBodyCells` для будущих колонок FF.
- What did NOT change: API; логика сохранения строк остаётся в родительских экранах.
- Verification: `npm run build`; e2e ff-dashboard, ff-inbound-boxes, seller-mp-unload, seller-cabinet — 8 passed; prod `194.87.96.144:8088` commit `9094acf`.
- Commit: 9094acf.

## TASK-44 — 2026-06-11 — Общий picker каталога WB для селлера

- What changed: `SellerWbProductPickerDialog` — единая модалка выбора товаров (поиск, категория, фото, qty); подключена в `SellerInboundDraftScreen` и `SellerMarketplaceUnloadDialog`. Отгрузка на МП передаёт `showAvailableColumn`, `filterRow`, `getAvailable`.
- What did NOT change: портал ФФ — подключён в TASK-45.
- Verification: `npm run build`; e2e seller-mp-unload, seller-available-stock, seller-cabinet, ff-inbound-boxes.
- Commit: 4cb7c33 (в prod вместе с 9094acf).

## TASK-43 — 2026-06-11 — Селлер: отгрузка на МП — добавление товаров как в приёмке

- What changed: в `SellerMarketplaceUnloadDialog` убрана старая таблица всех остатков; кнопка «Добавить товары» + модалка каталога WB (поиск, категория, фото, ШК, колонка «Доступно») как в `SellerInboundDraftScreen`; строки заявки редактируются в таблице с удалением. E2e `seller-mp-unload`, `seller-available-stock` обновлены.
- What did NOT change: API отгрузки на МП; портал ФФ (уже на новом паттерне).
- Verification: `npm run build`; e2e `seller-mp-unload.spec.ts`, `seller-available-stock.spec.ts` — 2 passed.

## TASK-42 — 2026-06-11 — Отгрузка на МП: видимая панель добавления + деплой

- What changed: панель «Добавление товаров» (скан ШК + «Добавить товары») перенесена **под склад WB, до таблицы строк**; Caddy `no-cache` для `index.html`; e2e проверяет отсутствие старого Select на МП.
- What did NOT change: логика модалки каталога и API строк (c8db069); акты расхождений.
- Verification: PR #33 CI green; prod `194.87.96.144:8088` commit `d3a951e`, bundle `ff-CC085PGz.js`.
- Commit: d3a951e (squash merge PR #33).

## TASK-41 — 2026-06-11 — Отгрузка на МП: добавление товаров как в приёмке

- What changed: в черновике отгрузки на МП — скан ШК/артикула, кнопка «Добавить товары» и модалка каталога WB (фото, артикулы, ШК, поиск, категория, кол-во) как в `FfInboundRequestView`; строки таблицы по-прежнему через `FfProductLineCells`. Старый Select по остаткам убран для МП.
- What did NOT change: сборка в короба, подбор по ячейкам, акты расхождений (там старый Select).
- Verification: `npm run build`; e2e `ff-dashboard.spec.ts`, `ff-mp-ship-pick.spec.ts`.
- Commit: c8db069; CI run 27307241687 success; prod deploy `194.87.96.144:8088`.

## TASK-40 — 2026-06-11 — Этикетка ШК 58×40 по макету WB (штрихкод сверху)

- What changed: макет термоэтикетки как на WB — штрихкод и цифры сверху, имя селлера, название, артикул, цвет, бренд, «Пожалуйста оставьте отзыв»; убраны EAC и строка размера. API каталога отдаёт `wb_brand` из карточки WB.
- What did NOT change: печать коробов/ячеек; накладные A4; размер по-прежнему в каталоге, но не на этикетке.
- Verification: `npm run build`; pytest `test_wb_card_enrichment`, `test_seller_wb_catalog_enriched_from_imported_card`; e2e `ff-product-barcode-print.spec.ts`.
- Commit: b5e3eba; prod deploy `194.87.96.144:8088`.

## TASK-39 — 2026-06-10 — Приёмка без обязательного короба; этикетка: размер/цвет WB

- What changed: пересчёт приёмки — факт по строкам вручную даже при коробах; короб опционален. Этикетка 58×40 — убрано «Производитель: Россия», добавлены `wb_size`/`wb_color` из карточки WB в каталог и печать.
- What did NOT change: печать коробов/ячеек; синхронизация WB.
- Verification: pytest inbound_box + wb_catalog; e2e `ff-inbound-box-intake`, `ff-product-barcode-print`.
- Commit: 47ab877

## TASK-38 — 2026-06-10 — Этикетка товара 58×40 (EAC, артикул, количество)

- What changed: печать по образцу WB — 58×40 мм, название (обрезка), «Артикул», «Производитель: Россия», знак EAC, CODE128; диалог с превью и полем «Количество этикеток»; API `GET /products/linked-wb-catalog` — баркоды до первого движения по складу.
- What did NOT change: этикетки ячеек/коробов; накладные A4.
- Verification: pytest `test_linked_wb_catalog_before_stock_movement`; e2e `ff-product-barcode-print.spec.ts`.

## TASK-37 — 2026-06-10 — Печать ШК товара в модалках FF (приёмка, сортировка, отгрузка, упаковка)

- What changed: единый блок строки товара (фото, артикул, ШК WB, артикул продавца, nm, название) + кнопка «Печать ШК» (CODE128, 58×40) в модалках приёмки, сортировки, отгрузки на МП и упаковки; каталог WB подтягивается через `useWbProductCatalog`.
- What did NOT change: печать ШК ячеек/коробов; накладные A4; синхронизация карточек WB.
- Verification: `npm run build`; e2e `ff-product-barcode-print.spec.ts` (TC-NEW-PRINT-01).

## TASK-36 — 2026-06-03 — MP unload: без блокировки по ТЗ упаковки

- What changed: снята проверка `packaging_instructions_required` при `plan`/`confirm` отгрузки на МП; поле ТЗ на товаре остаётся опциональным.
- What did NOT change: блок `packaging_not_done` при «Отгружено», если есть незавершённое задание упаковки; UI редактирования ТЗ.
- Verification: pytest `test_seller_marketplace_unload`, `test_product_packaging_instructions`.
- Commit: df1934e

## TASK-35 — 2026-05-30 — Упаковка E7 slice 4 (FF каталог, ячейка, отмена, resync)

- What changed: FF-каталог — колонки «Не упак./Упаковано», редактирование ТЗ; создание задания из любой ячейки (не только сортировка); `POST /packaging-tasks/{id}/cancel` для ручных заданий; `pick_resync_warning` (миграция `0037`, sticky при смене подбора с прогрессом); e2e `ff-products` (ТЗ), `ff-packaging-page` (ячейка, отмена).
- What did NOT change: биллинг упаковки; ЧЗ; dismiss предупреждения resync в UI (alert пока открыто задание).
- Verification: `ruff`/`mypy`; pytest 110 passed; `npm run build`; e2e 49 passed; prod deploy `194.87.96.144:8088` (migrations 0036→0037).
- Commit: 6d8647d (main `5c9d115`)

## TASK-34 — 2026-05-30 — Упаковка E7 (этапы 1–3, PR feat/packaging-e7)

- What changed: `packaging_task` API + миграция split unpacked/packed; авто-задание при confirm MP unload; ship блок до `done`; ТЗ `packaging_instructions` (селлер UI + валидация plan/confirm); раздел FF «Упаковка»; create from sorting; прогресс в карточке отгрузки; e2e `ff-packaging-page`, regression MP ship/pick/seller; docs `PACKAGING_RU.md`, TC-NEW-PKG-*.
- What did NOT change: FF-редактирование ТЗ в каталоге; задание из произвольной ячейки; отмена задания; биллинг; ЧЗ.
- Verification: `ruff`/`mypy`; pytest 106 passed; `npm run build`; e2e `ff-packaging-page`, `ff-mp-ship-pick`.
- Commit: 642cba7

## TASK-33 — 2026-05-30 — Упаковка (этап 2: ТЗ селлера, сортировка, валидация MP)

- What changed: `PATCH /products/{id}/packaging-instructions` (селлер/админ); блок `plan`/`confirm` MP unload без ТЗ (`packaging_instructions_required`); `GET /warehouses/{id}/sorting-location`; создание задания без ячейки → зона «Сортировка»; UI селлера — редактирование ТЗ; FF — «Создать задание» на странице упаковки + кнопка «Упаковать» на сортировке; sync упаковки при подборе в короб; pytest `test_product_packaging_instructions.py`; e2e seller-mp-unload/seller-available-stock — ТЗ перед plan.
- What did NOT change: FF-редактирование ТЗ в каталоге; биллинг упаковки; ЧЗ.
- Verification: pytest (packaging + seller MP subset) locally via `.venv`.
- Commit: (pending)

## TASK-32 — 2026-05-30 — Задание на упаковку (этап 1: backend + UI)

- What changed: миграция `0036` — `quantity_unpacked`/`quantity_packed` на остатках; модели/API `packaging_tasks`; авто-задание при confirm отгрузки на МП; блок `ship` до выполнения задания; раздел «Упаковка» в меню ФФ; диалог упаковки из отгрузки на МП; pytest `test_packaging_tasks.py`; e2e `ff-mp-ship-pick` дополнен шагом упаковки. Спека: `docs/PACKAGING_RU.md`.
- What did NOT change: ТЗ на упаковку в карточке товара (поле `packaging_instructions` в БД есть, UI селлера — позже); кнопка «Упаковать» на сортировке; биллинг; ЧЗ.
- Commit: (pending)

## TASK-31 — 2026-05-30 — Пользователи ФФ: добавление и права доступа

- What changed: роль `fulfillment_staff`; таблица `ff_staff_permissions`; API `/auth/staff-accounts` (создание, список, PATCH прав); первый вход с пустым паролем как у селлера; экран «Настройки → Пользователи» с матрицей галочек (настройки, отгрузки МП, приёмка, ячейки, инвентаризация); фильтрация меню по правам; backend-guards на приёмку/отгрузки/ячейки.
- What did NOT change: управление селлерами (только админ); seller portal; полноценный раздел инвентаризации (заглушка).
- Verification: `ruff`/`mypy`; pytest `test_staff_users`; `npm run build`; e2e `ff-staff-users.spec.ts`, `admin-shell-layout`.
- Commit: eb73025

## TASK-30 — 2026-05-29 — Отгрузка на МП: обязательная дата + календарь

- What changed: `planned_shipment_date` обязательна для plan/confirm/ship; селлер не передаёт ФФ без даты; PATCH даты; общий `WmsDateField` (MUI DatePicker) на MP, приёмке селлера/ФФ.
- What did NOT change: создание черновика без даты; логика состава/коробов.
- Verification: `npm run build`; pytest `test_seller_marketplace_unload` (CI).
- Commit: (pending)

## TASK-29 — 2026-05-29 — Отгрузка на МП: единое поле скана (короб / ячейка / товар)

- What changed: убрана отдельная строка «Штрихкод существующего короба»; WHB-скан в общем поле → attach + закрытый короб внизу; ячейка и товар — как раньше в открытую тару.
- What did NOT change: API `/boxes/attach`, backend attach logic, закрытие короба кнопкой.
- Verification: `npm run build`.
- Commit: 88dfd8c

## TASK-28 — 2026-05-27 — Логин: видимая ошибка при неверном портале

- What changed: исправлен «тихий» сброс формы логина — при входе селлера на главный портал ФФ (или админа на `/seller/`) сообщение об ошибке больше не стирается; e2e `auth-portal-mismatch.spec.ts`.
- What did NOT change: правила разделения порталов (селлер → `/seller/`, ФФ → `/`); API auth.
- Verification: `npm run build`; e2e `auth-portal-mismatch`, `auth-core`.
- Commit: 1158a25


- What changed: операция `collect_into_box` — снятие с ячейки и количество в открытый короб в одной транзакции; **«Собрано»** = сумма по всем коробам; скан в короб требует `storage_location_id`; pick/scan товара только при открытом коробе; ручной подбор (модалка) добавляет в открытый короб; UI: сводка «Нужно / Собрано / Осталось», один блок «Сборка в короба», поле кол-ва.
- What did NOT change: создание/утверждение отгрузки селлером; проведение ship по pick allocations; attach inbound-короба (с box_lines).
- Verification: `npm run build` OK; pytest 99 passed (Docker py3.11); e2e — CI.
- Commit: 97c5289

## TASK-26 — 2026-05-27 — Отгрузка на МП: подбор по ячейкам, план/факт, короба WHB

- What changed: подбор **со списанием по ячейкам** — `POST .../pick/scan` (ячейка → товар), `POST .../pick/add`; факт = сумма pick allocations; строки API/UI **план / факт / Δ** (красный при расхождении); отгрузка `ship` с `acknowledge_discrepancy`; сквозные `warehouse_boxes` (ШК `WHB-…`) при создании короба; `POST .../boxes/attach` для существующего короба (разворот в pick); снят лимит «факт ≤ план» при скане; короба не обязательны для ship.
- What did NOT change: operational outbound; создание поставок в WB; seller UI (без подбора).
- Verification: миграция `0034`; pytest 96 passed; e2e 42 passed (`ff-mp-ship-pick`, inbound fixes); prod deploy `194.87.96.144:8088`.
- Commit: fb36cbf

## TASK-25 — 2026-05-27 — FF: отдельный раздел «Отгрузка» (документы на МП)

- What changed: в боковом меню ФФ пункт **«Отгрузка»** (`/app/ff/mp-shipments`) — только документы отгрузки на маркетплейс; из «Поставки и отгрузки» убраны отгрузки на МП и кнопка их создания; дашборд открывает плановую отгрузку в новом разделе.
- What did NOT change: API `marketplace-unload-requests`, логика модалки документа, бэкенд.
- Verification: `npm run build`; e2e `admin-shell-layout`, `ff-mp-ship-pick` (по возможности полный `test:e2e`).
- Commit: bf34625; prod deploy `194.87.96.144:8088`.

## TASK-24 — 2026-05-27 — Сортировка: агрегация по ячейкам

- What changed: блок «Уже в ячейках» — карточка на ячейку (чип + товары под ней); операция «весь короб» — строка «Короб №…» с составом; кнопка «Весь остаток короба сюда» под каждой ячейкой; убрана плоская таблица и колонка «По ячейкам».
- What did NOT change: API putaway.
- Verification: `npm run build`; e2e `ff-reception-sorting`.
- Commit: 4b6be9d

## TASK-23 — 2026-05-27 — Сортировка: история разкладки по ячейкам

- What changed: на карточке короба — блок «Уже в ячейках» (чипы + таблица); колонка «По ячейкам» у строк; fallback для строк без `box_id` при одном коробе; кнопка «Распределить по ячейкам» скрыта в workspace sorting.
- What did NOT change: API putaway и миграции; логика количеств.
- Verification: `npm run build`; e2e `ff-reception-sorting` (assert history chips).
- Commit: d122625

## TASK-22 — 2026-05-27 — Сортировка: разкладка по коробам (целиком и частично)

- What changed: `posted_qty` на строках короба; `box_id` в строках распределения; `POST .../boxes/{id}/putaway` (весь короб или частично); экран **Сортировка** — карточки коробов с составом, «Весь короб в ячейку», частичная разкладка по SKU; приёмка без изменений логики количества.
- What did NOT change: инвентаризация; резерв с зоны сортировки; полный экран «Поставки» (`workspace=full`) — старый черновик распределения с авто-`box_id` при одном коробе.
- Verification: `pytest` test_inbound_distribution + test_inbound_box_intake; `npm run build`; e2e `ff-reception-sorting`, `ff-inbound-distribution`.
- Commit: 2067093

## TASK-21 — 2026-05-27 — Приёмка / Сортировка: зона сортировки и остатки

- What changed: системная ячейка `__SORTING__`; остаток на `verify`; transfer в ячейки через `distribution-complete`; разделы FF **Приёмка** и **Сортировка**; колонки «В сортировке» / «В ячейках» в товарах; API `quantity_in_sorting`; e2e `ff-reception-sorting.spec.ts` (TC-S06-007).
- What did NOT change: инвентаризация для отката количества; резерв с зоны сортировки по-прежнему запрещён.
- Verification: `pytest` 95 passed; `npm run build`; e2e `ff-reception-sorting`, `ff-inbound-cell-hints`.
- Commit: 2de3092

## TASK-20 — 2026-05-25 — Поставка: пустое распределение не оприходует; reopen

- What changed: `complete_distribution` требует строки и полное покрытие принятого (`distribution_incomplete`); `POST .../distribution-reopen` если `posted_qty=0`; UI предупреждение + кнопка «Открыть распределение заново», блок «Завершить» при остатке «без ячейки»; подсказка в каталоге «Товары».
- What did NOT change: логика пересчёта/коробов; ff-catalog по-прежнему только с движениями.
- Verification: `pytest tests/test_inbound_distribution.py` (3 passed); prod deploy `194.87.96.144:8088`.
- Commit: 5998780

## TASK-19 — 2026-05-25 — Селлеры: MUI + email в одной форме

- What changed: `SellersScreen` на MUI (как «Товары»); форма название + email → `POST /sellers` + `POST /auth/seller-accounts` без пароля; `docs/UI_DESIGN_SYSTEM_RU.md`, онбординг в `MVP_DECISIONS_RU.md` + `AGENTS.md`; дашборд — ссылка в «Селлеры».
- What did NOT change: API не отдаёт временный пароль; логика `must_set_password` / первый вход с пустым паролем.
- Verification: `npm run build`; e2e `sellers-create-ui` (полный онбординг); prod deploy.
- Commit: dd1ab61

## TASK-18 — 2026-05-25 — Раздел «Селлеры» в портале FF

- What changed: экран `/app/ff/sellers` — список селлеров и форма «Добавить селлера» (`POST /sellers`); пункт навигации `nav-sellers`; e2e `sellers-create-ui.spec.ts` (TC-S04-001).
- What did NOT change: выдача аккаунта селлера — по-прежнему на дашборде (`POST /auth/seller-accounts`).
- Verification: `npm run build`; e2e `sellers-create-ui`, `admin-shell-layout`; prod deploy `194.87.96.144:8088`.
- Commit: b18340f

## TASK-17 — 2026-05-25 — Резерв без ячейки + накладные (MP + outbound) + deploy

- What changed: складской резерв на submit outbound без ячейки (миграция 0032); post по-прежнему требует ячейку; печать накладной на МП и operational outbound (`printShipmentWaybill.ts`); e2e `ff-mp-print-waybill`, `outbound-print-waybill`; `scripts/deploy/prod-update.sh`, `docker-compose.wms-host-8088.yml`, `docs/DEPLOY_SERVER_RU.md`.
- What did NOT change: seller box composition; consumables inbound; FIFO/FEFO (#14).
- Verification: `ruff`/`mypy`/`pytest` 93 passed; `npm run build`; e2e waybill specs passed.
- Commit: 3a15051

## TASK-16 — 2026-05-25 — Outbound submit: ячейка обязательна (#13)

- What changed: `submit` outbound возвращает `lines_missing_storage`, если у строки нет ячейки; решение в `MVP_DECISIONS_RU.md`; UI — обязательная ячейка при добавлении, форма в draft, блокировка кнопки submit; RU-сообщения в `readApiErrorMessage`; pytest + e2e `outbound-submit-storage.spec.ts`.
- What did NOT change: soft-reserve на уровне склада; seller submit outbound (по-прежнему только admin API).
- Verification: pytest `test_outbound_submit_storage.py`; e2e `outbound-submit-storage.spec.ts`; `npm run build`.
- Commit: 906bfd8

## TASK-15 — 2026-05-25 — Селлер: доступный остаток в UI (#15)

- What changed: экран «Товары» в портале селлера — колонки остаток, зарезерв., доступно и подсказка `(доступно N)` при резерве; e2e `seller-available-stock.spec.ts` (TC-S09-001); `TC_AUTOMATION_COVERAGE` / EN test-case note.
- What did NOT change: API `inventory-balances/summary`; MP-диалог (уже показывал «Доступно на ФФ»); operational outbound у селлера.
- Verification: `npm run build` ok; e2e `seller-available-stock.spec.ts` passed.
- Commit: c608196

## TASK-14 — 2026-05-25 — Хвосты MP unload + prod celery beat

- What changed: UI «Изменено ФФ» (`ff_modified`) в списке и карточке отгрузки на МП; `celery_beat` в `docker-compose.prod.yml` / `docker-compose.yml`; расписание `wms.wb_mp_warehouses_daily_sync` (03:00 UTC); плановая дата отгрузки на МП в общем списке FF.
- What did NOT change: operational outbound в кабинете селлера; деплой на сервер (вручную `git pull` + compose prod).
- Verification: `ruff`/`mypy` celery_app; `npm run build` ok.
- Commit: e31fd17

## TASK-13 — 2026-05-24 — Отгрузка на МП от селлера (TC-NEW-MP)

- What changed: отдельный документ `marketplace_unload` (не operational outbound): селлер — таблица остатков, plan/unplan, резерв; FF — confirm → короба/подбор/ship; дашборд ФФ по `submitted`; lazy-sync складов WB; миграция 0031, резервы; e2e `seller-mp-unload`, обновлены `ff-mp-ship-pick`, `ff-dashboard`.
- What did NOT change: индикатор `ff_modified` в UI; celery beat для daily WB sync; operational outbound в кабинете селлера.
- Verification: `pytest` 92 passed; `npm run build` ok; e2e seller-mp-unload, ff-mp-ship-pick, smoke passed; docker `compose build` + `up -d` (api, web, web_seller, celery_worker).
- Commit: 8c5a1c6

## TASK-12 — 2026-05-23 — Печать ШК ячейки и поиск по штрихкоду (US-C-03, US-C-06)

- What changed: кнопка печати ШК у выбранной ячейки в распределении FF; поле «Добавить по ШК» + Enter в picker; каталог FF = `/products` + WB-поля из `ff-catalog`; v2 inbound: поиск по ШК в `wb-catalog` merge, авто-выбор SKU; util `resolveProductByBarcode.ts`; e2e TC-NEW-C03/C06.
- What did NOT change: US-C-07 печать накладной приёмки.
- Verification: build ok; e2e barcode-add, distribution, inbound-intake passed.
- Commit: ac8f5ad

## TASK-11 — 2026-05-23 — Зелёные строки и «без ячейки» (US-C-04, US-C-05)

- What changed: строка товаров FF зелёная при `actual_qty === expected_qty` (`ff-inbound-line-row-match`); блок «Остаток без ячейки» — warning-фон и `data-pending=1` при нераспределённом остатке; e2e TC-NEW-C04/C05 в существующих spec.
- What did NOT change: v2 InboundScreen; глобальный список остатков (US-E-04).
- Verification: build ok; e2e box-intake + distribution 3 passed.
- Commit: 2aaae47

## TASK-9 — 2026-05-23 — Поштучная приёмка по скану короба INB (US-C-01)

- What changed: миграция `0029` (`inbound_intake_box_lines`, `intake_opened_at`/`intake_closed_at` на коробах); API `POST .../boxes/open`, `.../boxes/{id}/scan`, `.../close`; агрегация `actual_qty` по сканам; блок ручного PATCH actual при наличии коробов; UI на `FfInboundRequestView` и `InboundScreen`; pytest `test_inbound_box_intake.py` + хелпер `inbound_box_intake_helpers.py`; e2e `ff-inbound-box-intake.spec.ts` (TC-NEW-C01); обновлены регрессионные тесты/e2e под box-scan.
- What did NOT change: подсказки ячеек (US-C-02), зелёные строки, предварительные остатки только по коробам, состав короба от селлера.
- Verification: `pytest` 86 passed; `npm run build` ok; e2e 3 passed (`ff-inbound-box-intake`, `ff-inbound-distribution`).
- Commit: a9cebe6

## TASK-10 — 2026-05-23 — Подсказки ячеек при распределении (US-C-02)

- What changed: `GET /operations/inventory-balances/locations-by-product`; чипы «Уже лежит: A-01 (N)» в блоке распределения FF (`FfInboundRequestView`), клик подставляет ячейку; pytest `test_product_location_hints.py`; e2e `ff-inbound-cell-hints.spec.ts` (TC-NEW-C02).
- What did NOT change: подсказки при поштучном скане в короб (только этап распределения); v2 InboundScreen.
- Verification: pytest 87 passed; e2e cell-hints 1 passed; build ok.
- Commit: a453666

## TASK-8 — 2026-05-22 — Внутренние ШК на короба поставки (US-B-02)

- What changed: таблица `inbound_intake_boxes`, генерация N коробов с `INB-{hex}` при primary-accept; API `boxes` в заявке и `POST .../boxes/{id}/mark-label-printed`; UI панель «Короба и внутренние ШК» с печатью; миграция `0028`; pytest расширен; e2e TC-NEW-B02 в `ff-inbound-boxes.spec.ts`.
- What did NOT change: скан короба на поштучной приёмке (US-C-01), паллетирование, предварительное увеличение остатков только по коробам.
- Verification: `pytest tests/test_inbound_box_acceptance.py` (3 passed); `npm run test:e2e -- tests-e2e/ff-inbound-boxes.spec.ts` (5 passed, TC-NEW-B01/B02).
- Commit: pending

## TASK-7 — 2026-05-22 — Приёмка по коробам (US-B-01 / US-A-01)

- What changed: поля `planned_box_count` / `actual_box_count` / `boxes_discrepancy` на заявке поставки; селлер указывает план коробов в черновике; ФФ принимает факт на этапе «Принято по коробам»; предупреждение при расхождении; миграция `0027`; merge `0026`; pytest `test_inbound_box_acceptance.py`; e2e `ff-inbound-boxes.spec.ts` (TC-NEW-B01).
- What did NOT change: внутренние ШК на короба (US-B-02), предварительное увеличение остатков только по коробам, паллетирование >10 коробов.
- Verification: `pytest tests/test_inbound_box_acceptance.py`; `npm run build`; Docker `api`+`web` пересобраны.
- Commit: pending

## TASK-6 — 2026-05-22 — Отгрузка на МП: подбор по ячейкам и списание при «Отгружено»

- What changed: статус `shipped` и `POST .../ship` списывает остатки по сохранённому подбору (товар × ячейка); `PUT .../pick-allocations` сверяет сумму с фактом скана в коробах; UI — «Начать подбор», «Утвердить заявку» (без списания), «Отгружено»; миграция `0025`; e2e `ff-mp-ship-pick.spec.ts` (TC-NEW-MP-01).
- What did NOT change: ТЗ упаковки в карточке товара, статус «Начата сборка», расходники, откат отгрузки, приёмка по коробам.
- Verification: `pytest tests/test_marketplace_unload_and_discrepancy_acts.py`; `npm run build`; `npm run test:e2e -- ff-mp-ship-pick.spec.ts ff-dashboard.spec.ts`.
- Commit: pending

## TASK-5 — 2026-05-03 — Production Docker Compose HTTPS via Caddy

- What changed: production `docker-compose.prod.yml` now publishes `80/443` for Caddy, persists ACME state in Docker volumes, and passes `WMS_PUBLIC_DOMAIN` into the `web` container; production Caddy site blocks use the public domain for automatic HTTPS; added `deploy/env.prod.example` and updated README production instructions for DNS + HTTPS.
- What did NOT change: application code, database schema/migrations, Celery task definitions, and dev `docker-compose.yml` behavior were not changed in this task.
- Verification: `WMS_PUBLIC_DOMAIN=example.com POSTGRES_PASSWORD=postgres JWT_SECRET_KEY=dev-secret WMS_SECRETS_FERNET_KEY=dev-fernet DATABASE_URL='postgresql+psycopg_async://postgres:postgres@db:5432/wms' docker compose -f docker-compose.prod.yml config --quiet`; `ruff check . && mypy . && pytest` in `backend/`; `npm run build` in `frontend/`.
- Commit: 20b1aef

## TASK-3 — 2026-05-03 — Post accepted seller inbound distribution into FF stock

- What changed: completing FF inbound distribution now creates inventory movements and balances from distributed actual quantities, so accepted seller products appear in the FF warehouse catalog.
- What did NOT change: seller private WB catalog import, marketplace shipment flows, billing, migrations, and Docker infrastructure were not changed in this task.
- Verification: `ruff check app/services/inbound_intake_service.py tests/test_inbound_distribution.py && mypy app/services/inbound_intake_service.py`; `pytest tests/test_inbound_distribution.py tests/test_products_wb_catalog.py`.
- Commit: d5a954f

## TASK-2 — 2026-05-03 — Split seller and FF product catalogs

- What changed: renamed the FF products endpoint to `/products/ff-catalog` and changed FF catalog visibility to products with warehouse movements only; seller `/products/wb-catalog` remains private to the seller role.
- What did NOT change: seller WB import mechanics, marketplace shipment stock movements, adjustment acts, billing, and docker-compose infrastructure were not changed in this task.
- Verification: `ruff check app/api/products.py app/services/seller_wb_catalog_service.py tests/test_products_wb_catalog.py && mypy app/api/products.py app/services/seller_wb_catalog_service.py`; `pytest tests/test_products_wb_catalog.py`; `npm run build`; `npm run test:e2e -- ff-products.spec.ts`.
- Commit: 4089d7e

## TASK-1 — 2026-05-03 — FF products catalog

- What changed: added the fulfillment admin products catalog screen with seller filtering, sorting by product name/stock, WB photo/barcode enrichment, and backend/admin API coverage.
- What did NOT change: marketplace shipment stock movements, adjustment acts, billing, and docker-compose infrastructure were not changed in this task.
- Verification: `ruff check . && mypy . && pytest` in `backend/`; `npm run build` and `npm run test:e2e` in `frontend/`.
- Commit: 728e894
