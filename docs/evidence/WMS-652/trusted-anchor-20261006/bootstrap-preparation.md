# WMS-652: явно утверждённый источник первой защиты

Это подготовленный код для входа в новую защиту, когда реальный BASE первого
PR в etalon ещё не содержит `guards/PROCESS_CONTRACTS.json`. По умолчанию без
конфигурации прежний отказ сохраняется. Автоматического выбора источника нет.
Главная ветка и активный workflow этой работой не изменены. Ведущий сообщил
о прямом разрешении владельца установить независимую защиту; конкретную
установку после итогового review и заполнения pin выполняет ведущий.

Новый контракт `test_trusted_process_bootstrap.py` сохранён **до кода** коммитом
`f4e6d2526b075a430491e57540c345dc214e3973`. Девять методов дали RED
1 FAIL+22 errors отсутствующего API/loader (`bootstrap-contract-red.log`).
После реализации общий результат39 PASS; ни одна из прежних30 проверок не
изменена. В новом тесте после фиксации изменён только порядок import для ruff,
без изменения ожиданий или состава.

## Точный разрешённый переход

CLI читает только `process_bootstrap.json` рядом с собственным checker в
доверенном checkout main: `Path(__file__).resolve().with_name(...)`.
Ни кандидат, ни событие, ни параметр CLI, ни environment variable не выбирают
этот файл. Отсутствие файла означает отсутствие разрешения. JSON должен
содержать ровно `base_sha` и `source_sha`: два полных lowercase40 SHA разных
коммитов. Duplicate keys, лишние поля, invalid SHA, symlink и файл свыше64KiB
дают отказ. Реальный pin не создан: source выбирает ведущий после review.

Схема будущего файла; placeholders ниже **не являются валидной конфигурацией**:

```json
{
  "base_sha": "EXACT_ORIGINAL_ETALON_BASE_40_HEX",
  "source_sha": "EXACT_INDEPENDENTLY_REVIEWED_SOURCE_40_HEX"
}
```

Наличие approved pin требует чтения полного Git BASE tree. Если policy есть,
используется только BASE: отсутствие доступа или повреждение содержимого
не подменяется source. Если policy действительно отсутствует, разрешение
применяется только при exact совпадении реального PR base с pin. SOURCE tree
также обязан быть полным, с policy regular blob/mode; SOURCE policy и все
защищённые SOURCE file bytes/modes сравниваются с HEAD и MERGE. Self-updated
hash или замена cases не разрешают поменять защищённый исходник.

SOURCE служит только исходным набором защиты. PR base, CI matching base,
artifact execution.json base и итоговый `base_sha` остаются настоящим BASE
этого PR. Возвращаемый `bootstrap_source_sha` явно показывает использование
approved source. Обязательные восемь jobs, latest current attempt, exact
artifact merge/head/base/run/attempt/policy digest и финальные rereads остаются
обязательными. API outage, truncated trees, отсутствующий source policy/file,
wrong base/source, missing/skip proof и подмена artifact base дают отказ.
Strict CLI никогда не ограничивается metadata-only helper.

После появления policy в BASE первого принятого выпуска approved source
перестаёт выбираться: обычный BASE получает приоритет, даже если сохранённый
pin имеет старый base. Это вход только для одного exact original BASE;
любой следующий BASE без policy не получает это разрешение.

## Проверки и доказательства

Из корня `.worktrees/wms652-trusted-anchor` выполнено:

```sh
python3 -m unittest scripts.ci.tests.test_trusted_process_check scripts.ci.tests.test_trusted_process_artifact scripts.ci.tests.test_trusted_process_cli scripts.ci.tests.test_trusted_process_publish scripts.ci.tests.test_trusted_process_queue scripts.ci.tests.test_trusted_process_bootstrap
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m ruff check scripts/ci/trusted_process_check.py scripts/ci/tests/test_trusted_process_bootstrap.py
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m mypy --follow-imports=skip scripts/ci/trusted_process_check.py
python3 -m compileall -q scripts/ci/trusted_process_check.py scripts/ci/tests/test_trusted_process_bootstrap.py
git diff --check
```

39 PASS, ruff/mypy/compileall/diff PASS (`bootstrap-tests-green.log`,
`bootstrap-ruff.log`, `bootstrap-mypy.log`). Mutation controls:
отключение exact base →1 FAIL; seed вместо существующего BASE →2 FAIL+1 error;
отключение Git byte/mode comparison →2 FAIL; CLI без trusted loader →1 FAIL
(`bootstrap-mutation-controls.log`). Checker восстановлен побайтно в finally;
после восстановления снова39 PASS. API/download/publication здесь только
синтетические callbacks; live принятия PR или публикации checks не было.

Минимальный будущий main diff теперь состоит из standalone checker,
подготовленного workflow и **реального** отдельно проверенного двух-SHA config.
Этот документ не утверждает source pin и не подменяет независимое review.
Ведущий заполняет pin после проверки итогового источника и проверяет exact
main diff. Main/default/rulesets, production, deployment, клиенты и секреты
этой подготовкой не изменены. Предел queue100 из queue-fix.md остаётся явным.
