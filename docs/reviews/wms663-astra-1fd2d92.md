# WMS-663: независимое Astra high ревью F4-R и коррекции fixtures

06.10.2026. **Product PASS — точный SHA `1fd2d92dc30eb376c1d8a8e27238e52d963a196e`, в пределах четырёхстрочной правки F4-R.** Неполный свежий STATUS больше не подтверждает все показанные документы. Конкретный F4-R из предыдущего FAIL закрыт; оставшихся технических дефектов в этой дельте не обнаружено.

**Fixture correction PASS — точный SHA `17ce363a8360620bc6b843e003278cd4ea106678`, отдельно от продукта.** Три положительные фикстуры (подготовленные ответы транспорта) дополнены до полного здорового состава A/81, A/82, B/91. Ожидания бизнеса не ослаблены. Это одобрение содержания коррекции, не подтверждение принятия её реестром/checker.

Оба PASS ограничены указанным предметом ревью. Они не означают полную приёмку WMS-663, зелёный CI или разрешение выпуска. Приёмка исходным/заменяющим аналитиком и полный CI итогового SHA остаются последующими шагами ведущего.

## Независимость и точный срез

Ревью выполнено этой сессией, без skills и дочерних агентов. Из аргументов родительского процесса PID 19111 выведены только модель `gpt-6-astra` и `model_reasoning_effort=high`; полный prompt, окружение и прочие аргументы не выводились. Основание замены недоступного Opus после 401 — прямое текущее поручение владельца; доступность Opus повторно не проверялась.

Свежий fetch origin/etalon выполнен. Полностью прочитаны AGENTS.md (236 строк), owner-cases.md (104) и failure-cases.md (359); правила совпадают с origin/etalon `0f1460b023700a99f17b504d6af3934a02bc68cc`, AGENTS.md и CLAUDE.md совпадают. Прочитаны требования WMS-663, особенно R6/R7, предыдущий FAIL `wms663-astra-9935c91.md`, F4-R tester handoff и полный новый контракт `8dfad7fa6e2d6e62f9aa264b7690032021550b9e`, handoff исправления положительных fixtures, изменённый сервис и окружающий путь get/resume/save/claim/checkpoint.

HEAD при проверках — `17ce363a8360620bc6b843e003278cd4ea106678`, его родитель — ровно product `1fd2d92dc30eb376c1d8a8e27238e52d963a196e`; родитель продукта — F4-R test contract `8dfad7fa6e2d6e62f9aa264b7690032021550b9e`. Product commit содержит только четыре добавленные строки в `backend/app/services/ozon_exemplar_documents_service.py::document_view`. Git diff подтвердил идентичность backend/app, frontend и docs/requirements между product и проверенным checkout. Blob сервиса в обоих SHA — `3a049785a37bab7e5984d637c992de5f4b379a3d`.

Correction commit меняет только старый тестовый файл (72 добавления, 0 удалений) и собственный handoff (120 добавлений). Новый F4-R test file побайтно совпадает с 8dfad7; его blob — `ffe1e5df71c51b1f1fad009cb148742a47696ce7`. Продуктовый PASS относится именно к 1fd2d92; выполнение на его потомке с поправленными fixture-данными не подменяет product SHA.

Рабочая ветка — `codex/wms662-663-priority`. Владение этого ревью ограничено настоящим отчётом. Чужие untracked WMS-675/evidence/result-файлы оставлены на месте. Продукт, тесты, требования, реестры и guards не редактировались.

## Почему продукт получил PASS

В предыдущем 9935c91 сервис сохранял отсутствующие экземпляры в snapshot, но считал общий результат accepted по вернувшейся части. Теперь после вычисления текущего состояния `document_view` строит ключи всех показанных экземпляров и разрешает общий accepted только при непустом expected и `expected.keys() <= remote.keys()`. Ключ включает product_id и exemplar_id, поэтому наличие одноимённого экземпляра другого товара не заменяет ожидаемый документ.

Проверяются все показанные экземпляры, а не только историческая цель A/81. Контракт реально исключает A/81, целый A, соседний A/82 и целый B; все четыре случая дают общий unknown. Сохранённый номер CABINET-NEW остаётся видимым; старый raw gtd_invalid у отсутствующего A не объявляется свежим отказом. Полный здоровый ответ по-прежнему даёт accepted и очищает старую ошибку свежим ответом. Пустой состав, неизвестный статус, неизвестный document check_status, свежие ошибки и ошибка чтения не дают ложного accepted.

