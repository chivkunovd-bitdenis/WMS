# WMS-652/663 — независимое Astra high review процессной дельты

**FAIL** для `8cc4bc390f2ae4e3d985c0b7ed769c8c903972b2`: два воспроизведённых
дефекта новых ограничений R39. Требуется исправление и повторное ревью этих
дефектов. Существующая реальная цепочка WMS-663 проходит scope-validator,
но это не доказывает невозможность обхода нового процессного правила.

Проверка 06.10.2026 выполнена отдельной сессией; из аргументов родительского
процесса прочитаны только модель `gpt-6-astra` и `model_reasoning_effort="high"`.
Skills, агенты, браузер, секреты, live DB/API, Telegram и deploy не использовались.
Владение ограничено этим отчётом. Продукт, тесты, требования и чужие файлы не менялись.

Сравнение checker выполнено с независимо проверенным
`de8e8973549eaedbd3f6c34e779405a44a5141ad`. Текущий HEAD при проверках —
`17a23e03b7f262387749447ecef3e58a8c90b321`, непосредственный потомок 8cc4bc39;
его единственное отличие — отчёт `2026-10-06-wms652-663-process-integration.md`.
Checker blob точного 8cc4bc39 и рабочего дерева:
`228de985abb90a108f41e73e92e5b0ef754dd3d7`.

Прочитаны локальный AGENTS.md целиком, актуальный AGENTS.md после fetch
origin/etalon `954862b718f9f2f1faefb2f00ad2fef72a6e1929`, полные owner-cases.md
(104 строки) и failure-cases.md (359 строк), R39, интеграционный отчёт,
healthy-positive-fixture-correction handoff и предыдущее процессное ревью.
Особенно применимы B11/B14: точная версия и зелёные проверки не заменяют
проверку причины ошибки. Прямое поручение владельца определяет модель и объём.

## F1 — P2: история слияния скрывает изменение и возврат frozen-файла

Место: `scripts/ci/check_task_documents.py:331–333`.
Проверка разрешает более поздний source, если обычный path-limited `git log`
пуст. Однако Git упрощает историю: merge, одинаковый по этому пути с основным
родителем, позволяет исключить боковую ветку из такого вывода. В результате
промежуточные изменение и возврат файла в вошедшей ветке не обнаруживаются.

Независимое воспроизведение через существующий тестовый harness: после первой
разрешённой коррекции создана боковая ветка; на ней frozen Python-файл изменён,
затем восстановлен; основная линия продвинута отдельным коммитом; выполнено
`merge --no-ff`, после него обычная пятая коррекция и связанный синтетический review.
`git log --format=%H baseline..source -- path` вернул пустую строку, а тот же
запрос с `--full-history` показал оба промежуточных коммита.
`contract_change_errors` ошибочно вернул `[]`.

Это нарушает R39 «при отсутствии любых изменений этого пути между прежним
baseline и source» и явно заявленную защиту от изменения с последующим возвратом.
Конечные before/after blob при этом остаются закреплёнными: обход относится
к полноте истории, а не к разрешению произвольных конечных бизнес-ожиданий.
Нужно проверять полную историю пути, включая вошедшие боковые ветки, и добавить
регрессию с таким merge. Прямолинейный существующий `gap=True` этого не проверяет.

## F2 — P2: существующий handoff другого режима считается отсутствующим

Место: `scripts/ci/check_task_documents.py:353`; причина также в семантике
`git_blob` на строках 229–242. `git_blob` возвращает None как для отсутствующего
пути, так и для существующего пути с mode, отличным от 100644. Поэтому условие
отсутствия handoff в родителе не доказывает отсутствие самого Git tree entry.

В изолированной цепочке до correction создан handoff с произвольным текстом
и mode 100755. Его реальное присутствие подтверждено `git ls-tree`:
`100755 blob b1a131fa618a45e9ca2532127235b2ccd815d504` по точному handoff path.
Correction заменил текст закреплённым blob и mode на 100644, сохранив полный
разрешённый набор путей. Валидатор снова вернул `[]` вместо отказа.

Это нарушает заявленное условие «до коррекции отсутствует». Проверку отсутствия
нужно отделить от проверки разрешённых типа/mode/blob: любой существующий entry
в родителе должен отклоняться. Добавить отрицательный сценарий с существующим
исполняемым файлом; аналогичную неоднозначность symlink следует закрыть тем же
условием. Конечный handoff по-прежнему обязан иметь закреплённые байты и mode;
их подмена в correction/HEAD обычным текстовым файлом корректно отклоняется.

## Подтверждённая часть интеграции и собственные проверки

Полные новые fixture-тексты из JSON независимо сопоставлены с Git-объектами:
Python `4e1aff5a80445fa61b5697d60a26985427dfd28e` →
`c92c075ba9f375c578538b776207cdc6b8b56ab3`; handoff
`75319cb7026d032af7e47946b4b636aadc39c8eb`. В allowlist ровно пять пар.
Прежние три process-test файла и старый fixture JSON побайтно совпадают с de8;
также совпадает перенесённый process handoff. Изменение новой lambda после
RED-коммита только связывает old/new аргументами по умолчанию и сохраняет ожидания.

