# WMS-652 / WMS-666: точная классификация исторических документов

Source: `cc8e6a019559343ac404e168a92ad36137255672` (CI37491310077).
Test-only: **`b1742141c4625d7ed9e238132d94ffea402f49ee`**, один scope-файл.
В CI frontend1555PASS/1FAIL; runtime, docs/backlog/guards зелёные по передаче ведущего.
Собственный целевой RED:7PASS/1FAIL,6.54s — ровно три документальных пути;
GREEN:11PASS,9.16s. Команда из frontend:
`node node_modules/vitest/vitest.mjs run src/screens/v2/wms666ChangeScope.test.ts --reporter=verbose`.
Node24.13.1, существующие deps через symlink, ничего не устанавливалось.

| Immutable commit | Исключается только этот path/blob transition | Весь commit |
| --- | --- | --- |
| `1d34b77874e1b1396d8bdd216bd0053a4a308440` | requirements517: `aca08cc54...` → `89a8fb5f...` | четыре docs, factual CI/staging SC16 update по прямому поручению |
| `c5d9255e5d912e13398c883961d0c476ee5a1938` | rollback scope: `664aa8ea...` → `c68d9ac1...` | один doc, сохранённый ранний аудит |
| `8ec0fcd6c7625a4351e6e9a04dfe80f055ac398a` | rollback scope: `c68d9ac1...` → `664aa8ea...`; earlier scope: absent → `9dda566e...` | два docs, возврат immutable owner artifact и перенос аудита |

Полные SHA/path/blob и wholecommit changedPaths закреплены в scope-test;
регулярный100644 Git blob обязателен, creation проверяет отсутствие старого файла.
Это историческая атрибуция, не разрешение новых правок этих путей: общий classifier
по-прежнему их отклоняет. Future committed, dirty и index-only edits всех трёх
путей проверены в одноразовых Git repositories. Старые8 assertions/cases сохранены,
workflow exception не расширена, backend/migrations/stock/guards запрещены.
Missing immutable objects fail closed. Expected fatal Git output относится к
отрицательным fixture-cases, не к ошибке GREEN. Raw [RED](red.log), [GREEN](green.log).

Два cumulative ledger refs original0e078/071a05 обновлены на exacttestSHA;
предыдущие Sol/Astra provenance сохранены целиком в previous_review.
Новая независимая оценка пока **PENDING**, передана отдельной сессии662 сразу
после push. Никакого фальшивого PASS, productreview, deploy или общего CI здесь нет.
Общий CI source продолжает ведущий; историю не переписывали.
