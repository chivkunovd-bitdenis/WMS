# WMS-675: штатное живое чтение Ozon, 06.10.2026

**Прочитаны все 31 отправление, 31 HTTP 200.** Run UTC
`2026-10-06T11:31:00.430695+00:00` → `2026-10-06T11:31:05.846885+00:00`.
Collector `767f19fd2f4ba479f2034f915c0f16a1a4d962d4`, отдельное
[независимое ревью PASS](independent-reader-review-767f19fd2.md).
Это живые ответы Ozon, не синтетика и не чтение cached WMS statuses.

Штатная среда: существующий `wms_prod-api-1`, `/app`, Python 3.11.17.
Использовано seller-bound подключение внутри обычного приложения. Перед
запуском SHA256 двух файлов совпали с опубликованными; настройки/credentials
не переносились, не печатались и не менялись. Read-only snapshot WMS завершён
до HTTP. Не запускались sync, conduct, deliver/ship/approve, печать или записи.
Повторных попыток не было; stderr пуст. Reader завершился exit0,
`READ_COMPLETE_REQUIRES_ACCOUNTING_PLAN`; unread_postings=[] и unknown=0.

## Точный состав и flags

Tenant `b80a893b-ab87-42b6-8fd7-6d41502c900f`, seller
`cf6d31c5-944b-4382-af34-636ca9aa8cc3`, supply
`b82d1e9a-30d2-4d7b-b52d-9775c3d266e3`, warehouse
`2d968c65-4a8d-414e-9076-0f201c2dba63`. Документ WMS остаётся draft.
Все 31 карточка содержат ровно одну единицу; SKU/offer/quantity совпали
с текущими 31 позициями scoped snapshot. Related/weight lists присутствуют
и пусты во всех карточках: дополнительных posting для чтения нет.

- 15 delivering: 9 posting_in_pickup_point, 6 posting_on_way_to_city.
- 11 delivered / posting_received.
- 4 cancelled / posting_canceled: 0181745532-0045-3, 0282817049-0013-1,
  80034639-0273-1, 99185584-1963-5. У последних двух cancelled_after_ship=true
  не считается доказательством новой сдачи.
- 1 awaiting_packaging / posting_created: 0148656673-0134-1.

По исходной таблице WMS-662 26 единиц имеют положительный статус и точный
состав; 4 отмены и 1 подготовка исключены из новой положительной передачи.
Это классификация прочитанного доказательства. Текущие ledger/movements
данным reader не читались; already_conducted_quantity и missing_delta
оставлены null, mutation_authorized=false. Резерв snapshot=16 не заменяет
проверку расхода. Исполнитель675 рассчитывает missing delta и план отдельно;
прежний снимок нулевого расхода на06:53–06:54UTC не выдаётся за текущий.

## Сохранённые доказательства

[Manifest](live-ozon-run-20261006-attempt1/manifest.json), scope_snapshot и31
posting JSON находятся в том же каталоге. SHA256 всех31ответов и snapshot
проверены против manifest (32/32), полный список файлов —
[live-read-checksums-20261006.json](live-read-checksums-20261006.json).
[Поштучная классификация](fresh-read-position-classification.json) сохраняет
точные позиции и связи с proof/hash, без восстановления/списания.

Результаты дополнительно сохранены в постоянном каталоге runner
`/opt/wms/audits/wms675/proofs-20261006-attempt1-767f19fd2f4ba479f2034f915c0f16a1a4d962d4`.
Возврат HTTP200 и положительный внешний статус не разрешают мутацию.
Следующий шаг — план675 по точному составу и свежему локальному учёту.
