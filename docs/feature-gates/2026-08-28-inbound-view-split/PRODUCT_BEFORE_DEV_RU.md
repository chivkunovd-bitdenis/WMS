# Product Before Dev — A-3: разделение экрана приёмки без изменения продукта

## Продуктовый вывод

Карточка допускается в разработку только как механическая декомпозиция. Для
сотрудника фулфилмента результат должен быть не «похожим», а наблюдаемо тем же
экраном: тот же путь от очереди к документу, те же действия для роли и статуса,
тот же порядок блоков, те же тексты, сканирование, печать, ошибки и итог
операции. Пользовательская ценность этой карточки не в новом действии, а в том,
что следующие изменения приёмки смогут затрагивать небольшую изолированную
часть и реже ломать соседний физический процесс.

Положительный verdict не разрешает исправлять найденные по дороге тексты,
кнопки, мёртвые флаги или старую вёрстку. Даже полезное изменение поведения
будет другой feature card и аннулирует этот verdict.

## Зафиксированный baseline

- Git SHA: `7783a27c8c49a60706bac70a155c0721601fbfbb`.
- SHA-256 исходного файла:
  `c5ff576a0a3f0657730421c82647a876b60f1723b44387761022e5b09257ceaa`.
- `FfInboundRequestView.tsx`: 3668 физических строк, 3669 строк по алгоритму
  `ui_guard`.
- Сохранённая запись guard: 3680 строк, 6 `Chip`, 36 `Button`, 4 `TableHead`.
- `python3 scripts/ui/ui_guard.py` завершается с exit 0, но лишь сообщает
  улучшение 3680 → 3669; монолит на baseline ещё существует.
- В исходнике зафиксированы 100 вхождений статического `data-testid` с 98
  уникальными значениями, пять динамических семейств для строк/коробов и
  грузомест, а также дочерние selector contracts через `testId` и
  `testIdPrefix`.

Этот baseline относится к состоянию до production-правок A-3. Параллельные
изменения других задач нельзя подмешивать в сравнение или массовое обновление
`docs/product/ui-guard-baseline.json`.

## Пользовательский процесс, который нельзя изменить

Основной пользователь — сотрудник фулфилмента с правом приёмки. Он открывает
документ из `/app/ff/reception`, `/app/ff/sorting`, dashboard или списка
документов, сверяет номер, селлера, статус и суммы, а затем выполняет действие,
разрешённое текущим статусом.

1. В черновике сотрудник добавляет товар из каталога или сканированием и
   начинает приёмку; селлер в разрешённом ему пути передаёт документ на склад.
   Эти действия нужны, чтобы состав физически приехавшего груза был связан с
   конкретным документом до пересчёта.
2. На приёмке оператор scanner-first принимает товар, при необходимости меняет
   фактическое количество и габариты, наполняет короба и печатает этикетки.
   Здесь скорость сканирования и сохранение выбранного короба важнее внутренней
   структуры React-компонентов.
3. При расхождении оператор видит тот же итог по строкам и коробам и явно
   подтверждает завершение; связанный акт утверждается или отклоняется только
   пользователем с прежними полномочиями. Это не даёт незаметно провести
   недостачу или излишек.
4. После приёмки документ уходит в сортировку. В workspace `sorting` сотрудник
   видит существующую сортировочную панель, а не дубль таблицы состава; до
   завершения приёмки он видит прежнее ожидание. Так оператор не начинает
   раскладку раньше физического пересчёта.
5. Кнопки печати накладной, коробов, грузомест и товара остаются в тех же
   состояниях. Они обслуживают разные физические носители и не могут быть
   объединены или переставлены в рамках механического split.
6. При закрытии с несохранённым фактом остаётся прежнее предупреждение, а при
   сканировании — прежняя последовательная очередь и debounce-перезагрузка.
   Это защищает от потери ручной корректировки и гонок быстрых сканов.

## Verdict по заметным элементам

- **Шапка и компактная сводка.** Номер документа, тип операции, marketplace,
  селлер, принятое количество, короба, литраж, вес и статус помогают оператору
  убедиться, что он считает нужный груз. Их тексты, порядок, переносы и
  условная видимость заморожены.
