# S09 UX_CONTRACT_AND_MOCKUPS — BLG-D16

## Source

Backlog item: `BLG-D16` — Дать оператору безопасную перевязку КИЗ между заказами

Business meaning:
Если код идентификации знака, то есть КИЗ, по ошибке привязан не к тому заказу, сейчас оператор не может нормально исправить это через рабочий интерфейс. Ручное исправление в базе опасно: можно оставить код сразу в двух местах или разойтись с состоянием Wildberries. Нужен единый подтверждаемый сценарий, который снимает код со старого заказа, проверяет возможность переноса, привязывает его к новому заказу и показывает итог обеих операций.

## UX Contract

### Operator intent
Интерфейс должен убрать конкретную складскую путаницу из карточки, не добавляя технический шум и не меняя соседние процессы. Все видимые элементы должны иметь прямую задачу: объяснить состояние, дать безопасное действие или показать результат.

### UI-kit components
Allowed components for the touched zone: ScreenShell, ScreenHeader, ToolbarLine, FilterBar, DataTable, StatusChip, MarkChip, PrimaryAction, SecondaryAction, DangerAction, IconAction, ActionGroup, PrintAction, TextInput, SelectField, CheckboxField, TabsBar, ModalDialog, ActionMenu, ErrorNotice, EmptyState, ScannerLine, QtyCell, PlanFactCell, TextCell, ProductCell.

Новый экран или новая зона не должны использовать сырые MUI `Button`, `Chip`, `TableHead` или локальные цвета. Если при S18 выяснится, что нужного компонента нет, Dev обязан вернуть typed design-system blocker, а не сверстать обход.

### Required states
- Success: оператор видит новое понятное состояние или действие именно в затронутой зоне.
- Empty: система объясняет действительно пустой результат без ложной ошибки.
- Error: ошибка написана человеческим текстом и ведёт к безопасному следующему шагу.
- Forbidden: если действие нельзя выполнить, причина и условие блокировки видимы.
- Partial: если применима частичная обработка, экран показывает обработанные и оставшиеся элементы отдельно.
- Repeat/cancel: повтор не создаёт дублей, отмена не теряет уже подтверждённый результат.

### Mockup description
Макет на этой стадии текстовый: зона экрана собирается из `ScreenShell`/`ScreenHeader`, рабочей строки действий `ToolbarLine`, фильтров `FilterBar`, таблицы `DataTable`, статусов `StatusChip`, форм `TextInput`/`SelectField`/`CheckboxField`, подтверждений `ModalDialog` и меню `ActionMenu` по необходимости. Конкретные подписи, колонки и негативные кейсы должны быть проверены в S10 и затем превращены в test cases в S15.

### Acceptance notes for S10
S10 должен проверить, что текст не выглядит техническим логом, не ломает scanner-first работу, не плодит лишние карточки/панели и не подменяет продуктовый вопрос локальной вёрсткой.

## Out of Scope

Нет реализации, нет изменения API, нет live browser acceptance, нет deploy и нет операций с секретами.

## S09 Verdict

`UX_CONTRACT_READY`: UX-контракт достаточно конкретен для Product/Design review. Product still may block S10/S11 if warehouse rationale or oracle is insufficient.
