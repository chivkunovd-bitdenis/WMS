# Замещающая приёмка WMS-652/517 перед итоговым CI

Отдельная сессия Sol6.1 заменяет недоступного исходного аналитика текущей
постановки. Приёмщик не подписывает исторические результаты от его имени.
Прочитаны исходные слова, последние уточнения владельца, требования, актуальные
правила etalon, аналитический навык и независимые заключения этой дельты.
Общая предъявленная база: `0151a555ac429957d0eee591317cc4326e909dfd`.
Постоянная ветка `codex/wms652-517-release-acceptance-20261006` внутри разрешённой
`.worktrees`. Изменены только два документа требований, их строки канонического
бэклога и этот каталог доказательств. Product/tests/registry не редактировались.

## Факты, принятые по доказательствам

`probe.py` читает сохранённые XML/TAP/JSON и Git bytes, проверяет current scope
CLI и регистрацию точных имён. Он не запускает тела прежних product tests,
браузер, CI, production API или внешнюю операцию. `probe.json` содержит результат
и полные параметризованные имена случаев.

- WMS-517: integrated110 уникальных TAP случаев совпали с exact registry110,
  все PASS, без skip. Четыре helper/launcher/generator/command файла совпали с
  `7a2fa31d83e06b2724edbcca1aaead0914ad5e56`; command SHA256
  `6e60684bbe8318178f0c97d34507f9a93f811c74ed3e2631ae249ac02a8505c9`.
  Прочитано независимое Astra high заключение
  `1bd1d850842860d0360133908a78a6cb68527e9e`: настоящий React/MUI0/700ms PASS,
  по одному native certificate dialog,6 registry GET,0signature/submit.
  До фикса separate frozen regression давал109 PASS/1 target FAIL; прежние109
  expectations сохранены, одинаковые unsafe TAP titles получили только index.
- WMS-652 C59: raw independent JUnit содержит51 точный whole-product scope
  PASS и20 shards PASS, дополнительно45 subtest records. Actual current scope
  относительно fixed `d61805978b3e7878d1056c99b4e6e0823edf49a5` пуст. Неизменённый
  product source не смешан с новыми process/test/docs changes.
- Geometry: exact43 упорядоченных случаев и PASS на source
  `1c045a4f2d6c1bb34eeed2f5e79f6e53be2a8a9d`; все12 browser closure files
  совпали. Три raw mutant reports имеют тот же43 состав и только7/2/1
  targeted assertion FAIL, остальные36/41/42 PASS. Измерения real Chrome
  1600×1000/long-data и HTTP boundaries являются synthetic тестовой средой.
  Independent Sol6.1 review `15c974f2232555cc4348a9b57059b13ba2f99514`
  подтвердил это отдельно; live browser в этой приёмке не повторялся.
- Remount: прочитан независимый `remount-selection-key-review.md`; исходный
  и восстановленный explicit selection имеют одинаковый key, а product mutant
  меняет только этот key и даёт3 meaningful RED. Это QR-only в трёх входах;
  print keys/pack и прежние business assertions сохранены.
- Registry:222 protected files/1146 suite IDs побайтно проверены, exact reports
  shards20/scope51/Mac110/browser43 зарегистрированы. Prepared first policy
  не выдаётся за самопринятую действующую trusted baseline.
- GitHub saved readback: ruleset24431521 active,9 requiredchecks, strict current
  base, no bypass. Main `045272b51f28829b6220410856e9216a3054ce33` содержит
  независимый checker/workflow по опубликованной передаче. Это данные настроек;
  конкретный SOURCE pin и работающий denial/canary этим не подтверждены.
- Fullbackend:4625 unique saved collection→2313/2312,0intersection,exact union;
  independent fresh collection/review совпал. Это сбор имён, не4625 PASS.
  Шардинг принят как механизм, цель полного CI10–15 минут ещё не измерена.

## Заключение

**Программная Mac-дельта517 и предъявленная process/scope/geometry/CI-дельта652
приняты в указанных границах. Общая WMS-652 и production-выпуск не приняты.**
Нет открытого воспроизведённого дефекта именно этой предъявленной дельты; прежний
700ms Mac P1 и C59 отсутствующий контракт закрыты. Полнота любых ещё неисполненных
вариантов карты не выводится из локального числа PASS.

До выпуска нужны конкретный независимо принятый SOURCE/bootstrap pin,
operational process-integrity denial/canary на текущем base, полный CI точного
итогового SHA со всеми обязательными platform/PG/browser/PDF/Mac/scope/shards
reports и отдельное доказательство installed SHA/runtime. По предъявленной
передаче production остаётся `8f11d912351e8de7633b4abcf74d195badaeb254`.

Последнее прямое уточнение владельца меняет последовательность WMS-517:
проверенное программное исправление выпускается до личной проверки Виталика.
SC14/SC15/SC18 не выполнены и остаются после выкладки; доступность Виталика,
реальный Mac/сертификат/ГОСТ-подпись/terminal ЧЗ не являются предварительными
условиями software release. Их результат не объявляется выполненным, вопрос
о его доступности повторно не требуется.

Документальный gate проверяет заполненность, а не готовность выпуска. Его
успех не превращает сохранённые «не проверено» в PASS и не разрешает production.

Воспроизводимая проверка из корня этой worktree:

```sh
python3 docs/evidence/WMS-652/release-acceptance-20261006/probe.py
python3 scripts/ci/check_task_documents.py d61805978b3e7878d1056c99b4e6e0823edf49a5
git diff --check
```