- **Строка действий.** Главная кнопка зависит от статуса, workspace и роли:
  «Передать на склад», «Начать приёмку», «Завершить подбор возврата» или
  «Завершить приёмку». Рядом остаются только уже существующие действия
  добавления, редактирования, печати, сохранения и закрытия. Новый shortcut,
  дубль или переименование запрещены.
- **Таблица состава.** Она нужна для сверки ожидаемого и фактического количества,
  габаритов и расхождения. В `sorting` она по-прежнему скрыта, потому что товар
  там представлен интерактивной сортировочной панелью. Порядок колонок,
  row-state, длинные SKU/ШК и внутренний горизонтальный overflow не меняются.
- **Акты расхождений.** Блок остаётся только у роли с FF-операциями и вне
  sorting-view. Статусы и действия нужны для явного решения финансово значимого
  расхождения; показывать их шире или раньше запрещено.
- **Короба и грузоместа.** Существующий accordion сохраняет раскрытие, счётчики,
  строки, «Наполнить», удаление и печать. Это физические единицы груза, поэтому
  выбранный короб, его номер и содержимое не должны сбрасываться при
  компонентном разрезе.
- **Сортировка и адресное хранение.** Текущий `workspace` и
  `addressStorageEnabled` продолжают управлять теми же видимыми состояниями.
  Недоступная сегодня ветка `documentDistributionEnabled = false` не удаляется
  и не включается «заодно».
- **Диалоги, snackbar и ошибки.** Picker товара, габариты, импорт коробов,
  создание грузомест, наполнение короба, подтверждение закрытия,
  подтверждение расхождения и печать должны открываться, закрываться,
  восстанавливать focus и показывать ошибки как раньше. Добавление общего
  технического сообщения вместо конкретной ошибки запрещено.
- **Пустые состояния.** «Заявка не найдена или недоступна», пустой состав,
  пустые короба/грузоместа, ожидание завершения приёмки и отсутствие ячеек
  сохраняются дословно и в прежнем месте.

## Замороженные контракты для Dev и Code Review

### Публичный React-контракт

Сохраняются exports `FfInboundRequestView`, `InboundRequestWorkspace` и
`WbCatalogRow`. Внешний вызов в `App.tsx` продолжает передавать:

- `token` и `requestId` без подмены scope;
- `isFulfillmentAdmin={canReceptionOps}` — именно существующее отображение
  permission в prop, несмотря на историческое имя prop;
- `workspace` со значениями `reception | sorting | full`;
- `sellers`, `addressStorageEnabled`, `onDirtyChange`, `onClose`;
- прежние defaults `workspace = 'full'` и `addressStorageEnabled = true`.

Извлечённые компоненты не получают permissive defaults. Право на действие
передаётся явно и не вычисляется заново по более слабому условию.

### DOM и доступность

Для одной fixture до и после должны совпасть:

1. типы DOM-узлов, nesting, sibling order и наличие/отсутствие wrapper-узлов;
2. accessible role/name, label association, tab order, focus после открытия и
   закрытия диалога, Escape/close behavior;
3. порядок landmarks внутри документа: error/warning → header/summary/status →
   actions → sorting panel или lines table → wait/discrepancy blocks → packages
   → existing post-reception/distribution area → dialogs/snackbars/print;
4. видимость, текст, цвет, размер, enabled/disabled и loading-state каждого
   существующего элемента;
5. отсутствие document-level horizontal overflow на 1600×1000 и 390×844;
   длинные название, SKU и ШК остаются внутри существующего внутреннего
   overflow и не перекрывают действия.

React fragment допустим только если он не создаёт DOM-узел. Новый `div`, новый
MUI-wrapper или перенос dialog/provider выше или ниже считается изменением до
тех пор, пока независимый review не докажет полную эквивалентность.

### `data-testid`

Критерий — равенство, а не «тесты нашли нужную кнопку»:

- набор и multiplicity всех статических `data-testid` baseline остаются
  прежними: 100 вхождений / 98 уникальных значений;
- сохраняются динамические семейства `rowTestId`,
  `ff-inbound-box-header-${box.id}`, `ff-inbound-box-fill-${box.id}`,
  `ff-inbound-box-delete-${box.id}`, `ff-inbound-box-print-${box.id}` и
  `ff-inbound-cargo-place-print-${place.id}`;
