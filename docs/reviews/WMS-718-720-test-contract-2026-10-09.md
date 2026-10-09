# WMS-718 / WMS-720 · Дополненный контракт тестов · 09.10.2026

Контракт локально реализован, не закоммичен. Коммиты и push оставлены ведущему
по прямому поручению. Этот отчёт дополняет прежнюю остановку: аналитик в
`e1dbce4cd` разделил автоматическую структуру/стили и ручную геометрию.
Прежний отчёт и закоммиченные контракты WMS-716/717/719 не изменены.

## Исходное состояние

- HEAD: `e1dbce4cdca9c6e3882c23e75747d045e9744265`.
- Ветка: `feat/wms716-720-fbs-orders-list`; рабочее дерево было чистым.
- Проверены обновлённые документы WMS-718/WMS-720, AGENTS.md и навык
  `docs/reviews/2026-09-11-analyst-draft/skills/wms-test-writer/SKILL.md`.
- Контракты ведущего: WMS-716 `08e5f87ff`, WMS-717 `bf91bc753`, WMS-719 `3365993fe`.
  Их тесты, постановки и общая фикстура не редактировались.
- node_modules доступен; запуск выполнялся через `--configLoader runner`.
  Новые наборы до первого запуска не имели результатов. Уже известны красные
  новые требования прошлого этапа, включая перенос размера и прежние 52/56 px.
  При запуске новых наборов ошибки окружения не выявлены; TypeScript проходит.

## Файлы и результаты

| Задача | Тестовый файл | Документ | Итог |
|---|---|---|---|
| WMS-718 | `frontend/src/screens/v2/FfFbsOrdersScreen.wms718.dom.test.tsx` | `docs/requirements/WMS-718.md` | 9 случаев: 7 зелёных, 2 красных |
| WMS-720 | `frontend/src/screens/v2/FfFbsOrdersScreen.wms720.dom.test.tsx` | `docs/requirements/WMS-720.md` | 19 случаев: 15 зелёных, 4 красных |

В требованиях заполнен только столбец «Тест»: WMS-718 C2–C6 и WMS-720 C1–C5/C7.
«Вердикт», классы, требования, заключение и остальные слова сохранены.
Ручные WMS-718 C1/C7 и WMS-720 C6/C8 оставлены без ссылок на автоматические тесты.
Общая фикстура `frontend/src/screens/v2/test-support/fbsOrdersDom.tsx` используется
без изменений. Экран, строки, FbsAssemblyTaskRows, ProductPhotoThumb и HTTP-адаптер
настоящие. Управляемы только внешние ответы, Image/IntersectionObserver/
ResizeObserver и входные измерения jsdom; соседние закрытые рабочие пространства
заменены в уже существующей фикстуре, их поведение этим набором не принимается.

## Что означает красное

WMS-718 C3 красная в обеих ветвях строки: шапка содержит SKU между артикулом и
штрихкодом, размер остаётся после штрихкода. Ожидание обновлённого документа
включает перенос из WMS-719. Это зависимость от ещё не реализованной соседней
задачи, а не доказательство причины «уползания» заголовка. Проверки последующего
соответствия ячеек после нового порядка пока blocked на этом первом ожидании;
они не названы успешно выполненными.

WMS-720 C1 на «Новых» получает фиксированные 52 px, на «Отменённых» — 56 px.
C2 привязки к целой строке Ozon и C3 общей области для разных источников падают
на том же старом независимом ограничении. Контролируемые размеры содержимого
80/160/200/180/120 px являются входами реакции, а не измерением настоящей
раскладки. Последующие проверки реакции и повторного входа одного размера
пока blocked на фиксированном ограничении; успешность не выдумывается.

## Что означает зелёное и как доказана польза

WMS-718 C2 проверяет computed CSS: sticky/top, непрозрачный фон, z-index над телом,
ограниченную высоту и прокрутку в общей таблице. C4 использует контролируемую
высоту панели 80→120 px и повтор 120 px, проверяет резерв 110→150 px, выбор,
снятие выбора, ручной и фоновый цикл. C5 проверяет четыре вкладки, реальные
сборочные/обычные строки и colSpan; «Просрочены» проверяются внутри случая
«Отменённые» только если вкладка присутствует. C6 завершает старый запрос после
смены контекста: новая поставка, колонки и шапка сохраняются, повтор чтения успешен.

