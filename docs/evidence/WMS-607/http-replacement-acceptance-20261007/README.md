# WMS-607: replacement acceptance, только P-A5/P-A6

**Software PASS на `dc652472d75812dbebc68ef4353a718b0f629cbe`; вся607 и выпуск
не приняты.** Прежняя `artmaks_test_contract` сессия недоступна из-за agent thread
limit. По прямому назначению её заменяет Sol6.1/high analyst
`01a11390-1014-76a0-9302-fbe0fd46ed1f`, автор R52/652, не автор607 product/tests/review.
Исходная отрицательная приёмка77443 и требования обновления сохранены как история
и отдельный pending-контракт соответственно; оригинальному аналитику подпись не приписана.

[Независимый TECHNICAL PASS](https://github.com/chivkunovd-bitdenis/WMS/blob/12c7826257c495c78edf1ede7a37587403fbb942/docs/evidence/WMS-607/artmaks-http-recovery-review-20261007/review.md)
`12c7826257c495c78edf1ede7a37587403fbb942` проверил точный77443→dc652,
Swift11 insert/3 delete. [Source probe](source-probe.json) связывает source/hash,
неизменные тесты, raw результаты и текущую приёмку без нового исполнения.
Actual frozen HTTP contract — `443bcbdf19ec3c81c1fc04dbc53a5a9a45ead609`, до кода;
переданный короткий443bcb2 не является Git revision.

| Требование → проверка | Сохранённый actual результат | Вердикт |
|---|---|---|
| R12 → P-A5 | Native Swift HTTP без protocolVersion:409 failed_before_submit, восстановление lpstat fixture, тот же POST200 accepted, повтор200 с той же receipt. До кода target assertion RED; после PASS. | Подтверждено в software contour |
| R12 → P-A6 | При failed_before_submit конкретная stored reason включена в legacy error, которое читает существующий экран. До кода target assertion RED; после PASS. | Подтверждено в software contour |

HTTP5 сохранены:2 targetRED/3 preservationPASS→5PASS0skip/error. Recovery-control
key отдельно доказывает восстановленную службу: его lp плюс1 lp исходного same-scan
дают2 в этом raw; same-scan не отправляется дважды. Supplemental8 одновременных
same-key legacy POST получают8 accepted с одной receipt и1 native Process вызовом
внешней lp fixture. Unknown/submitting/accepted cases остаются строгими; unsafe
COPY mutation даёт3 meaningful assertion RED. Автоматического unknown retry нет.
Повтор использует существующий retry только для validated failed_before_submit
под существующим recursive lock, без нового ключа/receipt/rebind или frontend правки.

Сохранённые prior frozen6/resolver5/native3 PASS0skip/error подтверждают прежний
58×40/copies1, публичный stable9a33/.4 receipt replay и journal3348. Bad wholeSwift
ed053 не выбран как база. Прежние P-A1–P-A4 не переписаны; P-A7 вручную pending.
Реальные HTTP/server/Printer/worker/журнал проверялись разработчиком с контролируемыми
lp/lpstat executable fixtures и изолированным store; это не клиентская CUPS/бумага.

R-U1–R-U8/U-C1–U-C10, updater/rollback, packages/distributionCI/immutable URLs,
установка/штатные разрешения/physical58×40 и читаемый QR/Telegram не приняты.
После этого software PASS ведущий может передать неизменённую updater-постановку
отдельному тестировщику до installer-кода. Новый вопрос владельцу не требуется.
652/main/etalon/production не изменены; интеграция туда не выполнялась.
Новых tests/browser/native print/build/install/provider/secret действий аналитик
не делал. Все прочие backlog sections и updater section сохранены побайтно.
