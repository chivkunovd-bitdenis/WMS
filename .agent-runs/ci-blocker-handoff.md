# WMS-652: handoff по техническим блокерам CI

Работа выполнена в `codex/night1007-wms652-ci-fix` от точного кандидата
`f6066d68bd198794602a6e8916612d0d3b32460f`. Product-код, protected guards,
workflow CI и доверенные хеши не менялись.

## Backend shard: `test_prod_deploy_backup.py`

Адресный RED воспроизведён до изменения командой
`pytest -n 0 -q backend/tests/test_prod_deploy_backup.py`: семь параметров
`test_deploy_requires_verified_backup_before_migration` завершались ошибкой,
а два bootstrap-теста оставались зелёными. Точная причина во всех семи случаях
одна: временный synthetic repository из fixture не содержал
`scripts/ci/verify_server_process_ci.py`, который актуальный
`scripts/deploy/prod-update.sh` запускает на строках 80–83 до любого Docker
действия. Поэтому сценарий не доходил до проверок backup, rollback и topology;
это неполнота тестового стенда, а не дефект production script.

Fixture теперь копирует сам server gate и его зависимость `verify_ci.py`.
Gate исполняется без обхода. Подменена только внешняя GET-граница публичного
GitHub API через `sitecustomize`; она возвращает согласованный exact-SHA
snapshot workflow, обязательных jobs и process-proof artifact. Docker-stub
аварийно завершится, если этот реальный gate ещё не завершился, а fixture
дополнительно проверяет, что запрос к runs workflow действительно был сделан.
Так сохранены исходные assertions о backup, network, rollback, retry и receipts.

Проверка после изменения:

```text
pytest -n 0 -q backend/tests/test_prod_deploy_backup.py
9 passed, 6 warnings in 25.61s

python3 -m unittest -v scripts.ci.tests.test_server_process_gate
Ran 11 tests in 3.283s
OK
```

Второй набор содержит отдельные негативные случаи gate: неуспешные/отсутствующие
jobs, чужой SHA/run, повтор artefact, expired artefact, изменение attempt,
неподходящий push и остановку до Docker при непроверенном сервере. Они не
ослаблялись и не переносились в fixture.

## WMS-672 C5

Изменений в production-коде или C5-контракте здесь нет. Read-only проверка
ветки `codex/wms672-c5-linux-diagnostic` и run `37527056184` подтвердила
причину на Linux/Chromium 141: искусственно введённая ошибка decode на 150
корректно дала ожидаемый alert без transfer и marks. После явного retry
нативный `HTMLImageElement.decode()` отверг уже валидный PNG label 227 с
`EncodingError`; это произошло до transfer. Ошибка из iframe не проходит
проверку parent-realm `instanceof Error`, поэтому существующий обработчик
теряет её сообщение и показывает generic alert; C5 затем закономерно ждёт
transfer до существующего timeout на строке 317.

Артефакт подтверждает валидность PNG (CRC/pixel decode и независимое CODE128
чтение). Это не ошибка fixture, не повод увеличивать timeout и не основание
отключать native readiness. Существующий C5 уже является адресным RED для
полного сценария; новый тест без согласованного решения не добавлялся, чтобы
не менять frozen contract вслепую. Для product-исправления нужны отдельный
узкий regression на iframe-native exception/message и повтор unchanged C5
на Linux141; возможное направление из diagnostics — меньший decode window
при сохранении readiness всех labels и нормализация cross-realm error message.

## Stage handoff: WMS-672 C5a test contract

Добавлен отдельный C5a рядом с неизменённым C5:
`frontend/tests-e2e/wms672-dom.test.tsx::C5a 33 labels: iframe EncodingError preserves its message; bounded readiness completes one explicit retry`.
Он использует настоящий `FfInboundRequestView`, `printBarcodeLabels`, generated
valid barcode PNG и iframe. Только отсутствующий у jsdom `scrollIntoView`
заменён no-op platform double.

До product change целевой запуск воспроизводит осмысленный RED: iframe
`DOMException('WMS672 decode failed at 2', 'EncodingError')` не является
`Error` родительского realm, а видимый alert сейчас равен
`Не удалось напечатать этикетки.` вместо исходного сообщения. Это фиксирует
точно нормализацию ошибки в screen catch, а не timeout или fixture.

После исправления этот же тест потребует: отсутствие transfer и POST marks
до честного error, снятие busy-state, затем один явный retry с полным readiness
всех 33 valid PNG, concurrency строго между 1 и N, ровно один transfer и 33
technical marks. Existing C5, его 300 labels, timeout и assertions не менялись.
Разработчику нельзя менять этот контракт; после product change обязательны
повтор C5a и unchanged Linux141 C5.

## Stage handoff: WMS-652 SOURCE binding transition contract

`ReleaseCommandContracts.test_actual_candidate_product_scope_uses_fixed_independently_reviewed_reference`
сохраняет literal `d61805978b3e7878d1056c99b4e6e0823edf49a5` без послабления.
Новая fixture `wms652_source_binding_transition.json` формализует состояние
`pending-final-independent-freeze`: финальный SHA отсутствует намеренно, текущий
integration candidate `f71b99c0f19bdbf48e8e0b95b62aefe8709307fc` не получает
доверие. Контракт отдельно отвергает `HEAD`, `${GITHUB_SHA}` и этот unreviewed
candidate при сохранении настоящей команды `product_scope`, а не dummy command.

После independent acceptance/freeze интегратор должен одновременно заменить
final fixture pin и literal workflow pin на один опубликованный 40-hex SHA.
До этого workflow, policy, checker и production code не менялись.

## Stage handoff: transition completion and WMS-686 raw receipt RED

SOURCE contract теперь имеет controlled independently accepted final-freeze
fixture: positive exact final pin проходит только при отдельной acceptance record;
старый pin становится mismatch. `HEAD`, `${GITHUB_SHA}` и unreviewed candidate
по-прежнему отказаны. Реальная fixture остаётся pending и продолжает строго
проверять actual `ci.yml` against `d618…` до независимого final freeze.

Добавлен raw-receipt contract WMS-686. На текущем candidate он намеренно RED,
поскольку job `wms686-mockup` отсутствует: будущая wiring обязана записывать
настоящий Node TAP всех 11 tests, загрузить exact-attempt artifact, включить job
в `process-proof.needs` и скачать этот exact artifact в reports. Controlled
mutations отдельно доказывают отказ при missing TAP, upload, download и required
job; policy/checker/workflow/product этим тестировщиком не менялись.
