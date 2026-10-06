# WMS-652: сохранение pending failure при третьем событии

Astra A проверила checkpoint `6b778ebb2aa4b8dbb4580201841f5ba0bfc4430f` и
воспроизвела остаточный P1. Доказательство сохранено reviewer commit
`fc81f1678ad034b384d14d66407664c0cba21aaa`, ветка
`codex/release-20261006-astra-a`, файлы
`docs/evidence/WMS-652/release-process-protection-20261006/anchor-6b778-pending-probe.py/.txt`.
Эти файлы перечитаны до новой правки. Два прежних P1 и frozen22 ожидания
остаются защищены; ни checker, ни прежние четыре test-файла не изменены.

Прежний двухпоточный mutex проверял только последовательность работающих
publishers. Он ошибочно предполагал сохранение каждого ожидающего запуска.
GitHub при default `queue: single` допускает один pending: третье событие
другого PR заменяло ожидающее падение первого PR. Задержанный старый success
первого PR завершался, а его новое failure никогда не публиковалось.

Официальная [документация concurrency GitHub](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency),
проверенная 06.10.2026, определяет `single` как замену pending, а `max` как
сохранение до 100 pending с отменой дополнительных новых запусков. Порядок
FIFO относится к моменту начала ожидания, не к dispatch времени события.
`queue: max` несовместимо с `cancel-in-progress: true`.

Новый additive `test_trusted_process_queue.py` сохранён коммитом
`b6cac70edddf9b383cae5c03eefc6b19cbe7a7f7` до YAML правки. Его три метода
проверяют точную конфигурацию, три события и ограничение 100 pending.
RED: все три FAIL (`queue-contract-red.log`). Детерминированная модель
начинается с уже работающего A-old success POST; затем A-new failure и
B-unrelated success попадают в очередь. Negative control default single
вытесняет A-new и оставляет A success. Текущая конфигурация сохраняет A-new:
публикации A-old success → A-new failure → B success. Проверка 101-го pending
показывает отмену overflow, сохраняя первые 100 и ранее ожидающее A failure.

Единственный YAML delta — `queue: max` в общей постоянной
`process-integrity-publishers` группе с `cancel-in-progress: false` плюс
комментарий о лимите. Файл только подготовлен в docs/evidence; активный
workflow, main/default/rulesets и bootstrap policy не менялись.

Из корня `.worktrees/wms652-trusted-anchor` выполнено:

```sh
python3 -m unittest scripts.ci.tests.test_trusted_process_check scripts.ci.tests.test_trusted_process_artifact scripts.ci.tests.test_trusted_process_cli scripts.ci.tests.test_trusted_process_publish scripts.ci.tests.test_trusted_process_queue
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m ruff check scripts/ci/trusted_process_check.py scripts/ci/tests/test_trusted_process_queue.py
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m mypy --follow-imports=skip scripts/ci/trusted_process_check.py
git diff --check
```

Итог30 PASS, ruff/mypy/diff PASS; BaseLoader YAML parse и trusted-main checkout
границы PASS (`queue-tests-green.log`, `queue-ruff.log`, `queue-mypy.log`,
`queue-workflow-validation.log`). Mutation controls удаления queue:max и
возврата explicit single дают по3 FAIL; true cancel даёт1 FAIL
(`queue-mutation-controls.log`). YAML восстановлен побайтно в finally,
после восстановления снова30 PASS.

Это synthetic проверка документированной семантики, не live GitHub scheduler
эксперимент. Лимит 100 — реальная граница: при переполнении новое failure
событие тоже может быть отменено, поэтому защита не гарантирует отзыв каждого
старого check при любой нагрузке или отказе POST API. Такой режим требует
отдельного решения о контроле переполнения/восстановлении; это исправление
закрывает конкретный трёхсобытийный дефект без заявления безграничной очереди.
Никаких внешних checks, production/deploy операций или секретов не затронуто.
Изменение передаётся ведущему для повторного независимого review.
