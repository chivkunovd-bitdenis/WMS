# WMS-663 / WMS-666 / WMS-662: текущая функциональная приёмка, 06.10.2026

**Программная коррекция принята на `1fe678d9abb4ed06afc79eba41461e3215978d5b`;
реальная визуальная C11 PENDING, физическая C12 OPEN.** Заменяющий аналитик Sol6.1
восстановил исходные слова/контракт и прежние отклонения, прочитал опубликованные
proofs и [отдельный независимый TECHNICAL PASS](wms663-666-owner-correction-independent-review-20261006.md)
`764701a36738170b255cb2faf8fdab3a77609e4d`, blob `b92b8a9e0b041f4e1253d4b89037c9271aad6f7f`.
Новый продуктовый прогон или собственное независимое code-review не заявляются.

663 соответствует прямому поручению: ровно одна «Без ГТД и РНПТ» в Ozon Коробах,
без production row forms/новых панелей/кнопок; ошибки через существующий supply
feedback. GET-only opening, явный bounded batch, сохранённый intent и unknown
readback не дают повторной записи/стирания. F1/F2/F3 закрыты reviewer: первая
неотправленная подготовка возобновляется, штатный КИЗ сохраняет выбранное отсутствие,
полный no-documents posting не блокирует другие required posting; partial/undefined
не превращаются в доказательство отсутствия требований. Внешний live SET не выполнен.

666/662 возвращают исходное «упаковано», history Link без нового composition chip,
удаляют sx ради row documents и дают целевую общую колонную разметку. Прежние чипы588,
QR681 и scan→immediate print сохранены по прочитанной ограниченной дельте/review.
Фактическая геометрия rect.x нового установленного стенда ещё не предъявлена:
старый585 rejection сохранён как история и не заменён ложным visual PASS.

Авторские proofs: [runtime progress](../evidence/WMS-663/boxes-checkbox-runtime-progress-20261006.md)
содержит10 backend PASS и3 completeness UI PASS на1fe; ранее44 UI/layout PASS и
8 UI PASS относятся к своим версиям, не названы повторным прогоном final1fe.
Reviewer самостоятельно получил7 backend наd01 и3 backend/3 UI наfinal1fe;
исторические PG-only skip не приписаны новым целевым10. Tsc/build и OpenAPI4 PASS
учтены с авторской атрибуцией. Actual staging, бумага, живые документы Ozon,
боевой выпуск и новый общий CI остаются отдельными этапами.

Owner test corrections667a/23b и отдельный F3 fixturea08 имеют настоящий
Sol6.1 high PASS764; реальные ledger заполнены exact source/final/evidence SHA/blob.
Legacy662 и прежняя fixturechain663 сохранены. Независимое ревью process-checker
8b/088 идёт отдельно, это product/test review его не подменяет. Требования/backlog
обновлены без удаления исходной истории; устаревшие test-name ссылки663 заменены
реальными A2/A5/A6 owner cases. Общий docgate запускает ведущий один раз.
