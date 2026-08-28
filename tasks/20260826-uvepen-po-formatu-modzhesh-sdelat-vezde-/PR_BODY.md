## Summary

Новые обычные физические короба `WHB` и `INB` получают один постоянный WB-совместимый Code 128: префикс и 14 символов Crockford Base32, всего 18 символов. Такая длина физически декодируется со штатной этикетки 58×40 мм при 203 dpi. Старые сохранённые коды продолжают сканироваться без миграции. FBS-короба, официальные QR грузомест и QR поставки не изменялись.

## Product gate

- [x] `BA_READY` — feature_cards и дословная просьба зафиксированы в `tasks/20260826-uvepen-po-formatu-modzhesh-sdelat-vezde-/NARYAD.md`.
- [x] `PRODUCT_APPROVED_FOR_DEV` — контракт экрана, API/данных и тест-кейсов зафиксирован до финальной реализации в `tasks/20260826-uvepen-po-formatu-modzhesh-sdelat-vezde-/CONTRACT.md`.
- [x] Разработка выполнена в изолированной именованной ветке; границы исключают весь FBS runtime и его тесты.
- [x] Полные локальные гейты пройдены: Ruff, mypy, `1054 passed, 5 skipped`; production build и Playwright `202 passed, 7 skipped`.
- [x] `CODE_REVIEW_PASSED` — изолированная сильная модель повторно проверила формат, вероятность коллизии, старые коды, все генераторы обычных коробов, физическую печать и отсутствие изменений FBS. Отчёт: `tasks/20260826-uvepen-po-formatu-modzhesh-sdelat-vezde-/CODE_REVIEW.md`.
- [x] `PRODUCT_BROWSER_APPROVED` — независимый судья прошёл сценарий в реальном браузере с видимой вкладкой: новый 18-символьный INB-код, старый 30-символьный код, модалка печати 58×40 и экран FBS без ошибок консоли.
- [x] Evidence_paths: `docs/evidence/20260826-uvepen-po-formatu-modzhesh-sdelat-vezde-/backend-verification.md`, `docs/evidence/20260826-uvepen-po-formatu-modzhesh-sdelat-vezde-/inbound-box-live.png`, `docs/evidence/20260826-uvepen-po-formatu-modzhesh-sdelat-vezde-/inbound-box-label-live.png`.

### Test coverage

| TC-ID | Applies | Notes |
| --- | --- | --- |
| TC-NEW-B02-WB-BOX-01 | Y | Given создаются новые обычные WHB/INB-короба, when генератор выдаёт и сохраняет `internal_barcode`, then значение имеет точный формат `<PREFIX>-[0-9A-HJKMNP-TV-Z]{14}`, длину 18 и остаётся тем же при повторной загрузке. Negative: валидатор отклоняет пробелы, кириллицу, длину вне 6–30 и запрещённый префикс `WB_`. Restriction: генератор разрешён только для WHB и INB. |
| TC-NEW-INTERNAL-LABEL-01 | Y | Given оператор запускает общую печать коробов, when production helper строит одно печатное задание штатного размера 58×40, then все сохранённые коды присутствуют в HTML, каждый Code 128 достаточно крупный и первый реальный штрихкод декодируется обратно без искажения. Expected: кнопка блокируется на время операции и снова доступна после результата. |
| TC-NEW-INTERNAL-LABEL-02 | Y | Given реальный `internalBox` renderer и плотность термопринтера 203 dpi, when четыре худших шаблона и 256 детерминированных 18-символьных кодов рендерятся на 58×40 мм, then ZXing декодирует каждый код точно. Negative canary: известный небезопасный 20-символьный код при той же геометрии не должен декодироваться, чтобы тест обнаруживал возврат к слишком длинному формату. |
| TC-LEGACY-BOX-SCAN-01 | Y | Given в базе уже сохранены старые WHB/INB-коды, when выполняются настоящие SQLite/service attach и scan paths, then короб находится без миграции и переклейки. Restriction: существующие значения не переписываются, а FBS-коды и официальные WB QR остаются вне изменения. |

## Test plan

- `ruff check app tests` — passed.
- `mypy app` — passed, 307 source files.
- Full backend pytest — `1054 passed, 5 skipped`.
- Production frontend build — passed.
- Full Playwright — `202 passed, 7 skipped`.
- Physical Code 128 regression — 260 positive values decoded exactly at 58×40 mm / 203 dpi; unsafe 20-character canary rejected.

## Browser review

Agent: `final_feature_browser_judge`. Isolated local frontend `127.0.0.1:5191`, API `127.0.0.1:18102`. Verified at 1280×720 in a real visible browser; local review servers were stopped after the verdict.