- сохраняются переданные дочерним компонентам `ff-inbound-line-photo`,
  `ff-inbound-box-line-photo`, `ff-inbound-marketplace-chip`,
  `ff-inbound-planned-date`, prefixes `ff-inbound-picker` и
  `ff-inbound-box-import`, а также `ff-inbound-box-print-dialog`;
- ни один selector не переименовывается, не дублируется в другой ветке DOM и не
  переносится на семантически другой элемент.

Сравнение выполняется с исходником на baseline-SHA, а не только с текущими
ожиданиями Playwright: тест может не покрывать редкий selector.

### API и runtime

Разделение не меняет ни одного URL, HTTP-метода, заголовка, query-параметра,
body, момента вызова, retry/error handling или порядка зависимых запросов.
Нормализованный network trace одинакового пользовательского пути должен быть
равен baseline.

Особенно фиксируются группы запросов:

- загрузка документа, связанного каталога, складов/ячеек, актов расхождения и
  текущего распределения;
- draft lines/expected, submit и begin-receiving;
- receiving lines/scan/actual, complete и reopen;
- boxes, cargo places, mark-label-printed и существующий import base path;
- approve/reject акта, product dimensions и существующие distribution routes;
- API, вызываемые `FfInboundSortingPanel`, `FfInboundBoxAddDialog`,
  `WbProductPickerDialog` и `useOzonReturnWorkflow`, через неизменные props и
  callbacks.

Один физический скан по-прежнему создаёт одну операцию в существующей serial
queue; debounce reconciler отменяется при unmount. Нельзя получить двойной
запрос из-за двух mounted extracted components или изменить последовательность
reload после mutation.

### Роли, workspace и scope

- Маршруты `/app/ff/reception` и `/app/ff/sorting` по-прежнему доступны только
  при `token && canReceptionOps`; split не расширяет route access.
- `isFulfillmentAdmin` в самом компоненте продолжает ограничивать scanner,
  приёмочные действия, акты, короба/грузоместа и распределение по тем же
  условиям.
- `workspace='reception'` не показывает sorting panel и не запускает
  distribution load; `workspace='sorting'` отключает scanner, скрывает таблицу
  состава, акты и packages и показывает sorting panel только после закрытия
  приёмки; `workspace='full'` сохраняет текущую совмещённую семантику.
- `seller_id` используется для каталога того же селлера, `warehouse_id` — для
  ячеек того же склада, `requestId` — для всех document mutations. Нельзя
  fallback-ить на глобальный каталог, выбранный в другом экране склад или
  permissive tenant data.
- `addressStorageEnabled` продолжает влиять только на прежние тексты/ветки;
  механический split не включает скрытое распределение.

## Структурный guard и граница diff

После разделения `FfInboundRequestView.tsx` и каждый новый TSX-файл A-3 должны
иметь не более 600 строк по формуле `text.count("\n") + 1`. В итоговой
`ui-guard-baseline.json` запись `экран-монолит` для
`src/screens/ff/FfInboundRequestView.tsx` отсутствует, а общее число
baseline-монолитов уменьшается минимум на один.

Суммарно по всем TSX-файлам зоны A-3 разрешено не более исходных 6 `Chip`, 36
`Button` и 4 `TableHead`; новый `свой-цвет` или другой guard-дефект запрещён.
Baseline обновляется точечно только для A-3. Перенести монолитный JSX в один
новый файл, скрыть его расширением вне сканирования или поднять порог — не
выполнение карточки.

Diff не должен содержать ни одного файла из:

- `frontend/src/screens/ff/warehouse-map/`;
- `frontend/src/screens/ff/sorting-objects/`;
- `frontend/src/ui-kit/`.

Также запрещены изменения backend/API и соседних экранов: они не нужны для
механического split.

## Обязательные доказательства после разработки

До первой production-правки Dev фиксирует воспроизводимую fixture и before
evidence для одной роли/тенанта/селлера/склада в состояниях draft, receiving с
коробами и расхождением, sorting — на 1600×1000 и 390×844. После разработки
повторяются те же состояния.

Технический минимум:

- `npm run build`;
- `python3 scripts/ui/ui_guard.py`;
- утверждённый BA-набор из восьми Playwright-spec без новых `skip`, ослабления
  visible assertions или замены пользовательского пути одним API-вызовом;