WMS-720 C2 сохраняет одно фото заказа, первую позицию либо product как запасной
источник, названия всех позиций и обе ветви строк. C3 защищает cover вместо fill
и стабильность CSS/источника при повторе; у управляемых проб изображений заданы
естественные размеры 100×100, 60×120 и 120×60 для трёх типов источника. Декодирование
изображения настоящим браузером не утверждается. C4 проверяет отсутствие/null/
пустую ссылку, отказ пробы, заглушку и восстановление без замены правил области.
C5 проверяет положительные/отрицательные события IntersectionObserver, поздний
ответ A после перехода к B, повторное открытие и устаревший отказ при смене
источника того же заказа. C7 вызывает общий ProductPhotoThumb с прежними
src-only аргументами из SellerCatalogSelectionDialog: 44 px и просмотр 240 px,
hover/focus и закрытие. Отдельный C7 проверяет просмотр 280 px в FBS, таблицу
поставок и отсутствие запросов изменения заказа/остатка/резерва; БД здесь не
подменена утверждением о её физической проверке.

Все 22 зелёных случая стали красными при целевой временной порче:

| Группа | Временная порча | Пойманный результат |
|---|---|---|
| WMS-718 C2/C5 | Удалено закрепление обеих таблиц | computed position перестал быть sticky |
| WMS-718 C4 | Высота панели исключена из резерва | 30 px вместо 110 px |
| WMS-718 C6 | Удалена защита по последовательности запросов | Поздний ответ убрал поставку нового контекста |
| WMS-720 C2 | Источник взят со второй позиции | second.jpg вместо first.jpg/product.jpg |
| WMS-720 C3 | object-fit изменён на fill | fill вместо cover |
| WMS-720 C4 | Существующая заглушка заменена чужим текстом | Отсутствует ожидаемая иконка заглушки |
| WMS-720 C5, видимость | Удалено ленивое включение src | Пробы стартуют до входа в область видимости |
| WMS-720 C5, старый отказ | Удалена защита неактивной пробы | Поздний отказ скрывает текущее рабочее фото |
| WMS-720 C7, сосед | Изменены общий размер и размер просмотра | 45 px вместо 44 px |
| WMS-720 C7, запросы | В просмотр добавлен POST | Чтение/просмотр отправляет изменение |

Повреждения выполнялись только для доказательства, а исходные байты двух
продуктовых файлов сохранены и восстановлены в finally. В mutation-прогоне
выбирались 22 ранее зелёных случая; все 22 упали содержательно. Остальные шесть
были вне адресного фильтра этого диагностического прогона. После отката финальный
запуск без фильтра выполнил все 28 случаев: **22 зелёных, 6 ожидаемых красных,
0 пропусков**. Никаких skip в тестовых файлах нет.

## Полные имена тестов и индивидуальный результат

### WMS-718

- `C2 keeps one opaque sticky header with the body in a bounded scroll container` — зелёный. На временной порче: expected '' to be 'sticky' // Object.is equality.
- `C3 aligns semantic cells and width rules after size replaces SKU on Новые` — красный. expected [ '', 'Товар', …(7) ] to deeply equal [ '', 'Товар', …(6) ].
- `C3 aligns semantic cells and width rules after size replaces SKU on Отменённые` — красный. expected [ '', 'Товар', …(8) ] to deeply equal [ '', 'Товар', …(7) ].
- `C4 reserves measured panel space and keeps selection and header through resize and refresh` — зелёный. На временной порче: expected 'calc(100vh - 330px - 30px)' to contain '110px'.
- `C5 preserves В работе columns, row spans and one sticky header` — зелёный. На временной порче: expected '' to be 'sticky' // Object.is equality.
- `C5 preserves В доставке columns, row spans and one sticky header` — зелёный. На временной порче: expected '' to be 'sticky' // Object.is equality.
- `C5 preserves Завершённые columns, row spans and one sticky header` — зелёный. На временной порче: expected '' to be 'sticky' // Object.is equality.
- `C5 preserves Отменённые columns, row spans and one sticky header` — зелёный. На временной порче: expected '' to be 'sticky' // Object.is equality.
- `C6 ignores the old list response after switching context and preserves the new header on retry` — зелёный. На временной порче: expected 'Заказы FBSОбновлено только чтоОбновит…' to contain 'Поставка нового контекста'.
### WMS-720

