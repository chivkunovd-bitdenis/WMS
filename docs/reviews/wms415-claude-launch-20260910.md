# WMS-415 — управление продолжением через Claude CLI

Это журнал запуска и исполнения, а не отдельный бэклог. Все работы и статусы — в [каноне](../KANONICHESKIY_BACKLOG.md). Постановка — [полный хэндофф](WMS_CLAUDE_HANDOFF_2026-09-09.md).

## Поручение и состояние подготовки

Владелец 10.09.2026 поручил после аудита самому передать работу Claude, Opus extra, запустить мультиагент и довести до production и приложения с обновлением из себя. В CLI 2.1.123 приняты `--model opus --effort xhigh`; стартовый экран подтвердил **Opus 4.7 with xhigh effort · Claude Max**. Режим полномочий — `auto`: выбран пункт только текущей сессии, глобальный default не менялся; обход проверок не включался.

Сначала открыт отдельный простаивающий интерфейс квоты, без задачи модели. `/usage` показал **75% used current week (all models), 25% remaining**; session cost/input/output были нулевыми. Это недельный лимит Claude, а не Codex. Сброс показан как 9:59am Europe/Moscow без даты; дату не домысливать. Отдельный ограничивающий недельный Opus-показатель на просмотренном экране не показан.

Сессия квоты: Claude `5ed12390-4d22-4b83-b183-114202609010`, tool PTY `75581`. Она не исполняет разработку. Для обновления закрыть меню Escape и вновь вызвать `/usage`. Не отправлять такие команды в работающий координатор. Если PTY исчез — открыть новый отдельный интерактивный процесс только для квоты. Не читать хранилища ключей/OAuth. Автообновление CLI показало ошибку; сам CLI продолжает открываться, его переустановка не выполнялась.

## Монитор

Автоматизация приложения `wms-claude`, target `01a08676-9477-72f0-808f-80aed056c6d5`, ACTIVE. В приложении допускается только один heartbeat на чат. Поэтому техническое пробуждение — каждые **10 минут** для квоты, полный контроль работ — каждые **20 минут** по сохранённому времени последнего контроля. Отдельный второй монитор не создан; cron-обход не создавался. Старые WMS-мониторы остаются PAUSED.

При квоте менее 7%: безопасная остановка Opus, подробный хэндофф каждого агента и Git; затем Astra 6 high через CLI в мультиагенте. После переключения автоматизацию перевести на 20 минут. Не прерывать транзакции/внешние передачи вслепую, не оставлять параллельных писателей.

## Координатор разработки

Передача ожидает финального сохранения аудита. Сам открытый интерфейс квоты не означает принятия задачи или запуска агентов. После запуска здесь будут сохранены session ID, PID/PTY, рабочая ветка, точный исходный SHA документа и доказательство принятия задания.

## Фактический запуск 10.09.2026

Координатор Claude Opus 4.7 принял поручение в этой сессии. Session id `2a1f478a-9d10-48fe-b183-114202609010`, checkout `/Users/deniscivkunov/Projects/WMS/.worktrees/wms415-claude`, рабочая ветка `codex/wms415-claude-extra-20260910`, исходный HEAD `bc7f760c11b032fbb94376f042bb6d0f2dd7c13b` (документ WMS-415 и хэндофф уже в дереве). Аудит-исходник `c91af35d1c96c3d0ab3678817f415ef1b86bd34d` подтверждён владельцем как запушенный в `codex/weekly-release-20260909`.

**Фактический режим:** родительский Claude Code запущен с `CLAUDE_CODE_EFFORT_LEVEL=xhigh` и `--effort xhigh`; координатор наблюдает соответствующие метаданные в стартовом экране. Инструменты порождения подагентов в этом рантайме — `Agent` (эквивалент прежнего TeamCreate по функции; подтверждён как рабочий), с параметрами `model=opus`, `subagent_type=general-purpose`, `isolation=worktree`, `run_in_background=true` и именами для адресации через `SendMessage`. Отдельного per-child переключателя усилия у этого инструмента нет: дети запускаются на дефолтном усилии Opus 4.7, а не на xhigh. Это ограничение зафиксировано честно; ускорять параллелизм слепо не будем. TeamCreate как отдельный инструмент помечен как отложенный в списке, но по функции полностью покрыт именованными параллельными вызовами `Agent`.

**Четыре параллельных исполнителя запущены в фоне в изолированных worktrees основного репозитория:**