Четыре добавленные строки меняют только вычисляемый ответ. Они не записывают unknown поверх исторически завершённого intent (явного действия оператора). `classify_document_status`, claim, checkpoint, version, choices и текущий writer не изменены. Поэтому повторный GET после неполного чтения не оживляет историческую запись A и не накладывает старый 001/ABC-09 на CABINET-NEW. Следующие разрешённые save B и КИЗ получают свежий полный snapshot, сохраняют текущие номера A, увеличивают версию на один и дают ровно второй SET. Устаревшая версия, действующий writer и неизвестный исход незавершённой записи сохраняют прежний конфликт; запоздалый GET не перезаписывает более новый claim.

GET безопасен относительно внешних изменений: в рассмотренном повторном открытии транспорт получает только `/v5/fbs/posting/product/exemplar/status`, без SET и create-or-get. Начальное открытие без snapshot по прочитанному коду использует STATUS и `/v3/posting/fbs/get`, оба через `read=True`. Это чтения по смыслу операции; HTTP-метод Seller API сам по себе не называется GET. Локальный checkpoint обновляет сохранённый snapshot/status, поэтому весь сервисный GET не объявляется немутирующим для локальной БД. При fake-ошибке 503 выполнены три разрешённые попытки чтения STATUS, внешней записи не было.

Изоляция клиента сохранена: `document_order` выбирает одновременно order_id и tenant_id до вызова провайдера. Независимая проба чужого tenant на GET дала 404/order_not_found, ноль транспортных вызовов и неизменные данные заказа; существующий тест чужой записи также прошёл. Новых состояний, ограничений, таблиц или пользовательских запретов правка не добавляет. Применимые случаи библиотек B02/B03/B09 защищены различением неизвестности и успеха, B14 — сохранением смысла проверок, B19/B20 — сохранением версии и актуального действия.

## Почему коррекция fixtures получила отдельный PASS

Три прежних положительных ответа описывали успешный restart, разрешение потерянного SET и здоровую accepted-ветвь матрицы, но возвращали только A/81 при сохранённом полном составе A/81+A/82+B/91. Смысл этих сценариев не требует принятия частичного ответа: R7 и отдельные отрицательные F4-R проверки требуют обратного. Дополнение именно здоровых ответов согласует подготовку с исходным ожиданием, а не переписывает бизнес-результат под продукт.

Независимая AST-проверка сравнила полные файлы прямо из Git. Разрешены только шесть добавленных узлов: A/82 и B/91 в каждом из трёх ответов. Каждый узел до удаления сравнен с соответствующим узлом исходного `_remote_snapshot()` и полностью совпал. После удаления этих шести узлов `ast.dump(before, include_attributes=False) == ast.dump(after, include_attributes=False)` для всего файла. Любое изменение assert, имени, сигнатуры, decorator, параметров, skip, helper либо отрицательного случая нарушило бы это равенство.

Подтверждённые места коррекции:

| Сценарий | Изменённые данные | Сохранённое ожидание |
|---|---|---|
| `test_wms663_explicit_choice_is_saved_exactly_and_resumes_after_restart` | Только второй queued STATUS ship_available: +A/82, +B/91 | Точный явный выбор, restart/expire_all, accepted, один SET |
| `test_wms663_lost_set_response_reads_status_before_any_repeat` | Только matching STATUS products: +A/82, +B/91 | Потерянный SET разрешается чтением, accepted, SET остаётся один |
| `test_wms663_status_accepts_only_matching_and_keeps_other_results_nonaccepted[status_payload1-accepted]` | Только здоровый элемент параметризации: +A/82, +B/91 | Девять случаев в прежнем порядке, прежние expected_state и все отрицательные ответы |

A/81 и его явный выбор не изменены. B/91 включает исходный is_rnpt_needed; номера, absent-флаги, weight и marks обоих добавленных соседей взяты из существующей оснастки. Равенство AST после обратного удаления доказывает отсутствие подмены ожиданий, включая все параметры матрицы; новый отрицательный контракт дополнительно проверен на идентичность Git blob.

## Собственные выполненные проверки

Сняты `WMS_TEST_DATABASE_URL` и `WMS_TEST_DATA_DIR`; conftest прочитан до запуска. Он назначает отдельный SQLite-файл по ID запуска/worker до импорта приложения. Новый контракт дополнительно проверяет SQLite перед созданием заказа. Один pytest worker, каждый вложенный Node/Vitest/jsdom также с одним worker. PG517, другие общие БД, живой API, браузер/Chrome/Playwright, Telegram, секреты и deploy не использовались.

