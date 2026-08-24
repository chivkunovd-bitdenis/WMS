# Разбор срыва `volna-9`: где пайплайн расширял задачи, ломал границы и сжигал время

Дата: 24 августа 2026 года

Область: `night/volna-9`, `night/volna-9-recovery` и связанная карточка каталога коробов

Статус документа: фактический разбор по сохранённым артефактам, Git-веткам, ревью, макетам и browser evidence

## Короткий вывод

Проблема была не в одном плохом агенте и не в одном неудачном макете. Сломалась вся цепочка защиты границ задачи.

Узкие требования попадали в пайплайн уже расширенными, аналитик дополнял их конкретными решениями, критик требований замечал лишнее, но не мог остановить карточку, Product был обязан «решить сам», UX проектировал по этим решениям самостоятельный HTML-макет, splitter превращал его в множество мелких атомов, а содержательное ревью приходило только после большой реализации. Когда ревью наконец находило лишнее, пайплайн не собирал один связный пакет ремонта, а снова дробил находки и запускал новые круги разработки.

Итогом стали одновременно четыре типа ущерба:

1. **Продуктовый:** в существующие FBS-экраны, печать, сканирование и складские сценарии попадали элементы и поведение, которых владелец не просил.
2. **Технический:** соседние действия меняли семантику, включая массовую печать и Честный знак.
3. **Процессный:** десятки модельных вызовов и повторов не давали сохранённого готового результата.
4. **Операционный:** статус пайплайна не отражал реальное состояние веток, стендов, browser evidence и Git-коммитов.

Самый наглядный пример — карточка `06-picking-list-order`. Вместо одной общей сортировки существующего листа и существующей ленты первая реализация изменила **23 продуктовых файла** и дала diff **+2165 / −603 строк**. Она затронула общий FBS preview, `Печать всего`, строковые QR, формирование Честного знака и формат физической ленты. Первое содержательное ревью пришло уже после этого и нашло семь серьёзных нарушений.

