# Разбор · Короба и грузоместа в каталоге

## Дословно

> Короче, мы когда создаём приёмку, мы в ней создаём кораба, и в эти кораба распределяем товар. Соответственно, нам нужно в разделе каталог с товарами сделать внизу подраздел, раскрывающийся, типа кораба грузоместа, и в нём отображать конкретно те товары, закреплённые за теми корабами, которые у нас есть. То есть приняли короб, в нём количество товаров, либо там грузоместо, да, и они все там висят, они как бы раскрываются. Плюс должна быть возможность сканировать просто на экране каталога короб и чтобы открывалось... нет, чтобы тебя, короче, в явном виде перебрасывало на карточку того короба, который... Ну, ты когда задаёшь короб, можно напечатать штрихкод. Когда ты его сканируешь просто в каталоге, тебя перебрасывает именно на раздел этого короба, да, и он раскрывается, видно там, какие в нём товары лежат. Строки с товарами наши стандартные, как во всей системе, там, ну, фотка, шика, вот эта вся история. Вот задача какая? То есть они раскладывают по корабам товар, да, и он у них лежит на складе. И потом им нужно пойти, отсканить короб реальный и быстро понять, что в нём лежит у них. То есть что это вообще за коробка на складе стоит.

## Что сейчас

Сначала проверил, не сделана ли задача в другом месте. Поиск шёл по всем веткам через
`git log --all` с формулировками «Короба и грузоместа», `catalog box lookup`, `INB-`,
`internal_barcode`, по содержимому изменений через `git log -S`, по именам веток и по
текущему незакоммиченному состоянию. Нашлись два коммита этой волны: `276e1ba3` только
сохраняет краткую постановку, а `7545fa9b` привязывает её к экрану `S-16` и создаёт
`/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/ISTOCHNIK.md`.
Оба коммита есть в локальной и удалённой ветке
`process/pipeline-on-etalon-20260821`, но не являются предками `origin/etalon`; реализации
в них нет. В `origin/etalon` и в текущем коде раздела коробов, поиска короба из каталога и
перехода к нему нет. Значит, сделана только постановка задачи, на бой функция не влита.

Нужный экран — `S-16`, маршрут `/app/ff/products`, компонент
`FfProductsCatalogScreen`: это прямо записано в
[`/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/frontend/screens.registry.json`](</Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/frontend/screens.registry.json:1312>).
Маршрут открывается фулфилмент-администратору либо сотруднику с правом на ячейки или
остатки; проверка маршрута находится в
[`/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/frontend/src/App.tsx`](</Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/frontend/src/App.tsx:2750>)
и
[`/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/frontend/src/App.tsx`](</Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/frontend/src/App.tsx:2949>).
Обнаруженные ограничения экрана занесены шестью полями в
[`/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/docs/blockers/S-16.md`](</Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/docs/blockers/S-16.md>).

Сейчас каталог загружает только товары через `GET /products/ff-catalog` и отдельно
сводный остаток через `GET /operations/inventory-balances/summary`; коробов в состоянии
экрана нет. Это видно в
[`/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/frontend/src/screens/v2/FfProductsCatalogScreen.tsx`](</Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/frontend/src/screens/v2/FfProductsCatalogScreen.tsx:225>).
Единственное поле поиска фильтрует уже загруженные строки товаров по названию, артикулу,
SKU и товарным штрихкодам
([`/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/frontend/src/screens/v2/FfProductsCatalogScreen.tsx`](</Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/frontend/src/screens/v2/FfProductsCatalogScreen.tsx:133>)).
Поэтому скан `INB-…` воспринимается как обычный текстовый запрос к товарам и обычно даёт
«Ничего не найдено»; раскрыть или прокрутить короб экрану нечего. После таблицы товаров
сразу идут диалоги и боковая панель резервов, отдельного нижнего подраздела нет
([`/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/frontend/src/screens/v2/FfProductsCatalogScreen.tsx`](</Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/frontend/src/screens/v2/FfProductsCatalogScreen.tsx:1032>)).

