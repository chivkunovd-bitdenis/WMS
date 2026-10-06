# WMS-652: handoff узкого fixture-only пути

06.10.2026. Самостоятельный ремонт процесса по прямому поручению владельца,
без skills/subagents и без рекурсивного запуска продуктовых ролей. Ownership:
checker, его новые отдельные регрессии, дополнение requirements WMS-652 и этот
handoff. Продукт, frozen tests и guards WMS-517/663, их существующие реестры,
исторические review и прочая чужая работа не менялись. Никаких cherry-pick
в продуктовые ветки, merge, CI, deploy, Telegram или действий с секретами.

Свежий origin/etalon получен fetch; проверен AGENTS.md из точного
`0f1460b023700a99f17b504d6af3934a02bc68cc`. Ветка продолжает существующую
`codex/wms652-disjoint-contract-corrections`, основу checker `8d6cdd80c` и R33–R35.
Оба governance handoff WMS-517/663 и исходные исторические diff/review прочитаны.

## Почему новый путь достаточно узкий

Новый формат `fixture_corrections` выбирается явно. Прежние одиночный/массивный
форматы сохраняют strict subset и запрет пересечений; их ожидания не изменены.
Новый путь закрепляет четыре точные полные before/after Git blob-пары, а не
доверяет названию fixture или неполному сравнению только assert. Все остальные
байты Python/TSX должны совпасть. Поэтому имена, assertions, параметризация,
skip/xfail/only, ветвления, импорты и любые иные изменения отвергаются автоматом.
Отдельный тест проверяет, что полные исторические тексты отличаются ровно
описанными UUID capture, explicit seed keyword и двумя DOM selector заменами.
Общий механизм AST-нормализации намеренно не нужен: он существенно шире этих
четырёх проверенных полных пар. Новые случаи требуют отдельного расширения
checker и новых RED, а не произвольной записи реестра.

Каждая запись содержит настоящий исходный контракт, exact source/correction
SHA и exact files/blob. Источник файла обязан быть исходным контрактом либо
предыдущей проверенной коррекцией этого файла. Первый родитель correction
должен содержать именно исходный blob; changed paths всего коммита обязаны
совпасть с записью. Файлы в HEAD, включая нетронутые frozen файлы, сравниваются
с конечной цепочкой. Разрешён только обычный файл Git mode 100644. Симлинк,
изменение mode, смена HEAD во время проверки и подмена SHA вызывают отказ.

432516e8 содержит также legacy fixture. Для него допускается единственный
companion: точная полная before/after blob-пара test_withdrawal_ledger.py.
Произвольные дополнительные файлы не допускаются. Companion проверяет область
исторического коммита; он не становится новой замороженной бизнес-проверкой,
не легализует изменения до/после этого коммита и не заменяет их review/приёмку.
427fc2 отсутствует в allowlist и остаётся бизнес-миграцией, не scope-only.

Для каждой дельты нужны отдельные Astra high PASS и exact source/correction
SHA в review записи, path/evidence_commit/evidence_blob. Review artifact должен
быть отдельно сохранён после correction, входить в HEAD, оставаться неизменным
и называть проверенную коррекцию. Старое сокращение SHA допускается от 9 символов
только если оно действительно является префиксом exact correction; другой
полный SHA с совпавшими 9 символами не принимается. Checker не удостоверяет
авторство модели криптографически: реальное независимое review получает и
честно записывает ведущий, как и в прежнем протоколе. PASS продукта не подменяет
отдельный PASS дельты; отдельный PASS дельты не означает PASS продукта.

## RED и локальные проверки

Первый отдельный контракт опубликован в `e76dd7aa1`: 8 методов на полных
исторических файлах, 4 адресных RED на старом checker. Второй контракт
`990941dff` добавил 5 методов; до исправления подтверждены 2 RED на mode и
на подмене полного SHA в review. Оба контракта сохранены до соответствующих
исправлений; их файлы после этих коммитов не менялись.

Единый заключительный прогон: **73 passed, 209.473s, exit 0** — все 60 прежних
проверок checker и 13 новых. Ruff implementation + дополнительные edge tests
пройден без исключений. Для первоначального frozen regression harness применён
только `--ignore B023`: его два lambda синхронно вызываются внутри того же цикла
(не сохраняются для позднего выполнения). Это три предупреждения lint об
отсутствии захвата loop variable, а не изменение тестового ожидания. Frozen
harness ради lint не правился. Ни один gate или рабочий CI config этим
исключением не изменён.

