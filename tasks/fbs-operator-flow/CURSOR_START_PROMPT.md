# Стартовый prompt для Cursor

Скопируй Cursor текст ниже целиком.

---

Работай в репозитории `/Users/deniscivkunov/Desktop/WMS ` — в имени каталога есть пробел в конце. Текущая integration branch на момент постановки: `feat/fbs-stock-sync`, исходный HEAD `ef92a22`. Сначала проверь фактические branch/HEAD/status; чужой dirty tree не чисти, не stash и не перезаписывай.

Твоя зона ответственности — только backend полноценного FBS-процесса: модели и миграции, WB client, application/service layer, API, фоновые sync/reconcile jobs, emulator, backend/integration tests и backend handoff. Frontend реализует другой исполнитель; файлы `frontend/**` не меняй.

Обязательные документы, в порядке чтения:

1. `tasks/fbs-operator-flow/README.md` — цель, границы и бизнес-правила.
2. `tasks/fbs-operator-flow/BACKEND_CONTRACT.md` — обязательные URL, request/response, ошибки, атомарность и идемпотентность.
3. Разделы 1–2 `tasks/fbs-operator-flow/FRONTEND_TASKS.md` — binding wire-format и точные frontend function names, под которые должен отвечать backend.
4. `tasks/fbs-operator-flow/CURSOR_TASKS.md` — очередь FBSFLOW-000…140, ownership, зависимости и gates.
5. `tasks/fbs-operator-flow/TEST_CASES.md` — обязательные сквозные и негативные сценарии.
6. Корневой `AGENTS.md`, `.dev/PROCESS.md` и `tasks/fbs-stock-sync/HANDOFF.md`.

Начни с FBSFLOW-000. Не переходи к следующей задаче, пока gate текущей не доказан. Одна задача — один небольшой commit с ID `FBSFLOW-NNN`. Если baseline уже красный, зафиксируй это до правок и не чини посторонние модули.

Контракт нельзя самовольно упрощать или переименовывать. В частности:

- не возвращай локальные file paths вместо `preview_url`/`download_url`;
- не переноси серверное состояние подбора в browser/localStorage;
- не создавай вторую сущность упаковки параллельно существующему `PackagingTask`;
- не делай ручную связь order → trbx обязательной;
- не считай timeout, 409 или неоднозначный ответ WB успехом;
- не меняй локальный статус на успешный до ответа WB или доказанного reconcile;
- не добавляй frontend fallback на старые endpoints;
- сохраняй tenant/seller isolation для заказов, остатков, КИЗ, поставок и печатных активов.

Если текущий WB API расходится с документом, не импровизируй молча: приложи ссылку на официальную документацию, точный diff контракта и останови затронутую задачу до согласования. Внутренние имена классов выбирать можно, публичный wire-contract менять нельзя.

Финальный результат FBSFLOW-140 должен содержать `tasks/fbs-operator-flow/HANDOFF.md` с:

- реализованными endpoint-ами и OpenAPI;
- применёнными миграциями;
- точными командами тестов и их результатами;
- реальными JSON fixtures каждого endpoint-а;
- поднятым compose/emulator full flow для трёх селлеров;
- известными ограничениями и отдельно статусом live WB smoke;
- точным commit SHA, от которого Codex начнёт frontend.

Не объявляй задачу готовой только по unit tests и не делай deploy/merge в main без отдельной команды пользователя.

---