Из backend выполнена команда:

```sh
env -u WMS_TEST_DATABASE_URL -u WMS_TEST_DATA_DIR PYTHONDONTWRITEBYTECODE=1 \
  /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest \
  tests/test_wms663_customs_documents_contract.py::test_wms663_explicit_choice_is_saved_exactly_and_resumes_after_restart \
  tests/test_wms663_customs_documents_contract.py::test_wms663_lost_set_response_reads_status_before_any_repeat \
  'tests/test_wms663_customs_documents_contract.py::test_wms663_status_accepts_only_matching_and_keeps_other_results_nonaccepted[status_payload1-accepted]' \
  tests/test_wms663_partial_accepted_status.py \
  -n 1 -q --tb=short -p no:cacheprovider \
  --basetemp=/private/tmp/wms663-astra-1fd2-review-20261006
```

Результат: **19 passed, 12 warnings in 10.19s, exit 0, skip 0**. Это три исправленных положительных случая и все 16 F4-R, включая три реально выполненные проверки существующего React-компонента в jsdom с JSON настоящего сервиса. Браузерная геометрия этим не проверялась.

Дополнительный ограниченный прогон тем же Python/env и флагами, с basetemp `/private/tmp/wms663-astra-1fd2-guards-20261006`:

```text
tests/test_wms663_accepted_current_status.py::test_f4_current_rejection_is_visible_in_view_and_exemplar
tests/test_wms663_accepted_current_status.py::test_f4_current_validation_is_checking_not_historical_acceptance
tests/test_wms663_accepted_current_status.py::test_f4_unknown_current_document_status_is_not_accepted
tests/test_wms663_accepted_read_regressions.py::test_f1r_unresolved_writer_still_blocks_new_claim
tests/test_wms663_accepted_read_regressions.py::test_f1r_old_get_cannot_overwrite_newer_document_claim
tests/test_wms663_customs_documents_contract.py::test_wms663_write_is_tenant_isolated_and_rejects_a_stale_version
```

Результат: **7 passed, 12 warnings in 4.12s, exit 0, skip 0**. Проверка текущего writer параметризована двумя случаями. Это адресное подтверждение границ новой агрегации, а не повтор неизменённого полного набора.

Дополнительно собственная последовательная stdin-проба на отдельной SQLite вызвала настоящий get/resume после `_accepted_then_current_status(session, 'rejected')`. Все ответы fake, каждый шаг сверял неизменность historical state/version/choice/choices/in_flight, editable=true, CABINET-NEW и точный список вызовов только STATUS:

```text
foreign_tenant_get PASS: 404, zero provider calls, no stored changes
empty_products PASS unknown STATUS calls 1
unknown_status PASS unknown STATUS calls 1
read_transport_error PASS unknown STATUS calls 3
posting_mismatch PASS unknown STATUS calls 1
healthy_recovery PASS accepted STATUS calls 1
```

Первый запуск этой разовой пробы остановился после первых трёх успешных проверок: в reviewer harness ошибочно передан `message` конструктору MarketplaceProviderError. Это ошибка пробы, не продуктовый FAIL. После чтения сигнатуры использован `MarketplaceProviderError('ozon', 503, code='transport_error')`; весь перечисленный сценарий прошёл, exit 0. Код продукта/контракта не менялся.

Предъявленные владельцем NEW16 GREEN, adjacent101 GREEN, old42 PASS/3 positive fixture FAIL/1 PG skip, полный ruff и mypy по 552 файлам здесь не выдаются за собственные прогоны. Handoff тестировщика сообщает 19 PASS/40.82s после коррекции; собственный результат выше получен независимо. Старые 146, полный build, полный ruff/mypy и CI не повторялись. `git diff --check` прошёл.

## Точные данные для последующего реестра

Ниже запись доказательств для ведущего/будущего checker, а не изменение существующего correction ledger или утверждение о поддержке такого формата текущим checker. `source_commit` — непосредственная полная версия файла до этой коррекции; она не переименовывается в новый исходный тестовый контракт. Исторический контракт `ae2ebd3d17f4e7364b1b52de4126b8f70937652b` и прежняя коррекция `76f2162e22f1aa9e33a336b01109882d8a8969c6` остаются отдельными фактами. SHA настоящего отчёта передаётся после commit; самоодобрение/изменение реестра этим файлом не выполняется.

