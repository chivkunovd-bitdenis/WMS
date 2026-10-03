## Повторная сверка WMS-641: исправления по трём коммитам

Scope: `749ed8e83`, `24d58ef28`, `7b6be4e9d`. Остальные замечания моего прежнего отчёта принимаю как снятые согласно решениям владельца (п. 1, 4, 6, 8, 9, 10, 11). Полный прогон не делал; принимаю `pytest-final.log` (559 passed, 1 известный baseline-фейл `test_deploy_files.py::test_workflow_server_part_refuses_foreign_or_malformed_sha_before_running_anything`).

### Статус прежних дефектов 2, 3, 5, 7, 12

**№2 (гонка cancel/completion) — закрыто.** В `agent_coordinator._save_job` добавлена ветка: если `current.cancel_requested` и `job.status == "done"`, статус переводится в `needs_review`, результат уходит в `interim_result`, добавляется `recovery_note` «Cancel raced completion; inspect actual commands and external outcome», `result` снимается. В `_run_job` после `_save_job` отдельная проверка: если KV-статус уже не `done`, при `cancel_requested=True` ставится отдельный outbox `agent_job_cancel_unknown:{job_id}` с текстом «Исход команд нужно проверить; успех не подтверждаю». Тест `test_cancel_race_is_reported_unknown_and_deadline_callback_reads_current_state` подменяет `agent_turn` и во время него выставляет `cancel_requested`; после возврата `_run_job` в KV `status="needs_review"`, `cancel_requested=True`, нет `agent_job_done`, есть `agent_job_cancel_unknown`. Ограничение: возврат из `needs_review` в работу штатным инструментом не предусмотрен — владельцу придётся создать новое `project_job`. Это осознанная «ждём инспекцию», совместимо с R83.

**№3 (устаревший локальный `deadline_at` в cancel-коллбэке) — закрыто.** Коллбэк переписан на walrus-чтение KV: `(deadline := self.store.kv_get(f"agent_job:{job_id}", {}).get("deadline_at")) and self.clock() >= float(deadline)`. Тот же тест подтверждает: обновление `deadline_at` через `_patch_job` до `99.0` при `clock=100` сразу переводит коллбэк в True. Минор: лишний KV-lookup внутри горячего колбэка — приемлемо.

**№5 (относительный путь в `send_job_file`) — закрыто.** Теперь `(raw_path if raw_path.is_absolute() else root / raw_path).resolve()`. Тест `test_job_file_relative_path_is_anchored_under_verified_worktree` подтверждает: `out/export.csv` → `queued=True`, `file_path` = абсолют внутри worktree; `../outside.csv` → `file_not_in_job_worktree`. Проверка `root not in path.parents` после `.resolve()` корректно отбивает traversal, в т.ч. через symlink наружу.

**№7 (жёсткий `owner=True` в inline-вызове Trello) — закрыто.** `_tool_task_record` теперь передаёт реальный `owner` в `self._tool_trello_sync({...}, event, owner)`. Тест `test_author_confirmation_requires_sent_description_and_later_author_message` расширен и утверждает `seen_owner == [False]` при подтверждении клиентом — scope-ограничения `_ticket` снова работают именно по сцене клиента.

**№12 (dynamic tools теряются на resume) — снято владельцем** со ссылкой на официальную документацию app-server, подтверждающую персистенцию `dynamicTools` в rollout и восстановление их на resume; реальный Codex resume работает в независимом двухпроходном прогоне. Принимаю, своих обоснований для оспаривания нет.

### Новые заявленные правки