Нужные данные коробов уже существуют, поэтому новую параллельную сущность создавать не
нужно. `InboundIntakeBox` хранит тенант, приёмку, номер, внутренний штрихкод `INB-…`, время
печати этикетки и строки состава; каждая строка связывает короб с товаром и хранит принятое
и уже разложенное количество. Модель находится в
[`/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/backend/app/models/inbound_intake.py`](</Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/backend/app/models/inbound_intake.py:162>)
и
[`/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/backend/app/models/inbound_intake.py`](</Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/backend/app/models/inbound_intake.py:215>).
Штрихкод уникален внутри тенанта, что позволяет делать точный адресный поиск без просмотра
чужих данных. Текущее содержимое нельзя брать из поля `quantity` как исторический итог
приёмки: сервис считает остаток в коробе как `quantity - posted_qty`
([`/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/backend/app/services/inbound_intake_service.py`](</Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/backend/app/services/inbound_intake_service.py:997>)).
При раскладке товар переносится из короба в ячейку, а `posted_qty` увеличивается
([`/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/backend/app/services/inbound_intake_service.py`](</Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/backend/app/services/inbound_intake_service.py:1107>)).
Иначе каталог покажет в физическом коробе товар, который уже вынули и разложили по
ячейкам.

Готового безопасного API для этого сценария нет. Имеющийся поиск короба по штрихкоду
требует заранее знать `request_id`, доступен роли приёмки и не является чтением: он ставит
`intake_opened_at` и делает commit
([`/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/backend/app/services/inbound_intake_box_service.py`](</Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/backend/app/services/inbound_intake_box_service.py:344>),
[`/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/backend/app/api/inbound_intake.py`](</Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/backend/app/api/inbound_intake.py:1097>)).
Его повторное использование в каталоге незаметно изменяло бы приёмку и отрезало бы
сотрудников, у которых есть право на каталог, но нет права `reception`. Сервер каталога,
наоборот, разрешает чтение администратору и сотрудникам с правом `cells` или `inventory`
([`/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/backend/app/api/deps.py`](</Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/backend/app/api/deps.py:222>)).

Стандартная компактная строка состава уже есть на экране приёмки: фотография, название,
SKU, товарный ШК и количество
([`/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/frontend/src/screens/ff/FfInboundRequestView.tsx`](</Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/frontend/src/screens/ff/FfInboundRequestView.tsx:261>)).
Там же администратор уже видит короба с содержимым и может печатать их этикетки
([`/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/frontend/src/screens/ff/FfInboundRequestView.tsx`](</Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/frontend/src/screens/ff/FfInboundRequestView.tsx:2618>)).
Это подтверждает, что источник данных и визуальный паттерн существуют; отсутствует именно
тенантный read-only срез для каталога и поведение перехода по скану.

У сущности `InboundIntakeCargoPlace` сейчас другая семантика: модель прямо описывает её как
физическое место без обязательной детализации товаров и хранит только приёмку, номер,
штрихкод и факт печати
([`/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/backend/app/models/inbound_intake.py`](</Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/backend/app/models/inbound_intake.py:120>)).
В API грузоместа также нет строк состава
([`/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/backend/app/api/inbound_intake.py`](</Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/backend/app/api/inbound_intake.py:114>)).
Поэтому показать «конкретные товары грузоместа» из текущих данных невозможно; для коробов
такая связь есть.

Живой экран тоже проверял: локальные порты `5173`, `4173`, `3000`, `8000` и `8010` не
отвечают, а публичный staging URL из сохранённых evidence-файлов не разрешается по DNS из
этой рабочей среды. Авторизованную сессию, секреты и кабинеты учётных данных не использовал,
боевой `194.87.96.144` не трогал. Поэтому живые данные и вкладку после входа подтвердить
не удалось; вывод о текущем поведении дополнительно сверён с кодом `origin/etalon`, где
раздела и поиска также нет. Карта волны
`/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-etalon/night/catalog-box-lookup-20260823/MAP.md`,
на которую ссылается запуск, в рабочей копии отсутствует; это разбор не остановило.