| Полоса | Задачи | Имя | Ветка | Владение файлами |
|---|---|---|---|---|
| Чат | WMS-397, WMS-399 | `chat-lane` | `feat/wms397-chat-mvp` | НОВЫЕ backend chat_*.py в api/v2, services, models; alembic; НОВЫЕ frontend screens/chat, components/chat; точечная вставка кнопки «Написать сообщение» в существующие экраны документов без переработки колонок FBS. |
| Остатки/публикация | WMS-338, WMS-341, WMS-329, WMS-060 → WMS-352, WMS-386, WMS-384 | `stock-lane` | `feat/wms338-stock-min-formula` | ЭКСКЛЮЗИВНО `backend/app/services/inventory_service.py`; точечные правки FbsBindingStockPool в `wb_marketplace_orders_service.py`; сервисы Ozon-импорта; тесты. Формула `min(cap, свободный остаток)` без журналов и счётчиков. |
| Android/обновление/печать | WMS-401, WMS-363, сохранить WMS-412, отметить WMS-402 | `mobile-lane` | `feat/wms401-mobile-followup` (WMS-стороне) + локальные коммиты в отдельном mobile Git `codex/wms397-mobile` | Всё в `/Users/deniscivkunov/Projects/WMS/.worktrees/wms397-mobile` (без push, без чтения signing секретов, без переписывания WMS-412) плюс узкие безопасные патчи-зеркала в WMS Git. |
| Складские документы | WMS-062 → WMS-153/154/155/156/174/177 → WMS-179/182/184-187/190, тара WMS-055/056 | `warehouse-lane` | `feat/wms062-warehouse-docs` | Роуты `backend/app/api/v2/inventory_*`, `transfer_*`, `acceptance_*`; сервисы актов/перемещений/упаковки (кроме `inventory_service.py`); фронт-экраны inventory/transfers/acceptance; миграции своих схем; тесты. |

Все четыре работают с общим стартовым SHA `bc7f760c` в собственных изолированных worktrees и не пересекаются по владению. Явные запреты им переданы: не трогать чужие файлы, не откатывать колонки FBS, не воскрешать блокировки FBS-вкладок, не касаться поставки `85a8476c-05b4-46a8-a90f-77d5199257b4`, не повторять WMS-406/409/410, не менять APP_ENV/ключи, не мержить в main, коммиты обязательно с WMS-NNN. Каждый пишет верификационную заметку в `docs/reviews/`.

Координатор оставляет за собой канонические статусы (WMS-415, канонический бэклог) и сведение результатов; полосы владеют своим кодом. Ревью Astra 6 high по каждому готовому срезу — по правилу handoff §5; Opus финальный ревью — когда позволит квота. Астра не запускается ниже порога 7% остатка.

**Мониторинг и квота:** heartbeat `wms-claude` каждые 10 минут для квоты и каждые 20 минут для полного контроля работ — активен в отдельной сессии root. Отдельная idle CLI-сессия квоты не трогается координатором. Свежее чтение: 75% used current week (all models), 25% remaining. Порог остановки 7% и передачи Astra 6 high описаны в handoff §6 — координатор его соблюдает.

## Восстановление 10.09.2026 после сбоя изоляции подагентов

Через несколько минут после первого запуска обнаружено, что параметр `isolation: worktree` инструмента `Agent` не создаёт настоящей изоляции для этих подагентов: их создавали каталоги-заглушки в `/Users/deniscivkunov/Projects/WMS/.claude/worktrees/agent-*` со стартовым SHA `ff5555e2` (не аудированный `bc7f760c`), а сами подагенты писали и коммитили в общий координаторский checkout `/Users/deniscivkunov/Projects/WMS/.worktrees/wms415-claude` абсолютными путями. Root подтвердил конфликт независимой проверкой: HEAD общего checkout переехал на `feat/wms397-chat-mvp`, в дереве остался `M backend/app/services/inventory_service.py` (правка `stock-lane`) и `?? backend/tests/test_chat_api.py` (правка `chat-lane`).

Восстановление выполнено без `git reset`/`git stash`, все правки сохранены. Отчёты подагентов подтвердили точное содержание оставленного:

- `chat-lane` (a6e9bcf0dbbdafa7b): три коммита `71c903ca → d16e8589 → d73c05f0` в общем checkout плюс новый файл теста; harness-каталог оставался нетронутым.
- `stock-lane` (a254e6d9b275d4afb): пять удалений мутаций `FbsBindingStockPool.quantity` в `inventory_service.py` (пути резерва, отмены, недостачи, `apply_fbs_supply_write_off`, реверса `units_mode`) плюс комментарии WMS-338/341 — не коммитилось.
- `warehouse-lane` (a7a57b97a3faeba40): один коммит `5fee5efd` (WMS-062, default «Основной» при регистрации), плюс WMS-153/155 partial в четырёх файлах — уже жил в собственном harness-каталоге, но не под `.worktrees`.
- `mobile-lane` (a6bcd38a653b6a036): САМОСТОЯТЕЛЬНО выполнил правильный `git worktree add -b feat/wms401-mobile-followup .worktrees/wms401-mobile-followup codex/wms415-claude-extra-20260910` на `bc7f760c`; отдельный mobile Git на `codex/wms397-mobile` получил локальный коммит `9a83ef6133201cea178cdda8a9437a165892a458` (WMS-401: orders-first + sortedOrders + versionCode 8→9), APK собран (`ccb8d7ea57863133f1b2c0dc549ffb10c74d17620203ff0ba3f43f88726457a6`, 45 281 897 байт), загружен в релиз `tsd-preview`, `update.json` намеренно ещё не переключён.