- отдельная проверка равенства DOM/data-testid и нормализованного network trace;
- scoped diff защищённых каталогов равен пустому.

После Code Review отдельный Product Agent обязан в живой видимой вкладке руками
пройти draft → receiving → sorting, включая скан, короб, ручной факт,
расхождение, закрытие с dirty-state и desktop/mobile geometry. Скриншоты и
Playwright — техническое evidence, но не `PRODUCT_BROWSER_APPROVED`.

## Обязательный verdict

```yaml
feature_id: A-3
agent_name: "/root/a3_product — изолированный Product Agent Before Dev"
isolated_agent: yes
review_stage: before_dev
professional_context:
  wms: yes
  logistics: yes
  fulfillment: yes
  marketplaces_wb: yes
real_browser_used: no
browser_type: "не применимо на before_dev; обязательна живая видимая вкладка после разработки"
environment_url: "не открывался на before_dev"
role: "проверены контракты canReceptionOps, FF admin/operator и ограниченного пользователя"
tenant: "baseline scope; конкретная fixture должна быть закреплена до первой production-правки"
seller: "baseline scope; seller_id обязан остаться частью catalog scope"
warehouse: "baseline scope; warehouse_id обязан остаться частью location scope"
screen_urls:
  - "/app/ff/reception"
  - "/app/ff/sorting"
  - "/app/ff/dashboard и существующие full-workspace входы"
actions_clicked: []
inputs_or_scans: []
success_seen: "не заявляется: это review до разработки по коду и действующим browser contracts"
error_seen: "не заявляется; существующие error contracts зафиксированы для parity review"
empty_state_seen: "не заявляется; существующие empty contracts зафиксированы для parity review"
reload_readback_seen: "не заявляется; обязателен после разработки"
element_verdicts:
  rows: "сохранить порядок, match/discrepancy states, sorting visibility и длинные значения"
  columns: "сохранить состав, порядок, ширины и internal overflow; новых колонок нет"
  buttons: "сохранить тексты, порядок, handlers, role/status/workspace guards и disabled states"
  labels: "сохранить все русские тексты дословно; новый технический текст запрещён"
  fields: "сохранить значения, validation, focus, blur/Enter save и dirty semantics"
  filters: "новых фильтров нет; существующие picker/search contracts не меняются"
  chips: "сохранить шесть исходных guard-отступлений суммарно; новые chips запрещены"
  statuses: "сохранить текущие labels/colors и status-driven actions без remapping"
  dialogs: "сохранить open/close/Escape/focus, contents, actions and errors всех диалогов"
  text_fit: "сохранить desktop/mobile geometry, ellipsis и внутренний table overflow"
warehouse_usability_verdict: >-
  Механическое разделение допустимо: оно не добавляет оператору шагов и не меняет
  физический процесс, если все замороженные DOM/API/role/runtime contracts доказаны.
demo_risk: >-
  Высокий до browser parity: даже перестановка wrapper или effect способна изменить
  focus, scanner queue, порядок запросов, доступность кнопки или mobile overflow.
verdict: PRODUCT_APPROVED_FOR_DEV
evidence_paths:
  - "docs/feature-gates/2026-08-28-inbound-view-split/FEATURE_CARDS_RU.md"
  - "frontend/src/screens/ff/FfInboundRequestView.tsx@7783a27c8c49a60706bac70a155c0721601fbfbb"
  - "frontend/src/App.tsx"
  - "scripts/ui/ui_guard.py"
  - "docs/product/ui-guard-baseline.json"
  - "docs/MVP_DECISIONS_RU.md"
  - "docs/IMPLEMENTED_PRODUCT_SCENARIOS_TEST_CASES_EN.md#S06"
  - "frontend/tests-e2e/inbound-receiving-v2.spec.ts и BA-набор inbound specs"
blocking_issues: []
```

**Product verdict: `PRODUCT_APPROVED_FOR_DEV`.** Разработка разрешена только в
описанных границах механического split. Любое изменение видимого поведения,
текста, DOM-контракта, API, ролей или runtime переводит карточку в
`PRODUCT_REWORK_REQUIRED` и требует нового BA/Product прохода.
