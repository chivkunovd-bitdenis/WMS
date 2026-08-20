# Wave-driver Pipeline v2: dry-run allocation

`scripts/pipeline/wave_driver.py` читает только Git snapshots
`tasks/*/state.json` со статусом `WAITING` и печатает детерминированный JSON-план
изолированной волны. Формат описан в `pipeline/wave-plan.schema.json`.

```bash
python3 scripts/pipeline/wave_driver.py --format json
```

Для каждой карточки план содержит будущие `worktree`, два порта, database, Redis
namespace, Celery queue, emulator namespace, evidence directory и canonical
resources. Имена вычисляются из stable `wave_id` и `task_id`; одинаковый набор
ожидающих snapshots даёт одинаковую раскладку.

Этот slice намеренно **не является исполнительным driver**: он не создаёт
worktree, не пишет `.pipeline-state/`, не берёт lease-lock, не стартует agent и
не меняет frontend/backend/product state. Поэтому dry-run можно запускать для
проверки очереди до owner-approved `resume`, без запуска Dev fixes.

Проверка в CI:

```bash
python3 scripts/ci/check_pipeline_wave_driver_smoke.py
```

Smoke создаёт временные snapshots, проверяет план только для `WAITING`,
уникальность ресурсов и отсутствие записей в product code. Реальный
распределённый host и controller-owned внешний durable store остаются отдельным
следующим slice; текущий план не выдаёт write-capability исполнителям.
