# WMS-663: F4, передача продолжающего разработчика

06.10.2026. Отдельная продолжающая сессия Sol 6.1 по прямому поручению
владельца; навыки, CLI-дочерние исполнители и subagents не запускались.
Прочитаны AGENTS.md, R1–R15/C1–C19 и ревью `wms663-astra-112d421.md`.
Выполнен fetch origin/etalon; правила совпадают с эталоном
`0f1460b023700a99f17b504d6af3934a02bc68cc`. Это продолжение имеющейся
реализации, её база не заменялась. Ветка `codex/wms662-663-priority`.

## Опубликованный RED до кода

Продукт не изменялся до публикации независимого нового контракта
`e832a0f57f5b57d25607a3865b8b91d81d1b4543`.
HEAD и удалённая ветка сверены через git rev-parse / git ls-remote;
SHA-256 рабочего теста совпал с файлом из коммита. Прочитана передача
`wms663-f4-testwriter-handoff.md`. Собственный повтор нового файла на
неизменённом продукте дал **3 failed / 12 passed**, exit 1, 7.13s:
скрытый отказ, ложное принятие validation_in_process и неизвестного
document check_status. Ожидания всех четырёх frozen backend-наборов
сохранены без изменений; итоговый git diff этих файлов к RED-коммиту пуст.

## Семантика исправления

`document_data.state=accepted` по-прежнему означает завершение конкретного
сохранённого действия. Оно не становится новым незавершённым writer из-за
чтения изменённых данных кабинета. choices остаются историей: не заменяются
снимком кабинета и не накладываются на него в представлении либо следующем SET.

Классификатор больше не возвращается рано для accepted: он разбирает свежие
ошибки всех документов и сохраняет их в существующие errors/document_errors.
Сопоставление незавершённого действия со своими targets и правила его
завершения сохранены. Принятую историческую операцию классификатор не открывает заново.

`document_view.state` и состояние экземпляра для завершённого действия
вычисляются по текущему last_status: validation_in_process → checking;
явный отказ с document errors → rejected; неизвестный непустой document
check_status, неизвестный общий статус или пустой ship_available → unknown.
Свежий ship_available без document errors/неизвестной проверки показывает
accepted для возвращённых текущих сведений. Отсутствующий в свежем ответе
экземпляр не получает accepted только из старого snapshot.
Ошибки возвращаются через реальные view.errors и exemplar.errors.
Сбой чтения или несовпадение posting не выдаются за принятие текущих данных;
последний снимок сохраняется, историческая завершённость не отменяется.

Возможность новой записи определяется существующим состоянием операции
и штатным запретом update_not_available. Поэтому текущие checking/unknown
после уже завершённой операции могут иметь editable=true. В существующем
компоненте изменено только вычисление disabled: явное серверное editable=true
разрешает действие; editable=false блокирует. Ответы без editable сохраняют
прежнюю защиту pending. Опрос статуса продолжается при текущих checking/unknown.
Разметка, тема, компоненты, поля и подписи не менялись. Новых хранимых полей,
таблиц, статусов или пользовательских сущностей нет.

Новый claim заменяет текущие targets, увеличивает версию и снова использует
строгое подтверждение собственного действия. Активный writer/unknown outcome,
проверка expected_version, checkpoint запоздавшего GET и восстановление
потерянного SET не изменены. update_not_available не обходится.

## Проверки окончательного кода

Из backend:

```sh
env -u WMS_TEST_DATABASE_URL -u WMS_TEST_DATA_DIR \
  /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest \
  tests/test_wms663_accepted_current_status.py \
  tests/test_wms663_accepted_read_regressions.py \
  tests/test_wms663_astra_regressions.py \
  tests/test_wms663_customs_documents_contract.py \
  tests/test_ozon_fbs_process_contract.py tests/test_fbs_ozon_lane.py \
  tests/test_ozon_box_assembly.py tests/test_ozon_fbs_openapi_models.py \
  -n 1 -q --tb=short
```

**146 passed, 1 skipped, 12 warnings in 21.80s**, exit 0: 15 новых F4,
8 accepted GET, 22 предыдущих и 101 соседний тест. Skip — существующая
PostgreSQL-гонка; PostgreSQL не использовалась. Реальная SQLite-гонка позднего
GET с новой записью входит в эти восемь проверок. Новый контракт отдельно
проверяет следующую запись B/КИЗ и stale version после каждого из трёх
результатов кабинета; здоровый кабинет проверен прежним набором.

Полные `ruff check .` и `mypy .` — PASS, mypy: 552 файла.
`git diff --check` — PASS. Для фронта `npx tsc --noEmit -p tsconfig.app.json`
и `npm run build` — PASS; build сообщил обычное предупреждение о крупных chunks.

Разовая DOM-проба после реализации — **1 PASS / 7 строк матрицы**, 3.18s.
Она монтирует настоящий OzonExemplarDocuments, получает fake GET и проверяет
текущий номер, видимый отказ в обеих коллекциях, отсутствие ложного «Принято»,
состояния checking/unknown, доступность ввода/галки/сохранения при editable=true
и запрет ввода при editable=false для checking/unknown/preparing. Во всех
четырёх разрешённых случаях меняется номер и проверяется фактический PUT с
новым явным вводом и expected_version. Это не полный C16 и не браузерная геометрия.

Точное тело разовой пробы сохранено в
[wms663-f4-developer-dom-probe.txt](wms663-f4-developer-dom-probe.txt).
Для повторения копировать его в
`frontend/src/screens/v2/OzonExemplarDocuments.f4.developer-probe.test.tsx`,
запустить из frontend:

```sh
npx vitest run src/screens/v2/OzonExemplarDocuments.f4.developer-probe.test.tsx \
  --maxWorkers 1 --minWorkers 1
```

После проверки созданный для пробы файл удалён из frontend; его источник
сохранён в Git как evidence. Он не объявляется frozen тестовым контрактом
или постоянной охраной. Первое обращение к пробе из неверного относительного
пути дало no test files, после исправления пути указанная проба прошла.

Дополнительная разовая проверка настоящих сервисов на отдельной SQLite:
accepted A → CURRENT/CURRENT-RNPT → ship_available / update_available /
update_not_available / validation_in_process / future_status. Выходные
state/editable: accepted/true, editable/true, editable/false, checking/true,
unknown/true. Далее пустой ship_available, чужой posting и fake_read_failure
дают unknown, свежие ранее прочитанные значения и исторический choices
сохраняются. Успешное последующее чтение снова даёт accepted без ошибок.
На всём цикле ровно один SET, ни одного повторного внешнего изменения.
Это разовая проба, не новая постоянная защита.

## Граница результата и дальнейшая проверка

Изменены только сервис, необходимая проверка disabled в существующем UI
и эта передача с источником DOM-пробы. Req, backlog и correction ledger
принадлежат другим исполнителям и не изменялись. Чужие untracked-файлы
не захвачены. Все вызовы провайдера — FakeMarketplaceTransport с фиктивными
данными, тестовая БД изолирована снятием переопределений.

Исправление передаётся на независимое Astra high ревью опубликованного SHA.
Приёмка аналитика и полный CI этим прогоном не заменяются. C16–C19/G2/G3
предыдущей приёмки не объявлены закрытыми. Браузер/геометрия стенда, реальный
Ozon, production, Telegram, подписи, управление секретами, merge и deploy
не выполнялись. Это сохранённое исправление разработчика, не разрешение выпуска.