## Что должно быть

На существующем экране `S-16` под таблицей товаров появляется свёрнутый по умолчанию
раздел «Короба и грузоместа». Он является только просмотром: создание, наполнение,
закрытие, раскладка и печать коробов остаются в приёмке и в эту карточку не входят.

В разделе оператор видит реальные приёмочные короба своего тенанта, которые ещё имеют
фактическое содержимое. Короб раскрывается и показывает текущий остаток по товарам, а не
исторически принятое количество. Строка товара следует уже существующему системному
паттерну: фотография, название, SKU/артикул, товарный штрихкод и количество. Для нового
пустого короба виден спокойный пустой текст; полностью разложенный исторический короб не
должен выглядеть как короб, в котором товар всё ещё лежит.

На этом же экране сканируется внутренний штрихкод с напечатанной этикетки. По завершении
скана система делает точный read-only поиск в границах тенанта, раскрывает общий раздел и
нужный короб, затем прокручивает его в видимую область. Скан не открывает короб для приёмки,
не меняет статус, время открытия, количество или остаток. Если код неизвестен, относится к
другому тенанту либо объект уже недоступен как текущий физический короб, чужие данные не
показываются, а оператор получает короткое понятное сообщение.

Признак результата: сотрудник с доступом к `S-16` подходит к физическому коробу, сканирует
его этикетку и без ручного поиска сразу видит на экране именно этот раскрытый короб и тот
остаток товаров, который по данным системы ещё находится внутри. Пользовательский сценарий
должен отдельно подтвердить обычное раскрытие, успешный скан, неизвестный код, чужой код,
пустое состояние и отсутствие изменений в приёмке после просмотра.

## Тип

ТИП: фича

## Экраны

`S-16` — `/app/ff/products`, существующий экран каталога товаров фулфилмента.

## Вопросы и допущения

1. **Грузоместо и состав.** В речи владельца «короб» и «грузоместо» местами звучат как
   взаимозаменяемые слова, но в данных это разные сущности: только короб имеет строки
   товаров. Вопрос для роли `product`: оставить грузоместо доступным для поиска и показать
   его без состава либо расширить домен отдельной связью «грузоместо — товары».
   **Допущение для продолжения новой функции:** текущая карточка показывает состав только
   у коробов; грузоместа перечисляются и находятся по штрихкоду, но честно сообщают, что
   по ним состав в системе не ведётся. Новую связь данных без решения product не выдумывать.

2. **Что считать коробом, который физически ещё есть с товаром.** Запись короба остаётся в
   базе и после полной раскладки, но её `remaining_qty` становится нулём. Вопрос для роли
   `product`: нужен ли отдельный архив в этом же разделе. **Допущение:** основной список
   показывает короба с ненулевым текущим остатком и новые пустые короба незавершённой
   приёмки; полностью разложенные короба в основной список не входят, а точный скан даёт
   понятный ответ «товар из короба уже разложен» без показа старого состава как текущего.

3. **Несколько складов.** Каталог `S-16` сейчас тенантный и не имеет фильтра склада.
   Вопрос для роли `product`: нужен ли склад в подписи или фильтре списка. **Допущение:**
   точный скан ищет по всему текущему тенанту, поскольку штрихкод уникален в его границах;
   список остаётся в том же тенантном масштабе, а различение складов product решает без
   расширения карточки на редизайн каталога.

4. **Роли.** **Допущение:** просмотр раздела и скан доступны всем ролям, которые уже могут
   открыть `S-16` (`fulfillment_admin` и `fulfillment_staff` с `cells` или `inventory`),
   а не только администратору или сотруднику приёмки. Это read-only действие и не должно
   требовать права на изменение приёмки.