- `C1 follows controlled row content heights without the old 52/56 px limit on Новые` — красный. the old independent thumbnail size must not constrain the row photo: expected [ '52px', '52px', '', '' ] to not include '52px'.
- `C1 follows controlled row content heights without the old 52/56 px limit on Отменённые` — красный. expected [ '56px', '56px', '', '' ] to not include '56px'.
- `C2 preserves one Ozon photo and all positions on Новые with first photo present=true` — зелёный. На временной порче: expected 'https://images.example/720-second.jpg' to be 'https://images.example/720-first.jpg' // Object.is equality.
- `C2 preserves one Ozon photo and all positions on Новые with first photo present=false` — зелёный. На временной порче: expected 'https://images.example/720-second.jpg' to be 'https://images.example/720-product.jpg' // Object.is equality.
- `C2 preserves one Ozon photo and all positions on Отменённые with first photo present=true` — зелёный. На временной порче: expected 'https://images.example/720-second.jpg' to be 'https://images.example/720-first.jpg' // Object.is equality.
- `C2 preserves one Ozon photo and all positions on Отменённые with first photo present=false` — зелёный. На временной порче: expected 'https://images.example/720-second.jpg' to be 'https://images.example/720-product.jpg' // Object.is equality.
- `C2 applies whole-order sizing to multi-position Ozon rather than the first position` — красный. the old independent thumbnail size must not constrain the row photo: expected [ '52px', '52px', '', '' ] to not include '52px'.
- `C3 retains cover scaling and stable sizing rules for a square source on refresh` — зелёный. На временной порче: expected 'fill' to be 'cover' // Object.is equality.
- `C3 retains cover scaling and stable sizing rules for a portrait source on refresh` — зелёный. На временной порче: expected 'fill' to be 'cover' // Object.is equality.
- `C3 retains cover scaling and stable sizing rules for a landscape source on refresh` — зелёный. На временной порче: expected 'fill' to be 'cover' // Object.is equality.
- `C3 applies a square row-relative area consistently to different image sources` — красный. the old independent thumbnail size must not constrain the row photo: expected [ '52px', '52px', '', '' ] to not include '52px'.
- `C4 restores a missing photo source undefined without replacing the area or hiding actions` — зелёный. На временной порче: expected null to be truthy.
- `C4 restores a missing photo source null without replacing the area or hiding actions` — зелёный. На временной порче: expected null to be truthy.
- `C4 restores a missing photo source  without replacing the area or hiding actions` — зелёный. На временной порче: expected null to be truthy.
- `C4 recovers from a failed image probe with the same sizing area after a source refresh` — зелёный. На временной порче: expected null to be truthy.
- `C5 keeps B after late A loading and gates new sources with viewport entry on reopening` — зелёный. На временной порче: expected [ <Anonymous Class>{ …(5) }, …(1) ] to have a length of +0 but got 2.
- `C5 ignores a stale image failure after the source changes on the same order` — зелёный. На временной порче: expected undefined to be 'https://images.example/720-second.jpg' // Object.is equality.
- `C7 preserves the ordinary shared photo defaults and hover/focus preview events outside FBS` — зелёный. На временной порче: expected '45px' to be '44px' // Object.is equality.
- `C7 keeps the supply table and sends only reads during photo preview and refresh` — зелёный. На временной порче: expected false to be true // Object.is equality.

## Ограничения и передача ведущему

Противоречий в обновлённых автоматических проверках не найдено. Геометрия,
фактическое смещение, отсутствие перекрытий и реальная высота фото остаются
ручными проверками ведущего. CSS и контролируемые входы jsdom не выданы за
воспроизведение/исправление экранной причины.

Продуктовые файлы совпадают с HEAD байт в байт. Закоммиченные контракты
WMS-716/717/719 и общая фикстура совпадают с HEAD. Новые изменения пока находятся
только в worktree; сохранение в Git выполняет ведущий. CI, ревью, приёмка,
браузер и деплой в этом этапе не выполнялись.

Адресный запуск:

```sh
cd frontend
npx vitest run --configLoader runner src/screens/v2/FfFbsOrdersScreen.wms718.dom.test.tsx src/screens/v2/FfFbsOrdersScreen.wms720.dom.test.tsx --maxWorkers=1 --minWorkers=1
```
