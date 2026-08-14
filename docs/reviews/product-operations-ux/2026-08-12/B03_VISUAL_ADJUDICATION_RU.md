# Батч 03. Личный visual verdict по каждому PNG

Все **58/58** кадров ниже лично открыты через `view_image` в оригинальном разрешении. `VALID` означает, что кадр сам показывает названное состояние. `LIMITED` — кадр полезен только для явно указанной части и не доказывает остальное. Runtime/DOM observations не превращают слабый PNG в визуальный `VALID`.

| PNG | Visual verdict |
|---|---|
| `b03-001-ff-admin-session-1280x720.png` | **VALID.** FF dashboard и admin-контекст видны; экран перегружен статистикой, но служит только session proof. |
| `b03-002-reception-queue-populated-1280x720.png` | **VALID.** Очередь populated; рядом черновики и рабочие строки, номера документа нет, seller/date/line count видны. |
| `b03-003-queue-keyboard-focus-skips-rows-1280x720.png` | **LIMITED.** Визуального focus на строках нет; отсутствие keyboard semantics подтверждено runtime, сам кадр показывает лишь тот же queue. |
| `b03-004-exact-submitted-inbound-detail-1280x720.png` | **VALID.** №000007, план 2 короба, A=3/B=2 expected, факт 0/0 и две Completion CTA видны; seller в detail отсутствует. |
| `b03-005-detail-close-returns-queue-1280x720.png` | **VALID.** После Close виден queue без dialog. |
| `b03-006-detail-reload-loses-open-document-1280x720.png` | **VALID.** После reload detail отсутствует, пользователь снова в queue. |
| `b03-007-exact-detail-reopened-after-reload-1280x720.png` | **VALID.** Exact detail снова открыт вручную, исходные строки/план видны. |
| `b03-008-exact-detail-1920x1080-dpr1.png` | **VALID с layout caveat.** Wide metrics доказаны; detail почти касается правого края, seller всё ещё отсутствует. |
| `b03-009-empty-scan-disabled-no-mutation-1280x720.png` | **VALID.** Пустое поле, disabled scan CTA и неизменный факт видны. |
| `b03-010-unknown-barcode-error-no-mutation-1280x720.png` | **LIMITED.** Факт не изменён, но toast на самом кадре уже не читается; текст ошибки подтверждён только Browser runtime. |
| `b03-011-valid-scan-a-once-1280x720.png` | **VALID.** A=1 и B=0 видны; поле очищено, визуального focus ring нет. |
| `b03-012-queue-raw-receiving-after-scan-1280x720.png` | **VALID.** Рабочая строка показывает технический статус `receiving`. |
| `b03-013-valid-scan-one-reload-readback-1280x720.png` | **VALID.** После reload A=1 сохранился; product metadata временно показаны тире, что увеличивает сомнение в identity. |
| `b03-014-two-repeat-scans-a-reach-three-1280x720.png` | **VALID.** A дошёл ровно до 3 и match-state визуально зелёный. |
| `b03-015-manual-negative-quantity-error-1280x720.png` | **VALID.** Отрицательное значение и конкретная красная validation видны у строки. |
| `b03-016-decimal-quantity-silently-floored-1280x720.png` | **VALID.** После ввода decimal B отображается как 2 без сообщения. |
| `b03-017-decimal-floor-reload-readback-1280x720.png` | **VALID.** Reload сохраняет B=2; silent transformation durable. |
| `b03-018-blank-quantity-silently-ignored-1280x720.png` | **VALID.** После blank-save B остаётся 2, ошибки нет. |
| `b03-019-blank-ignore-reload-readback-1280x720.png` | **VALID.** Reload снова показывает B=2; пустое действие не объяснено. |
| `b03-020-manual-overage-five-warning-1280x720.png` | **VALID.** A=5, красная строка и общий warning видны, но точной дельты `+2` нет. |
| `b03-021-manual-overage-reload-readback-1280x720.png` | **VALID.** Overage пережил reload. |
| `b03-022-exact-fact-a3-b2-1280x720.png` | **VALID.** Обе строки 3/3 и 2/2 зелёные; compact total `5/5` отсутствует. |
| `b03-023-exact-fact-reload-readback-1280x720.png` | **VALID.** Exact match durable. |
| `b03-024-create-box-doubleclick-result-1280x720.png` | **LIMITED.** Верх detail неизменён, box-row ниже fold почти не виден; точное число коробов подтверждено runtime/следующими кадрами. |
| `b03-025-box-reload-readback-1280x720.png` | **LIMITED.** Reloaded detail виден, но сам box-row ниже fold; durable box доказан `026`. |
| `b03-026-box-fill-dialog-empty-1280x720.png` | **VALID.** Dialog показывает номер/ШК короба, scan input и обе строки с 0; layout понятен. |
| `b03-027-box-unknown-scan-error-1280x720.png` | **VALID.** Ошибка `Товар не найден в этой поставке` хорошо читается, состав 0/0. |
| `b03-028-box-valid-scan-a-one-1280x720.png` | **VALID.** В dialog box A=1, за ним общий A=4 при плане 3: двойной учёт виден в одном кадре. |
| `b03-029-box-negative-quantity-error-1280x720.png` | **VALID.** Negative box qty и конкретная validation видны. |
| `b03-030-box-decimal-silently-floored-1280x720.png` | **VALID.** Box B=1, общий B=3 при плане 2, ошибки нет; обе проблемы видны одновременно. |
| `b03-031-nonempty-box-delete-disabled-1280x720.png` | **VALID.** Box 1/1, Delete disabled; причины блокировки рядом нет. |
| `b03-032-box-composition-reload-readback-1280x720.png` | **VALID.** Reopened dialog сохраняет A=1/B=1; фон сохраняет общие 4/3. |
| `b03-033-empty-box-ready-delete-1280x720.png` | **VALID.** Короб очищен до 0/0, Delete стал active. |
| `b03-034-empty-box-deleted-no-confirm-1280x720.png` | **VALID.** Dialog сразу исчез, empty-state коробов виден; confirm/Undo отсутствуют. |
| `b03-035-box-delete-reload-readback-1280x720.png` | **VALID.** После reload коробов нет, A/B вернулись к 3/2. |
| `b03-036-controlled-underage-b-one-1280x720.png` | **VALID.** B=1/2 красный, общий warning виден; дельта не вынесена в summary. |
| `b03-037-underage-completion-confirmation-1280x720.png` | **VALID.** Generic confirm виден; ни SKU, ни 1/2, ни −1, ни последствия stock не названы. |
| `b03-038-underage-completion-cancelled-1280x720.png` | **VALID.** После Cancel detail остаётся receiving, B=1. |
| `b03-039-cancel-reload-still-in-reception-1280x720.png` | **VALID.** Строка вернулась в Reception и показывает raw `receiving`. |
| `b03-040-exact-lines-no-boxes-no-warning-before-complete-1280x720.png` | **VALID.** A/B exact и empty boxes видны, header всё ещё говорит план 2; box mismatch warning отсутствует. |
| `b03-041-complete-doubleclick-single-sorting-result-1280x720.png` | **VALID.** Один completed state «В сортировке», A/B 3/2, success feedback и `Редактировать` видны. |
| `b03-042-completed-absent-from-reception-1280x720.png` | **VALID.** Exact seller row с двумя lines больше не находится в Reception. |
| `b03-043-matching-sorting-queue-five-units-1280x720.png` | **VALID.** Exact seller/date row в Sorting, qty=5, raw status `sorting`. |
| `b03-044-matching-sorting-detail-readonly-entry-1280x720.png` | **VALID.** №000007 и accepted A=3/B=2 с remaining 5 видны; B04 action не нажата. |
| `b03-045-catalog-sorting-stock-after-reception-1280x720.png` | **LIMITED.** Unfiltered catalog не показывает synthetic строки в видимой области; не является stock proof. |
| `b03-046-catalog-filtered-synthetic-stock-1280x720.png` | **LIMITED.** Synthetic rows найдены, но horizontal overflow обрезает identity слева и часть stock справа. |
| `b03-047-catalog-filtered-stock-1920x1080-dpr1.png` | **VALID.** На честном wide viewport видны A/B и все stock columns: sorting-only 3/2, available 0. |
| `b03-048-dashboard-completed-detail-reopen-action-1280x720.png` | **VALID.** Completed detail показывает `Редактировать` и дальнейшую action-area; последствия reopen не объяснены. |
| `b03-049-reopen-immediate-no-confirm-1280x720.png` | **VALID.** После одного click document уже в «Приёмка»; промежуточного confirm не было. |
| `b03-050-catalog-stock-reversed-after-reopen-1280x720.png` | **LIMITED.** Видимые synthetic stock values обнулены, правые columns частично clipped; runtime дал полный read-back. |
| `b03-051-reopened-document-back-in-reception-1280x720.png` | **VALID.** Документ снова появился в Reception с raw `receiving`. |
| `b03-052-final-recompleted-for-b04-1280x720.png` | **VALID.** Повторное completion вернуло state «В сортировке» и exact 3/2. |
| `b03-053-final-sorting-queue-readback-1280x720.png` | **VALID.** Финальный exact row в Sorting, qty 5. |
| `b03-054-waybill-print-action-outcome-1280x720.png` | **LIMITED.** После click экран visually unchanged; preview/печать не доказаны. |
| `b03-055-browser-back-route-changes-dialog-persists-1280x720.png` | **VALID.** Route перешёл к Reception, но Sorting detail остался поверх экрана — видимое state/history расхождение. |
| `b03-056-browser-forward-restores-sorting-detail-1280x720.png` | **VALID.** Forward возвращает Sorting route при том же открытом dialog; контекст не перерисовывается ожидаемо. |
| `b03-057-final-catalog-stock-a3-b2-sorting-only-1280x720.png` | **LIMITED.** Финальные synthetic rows видны, но ключевые правые stock columns скрыты горизонтальным overflow. |
| `b03-058-final-catalog-stock-reload-readback-1280x720.png` | **LIMITED.** Reload сохраняет строки/часть значений; полный stock verdict опирается на valid wide `047` и runtime state log. |

## Visual coverage result

- Лично просмотрено: **58/58 PNG**.
- Полностью самостоятельные визуальные доказательства: **47**.
- Ограниченные кадры, у которых scope явно сужен: **11** (`003`, `010`, `024`, `025`, `045`, `046`, `050`, `054`, `057`, `058` и wide-layout caveat `008`).
- Ни один limited frame не используется как единственное доказательство более широкого PASS.

