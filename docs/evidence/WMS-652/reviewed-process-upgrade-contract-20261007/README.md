# WMS-652: контракт точного обновления существующей охраны

Постановка: `reviewed-upgrade-contract-handoff.md` интегратора от 07.10.2026.
Контракт написан до реализации на проверенном `origin/etalon`
`4c532f0cccfb8f99b34d68d9630a3763038fbc5f`. Изменения реализации, workflow,
конфигурации main, старых тестов и policy не входят в этот коммит.

Пять методов в `scripts/ci/tests/test_reviewed_process_upgrade.py` используют
настоящие временные Git-коммиты BASE/SOURCE/candidate/merge. GitHub adapter
возвращает реальные policy, tree и blob bytes этого репозитория; настоящие
`baseline_policy`, `verify_pr_evidence`, `verify_integrity` не подменяются.
Повторно используется существующая ArtifactFixture для CI/ZIP boundary.

| Проверка | Класс | Тест | Ожидаемое поведение |
|---|---|---|---|
| U1 | навсегда | `scripts/ci/tests/test_reviewed_process_upgrade.py::ReviewedProcessUpgradeTests.test_exact_trusted_pin_upgrades_existing_base_and_checks_source_candidate_and_proof` | Fixed sibling trusted-main pin выбирает ровно SOURCE для существующей BASE-policy; SOURCE добавляет один путь и case, обновляет один digest. Реальный anchor проверяет candidate/merge/artifact; более поздний selfhash отвергается. |
| U2 | навсегда | `scripts/ci/tests/test_reviewed_process_upgrade.py::ReviewedProcessUpgradeTests.test_git_integrity_exact_approved_upgrade_accepts_reviewed_digest_and_additions` | Обычный BASE verifier отклоняет изменение; точный `approved_upgrade` принимает только согласованный SOURCE. |
| U3 | навсегда | `scripts/ci/tests/test_reviewed_process_upgrade.py::ReviewedProcessUpgradeTests.test_unapproved_base_source_or_candidate_config_cannot_authorize_upgrade` | Candidate config/env не дают разрешение; отсутствующий pin, другая BASE или SOURCE с прежними bytes не разрешают новую candidate policy. |
| U4 | навсегда | `scripts/ci/tests/test_reviewed_process_upgrade.py::ReviewedProcessUpgradeTests.test_reviewed_source_must_keep_every_base_path_case_and_suite_semantics` | Даже pinned SOURCE не может удалить BASE path/case или изменить report/format/exact. |
| U5 | навсегда | `scripts/ci/tests/test_reviewed_process_upgrade.py::ReviewedProcessUpgradeTests.test_corrupt_base_or_source_bytes_never_fall_back_to_candidate_hashes` | SHA-256 каждого защищённого Git blob проверяется в BASE и SOURCE; повреждённый источник не заменяется candidate hashes. |

## Проверенный RED

Команда: `python3 -m unittest scripts.ci.tests.test_reviewed_process_upgrade -v`.
Результат до реализации: 5 методов, 4.897 секунды, 3 assertion failures и 8 errors
в методах/подслучаях, без skip/xfail. U1 содержательно падает на `None != SOURCE`:
существующая `baseline_policy` игнорирует exact trusted-main pin при наличии BASE
policy. Отдельный вызов реального `verify_pr_evidence` на том же корректном
superset даёт `Candidate changed a protected baseline digest`. Обычный реальный
`verify_integrity` даёт `Changed protected contract hash: tests/scan.py`.

U2 и integrity-подслучаи U3/U4 получают `TypeError: unexpected keyword argument
'approved_upgrade'`: согласованный новый вход пока отсутствует. Это ожидаемый
дополнительный RED, а не доказанный успешный отказ canary после реализации.
U5 также содержательно падает: `baseline_policy` ещё не отвергает повреждённые
BASE/SOURCE bytes. После реализации все пять методов обязаны пройти без изменения
ожиданий; отдельное ревью проверит этот результат.

Отдельно фактически проверено: каждый BASE/SOURCE Git blob соответствует своему
SHA-256, все старые пути и cases сохранены, report/format/exact совпадают;
неизменённый обычный BASE `verify_integrity` проходит. Ruff и Python compilation
нового файла прошли. Полный набор, граф WMS-680, внешние API и CI не запускались.

SHA-256 проверенных файлов:

```
fda21e4257523bea342690a50d4871bbfee88e56b8f24405997f8cac8a816b4e  scripts/ci/trusted_process_check.py
a2143f35d99719b55d9a7e82ba4c3dcbba977d1996810e9905707b3d5df764f3  scripts/ci/process_contracts.py
29b67659877a7653f0c43bf01901caf4000a7722084239d0254aa7fcd97d966e  scripts/ci/tests/test_reviewed_process_upgrade.py
```
