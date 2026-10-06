# WMS-662 / WMS-663: exact owner-supersession gate, 06.10.2026

Прямое поручение ведущего по новому требованию владельца разрешает узкое изменение
процесса без новой продуктовой задачи и рекурсивной цепочки. Автор этого изменения
— Sol6.1; независимое ревью ещё не выполнено. Runtime и продуктовые тесты не менялись.
Основа собственной ветки — опубликованный owner contract `4c9e1238c85a50a9238bc109651c79cac5f10e03`.

## Изменение

В ledger добавлен отдельный `owner_supersessions`, который не называется fixture-only.
662 сохраняет исходный однофайловый legacy ledger `c466c65b → 5feca959`, без
преобразования в array и без снятия запрета whole-frozen для новых обычных коррекций.
663 сохраняет весь прежний fixture chain и его exact blob/review проверки.
Новый слой допускает ровно два опубликованных изменения старых UI-ожиданий:

- 662 C19: original `2006171f0feae5513f887b471125ecae1a96c2ae`,
  `667a136a2760ff62fc181f47772290a8388587c6`, blob
  `04379c221c29e9a70ae195ff3d834e1855b375de` → `eda2d0d82663c76a3042e3a161fb47f164ad4f08`.
- 663 прежний C16: original `ae2ebd3d17f4e7364b1b52de4126b8f70937652b`, reviewed
  frontier `d9e022697e098a2f9c0feee6a5bf03f99cac5945`; изменения
  `35ac50caa77f1ca5eb1905a23a730e1dee1e2f45` → `23b222dede4869ae6035c55175f5d14f6a6af5f4`,
  blobs `7b41916c43bf144d9fdeb7772d415bdf5535ff05` → `87d14b74cbfa4f7f119bb0c6374929259fed5dc5`
  → `e177548bb5a728cad63b32528071c1c5ac9995e1`.

Пины охватывают task/original/source/prior/path/every correction/blob. Source именно
`585877bedf948faf7e38d14acc7e89acbf4feab3`. Owner-request artifact привязан к
`4c9e1238c85a50a9238bc109651c79cac5f10e03`, точному пути и blob, неизменному в HEAD.
Обычные correction commits меняют ровно разрешённый UI-файл. Промежуточное изменение
и dummy revert/reapply после source/final отклоняются, включая merges/mode changes.
Сверка Git lineage учитывает потомков нужного frontier, а не добавление его идентичной
копии на другой интеграционной ветке. Фактически проверены119 commits 662 и125 commits
663 между reviewed frontier и585: различий исходного UI-blob нет.

Только после валидного отдельного Sol6.1 high PASS, artifact commit/blob и полного
final test SHA в тексте новый слой заменяет финальную HEAD-сверку этих UI-путей.
Все остальные frozen файлы сравниваются по прежним правилам. Историческая fixture
цепочка проверяется целиком даже при новом owner layer; её отрицательный review
не обходится. F3/new-file fixture не включён и требует отдельной честной записи,
если тестировщик его корректирует.

## Проверки

- 16 owner-supersession Git regressions PASS, включая тот же кейс RED на старом
checker из4c9 и GREEN на новом, legacy whole-file guard, сохранность fixture chain,
PENDING, owner/review identity, полные SHA, чужие frozen файлы, mode, duplicate,
изменение→возврат и FAIL-artifact с подложным PASS в ledger.
- 14 существующих fixture/edge regressions PASS.
- 61 существующая проверка check_task_documents PASS.
- `git diff --check` PASS. Общий CI/продуктовые тесты не запускались.

Все synthetic PASS artifacts в process-regressions явно synthetic и живут только
в одноразовых Git repositories. Они не используются в настоящих ledger.

## Что пока не принято

Оба настоящих owner-layer review остаются **PENDING**. Независимый Sol6.1 high
review выполняет отдельная сессия662, итогового artifact пока нет; он не придуман.
Gate честно остаётся закрытым до сохранения фактического review и интеграции test
commits в общий HEAD. Для завершения добавить в каждую новую review-запись реальный
`evidence`, `evidence_commit`, `evidence_blob`, сохранить `source_commit=585...` и
точный final test `correction_commit` (667a для662 /23b для663), и только по факту
PASS изменить verdict. Artifact должен называть полный проверенный final test SHA
и PASS; исторические review-записи не менять. Затем независимый reviewer проверит
сам этот узкий process diff. Данная ветка не является общим runtime кандидатом.