Команды:

```sh
python3 -m unittest discover -s scripts/ci -p 'test*.py'
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/ruff check scripts/ci/check_task_documents.py scripts/ci/test_fixture_contract_correction_edges.py
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/ruff check --ignore B023 scripts/ci/test_fixture_contract_corrections.py
```

## Проверка реальных продуктовых Git-деревьев

Предложенные записи находятся рядом с этим handoff:
[WMS-663.proposed.json](2026-10-06-wms652-fixture-only-handoff/WMS-663.proposed.json),
[WMS-517.proposed.json](2026-10-06-wms652-fixture-only-handoff/WMS-517.proposed.json).
Это reviewable handoff inputs, не установленные записи в продуктовых ветках.
В WMS-517 у второй дельты честно сохранён `review: null`.
Полные результаты и проверенный blob checker:
[local-results.json](2026-10-06-wms652-fixture-only-handoff/local-results.json).

На WMS-663 HEAD `9f93170c7e05378cf9b06cab095f7cb88ff0d124` новый
`exact_fixture_corrections` с предложенной записью реально вернул baseline
`76f2162e22f1aa9e33a336b01109882d8a8969c6` для обоих frozen файлов и **пустой
список ошибок: scope PASS**. Моков Git, подмен HEAD или редактирования продуктовой
ветки не было. Review взят из `4306d91b3a1963999780329127c19144e4902cf1`,
отчёт wms663-astra-7d9e9.md; его PASS относится к коррекции, продуктовый FAIL
не переписан.

На WMS-517 HEAD `447dd60ba64e559b573ce8838a0ca6bbf544337e` frozen файл совпадает
с конечной дельтой 432516e8, но реальный валидатор возвращает:
`WMS-517: fixture-only: нет отдельного Astra high PASS точной дельты`.
SC10 review 445c78a3 называет 042d9dbac; он не объявлен review 432516e8.
Без отдельного review этой второй дельты PASS не заявляется.

Общий `check(root, 0f1460b...)` с **существующими committed ledger** остаётся
красным: у WMS-517 — последующая мутация frozen sales contract; у WMS-663 —
прежнее strict-subset ограничение старого формата, 19 пустых вердиктов C1–C19
WMS-662 и отсутствие колонки «Тест» в таблице с «Класс» WMS-675. Последние
ошибки не относятся к новому пути. Полный общий GREEN не заявляется.

Повтор scope с этого checkout (только чтение, JSON для 517 намеренно даст отказ):

```sh
python3 - <<'PY'
import importlib.util, json
from pathlib import Path
spec = importlib.util.spec_from_file_location('checker', 'scripts/ci/check_task_documents.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
for task, worktree in [('WMS-517', 'wms517-sales-report-contract'), ('WMS-663', 'wms662-663-priority')]:
    root = Path('/Users/deniscivkunov/Projects/WMS/.worktrees') / worktree
    ledger = json.loads(Path(f'docs/reviews/2026-10-06-wms652-fixture-only-handoff/{task}.proposed.json').read_text())
    print(task, c.git(root, 'rev-parse', 'HEAD'), c.exact_fixture_corrections(root, task, ledger['fixture_corrections'][0]['contract_commit'], ledger))
PY
```

## Следующие действия ведущего

1. Независимое Astra high review точного опубликованного checker SHA из отчёта.
2. Отдельное review exact 042d9 → 432516e8, включая полный companion diff,
   затем добавить настоящие immutable evidence поля в предложенную 517 запись.
   Не дописывать PASS в исторический 445c78 и не выдумывать новый вердикт.
3. Уполномоченному владельцу governance перенести новый формат в существующие
   product ledger отдельными коммитами (сохранить исторические exclusions и
   честно обновить устаревший protocol_status), без изменения tests/product.
4. Повторить полный checker на фактических HEAD: для 663 после миграции записи
   ожидаются перечисленные посторонние doc errors до их отдельного исправления.
   Для 517 нужны review второй дельты и запись всей цепочки. Это прогноз,
   а не выполненная миграция или уже зелёный общий checker.

Независимое review самого ремонта, приёмка продукта и CI ещё не выполнялись.
История, main/etalon, установленные продуктовые checker и runtime не менялись.