[Открыть полный Git-сравнительный diff ошибочной реализации 06](https://github.com/chivkunovd-bitdenis/WMS/compare/d62f9afbef496916e0def30ba1c498ac31605a05...d634f43cd4d7134d1b5058362de49555a026bbe0). В него вошли не только профильные backend-сервисы, но и `FbsPrintPreviewDialog`, `FfFbsPickList`, весь `FfFbsSupplyWorkspace`, `fbsApi`, реестр экранов и семь файлов общего `ui-kit`, включая новый `ModalFrame` и showcase. Это и есть измеримый ответ на вопрос, насколько далеко карточка вышла за точечную сортировку.

## Как открыть макеты в полный размер

Сохранённые HTML-макеты лежат в worktree карточек. Если локальный сервер на порту `8877` не запущен, его можно поднять read-only командой:

```bash
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees
python3 -m http.server 8877
```

После этого ссылки вида `http://127.0.0.1:8877/.../MOCKUP.html` откроют макет в браузере полностью. У каждой ссылки ниже также указан локальный исходник, чтобы артефакт можно было найти без сервера.

## Карта волны и фактические проблемы

| Карточка | Что требовалось по смыслу | Что пошло не так | Чем закончилось |
| --- | --- | --- | --- |
| `01-wb-marking` | Получать и сохранять реальные ответы WB по маркировке | Первичная волна дошла до ролей, но не до живого браузера и Git-финиша; позже потребовалась отдельная backend-only сборка и отдельный stand-test | Узкая backend-реализация была восстановлена отдельно |
| `02-verdikt-screen` | Показать оператору короткий реальный статус WB перед передачей | Небольшая плашка обросла отдельным контрактом и browser-процессом; clicker падал на устаревших локаторах; позже независимое ревью нашло риск разрешения сдачи при несовпадении локального и подтверждённого WB-кода | Доведено отдельной узкой веткой и повторным browser evidence |
| `03-no-distribution-mode` | Существующий чекбокс должен снимать backend-блокировку, пока товар не разложен | Маршрут типа `баг` пропустил UX и breaker; последующий UX начал добавлять тексты, шапку и состояния; splitter пытался удалить существующую строку; reviewer нашёл шесть backend/frontend/test-регрессий | Пришлось пересобирать контракт и делать ограниченный ремонт |
| `04-warehouse-switch` | Автопривязать внешние WB/FBS-склады к единственному физическому складу и скрыть технические склады | Product и UX спроектировали общий складской контекст, переключатели, межскладской подбор, preflight, сканы склада/ячейки, парные движения и изменения множества экранов | Ошибочные решения и макеты архивированы; реализация сведена к backend-only |
| `05-prod-slow` | Найти и устранить реальную причину тормозов | Сначала проектировали polling, пагинацию и фоновые процессы без измерения фактического узкого места; отсутствие browser evidence splitter превратил в шесть dev-атомов | Реальная причина позже оказалась во фронтовой перерисовке сотен строк; исправлялась отдельным хотфиксом |
| `06-picking-list-order` | Один и тот же порядок существующего листа подбора и существующей полной ленты | Появились номера, диапазоны, служебная WMS-этикетка, новый preview и изменения соседних действий FBS/ЧЗ | Старую ветку пришлось архивировать и начинать с чистой базы |
| `07-reporting` | Отчётность для ФФ и селлера | Первый экран получился аналитическим дашбордом с графиком, сравнением и KPI, хотя складскому руководителю нужен простой табличный ответ | Позже график и сравнения удалены, экран упрощён |
| `08-storage` | Хранение, габариты, тариф и начисление | Экран был перегружен, колонки обрезались, тариф нельзя было задать при части состояний, месяц отображался по-английски; финансовые overflow-пути могли дать 500 | Понадобились несколько независимых ревью и отдельное упрощение S-11 |
| `09-billing` | Цифровой учёт работ и счета | Помимо визуальных проблем обнаружились развилка миграций, глобальная уникальность номера счёта между tenant, переполнение INTEGER, 500 в складской операции, пропуск проблемной операции из счёта, смена timezone всего Celery | Потребовалась отдельная чистая интеграционная ветка и несколько повторных ревью |

## 1. Ошибка началась до разработки: источник уже мог содержать лишнее

В карточке `06-picking-list-order` сохранённый `ISTOCHNIK.md` уже говорил не только об одинаковом порядке, но и о «сквозной нумерации позиций». Это важно: часть расширения появилась ещё до аналитика. Пайплайн воспринимал подготовленный источник как авторитетнее последующего живого смысла задачи.

Далее аналитик превратил общую фразу в конкретный интерфейс и печатный контракт:

- новая колонка `№`;
- диапазоны `1–5`, `6–8` в сгруппированном листе;
- номер на физической ленте;
- отдельная служебная WMS-этикетка;
- новый режим печати из листа;
- конкретная ширина колонки и место номера.

Критик требований это заметил. В `SVERKA.md` прямо записано, что диапазон, плашка номера, размер и место печати не опираются на слова владельца. Но критик не вернул карточку на сужение источника. Он передал конфликт дальше в Product.

Артефакты:

- [Исходник карточки 06](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/night/volna-9-recovery/cards/06-picking-list-order/ISTOCHNIK.md)
- [Разбор аналитика с диапазонами и новой этикеткой](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/night/volna-9-recovery/cards/06-picking-list-order/RAZBOR.md)
- [Сверка, которая нашла расширение, но не остановила его](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/night/volna-9-recovery/cards/06-picking-list-order/SVERKA.md)

### Почему аналитик решил, что ему можно придумывать

Фактический prompt аналитика одновременно содержал две несовместимые установки:

- «не выдумываешь»;
- если ответа нет, «решаешь сам», помечаешь допущением, владельцу вопросов не задаёшь, карточка едет дальше.

То есть запрет на выдумывание был декларацией, а маршрут фактически поощрял превращать неизвестное в допущение. Для существующего рабочего экрана это особенно опасно: любое «разумное» допущение почти неизбежно становится новой колонкой, кнопкой или состоянием.

Фактический prompt той волны: [analyst.md](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/.claude/agents/analyst.md).

## 2. Product был настроен не охранять scope, а закрывать все вопросы самостоятельно

Prompt Product содержал прямые правила «владельцу вопросов не задают» и «ты не согласовываешь, ты решаешь». В результате Product не отделял технический способ реализации от новых продуктовых решений.

В карточке 06 Product самостоятельно выбрал:

- порядок листа как главный;
- диапазоны номеров вместо буквального совпадения одной позиции;
- обязательную служебную этикетку даже там, где она раньше была выключена;
- изменение полной печати вне модалки листа;
- постоянную нумерацию полного набора независимо от фильтра.

В карточке 04 Product самостоятельно выбрал:

- сессионный складской контекст;
- работу одной FBS-поставки с несколькими физическими складами;
- межскладской подбор;
- скан склада и ячейки;
- связанную пару складских движений и undo;
- генерацию складских баркодов;
- новые правила видимости для ФФ и селлера.

Это не «техническая реализация». Это новые процессы склада и новые пользовательские обязанности.

Артефакты:

- [Ошибочные решения Product по карточке 06](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/night/volna-9-recovery/cards/06-picking-list-order/RESHENIYA.md)
- [Ошибочные решения Product по складам, сохранённые до owner correction](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/SUPERSEDED-OWNER-SCOPE/2026-08-23-product-scope-expansion/RESHENIYA.md)
- [Фактический prompt Product](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/.claude/agents/product.md)

Правильное правило здесь должно быть другим: Product может выбрать минимальный технический вариант в пределах уже названного поведения, но не может добавлять экран, контроль, колонку, документ, роль оператора или новый необратимый эффект.

## 3. UX рисовал самостоятельный мир вместо наложения на реальный экран

Старая версия prompt UX говорила пользоваться UI-kit, но runner проверял в основном наличие секций в `CONTRACT.md`. Он не требовал доказать, что `MOCKUP.html` собран из реальных React-компонентов, и не сравнивал макет с фактическим экраном пиксель-в-пиксель.

Поэтому возникли две характерные ошибки:

1. UX объявлял недостающими новые примитивы (`ModalFrame`, `ChoiceFilter`, `CheckCell`, расширение `PrintAction`), после чего screen-dev получал формальное разрешение создать их.
2. Макет показывал не точечную дельту на существующем экране, а автономную страницу, где можно было незаметно заменить таблицу, шапку, колонки и действия.

### Галерея ошибочных макетов

#### 06 — переделанный лист и физическая лента

- [Открыть ошибочный макет 06 в полный размер](http://127.0.0.1:8877/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/night/volna-9-recovery/cards/06-picking-list-order/SUPERSEDED-OWNER-SCOPE/MOCKUP.html)
- [Локальный исходник MOCKUP.html](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/night/volna-9-recovery/cards/06-picking-list-order/SUPERSEDED-OWNER-SCOPE/MOCKUP.html)
- [Контракт, по которому этот макет был создан](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/night/volna-9-recovery/cards/06-picking-list-order/SUPERSEDED-OWNER-SCOPE/CONTRACT.md)

Макет добавлял колонку номеров, диапазоны, служебную этикетку после WB-стикера, новый print-flow и новые состояния общей модалки. Всё это было отменено свежим `OWNER-SCOPE.md`.

#### 04 — общий редизайн склада поверх маленькой backend-задачи

- [Открыть первый ошибочный складской макет в полный размер](http://127.0.0.1:8877/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/SUPERSEDED-OWNER-SCOPE/MOCKUP.html)
- [Первый исходник MOCKUP.html](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/SUPERSEDED-OWNER-SCOPE/MOCKUP.html)
- [Открыть повторный, всё ещё расширенный макет](http://127.0.0.1:8877/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/SUPERSEDED-OWNER-SCOPE/2026-08-23-ux-scope-expansion/MOCKUP.html)
- [Повторный исходник MOCKUP.html](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/SUPERSEDED-OWNER-SCOPE/2026-08-23-ux-scope-expansion/MOCKUP.html)
- [Контракт первого широкого редизайна](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/SUPERSEDED-OWNER-SCOPE/CONTRACT.md)

Первый контракт распространял один `WarehouseContextSwitch` на S-01, S-03, S-04, S-14, S-22, S-24, S-25 и селлерские S-26/S-28/S-29. Он добавлял сканы склада и ячейки, preflight создания FBS-поставки и межскладской подбор. После первого возврата повторный UX формально сузился до S-03, но всё ещё оставил warehouse switch, preflight и scanner flow. Понадобилось отдельное owner-ограничение «backend-only, S-03 не менять вообще».

#### Каталог коробов — автономный список вместо сохранения каталога товаров

- [Открыть первоначальный макет каталога коробов](http://127.0.0.1:8877/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/MOCKUP.html)
- [Локальный исходник первоначального макета](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/MOCKUP.html)
- [Исправленный экран: отдельная вкладка, существующий каталог сохранён](/Users/deniscivkunov/Projects/WMS/.worktrees/catalog-box-tabs-stage-20260823/docs/evidence/catalog-box-tabs-source-20260823/catalog-boxes-tab.png)
- [Stage-ready экран коробов](/Users/deniscivkunov/Projects/WMS/.worktrees/catalog-box-tabs-stage-20260823/docs/evidence/catalog-box-tabs-stage-20260823/catalog-boxes-stage-ready.png)

Здесь пользователь отдельно зафиксировал правильную модель: вкладка `Товары` не меняется, рядом появляется `Короба и грузоместа`, а таблица коробов использует знакомые каталожные колонки. Первоначальное решение визуально воспринималось как подмена всего каталога.

## 4. Splitter дробил работу раньше, чем была доказана правильность контракта

В старом prompt splitter не было жёсткого бюджета атомов и правила «один finding-пакет по слою». Он мог умножить ошибочный контракт на множество задач.

По карточке 06 сначала появились шесть атомов, затем после ревью — ещё восемь ремонтных. В billing наблюдалась цепочка вида `20 → review → 7 → review → 4`; по журналу и сохранённой истории это означало десятки отдельных developer-вызовов вместо одного полного review и одного связного ремонта.

Проблема не только в стоимости. Мелкая нарезка разрушала контекст:

- backend-атом не видел, что frontend уже изменил соседнюю кнопку;
- frontend-атом закреплял ошибочную серверную семантику зелёным тестом;
- следующий reviewer заново собирал систему по кускам;
- сохранение checkpoint могло захватить чужие стадийные файлы.

В карточке 05 шесть «находок» ux-judge были только отсутствующим browser evidence, но splitter превратил их в шесть dev-атомов. В карточке 07 stale repair-plan заново просил создать три UI-kit-компонента, которые уже существовали в принятых коммитах.

## 5. Ревью приходило слишком поздно и проверяло не тот срез

Ревьюер карточки 06 правильно нашёл критические дефекты, но только после реализации всего широкого контракта. Среди них:

1. Нажатие печати из листа могло начать выпуск/привязку Честного знака, хотя задача была про порядок документов.
2. Существующая кнопка `Печать всего` перестала открывать прежний конструктор и обходила выбранный макет, partial-mode и подтверждение большой партии.
3. Неполную ленту можно было физически напечатать с неверными счётчиками.
4. Сервер проверял только набор ID, но не тот порядок, который видел оператор.
5. Общий preview добавлял лишнюю WMS-этикетку даже строковым QR и соседним видам печати.
6. Обязательный WB PNG уменьшался и мог печататься на другом формате.
7. Гонка запросов могла показать лист одной поставки и печатать для другой.

Полный документ: [REVIEW.md карточки 06](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/night/volna-9-recovery/cards/06-picking-list-order/SUPERSEDED-OWNER-SCOPE/REVIEW.md).

Это хороший пример того, почему «ревью потом всё поймает» не работает как защита scope. Оно действительно поймало, но после тысяч строк, множества тестов и нескольких часов разработки.

Отдельная проблема состояла в том, что reviewer и ui-critic получали разные источники правды. Старый ui-critic сравнивал экран с каноном, но не был обязан сравнить его с `CONTRACT.md` и `MOCKUP.html`. Старый ux-judge проверял тесты, скриншот и канон, но также не обязан был доказать отсутствие новых элементов относительно исходного экрана.

## 6. Маршрутизация стадий была логически неверной

Первая волна `20260821-r04` закончилась `0 done / 9 deferred`. Это не был случайный сбой модели. В runner были неправильные цепочки:

- тип `баг` шёл к dev без обязательного UX-контракта для видимой правки;
- у `фича` и `домен` ui-critic стоял до разработки и проверял старый экран;
- фраза «фича, но это домен» не распознавалась детерминированно;
- фраза `Нарушений не найдено` в секции `Находки` трактовалась как отрицательный вердикт;
- отрицательный ui-вердикт удалял артефакты и возвращал карточку в слишком раннюю стадию.

Полный ранний handoff: [HANDOFF-PIPELINE-R04-FAILURE-RU.md](/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/docs/process/HANDOFF-PIPELINE-R04-FAILURE-RU.md).

В recovery-версии добавились новые дефекты:

- `clicker` мог записать «стенд не поднялся», но runner всё равно запускал `ux-judge`;
- отсутствие screenshots классифицировалось как code finding и уходило в dev;
- resume прыгал в dev/clicker по парковочному маркеру, не пересверяя обязательный префикс стадий;
- точечный запуск `--карточки 04` валидировал зависимости других карточек и блокировал 04;
- старые номера атомов в `DEPENDENCIES.json` продолжали блокировать уже перепланированную карточку;
- `git add -A` при checkpoint захватывал удаление и перезапись чужих стадийных артефактов;
- статус `обзор` продолжал показывать агента в работе после исчезновения реального orchestrator;
- ни одна карточка долго не имела `BRANCH-SHA.txt`, upstream и честного терминального состояния.

Сохранённый общий журнал хорошо показывает симптом: десятки повторных запусков, постоянные `сделано 0`, межкарточные зависимости на уже несуществующие атомы, повторные SIGINT и ожидание product-acceptor, который не мог стартовать.

- [JOURNAL.md recovery-волны](/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/night/volna-9-recovery/JOURNAL.md)
- [Утренний отчёт с нулём принятых карточек](/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/night/volna-9-recovery/OTCHET.md)

## 7. Browser gate существовал на бумаге, но не был рабочим состоянием машины

На разных карточках повторялись одни и те же инфраструктурные ситуации:

- Docker Desktop не отвечал или находился в `stopping`;
- build занимал 25 минут и завершался timeout;
- диск заполнялся до `No space left on device`;
- sanitized snapshot отсутствовал;
- stand поднимался без нужной миграции;
- скрытый child-agent не имел доступного browser runtime;
- Playwright падал из-за устаревшего локатора, а не из-за продукта;
- clicker не создавал `CLICKS.md`, но pipeline уже переходил дальше.

Пайплайн не различал:

- `BLOCKED_INFRA` — сломан стенд;
- `EVIDENCE_ONLY` — код принят, нужны только клики и screenshots;
- `CODE_FINDING` — доказан дефект реализации;
- `PRODUCT_AMBIGUITY` — нужен Product;
- `GIT_BLOCKED` — код сделан, но checkpoint не сохранён.

Из-за этого отсутствие картинки превращалось в новый код, а недоступный Docker — в повторный вызов дорогой модели.

## 8. Статус процесса выдавался за результат

В течение волны неоднократно сообщалось, что «агент работает», «атом 1 из 4», «ревью идёт» или «карточка движется». Для владельца это выглядело как разработка, хотя фактически:

- первая волна закончилась нулём карточных коммитов;
- recovery долго не имела upstream у восьми из девяти веток;
- часть code diff лежала dirty после `index.lock`;
- `обзор` отставал от журналов и процессов;
- reviewer/UI verdict мог относиться к старому diff;
- browser evidence отсутствовал;
- product-acceptor не запускался до полного завершения очереди.

Правильный статус должен был отвечать всего на пять вопросов:

1. Какой продуктовый результат уже реализован?
2. В каком commit SHA он сохранён?
3. Есть ли независимый review verdict именно этого SHA?
4. Есть ли живой browser evidence именно этого SHA?
5. Куда этот SHA реально выкачен?

Количество запущенных ролей и созданных артефактов не является шестым доказательством.

## 9. Пайплайн не измерял проблему до проектирования решения

Карточка `05-prod-slow` особенно показательна. До измерения фактического пути обсуждались тяжёлый WB polling, фоновая подготовка, пагинация и server memory. Позже независимый разбор реального продового скана показал другое:

- серверный путь занимал около 116 мс;
- база — единицы миллисекунд;
- после одного скана React перерисовывал сотни строк и тысячи MUI-компонентов;
- пользовательские 15–16 секунд уходили в браузер.

То есть правильная последовательность должна была быть `замер → локализация bottleneck → минимальный фикс → повторный замер`. Пайплайн сделал `архитектура → продукт → UX → атомы`, не доказав, где теряется время.

## 10. Новые модули тоже страдали от визуального переусложнения

Здесь важно отличать незаконное изменение существующего FBS от допустимого создания новых разделов. Отчётность, хранение и billing действительно требовали новых экранов. Ошибка была не в самом факте нового UI, а в том, что первые варианты ориентировались на аналитический продукт, а не на кладовщика и руководителя склада.

### Отчётность

Первый контракт включал график движения, сравнение периодов, дополнительную линию, легенду и KPI сравнения. После продуктовой коррекции остались простые факты `остаток / приход / расход / нетто`, фильтры, группировка, CSV и одна таблица.

- [Первоначальный MOCKUP reporting](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/MOCKUP.html)
- [Финальный простой экран 1280 px](/Users/deniscivkunov/Projects/WMS/.worktrees/reporting-stage-finish-20260823/docs/evidence/reporting-stage-20260823/ff-reports-simple-1280.png)
- [Финальный простой экран 1440 px](/Users/deniscivkunov/Projects/WMS/.worktrees/reporting-stage-finish-20260823/docs/evidence/reporting-stage-20260823/ff-reports-simple-1440.png)

### Хранение

Первый экран перегружал строку seller/status/liters/days дополнительными подписями, обрезал SKU и артикул, терял правые колонки в диалоге и печати и показывал месяц в системной английской локали. Позже:

- заголовок детализации стал человеческим;
- склад вынесен в спокойную подпись;
- SKU и артикул объединены в одну товарную ячейку;
- тарифное действие оставлено одно;
- месяц переведён на русский DatePicker;
- горизонтальный overflow локализован внутри таблицы.

- [Первоначальный MOCKUP storage](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/MOCKUP.html)
- [Финальная основная таблица storage](/Users/deniscivkunov/Projects/WMS/.worktrees/codex-storage-stage-20260823/docs/evidence/storage-stage-20260823/storage-long-sku.png)
- [Финальная детализация storage](/Users/deniscivkunov/Projects/WMS/.worktrees/codex-storage-stage-20260823/docs/evidence/storage-stage-20260823/storage-history.png)
- [Финальная печатная форма storage](/Users/deniscivkunov/Projects/WMS/.worktrees/codex-storage-stage-20260823/docs/evidence/storage-stage-20260823/storage-print-preview.png)

### Billing

Первый billing прошёл много зелёных тестов, но независимое ревью последовательно нашло:

- две головы Alembic при интеграции с reporting;
- глобальную уникальность номера счёта при tenant-scoped нумерации;
- переполнение PostgreSQL INTEGER до записи;
- 500, блокирующий завершение складской операции при ошибке начисления;
- строковые Decimal в API при числовом frontend-контракте;
- глобальный `minWidth:0`, затрагивавший все существующие FF/FBS-экраны;
- глобальную смену Celery timezone, сдвигавшую старую WB-задачу;
- выпуск счёта без операции, по которой billing overflow сохранил issue;
- английский месяц в русском интерфейсе.

Это показывает ещё одну процессную проблему: модуль считался почти готовым несколько раз, хотя каждое следующее независимое ревью находило новый P1 на границе другого слоя.

- [Первоначальный MOCKUP billing](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/MOCKUP.html)
- [Финальная таблица начислений](/Users/deniscivkunov/Projects/WMS/.worktrees/billing-stage-finish-20260823/docs/evidence/20260823-billing-stage-finish/billing-charges-right.png)
- [Финальная форма счёта](/Users/deniscivkunov/Projects/WMS/.worktrees/billing-stage-finish-20260823/docs/evidence/20260823-billing-stage-finish/billing-invoice.png)

## 11. Что пришлось сделать вручную, чтобы вернуть задачи в нормальный scope

### Для карточки 06

1. Сохранить старую ветку как архив, чтобы не потерять работу и доказательства.
2. Создать `OWNER-SCOPE.md`, который явно запретил новые колонки, номера, WMS-этикетки, preview, ЧЗ и изменения соседних кнопок.
3. Перезапустить Product и UX на чистой базе.
4. Допустить ровно один связный backend-пакет сортировки.
5. Отдельно проверить, что видимый FBS UI не изменился.

- [Финальный owner scope 06](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/OWNER-SCOPE.md)
- [Финальное browser evidence порядка ленты](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/docs/evidence/06-picking-list-order/full-tape-preview-order.png)
- Финальный опубликованный SHA recovery-ветки: `443638a1fb14f14be727eab5f4debb7a0a6a5230`.

### Для карточки 04

1. Дважды остановить runner до разработки, потому что Product/UX снова расширяли scope.
2. Архивировать ошибочные `RESHENIYA.md`, `CONTRACT.md` и `MOCKUP.html` recoverably.
3. Зафиксировать backend-only owner scope.
4. Реализовать только автопривязку при одном физическом складе и сохранить существующие явные привязки.
5. Отдельно доказать в браузере, что S-03 не изменился, а технический `FBS WB *` скрыт.

- [Финальный owner scope 04](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/OWNER-SCOPE.md)
- [S-03 без новых элементов](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/docs/evidence/04-warehouse-switch/fbs-screen-scope-regression.png)
- [Технический склад скрыт](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/docs/evidence/04-warehouse-switch/warehouses-technical-hidden.png)
- Финальный опубликованный SHA: `88bed22a78642820812a22f4e25b3397451d6d68`.

## 12. Какие правила обязаны быть машинными, а не текстом prompt

### Scope до разработки

- Для существующего экрана сохраняется baseline screenshot и список видимых элементов.
- Каждый новый экран, элемент, колонка, действие и новый side effect обязан иметь дословную ссылку на требование владельца.
- Если такой ссылки нет, контракт не проходит в splitter.
- Формулировка «это полезно» или «так делают другие» не является разрешением.

### Product

- Product охраняет существующий процесс и выбирает минимальное решение.
- Product не может сам добавлять экран, control, документ, роль оператора, необратимое действие или новый вид печати.
- Неопределённость в техническом способе Product может закрыть сам; неопределённость в пользовательском поведении возвращается владельцу либо фиксируется как явно не реализуемая часть.

### UX

- `MOCKUP.html` для существующего экрана строится как дельта поверх реального baseline, а не как автономная страница.
- Список видимых элементов до/после сравнивается машиной.
- UI-kit-компонент можно объявить недостающим только если владелец действительно потребовал новый элемент.

### Splitter и repair

- Сначала полный review всего diff, потом один связный repair-пакет.
- Не больше трёх атомов на круг, сгруппированных по слоям и общим файлам.
- Отсутствие browser evidence не создаёт dev-атом.
- После двух отрицательных repair-раундов карточка останавливается, а не начинает третий цикл автоматически.

### Reviewer

- Проверяет не только корректность кода, но и `git diff` против owner baseline.
- Любой новый файл или видимый элемент вне allowlist — finding до анализа красоты реализации.
- Старый принятый код не становится автоматически допустимым scope после resume.

### Browser и состояние

- `clicker BLOCKED` останавливает цепочку до judge.
- Stand/snapshot/Docker/Git имеют отдельные технические состояния и не занимают модельный слот.
- Resume всегда пересверяет обязательный префикс стадий и hash артефактов.
- Checkpoint индексирует только allowlist текущего атома, а не `git add -A`.
- Финал возможен только при clean branch, commit SHA, push, reviewer/UI clean, screenshots, invariants и живом judge.

## 13. Главный организационный вывод

Полностью отдавать маршрутизацию свободному «умному оркестратору» опасно: он снова начнёт рационализировать расширение scope. Полностью жёсткая последовательность тоже не сработала: она запускала ненужные роли, неправильно обрабатывала blockers и зацикливала rework.

Нужна гибридная схема:

- маленький per-card supervisor выбирает **следующую допустимую стадию**, но не решает продукт;
- machine gates защищают baseline, allowlist, Git, browser evidence и лимит rework;
- Product/UX/dev/reviewer остаются отдельными ролями;
- для маленькой backend-задачи путь короткий;
- новый экран проходит полный контракт и browser-приёмку;
- один supervisor отвечает за то, что карточка не стоит, но не имеет права расширить её смысл.

Основной эталон для любого такого supervisor: **задача должна закончиться минимальным diff, который невозможно ещё уменьшить без потери прямо требуемого поведения**.

## Приложение A. Фактические prompts той волны

Показывать текущие prompts из `pipeline-etalon` как prompts того запуска нельзя: после инцидента они менялись. Фактические версии сохранены внутри архивной lane карточки 06:

- [analyst](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/.claude/agents/analyst.md)
- [requirement-critic](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/.claude/agents/requirement-critic.md)
- [product](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/.claude/agents/product.md)
- [ux-architect](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/.claude/agents/ux-architect.md)
- [tester](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/.claude/agents/tester.md)
- [breaker](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/.claude/agents/breaker.md)
- [splitter](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/.claude/agents/splitter.md)
- [screen-dev](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/.claude/agents/screen-dev.md)
- [backend-dev](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/.claude/agents/backend-dev.md)
- [reviewer](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/.claude/agents/reviewer.md)
- [ui-critic](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/.claude/agents/ui-critic.md)
- [clicker](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/.claude/agents/clicker.md)
- [ux-judge](/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/archive-lane-3-06-picking-list-order-pre-owner-scope/.claude/agents/ux-judge.md)

Runtime prompt дополнительно собирался из `scripts/night.py`, текущих артефактов карточки, diff и retry-находок. Полный байт-в-байт transcript prompt не сохранялся, поэтому честно восстановить его только из role-файла невозможно. В документе выше выводы сделаны по тем инструкциям и артефактам, которые действительно сохранились в lane.

## Приложение B. Восстановимость

Ключевые ветки и SHA:

- ранний процессный handoff: `f8c646f2545ef9c9dcc6c8848352828e33149c4c`;
- архив ошибочной карточки 06: branch `archive/night/volna-9-recovery/lane-3/06-picking-list-order-pre-owner-scope-20260823`, SHA `d634f43cd4d7134d1b5058362de49555a026bbe0`;
- финальная recovery 06: `443638a1fb14f14be727eab5f4debb7a0a6a5230`;
- финальная recovery 04: `88bed22a78642820812a22f4e25b3397451d6d68`;
- упрощённая reporting-ветка: `codex/reporting-stage-finish-20260823`, SHA `99f3b95b723fc27921f73e7d59bd657e798de66f`;
- storage: `codex/storage-stage-20260823`, SHA `78b1e9d0eeb8d08a564850a4ef4e54807a6b7dcb`;
- billing: `codex/billing-stage-finish-20260823`, SHA `5f382cccfc11e0ae23dc44e229e466d39d7435a2`;
- исправленная вкладка коробов: `codex/catalog-box-tabs-stage-20260823`, SHA `dab770c4f8ea85f7d47a3106cf0a3115695d4b41`.

Эти SHA фиксируют разные этапы и не означают, что каждый из них был выкачен на prod. Для утверждения о deploy всегда требуется отдельная проверка deployed SHA и живого экрана.