**Mockup-ретраи (reuse worktree/public_id, возврат фактического статуса).** `_tool_request_mockup`:
- `status=published` того же `version` → возврат текущего `url`, `queued=False`;
- `status in ("queued","running","unknown")` → возврат фактического статуса без повторной постановки;
- `status=="failed"` → `retry=True`, стадия обращения возвращается в `agent_discussion`, mockup помечается `queued` с `recovery_note` «Inspect existing worktree and publication before continuing»;
- иначе — обычный `kv_once(key)` создаёт первую постановку.
`recover_after_restart` поднимает прерванный `status="running"` в `queued` (вместо прежнего `unknown`) с тем же `recovery_note`. `MockupRunner.run` дополняет промпт блоком «Previous run was interrupted. Inspect the existing worktree and already published URL before changing files or publishing. Reuse the completed artifact if valid; do not delete or duplicate it.». Фактический reuse обеспечивается:
- Имя `name` детерминировано `mockup-{tid}-{version[:12]}` и ветка та же → `if not path.exists():` обходит `worktree add` и переиспользует;
- Публичный ID кэшируется в `mockup_public_id:{tid}:{version}` → `publish()` получает прежний `public_id` → при повторе `GET index.html` возвращает 200 с тем же `marker`, функция возвращает прежний URL без повторной заливки.
Тест `test_mockup_retry_reuses_task_after_failure_and_reports_published_version` проходит путь `failed → request_mockup → queued (retry=True, recovery_note set, stage=agent_discussion) → published → request_mockup → status=published, url` возвращены. Защита от перезаписи успешного артефакта в `publish_mockup.publish` сохраняется (новое содержимое с тем же `public_id`, но другим `marker` даёт `PublishError("public URL exists with different content")`). Валидно и консистентно с R35.

**Инструкция «draft перед author-confirm» — закрыто.** В `agent_instructions.md` добавлен абзац, который прямо указывает модели: сначала `task_record(confirm_author=false)` для получения `ticket_id` (локальный черновик, без Git/Trello), затем `queue_process_reply(kind=necessary_question|description_confirmation)` с этим `ticket_id`; `task_record(confirm_author=true)` повторяется только после подтверждения автора. Это снимает прошлую двусмысленность, где модель могла пытаться получить WMS-номер до диалога с автором. Код `task_record` без `confirm_author` создаёт/обновляет только `tickets` + `data.agent` (без `persist_task`/`ensure_card`) — консистентно.

**Дедуп `owner_digest` после `task_notice` — закрыто.** В транзакции внутри `_tool_task_record` после отправки `agent_task_confirmed:{tid}:{version}` обновляется `agent_task_notice_event:{event_id}` — список `tid`. `_tool_owner_digest` на том же `event_id`:
- `tid` указан и в списке → `{"status": "covered_by_task_notice", ...}` без второй отправки;
- `tid` не указан и в списке ровно один `tid` → такой же короткий замыкания;
- иначе — обычный путь.
Тест `test_author_confirmation_requires_sent_description_and_later_author_message` подтверждает: единственный `owner`-outbox с `purpose="task_notice"`, последующий `owner_digest` для того же `ticket_id` (и для пустого `ticket_id` при одном уведомлении) возвращает `covered_by_task_notice`. Защита точечная; ambiguous-случай с ≥2 задач за один event и `owner_digest` без `tid` намеренно НЕ дедуплицируется — корректно.

### Smежные регрессии

- `_save_job` merge-правила: `cancel_requested` сохраняется только при `job.status=="done"`. При других путях (например, `needs_review` из `except LlmUnavailable`) флаг `cancel_requested` берётся напрямую из KV через повторный `kv_get` в коллбэке и не теряется, т. к. эти пути `_save_job(job)` вызывают с явным `status`/`error`, не пересекаясь с ранее сохранённым `cancel_requested`. OK.
- `request_mockup` при `failed` принудительно двигает `stage → "agent_discussion"`. Если задача раньше была в owner-инициированной стадии («sending»/«hotfix»/«deploy»/«verify»), `_ticket` даёт её без ограничений scope, но `_tool_task_record` на тех же стадиях бы отказал. Для mockup-ретрая это допустимо, т. к. макет обслуживает документ, не продуктовый релиз. Low.
- `agent_task_notice_event:{event_id}` список растёт только при явных `task_record(confirm_author=True)` для разных `tid` в одном `event_id`. Границы разумные.
- Валидный путь ответа тулов не нарушен: `_tool_owner_digest` при `covered_by_task_notice` всё равно возвращает `owner_chat_id` и `source_message_id`, не разглашая секретов. OK.

### Непроверенное

Живого Telegram/Trello/прод-деплоя не трогал. `.bot-audit-20261003/mockup-publish.log` и Sol-nativeexport под `docs/reviews/artifacts/wms-641` в этом раунде только отмечены как evidence; содержимо не раскрывал. Приёмку/релиз не объявляю.

Reviewed Git HEAD SHA: `7b6be4e9d3db0465077765d02473f9631320fa64`.
