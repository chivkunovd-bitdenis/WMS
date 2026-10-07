# WMS-652: независимое ревью двух CI fixture corrections

**Frontend: PASS для `a0261518f5d292e7f178f1e59ad1d20ec10a051e`, proof `05788bae14880fc93171e7c48a65ff825f343415`. Backend: PASS для `bdfea8e006c9dd7a15341b9aef27abeaaefa3b02`, evidence `1e65ec682c4afd870b98edf85ca723b18115842b`.** Продолжение той же независимой Sol6.1/high reviewer session. Native PASS1373, прежние F6/672/PDF и продуктовые приёмки не повторялись. Проверяемые исходники прочитаны исключительно по immutable Git SHA; чужие рабочие файлы не редактировались.

После fetch прочитан актуальный `origin/etalon:AGENTS.md` на `4c532f0cccfb8f99b34d68d9630a3763038fbc5f`. Полные owner/failure библиотеки, прочитанные ранее в этой сессии, остались неизменными.

## Frontend: ограничение времени и teardown

Прочитаны README и все четыре сырых лога ca6-dom-clock, а также оригинальный Linux CI log run 37553998053. Его первый 5000 ms timeout относится к сценарию шести печатных jobs и двух remount; далее видны overlapping act, ошибки terminal-state/detail loads и четыре каскадных FAIL. Исходная isolated версия проходит 11/11: это не воспроизведение Linux нагрузки и не основание переписать тот CI FAIL в PASS. Controlled 1500 ms fault воспроизводит прерывание первого сценария и последующий каскад: до коррекции все пять выбранных случаев FAIL.

Исправление включает fake Date/setTimeout/clearTimeout **только в dedicated DOM suite**. Реальный production delayed-print callback выполняется через controlled advancement внутри act; assertions по-прежнему требуют фактические print jobs, marks, recovery/readback и terminal UI. Никакой callback не вызывается вместо beforeTransfer, printer или mark. Product screen, JsBarcode/print utility, PDF tests, workflow и policy не изменены. Deadline и 200 × 10 ms polling bound не увеличены. Для других consumers сохраняется real timer branch.

Оригинальные it bodies/идентификаторы и бизнес-assertions сохранены; самостоятельный AST audit после удаления ровно трёх новых job-count assertions получает прежние test bodies. Новые проверки усиливают обе recovery ветки: ровно один job до/после явной reconciliation, второй только для документа B. Harness отменяет owned polling waits при dispose и дожидается их settlement **до** unmount/restoration; afterEach гарантированно очищает таймеры и возвращает real clock. Rejection остаётся rejection, а не successful print result. Реальный сохранённый iframe onload доставляется один раз; поздний jsdom navigation load не дублирует handoff.

Reviewer выполнил узкие probes фактических fixture functions на синтетических act/clock/iframe boundaries: успешное ожидание требует наблюдённого state, неуспешная бизнес-проверка после 200 попыток возвращает исходную ошибку, abort до/во время turn отвергается, real branch не вызывает fake advance. Два explicit load обращения плюс queued platform load доставляют один сохранённый callback с исходным srcdoc. Это собственные локальные method probes, **не** исполнение React/browser/11-case suite.

Опубликованный ordinary after log содержит 11 PASS. Negative after log честно остаётся **1 intentional timeout FAIL / 4 PASS / 6 filtered**, без overlapping act warning; он доказывает ограничение каскада, не зелёный весь набор. Авторские ESLint/tsc PASS прочитаны как evidence, здесь не воспроизведены. Результат технически достаточен для этой fixture timing/lifecycle ошибки; production latency и новый Linux full CI этим не доказаны.

## Backend: строгое UTC-представление после round-trip

Оригинальный backend shard log того же CI действительно сравнивает `2026-09-01 10:30` без timezone с тем же `10:30+00:00`: один FAIL при 2287 PASS. Прочитаны product parser `_parse_datetime`, оба timezone-aware model columns и точные исходные posting_row поля `in_process_at`/`shipment_date`, содержащие Z. Продуктовый parser уже возвращает UTC; фикстура должна различать потерю SQLite tzinfo и ошибку самого timestamp.

Pure commit изменяет только test_ozon_posting_contract.py. Добавленный refresh принуждает читать сохранённый объект вместо случайного identity-map состояния. Normalization разрешает **только naive результат фактически SQLite dialect** интерпретировать как UTC без изменения часов/минут/даты. Другие dialects обязаны вернуть aware значение и сохраняют тот же instant через astimezone(UTC). Проверка timezone=True добавлена. Точные ожидаемые UTC instants обоих полей, исходная дата, price 250000, barcode и остальные тесты/декораторы неизменны.

Самостоятельный AST audit доказал сохранность всех прочих test functions и оригинальных assertions после удаления ровно normalization wrapper слева в двух сравнениях дат. Reviewer исполнил настоящий helper отдельно: naive SQLite и эквивалентный aware instant принимаются; **wrong hour для SQLite/PostgreSQL, wrong day, потерянный tzinfo PostgreSQL и неожиданный aware SQLite отвергаются**. Это не округление времени, сравнение только даты или безусловное снятие timezone.

Прочитаны реальные command outputs автора: refresh-before воспроизводит RED, целевой SQLite файл даёт 44 PASS. Сверены actual PG XML/log и оба опубликованных SHA-256: единственный точный date scenario PASS, без failure/error/skip. Исполнителем SQLite/PG был исходный writer; reviewer не запускал backend заново. Новая интерпретация технически достаточна для этой representation ошибки и сохраняет чувствительность к неверному source instant.

## Границы заключения

Оба PASS относятся только к указанным тестовым коррекциям. Historical Linux/negative FAIL сохранены, intentional fault не посчитан зелёным. Product modifications, изменение frozen бизнес-ожиданий, generic timeout/timezone exemptions, final SOURCE/P/S, полный CI, продуктовая приёмка и deploy этим отчётом не разрешены/не объявлены пройденными. Обновление точных frozen fixture/policy bindings производится отдельно после этого реального review publication.

Собственные scripts/results и byte-preserving author readbacks: `docs/evidence/WMS-652/final-ci-fixtures-review-20261007/`. Воспроизведение узких probes: `node .../front-audit.cjs` и `python3 .../backend-audit.py` с полным путём этого evidence каталога. Новые агенты, dependency installs, весь DOM/backend набор, полный CI и старый 680 graph не запускались.