Резервные копии обоих несохранённых файлов положены в `/tmp/wms415-recovery/` перед любыми git-операциями. Затем:

1. `git worktree add -f /Users/deniscivkunov/Projects/WMS/.worktrees/wms397-chat-mvp feat/wms397-chat-mvp` — включая три коммита chat-lane; поверх положен сохранённый `test_chat_api.py`.
2. `git worktree add -b feat/wms338-stock-min-formula /Users/deniscivkunov/Projects/WMS/.worktrees/wms338-stock-min-formula bc7f760c…` — свежая ветка на аудированном SHA; поверх положена сохранённая правка `inventory_service.py` (uncommitted).
3. `git worktree unlock` + `git worktree move` для `warehouse-lane` из `.claude/worktrees/agent-a7a57b97a3faeba40` в `.worktrees/wms062-warehouse-docs` — атомарно, все uncommitted файлы перенесены.
4. `mobile-lane` не двигали — уже правильно.
5. `git worktree add -b codex/wms415-coord-20260910 /Users/deniscivkunov/Projects/WMS/.worktrees/wms415-coord bc7f760c…`, затем `git cherry-pick ff7d100d` — координаторский doc-коммит переехал на изолированную ветку `codex/wms415-coord-20260910` (новый SHA `10925387`). Старая ветка `feat/wms397-chat-mvp` продолжает нести коммит `ff7d100d` в середине — редактировать её историю нельзя, чтобы не рушить работу chat-lane; при финальном сведении coordinator-документы вынимаются отдельно.
6. `.worktrees/wms415-claude` объявлен read-only quarantine: остаётся с исходным «грязным» состоянием как исторический артефакт, писать в него больше нельзя.

Root независимо проверил в 21:36 UTC: все пять правильных worktrees существуют под `.worktrees/`, все происходят от `bc7f760c`, скопированные файлы совпадают с резервными копиями побайтово. Дальнейшая работа ведётся строго в этих пяти путях.

## Повторный запуск подагентов после восстановления

Прежние сессии подагентов уже завершились (адресация по имени истекла), поэтому созданы четыре свежих Opus-подагента без `isolation: worktree` — с явным абсолютным путём в промпте и жёстким запретом на `cd` за его пределы. Каждому передан полный список сохранённого предыдущей сессией, чтобы не переделывать её работу:

| Полоса | Абсолютный путь | Ветка | Стартовое состояние |
|---|---|---|---|
| `chat-lane` | `/Users/deniscivkunov/Projects/WMS/.worktrees/wms397-chat-mvp` | `feat/wms397-chat-mvp` @ `d73c05f0` | 3 коммита моделей/сервиса/API уже есть; `test_chat_api.py` uncommitted; далее — фронт, alembic upgrade, note, push. |
| `stock-lane` | `/Users/deniscivkunov/Projects/WMS/.worktrees/wms338-stock-min-formula` | `feat/wms338-stock-min-formula` @ `bc7f760c…` | Правка `inventory_service.py` uncommitted; далее — атомарный коммит с WMS-338/341/329, регрессионные тесты, обход остальных мутаций quantity, WMS-060/352/386/384, note, push. |
| `warehouse-lane` | `/Users/deniscivkunov/Projects/WMS/.worktrees/wms062-warehouse-docs` | `feat/wms062-warehouse-docs` @ `5fee5efd` | WMS-062 коммит есть; WMS-153/155 partial в 4 файлах uncommitted; далее — доделать WMS-153/155, потом WMS-154/156/174/177, потом UI defect batch и тары. |
| `mobile-lane` | `/Users/deniscivkunov/Projects/WMS/.worktrees/wms401-mobile-followup` + `/Users/deniscivkunov/Projects/WMS/.worktrees/wms397-mobile` | `feat/wms401-mobile-followup` (WMS) + `codex/wms397-mobile` (mobile) | APK 0.1.8 собран и загружен; далее — swap `update.json`, in-app 0.1.7→0.1.8 verify на эмуляторе, WMS-401 note, узкий mirror patch; затем **WMS-363** как отдельный следующий срез (root корректировка: жёсткий `marketplace=wb` — доказательство пробела, а не повод отменить задачу). |

Каждый повторный подагент явно обязан `pwd && git branch --show-current && git status --short` в начале каждого шага, коммитить только на свою ветку, никогда не переходить в чужой worktree, никогда не удалять и не откатывать чужие правки. При сомнении — пауза с концретным вопросом, не молчаливый пропуск задачи.
