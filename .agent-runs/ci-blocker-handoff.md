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

## Stage handoff: promote preserves immutable original tests

До изменения `scripts/ci/promote_guards.py` добавлены два meaningful RED в
`scripts/ci/tests/test_promote_guards.py`. Первый создаёт активный saved
`PROCESS_CONTRACTS.json`, где original `backend/tests/test_immutable_contract.py`
уже защищён, и требует, чтобы штатный `promote` оставил original path, старый
test ID, requirement reference и bytes saved protection нетронутыми; второй
вызов должен быть idempotent. Текущий скрипт действительно делает `git mv`,
поэтому RED — original file исчезает.

Второй RED требует полностью разобрать три valid references из одной ячейки
`Test`, разделённые `<br>` и `;`; current parser склеивает их в один test name.
После полного разбора он также требует, чтобы штатная неприкрытая move-ветка
сохранила в переписанной ячейке все три новых target references, а не только
последнюю.
Отдельная зелёная проверка сохраняет fail-closed правило: пустая active
`навсегда` reference вызывает `ValueError`, а не пропускается. Existing
non-protected move scenario и rejection test outside supported trees повторно
PASS. Исправление должно только распознать сохранённую active protection и
регистрацию/check без move для такого original; новую policy migration,
allow-all или ослабление guards не добавлять.

## Stage handoff: WMS-654 protected Vitest templates

`test_promote_guards.py` теперь фиксирует genuine C6 template references из
WMS-654: `independent coordinates sides=%s tiers=%s` и
`${entry} sides=%s tiers=%s`. Positive contract требует original source без
move и все реальные 12 expanded IDs: четыре CatalogSection combinations и
восемь map-entry combinations, bound к hash-protected source и existing
`frontend-all.json` Vitest receipt. Current matcher не умеет связать template
с expanded names, поэтому positive RED воспроизводим до process-fix.

Negative contracts отдельно требуют отказ при missing expanded case, неверном
expanded name, case из другого source file, другом report и неверном source
hash. Нельзя реализовывать это prefix/substring match или пропуском одного
case: exact full set и source/report binding обязательны.

## Stage handoff: WMS-687 reviewed correction ledger

`test_check_task_documents.py` добавляет positive WMS-687 correction: один
reviewed frozen DOM test меняется, а commit дополнительно только создаёт два
новых `*.wms687.*` tests и меняет лишь Test links в собственном requirements
document. Ledger по-прежнему называет ровно changed frozen subset, сохраняет
existing exact contract/correction SHA ancestry и approved high PASS review.
Current checker RED, потому что требует equality всей дельты и ledger files.

Negative cases не позволяют расширить исключение: product path, новый test
другой WMS, чужой requirements, изменение R либо expected result собственной
requirements, undeclared changed frozen test и deletion frozen test обязаны
отказать. Нельзя превращать это в generic companion allowlist или ослаблять
review/SHA/evidence checks.

## Stage handoff: saved policy must not downgrade to legacy promotion

Independent review `c737647b5ec5c737b96508b8669b9b1eca70066e` found that
`cafaaef` returns `None` when `guards/PROCESS_CONTRACTS.json` is absent from
the working tree, even if the exact file is present in `HEAD`. Two new
regressions cover a deleted file and a dangling symlink at that path. Both
require a `ValueError` before any `git mv`, with the protected original and
requirement reference untouched; the pre-existing no-policy fixture remains
the separate proof that truly legacy promotion still moves a new test.

The same isolated test module was run with
`../night1007-integration/scripts/ci/promote_guards.py`, not the older local
promoter. It reproduces both bypasses (`ValueError not raised`). Its WMS-654
positive reaches `verify_registered_case` and fails specifically on template
`C6 independent coordinates sides=%s tiers=%s` lacking an expanded case/report
binding, proving the prior template contract is exercising the new matcher
rather than the old unsplit-reference path.

## Stage handoff: legacy WMS-654 report versus ancillary WMS-687 proof

Two focused document-gate contracts distinguish compatibility from a new
exception. The accepted-style WMS-654 exact-files ledger changes only its
frozen test and retains valid `model=gpt-6-astra`, `effort=high`, `verdict=PASS`
and historical `report`, deliberately without `report_commit`; it must pass.
The WMS-687 counterpart uses an allowed new own-task test and Test-link
companion but has `report` without `report_commit`; it must reject.

Running these tests by importing the current integration
`check_task_documents.py` reproduces the defect in the first case: it returns
the correction-scope error because `correction_companions` unconditionally
requires `report_commit` whenever any report field exists. The second case
still rejects. The fix therefore must make the proof-SHA requirement specific
to the new ancillary WMS-687 path, while retaining frozen-file equality and
existing model/effort/verdict validation for WMS-654.