```json
{
  "task": "WMS-663",
  "product_commit": "1fd2d92dc30eb376c1d8a8e27238e52d963a196e",
  "product_review": {
    "model": "gpt-6-astra",
    "effort": "high",
    "verdict": "PASS",
    "scope": "Exact four-line F4-R document_view delta only; not full product acceptance or CI"
  },
  "source_commit": "1fd2d92dc30eb376c1d8a8e27238e52d963a196e",
  "correction_commit": "17ce363a8360620bc6b843e003278cd4ea106678",
  "files": [
    {
      "path": "backend/tests/test_wms663_customs_documents_contract.py",
      "before_blob": "4e1aff5a80445fa61b5697d60a26985427dfd28e",
      "after_blob": "c92c075ba9f375c578538b776207cdc6b8b56ab3",
      "before_sha256": "f05ebf4ca228aaddc6addb50abf07d8cb18da8e93fc1dc2f9b254b4b92851665",
      "after_sha256": "bf1654d769157c12c48577213a2a28358e96441d12d07a32d0b8abe2225460f8",
      "insertions": 72,
      "deletions": 0,
      "reversed_fixture_nodes": 6,
      "whole_ast_identical_after_reversal": true
    }
  ],
  "correction_changed_paths": [
    "backend/tests/test_wms663_customs_documents_contract.py",
    "docs/reviews/wms663-healthy-positive-fixture-correction-handoff.md"
  ],
  "review": {
    "model": "gpt-6-astra",
    "effort": "high",
    "verdict": "PASS",
    "scope": "Exact 17ce363 healthy positive fixture correction content only; assertions and negative cases unchanged",
    "evidence": "docs/reviews/wms663-astra-1fd2d92.md"
  },
  "checker_acceptance": "not_evaluated",
  "full_ci": "not_run",
  "product_acceptance": "pending_analyst"
}
```

Исходный blob дополнительно совпал в 9935c91, 8dfad7 и 1fd2d92. Оба полных файла восстанавливаются через `git cat-file blob <SHA>`; обе SHA-256 вычислены независимо из Git bytes.

Для повторения AST-проверки без правки файлов достаточно следующего Python из корня checkout. Сравнение не импортирует приложение и не обращается к БД:

```python
import ast
import collections
import subprocess

path = 'backend/tests/test_wms663_customs_documents_contract.py'
before = ast.parse(subprocess.check_output(['git', 'show', f'1fd2d92:{path}']))
after = ast.parse(subprocess.check_output(['git', 'show', f'17ce363:{path}']))
dump = lambda node: ast.dump(node, include_attributes=False)
def field(node, key):
    return next(v for k, v in zip(node.keys, node.values)
                if isinstance(k, ast.Constant) and k.value == key)
ref = next(n for n in before.body if isinstance(n, ast.FunctionDef)
           and n.name == '_remote_snapshot')
snapshot = next(n.value for n in ref.body if isinstance(n, ast.Return))
products = field(snapshot, 'products').elts
allowed = {dump(field(products[0], 'exemplars').elts[1]): 'A/82',
           dump(products[1]): 'B/91'}
removed = []
def reverse(x, y, scope=''):
    assert type(x) is type(y)
    if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)):
        scope = x.name
    if isinstance(x, ast.AST):
        for key, value in ast.iter_fields(x):
            reverse(value, getattr(y, key), scope)
    elif isinstance(x, list):
        if len(y) == len(x) + 1:
            assert isinstance(y[-1], ast.AST)
            label = allowed[dump(y[-1])]
            removed.append((scope, label))
            y.pop()
        assert len(x) == len(y)
        for a, b in zip(x, y):
            reverse(a, b, scope)
    else:
        assert x == y
reverse(before, after)
scopes = [
    'test_wms663_explicit_choice_is_saved_exactly_and_resumes_after_restart',
    'test_wms663_lost_set_response_reads_status_before_any_repeat',
    'test_wms663_status_accepts_only_matching_and_keeps_other_results_nonaccepted',
]
assert collections.Counter(removed) == collections.Counter(
    (s, label) for s in scopes for label in ['A/82', 'B/91'])
assert len(removed) == 6 and dump(before) == dump(after)
print('PASS: only six fixture additions; whole remaining AST identical')
```

Следующий шаг ведущего — использовать два раздельных PASS и эти точные source/blobs при оформлении коррекции, затем передать результат аналитику и полному CI. Исторические открытые пункты приёмки и ограничения checker этим узким ревью не закрываются. Merge в main/etalon и deploy не выполнялись.