Реестр и Git подтверждают исходный контракт
`ae2ebd3d17f4e7364b1b52de4126b8f70937652b`, первую коррекцию
`76f2162e22f1aa9e33a336b01109882d8a8969c6` и её настоящий scoped PASS
`4306d91b3a1963999780329127c19144e4902cf1`, evidence blob
`4d0860e779ff6325584a14ae39065aecf12fd7b3`. Вторая коррекция
`17ce363a8360620bc6b843e003278cd4ea106678` имеет непосредственного родителя
`1fd2d92dc30eb376c1d8a8e27238e52d963a196e` и отдельный PASS
`e27c0eab577fd7cc183aeec14c2451e1c7d8b7c2`, evidence blob
`ea2aab84f2b8d48966c74f11abd463ced0837228`. Валидатор реальной цепочки вернул
без ошибок baseline Python=17ce363 и DOM=76f2162. Исторический продуктовый FAIL
первого review не превращён в PASS продукта.

Diff backend, frontend и требований WMS-662/663/675 между e27c0eab5 и 8cc4bc39
пуст. Продукт 1fd2d92 и содержание fixture-коррекции 17ce363 заново не ревьюились:
их независимые PASS из e27c0eab5 остаются отдельными доказательствами.

Выполнено независимо:

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts/ci -p 'test*.py' -q`:
  **77 tests, 150.719s, OK, exit 0**. Старые 73 проверки сохранены.
- Четыре новых теста с checker из de8, загруженным только в память:
  **4 tests, 24.398s, 3 ожидаемых assertion failures, 0 errors**.
  Исторический RED воспроизведён; RED-коммит 1eb2fa4 предшествует реализации.
- Отдельный положительный контроль и отрицательные пробы unknown transform,
  неверного source, неверного review source, незакреплённого initial handoff:
  положительный принят, все четыре отрицательных случая отвергнуты.
- Набор из 77 проверяет бизнес-assertions, имена, skip/параметры/ранний return,
  чужие blob, лишние пути, mode, пропуск/перестановку дельт, отсутствие review,
  мутацию handoff в HEAD и другой полный SHA review с тем же префиксом.
  Два дополнительных случая F1/F2 проходят ошибочно и в эти 77 не входят.
- Ruff checker и нового тестового файла с `--no-cache`, `git diff --check`,
  совпадение локальных AGENTS.md/CLAUDE.md — PASS.

## Полный документный checker остаётся красным

Команда `python3 scripts/ci/check_task_documents.py <base>` отдельно выполнена
с обеими точными базами: `0f1460b023700a99f17b504d6af3934a02bc68cc` и
`954862b718f9f2f1faefb2f00ad2fef72a6e1929`. В обоих случаях **exit 1,
ровно 20 исторических ошибок**, сверенных программно с полным ожидаемым списком:

- WMS-662: `Нет вердикта у проверки: C1` … `C19` — все 19 отдельных ошибок.
- WMS-675: `В таблице с колонкой «Класс» нет колонки «Тест».` — одна ошибка.

Ошибок WMS-663 в текущей реальной цепочке нет. Требования не переписывались,
приёмка не выдумывалась; этот scope PASS не превращает полный checker в PASS.
Full CI, продуктовые тесты, приёмка аналитиком и выпуск здесь не выполнялись.

## Повторяемое воспроизведение F1/F2

Запустить из корня checkout. Код создаёт только временные синтетические Git-репозитории
через существующий harness; производственные файлы не меняет. Синтетические review
не являются настоящими независимыми заключениями. На 8cc4bc39 оба результата — `[]`.

```python
import inspect
import sys
import textwrap
sys.path.insert(0, "scripts/ci")
import test_wms663_positive_fixture_chain as t

case = t.PositiveFixtureChainTests()
case.setUp()
try:
    repo = case.repo
    commit_original = repo.commit
    def commit(subject):
        if subject == "product delta leaves frozen files unchanged":
            branchpoint = repo.git("rev-parse", "HEAD")
            repo.git("checkout", "-qb", "side-probe")
            path = "backend/tests/test_wms663_customs_documents_contract.py"
            repo.write(path, t.DATA["before"] + "\n# unreviewed mutation\n")
            commit_original("side change")
            repo.write(path, t.DATA["before"])
            commit_original("restore bytes")
            repo.git("checkout", "--quiet", branchpoint)
            commit_original("unrelated mainline product commit")
            repo.git("merge", "--no-ff", "-qm", "merge side", "side-probe")
        return commit_original(subject)
    repo.commit = commit
    print("F1", repo.errors(case.chain()))
finally:
    case.doCleanups()

source = textwrap.dedent(inspect.getsource(t.PositiveFixtureChainTests.chain))
source = source.replace(
    'source = repo.commit("product delta leaves frozen files unchanged")',
    'repo.write(DATA["handoff_path"], "existing handoff\\n")\n'
    '    (repo.root / DATA["handoff_path"]).chmod(0o755)\n'
    '    source = repo.commit("product delta leaves frozen files unchanged")',
)
source = source.replace(
    'repo.write(DATA["handoff_path"], DATA["handoff"])',
    'repo.write(DATA["handoff_path"], DATA["handoff"])\n'
    '    (repo.root / DATA["handoff_path"]).chmod(0o644)',
)
namespace = dict(vars(t))
exec(source, namespace)
case = t.PositiveFixtureChainTests()
case.setUp()
try:
    print("F2", case.repo.errors(namespace["chain"](case)))
finally:
    case.doCleanups()
```

**Заключение:** процессная дельта 8cc4bc390f2ae4e3d985c0b7ed769c8c903972b2
получает FAIL до устранения F1/F2. Исправления checker и новых регрессий в этом
review не выполнялись. Main/etalon не изменялись; отчёт публикуется отдельным
коммитом существующей рабочей ветки без merge/deploy.