## Stage handoff: bounded independent-review chains WMS-658 and WMS-681

`scripts/ci/tests/fixtures/wms652_exact_reviewed_correction_chains.json` is a
checked-in, immutable transcription of the published Sol 6.1/high mapping for
658 and 681:
the original contract, each exact source/correction pair, every frozen blob
transition, the sole WMS-658 own-requirements Test-links companion, and the
published review report commit/blob.  It intentionally contains no WMS-680
numeric-subtable extension: that later blob still needs the separate narrow
review stated by the integrator.

Two positive tests in `test_check_task_documents.py` build isolated Git graphs
from those published blob objects, rather than from moving `HEAD`.  They require
WMS-658's 2-frozen-files-plus-only-own-Test-links first correction followed by
its three single-file corrections, and WMS-681's two corrections that each
change both of its two frozen tests.  Current checker RED is exact for both:
`fixture-only: неподдерживаемое преобразование или изменены frozen
expectations`.  This records the missing bounded registration, not a generic
failure in the synthetic graph.

The accompanying canaries retain rejection for a changed source, changed blob,
extra product file, missing permitted high/PASS review, and rewritten report.
The process fix must extend the existing `fixture_corrections` path with only
the recorded transforms and review/report bindings (including true source and
ancestor checks); it must not add a task-wide exemption, arbitrary blob pair,
or generic requirements companion.  Existing legacy, WMS-654 and WMS-687 paths
remain outside this requested scope.

## Stage handoff: WMS-680 closed owner-to-fixture chain

The exact-chain fixture now contains the published WMS-680 record, including
the owner evidence commit `3be84bb091712caa2e32226f989e3008e47618a5`, semantic
contract `5739ed2ea900b8d6ddc8a9326bf1dc07e687fd8e`, fixture corrections
`7ad0aa781d175ef7f4e1d16074a12b47eed655f2`,
`11806bd237c48a030a4e0ff49bb12dd90dfe6778`,
`739bcadf1be4fe92e24af3d30b42f892f858e598`, and the independently reviewed
Sol 6.1/high numeric-subtable append
`f2de20008df3b21c1decead0e1051dbda4a4a08a`.  Its review artifact is bound to
`d0de155adcc31a7d33dca43d857a22e49897b981` and exact blob
`e4d18d7879c31d31b4841167173a48f8dc50c9eb`.

The immutable-object test verifies every correction parent/source, each
before/after blob, all three frozen contract frontiers (`240094`, `5739`, and
`739`), the owner evidence artifacts, and ancestry to the published report;
it does not rely on the current checkout HEAD.  The positive registry test is
currently RED exactly because `OWNER_UI_SUPERSESSIONS` has no `WMS-680` entry
and all four WMS-680 exact transform/blob pairs are absent.
The other two focused tests PASS: the actual published matrix is internally
consistent and wrong source/owner artifact, report, assertion blob or unrelated
file cannot coincide with its closed pair set.

Implementation must extend the existing owner-supersession and exact-fixture
mechanisms only for this recorded matrix.  It must retain exact owner evidence,
report/model/effort, parent/ancestor and every listed blob; it must not accept
another owner request, arbitrary test assertion change, extra product path, or
new transform.  No further WMS-680 frozen blob is approved by this contract.

## Stage handoff: WMS-687 protected expanded test references in document gate

`test_check_task_documents.py` now contains an isolated saved-Git
`PROCESS_CONTRACTS.json` fixture for the real WMS-687 `test.each` source.  Its
two document references are the actual expanded inbound and return names while
the source contains only the `%s` template.  The typed Vitest receipt has the
two exact full names under `frontend-all.json`; the source is both a normal Git
blob in HEAD and SHA-256 pinned by the policy.

Both positive tests are meaningful RED against the current integration
`check_task_documents.py`: it returns `не найдено имя теста ...` because it
does only literal source substring matching.  The desired narrow path is: only
when a saved, non-symlinked protected source matches both HEAD bytes and policy
digest may document validation accept an exact registered expanded case bound
to its typed receipt/report.  Reusing the existing registered-case verifier is
appropriate; wildcard, describe/group prefix, or a document-only bypass is not.

Five negative cases remain required: protected source changed in committed
HEAD, dirty source, missing exact case, wrong report, and unregistered source.
They must all fail closed.  A separately tested unprotected legacy source with
a literal test name still passes, so this is not a relaxation of ordinary test
reference validation.
