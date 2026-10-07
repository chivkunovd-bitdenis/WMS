# Отдельный тестовый контракт до реализации

База: `585877bedf948faf7e38d14acc7e89acbf4feab3`. Постоянный checkout:
`.worktrees/wms653-scope-attribution-20261006`, ветка
`codex/wms663-owner-checkbox-test-contract-20261006`. Тестировщик — фактический
Sol 6.1; разработчик priority_663 ожидает опубликованный контракт, runtime не менялся.
Источник нового прямого поручения владельца и аудита аналитика:
`c395a68d3f2477fba8eda923f967dd69c7ca5b28`,
`docs/reviews/wms663-666-frontend-rollback-scope-20261006.md`.

## Единственные отменённые прежние ожидания

Владелец требует одну галку «Без ГТД и РНПТ» в Коробах текущей Ozon-поставки,
без строковых форм и отдельного сохранения. Поэтому прежний C16 в
`FfFbsSupplyWorkspace.wms663.dom.test.tsx`, требовавший раскрытия строки,
полей номеров и сохранения по экземпляру, заменён семью целевыми DOM-проверками.
Backend per-exemplar API и все прежние backend guards сохранены; они продолжают
защищать маркировку, чужие документы и реальные ответы Ozon.

Владелец также отклоняет добавленный чип в Составе. В C19 WMS-662 отменены только
две soft-проверки текста этого чипа; вместо них проверяются отсутствие добавленного
чипа и прежняя ссылка прямо в ячейке. Подбор, история, закрытие/повторное открытие,
отсутствие любых внешних writes/печати и остальные исходные assertions сохранены.
Удалён только вспомогательный visibleText, использовавшийся этими двумя assertions.
Старые чипы FbsAssemblyTaskRows, охрана WMS-681 и другие бизнес-контракты не менялись.

## Новая минимальная защита

Frontend: отсутствие row-document blocks; одна unchecked галка только в Коробах
Ozon; отсутствие её у WB; открытие без writes; явный POST точного текущего order
`/ozon-exemplar-documents/absent` с `{expected_version:4}`; persisted unknown intent
после нового mount, обратный клик без стирания/повтора; конкретная ошибка через
существующий supply alert и доступное закрытие; исходное слово «упаковано».
Не создаются тестовые ожидания новых panels, statuses, instructions или save buttons.

Backend: отдельный файл `test_wms663_owner_absent_batch_contract.py` фиксирует
`documents.save_absent_exemplar_documents` с согласованной сигнатурой. Пять cases:
один SET на два SKU/три реальных экземпляра, только требуемые документы отсутствуют;
точное полное равенство payload сохраняет marks, weight и нетребуемые ГТД/РНПТ;
HTTP200 не доказывает accepted; persisted version/choices и чужая metadata сохранены;
unknown после потери ответа переживает новую DB session, повтор делает только STATUS;
чужой tenant и WB отвергаются до I/O; устаревшая версия не делает SET.

## Фактический RED на базе 585 до runtime-кода

Команда из frontend:
`npm exec --yes --package=node@20 -- node node_modules/vitest/vitest.mjs run src/screens/v2/FfFbsSupplyWorkspace.wms663.dom.test.tsx src/screens/v2/FfFbsSupplyWorkspace.wms662.c19.dom.test.tsx --no-file-parallelism`.
Результат: **7 FAIL / 1 PASS**, 18.11 s. Единственный PASS — неизменная граница WB.
Первый отказ C19 — реально присутствующий `fbs-status-chip`; A1 — один row block
вместо нуля; A2/A4/A5/A6 — отсутствие галки; A7 — реальный текст «Обработано».
Последующие assertions transport/unknown/error на исходном runtime ещё не достигнуты;
их PASS не заявляется. После этого RED проверка отсутствия кнопки «Сохранить» ограничена
контекстом Коробов: существующая metadata-кнопка в шапке остаётся разрешённой.
Error assertion уточнён до существующего role=alert; исходный первый отказ A6 тот же.

Команда из backend:
`/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -n 0 -q tests/test_wms663_owner_absent_batch_contract.py`.
Результат: **5 FAIL**, 2.32 s, все по явному отсутствию новой операции, без collection
или environment failures. Ruff этого нового тестового файла — PASS.

Реальная геометрия: ведущий выполнил read-only функцию в CUA IAB на staging585,
1600×1000, две WB и три Ozon строки. **RED**: размер 230 px, стикер 100 px,
ЧЗ 68 px при допуске 1 px. Копия исходного JSON и browser DOM функция сохранены в
`docs/evidence/WMS-666/mixed-packing-geometry-red-20261006.json` и
`mixed-packing-geometry-contract-20261006.js`. Это реальные rect.right,
не source-string assertions и не jsdom geometry. Local Chrome/Playwright не запускались.

## Сохранение и передача

Прежние UI-контракты исправлены отдельными коммитами, чтобы будущий реестр коррекций
мог ссылаться на точную однофайловую дельту после независимого review:
`667a136a2760ff62fc181f47772290a8388587c6` — только C19 WMS-662;
`35ac50caa77f1ca5eb1905a23a730e1dee1e2f45` — только frontend C16→owner WMS-663.
Новый backend контракт: `da3a34a8005489c85899d310c038691ff490d8cf`.
Последующая однофайловая привязка ошибки к supply alert заменяет frontend baseline
35ac при cumulative ledger. Фиктивного review/PASS в ledger нет.

Scope666 изучен без изменения guard: новый backend runtime имеет primary WMS-663;
отдельная геометрия/rollback666 остаются frontend и его evidence namespace.
Pending/index/untracked по-прежнему проверяются; общая история после интеграции
должна быть чистой. Backend не разрешён глобально для666.

Контракт фиксируется до реализации. GREEN, независимое review, staging после
коррекции и CI пока не заявляются. Skills/Astra/общий CI не запускались.
