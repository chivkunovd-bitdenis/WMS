# WMS-415/338: read-only staging preflight, 10.09.2026 12:01 UTC

Проверено после сборки `4221969c` без deploy, миграций, создания backup-файла или изменения данных. Railway SSH выполнялся только для существующего проекта loyal-wonder `c28e681d-4535-4c96-ac97-c7b600a7f8e4`, среды `58a08b66-1290-45a2-8737-e3d7408389e5` (имя production внутри STAGING проекта, не VPS). Environment/ключи/URL подключения не выводились.

## Фактический результат

На WMS service `e4a67f11-4318-4386-b9f9-fe5ae0d4f5cc` через импорт существующего SQLAlchemy engine и транзакцию `SET TRANSACTION READ ONLY`:

```json
{"revision": ["20260908_0257"], "is_fbs_column_exists": true, "is_fbs_true_count": 0}
```

На Postgres service `7ba030a6-5608-406f-838f-22cd19b44a11` доступны `/usr/bin/pg_dump`, `/usr/bin/pg_restore`, `/usr/bin/psql`; pg_dump и pg_restore версии18.6. Выполнен только `pg_dump --schema-only --no-owner --no-privileges >/dev/null` с существующими POSTGRES_USER/POSTGRES_DB, exit0. Значения переменных не раскрывались. Проверки `test -d "$PGDATA"` и `test -w "$PGDATA"` успешны. Это подтверждает чтение схемы и доступный локальный путь для backup, но НЕ утверждает, что полный архив создан/проверен.

## Когда запускаются миграции

`backend/Dockerfile.railway`:

```dockerfile
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

Upgrade запускается на старте нового API контейнера до healthcheck/uvicorn. Поэтому сначала backup, затем API upload. Stage может кратко обслуживаться предыдущим API во время миграции:0261 удаляет поле старой модели, пока новый API ещё запускается. Не выдавать наличие прежнего deployment за безопасный rollback схемы. Возврат прежнего app image после0261 потребует согласованного восстановления схемы/backup. Сама migration guard откажет, если к моменту её исполнения появится true is_fbs.

## Штатный backup перед разрешённым stage (подготовлен, НЕ выполнен)

Используется та же PostgreSQL-механика, что в `scripts/deploy/prod-update.sh`: custom-format pg_dump и pg_restore --list. VPS-script не запускается. `railway backup` в установленном CLI отсутствует; никакой внешний backup dashboard не открывался. Архив сохраняется приватно в существующем PGDATA volume; это переживёт API redeploy, но не является независимой копией на случай удаления самого DB volume.

Из CLI вызвать `railway ssh` с указанными project/environment и **Postgres service**, передав следующий shell-код без интерполяции локальным shell:

```sh
set -eu
umask 077
wms_stage_backup="$PGDATA/wms-stage-before-0261-20260910.dump"
test ! -e "$wms_stage_backup"
pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "$wms_stage_backup"
test -s "$wms_stage_backup"
pg_restore --list "$wms_stage_backup" >/dev/null
printf 'stage_backup_created_and_archive_list_verified\n'
```

Префикс команды: `railway ssh --project c28e681d-4535-4c96-ac97-c7b600a7f8e4 --environment 58a08b66-1290-45a2-8737-e3d7408389e5 --service 7ba030a6-5608-406f-838f-22cd19b44a11 -- sh -c ...`. Для многострочного payload использовать subprocess argv, как при проверке, либо одинарное shell quoting. Не печатать dump/list/environment. При существующем файле команда остановится, не перезапишет старую копию. При ошибке backup или проверки не запускать API deploy.

## Restore при отдельно принятом решении об откате (НЕ выполнен)

Остановить stage application writers до восстановления. Для полного возврата к снимку в том же Postgres service:

```sh
set -eu
wms_stage_backup="$PGDATA/wms-stage-before-0261-20260910.dump"
test -s "$wms_stage_backup"
pg_restore --list "$wms_stage_backup" >/dev/null
pg_restore --clean --if-exists --exit-on-error --single-transaction -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$wms_stage_backup"
```

Это заменяет данные снимком и не должно исполняться автоматически или при работающих writers. После восстановления проверить alembic0257, наличие is_fbs и старт согласованной предыдущей версии. Команда restore подготовлена по штатному pg_restore; фактический restore не проверялся и права на полный restore не объявлены доказанными schema-only чтением. Stage-префикс выше обязателен; production services/DB не затрагивать.
