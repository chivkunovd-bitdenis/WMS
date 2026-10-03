# WMS-625 — независимое Astra high ревью выпущенной .4

Дата: 2026-10-01. Это ревью исходного релиза и границ всей цепочки; исправленная реализация ещё не предъявлена. Ночное происшествие по этим тестам не диагностировано.

## Объект и правила

Прочитаны `/Users/deniscivkunov/Projects/WMS/AGENTS.md`, целиком `owner-cases.md` и `failure-cases.md` из `docs/reviews/2026-09-11-analyst-draft/` основного checkout. В worktree этих библиотек нет. Прочитана постановка `docs/requirements/WMS-625.md`. Ревьюер не менял продуктовый код, production, реальные очереди и настройки принтера.

Исследован точный исходник `9a33b651c309796707053e1056c7f80dff7194d5`, релиз `wms-print-direct-v2026.09.30.4`. Подтверждение GitHub-релиза и digest Mac arm64 ZIP `962a755b685d839adb545710878218efb7372d0c6cc655aa945fe0c18c4a60ef` предоставил ведущий. Сам ревьюер читал исходники через `git show 9a33b651:<path>`; бинарник из ZIP в этих воспроизведениях не использован. База worktree `7f73efe045cbb7067d3122b165964a8a83d306aa` содержит Swift до изменения размера .4. Все номера строк ниже относятся к `9a33b651`, а не будущему исправлению.

По уточнению владельца: около 17 пропусков, число «350» не обозначает количество. Программа должна работать с системным принтером по умолчанию без привязки к конкретной модели. По переданным ведущим данным соседнего разбора, отметки WMS «печать запущена», КИЗ и packed у отдельных заказов существуют; они не доказывают выход бумаги. Журнал рабочего Mac ревьюеру недоступен.

## Подтверждённые находки

### P1. Неуспешная попытка остаётся запретом повторять без восстановимого задания

`tools/print-agent/wms_print_direct_macos.swift:195–200` сохраняет `hash + nil` до `submit`. `submitToDefaultPrinter:117–125` только после этого создаёт временную директорию, пишет PNG и запускает `lp`. Даже достоверный отказ создания файла до первого системного вызова оставляет запись «уже передавалось»; `187–192` одинаково обрабатывает этот случай и потерю ответа после фактического принятия. Python/Windows повторяет конструкцию в `wms_print_direct.py:133–150`; создание DC/раскодирование PNG в `67–77` также может упасть до `StartDoc`, уже после сохранения NULL.

В обоих исполненных воспроизведениях submit-заглушка бросила исключение до имитации очереди. После пересоздания Printer в том же каталоге повтор не дошёл до исправной заглушки. Сохранились только hash и отсутствующая receipt. Нельзя восстановить изображение, время, выбранную очередь, ошибку или принадлежность заказа. У Swift временный PNG удаляется `119` даже при ошибке; постоянное хранилище содержит только поля `26–29`. У Python постоянная таблица в `117` также содержит только id/hash/receipt.

Исправление: до внешнего действия сохранять точные данные и контекст с отдельным состоянием «ещё не передано». Проверки и подготовку, заведомо не пересекающие границу системной печати, отличать от неопределённой отправки. Не удалять восстанавливаемую этикетку после неуспеха. При неопределённости сначала сверять состояние очереди по сохранённой идентичности; отсутствие задания в очищенной истории не доказывает отсутствие печати. Тесты: ошибка постоянного/временного диска, driver/DC failure до StartDoc, ошибка после принятия, kill процесса перед/после внешней отправки, restart и восстановление без нового заказа/КИЗ.

### P1. Потеря браузерного ключа оставляет серверную selection и выбирает соседний заказ

`frontend/src/screens/v2/fbsScanAutoPrint.ts:104–115` молча поглощает ошибки localStorage. `123–145` выдаёт новый ключ при следующем вызове, если сохранение не получилось. Исполняемый тест с `setItem -> QuotaExceededError` получил `request-1`, затем `request-2` для одного штрихкода. Даже в одной открытой странице нет памяти последнего selection-request внутри этой функции.

Сервер фиксирует выбор до получения стикера: `backend/app/api/fbs_supplies.py:2432–2446`. `backend/app/services/fbs_scan_auto_print_service.py:250–268` восстанавливает выбор только по digest прежнего ключа, а любое другое событие выбора исключает заказ из кандидатов независимо от результата печати. Получаемый сценарий: selection A сохранена → ответ потерян или стикер не получен → ключ не сохранился/потерян → повторный скан получает B, а A остаётся зарезервированным без восстанавливаемого результата печати в текущем пути. Аналогичная граница существует после удаления данных браузера либо на другом рабочем месте. Это не доказательство причины ночных пропусков.

Исправление должно охватывать браузер и backend: узнаваемая незавершённая selection с исходными scan/order/key, доступная после reload и с другого допустимого рабочего места; браузерная ошибка сохранения не должна молча превращаться в новую вещь. При этом нельзя автоматически брать любую чужую незавершённую selection: одновременные операторы и два одинаковых физических товара требуют сохранения владельца операции и явного контекста восстановления. Тесты: потеря ответа после commit selection, storage error, reload, смена вкладки/оператора, два одновременных товара одного SKU, отказ получения QR.

### P1. Принятие очередью завершает прикладной путь без истории результата очереди

`frontend/src/utils/printDirectQr.ts:16–17` проверяет receipt и отбрасывает её. `fbsSequentialPacking.ts:223–233` затем записывает print-started, а `57–65` упаковывает и удаляет pending. `fbsKizAutoReprint.ts:54–69` при повторе started вообще не вызывает локальную программу. Серверный `fbs_scan_auto_print_service.py:839–855` хранит факт started без OS receipt, очереди и наблюдаемого состояния.

Swift после `lp` проверяет только exit status и текст квитанции (`127–135`), Python Windows после EndDoc возвращает `windows-N` (`77–91`). В обоих локальных HTTP API есть health/print, но нет поиска задания, наблюдения состояния или восстановления списка. Health проверяет выбор системного принтера, не исправность устройства. Поэтому hold/offline/filter error/отмена после принятия нигде не доводятся до WMS; повтор старого ключа возвращает старую receipt даже после отмены задания.

Исправление: сохранять и возвращать receipt, queue и наблюдаемые состояния, привязывать их к уже существующему scan/order. Состояние CUPS completed следует показывать как факт очереди, а физическое подтверждение — отдельным фактом с источником; не выдавать принтерный порт или драйверную квитанцию за наблюдение бумаги. В универсальном драйверном режиме достоверное физическое подтверждение может отсутствовать. Операции продолжения и явной допечатки должны сохранять исходную историю, не сбрасывать selection вслепую.

Официальный IPP guide описывает состояния pending/held/processing/completed/canceled/aborted и отдельные причины: [Printer Working Group](https://www.pwg.org/ipp/ippguide.html). Способы CUPS получать задание и его состояние описаны в [CUPS Programming Manual](https://www.cups.org/doc/cupspm.html). Само наличие этих протоколов не доказывает возможности неизвестной модели устройства сообщить физический результат.

### P2. Ошибка первой записи журнала отравляет память Swift-процесса

`wms_print_direct_macos.swift:196–197` меняет `jobs` до неуспешного `persist`, без rollback. При исправлении диска тот же процесс считает ещё не отправленное и даже не сохранённое задание уже переданным. Исполненный тест: файл вместо директории вызывает Cocoa 512/ENOTDIR; директорию восстанавливаем; повтор возвращает «Задание уже передавалось»; счётчик OS submit остаётся 0.

Симметрично `199–200` записывает receipt в память до её сохранения: после ошибки записи повтор может вернуть успешную receipt без новой попытки сохранить её, хотя после restart диск всё ещё содержит nil. Нужна атомарная согласованность памяти и долговечного состояния, а не только атомарная замена файла. Тестировать сбои первой и второй записи, восстановление IO в том же процессе и restart.

### P2. Таймаут HTTP короче отправки, а ограничение процесса не жёсткое

Браузер ждёт 30 секунд (`printDirectQr.ts:11`), Swift может потратить 10 секунд на defaultPrinter (`66`) и 60 на lp (`125`), удерживая общий NSLock (`185–200`). Поэтому нормальная медленная отправка может завершиться после показанной ошибки браузера; отмена fetch не отменяет работу обработчика. Следующий запрос может ждать тот же lock и также потерять свой HTTP-ответ. Это само по себе не теряет сохранённый результат, но без status API и журнала создаёт каскад неопределённых попыток.

`run:49–58` по таймауту делает только terminate и продолжает `waitUntilExit`; SIGTERM-игнорирующий дочерний процесс не обязан завершиться. Исполненный тест `/bin/sh -c "trap '' TERM; sleep 1"` с timeout=0.2s завершился приблизительно через 1.07s. Реальное зависание такого процесса будет держать общую блокировку сколь угодно долго. Также stdout/stderr читаются только после wait: быстрый дочерний вывод 200000 байт заполнил pipe; процесс, который должен сразу закончить работу, был убит по timeout, прочитано лишь 65536 байт.

Исправление: принять и сохранить задание быстро, продолжать отправку отдельно, давать запрос результата с прежним ключом. Процессный runner должен одновременно читать pipe, ограничивать объём вывода и гарантированно завершать дочерний процесс после grace period, сохраняя outcome_unknown при пересечении внешней границы. Тестировать медленную отправку >30s, concurrent reads/POST, ignore-TERM, большой stdout, оборванный HTTP после принятия.

### P2. .4 несовместима с прежним журналом повторов без миграции

В базе/предыдущей версии hash вычислялся по PNG; .4 `180–183` прибавляет строку размеров. `StoredJob` не хранит версию схемы или размера. Загрузка старого словаря проходит, но `188` всегда отвергает повтор старого задания, даже если receipt уже известна. Исполненная проверка старой записи с корректным hash(PNG) и receipt возвращает «Содержимое этого задания изменилось».

Новый релиз должен читать оба формата и не объявлять старую запись новой пустой очередью. Старые записи без PNG не позволяют восстановить неизвестный результат самостоятельно; это должно быть явно отражено и связано с существующим scan. Тестировать legacy запись с receipt и без неё, .4 запись, новый формат, повтор сменившегося размера, миграцию и rollback установки.

## Сборка и границы существующих тестов

`tools/print-agent/build_console.py:16–21` проверяет чистоту исходников пакета и берёт commit HEAD; Mac `32–38` действительно компилирует Swift и подписывает локально, Windows `40–47` собирает Python. `build.json` честно хранит `physical_print_verified: false` (`48–52`). Mac archive self-test (`64–70`) проверяет распаковку, подпись и тестовый вызов. Это полезная проверка пакета, но её fake PNG состоит только из заголовка и submit подменён (`Swift:342–359`), поэтому она не проверяет ни пригодность PNG, ни отказ очереди, ни аварийное восстановление. Python self-test (`wms_print_direct.py:238–240`) только создаёт adapter. CI выполняет эти self-tests, а не fault-injection набор.

HTTP в Swift имеет 15s receive timeout (`303–307`), ограничение тела/заголовков и отправку с подавлением SIGPIPE; потеря ответа не откатывает операцию. Проверка Host/Origin и X-WMS-Print присутствует. Из этого чтения не следует отдельный доказанный HTTP-parser дефект. Один live listener на стандартном порту ограничивает повторный запуск, а глобальная блокировка защищает одинаковые POST внутри процесса; её цена — остановка всех print POST за зависшим submit. Перезапуск с другим каталогом распаковки не меняет Application Support, что правильно сохраняет старый журнал.

Обычное окно использует браузерную печать с другим смыслом started; независимый разбор обычного окна поручен другому агенту. Настоящая бумага, рабочая очередь, выбранный драйвер и ночной журнал этим ревью не проверены.

## Воспроизведение без реального принтера

Команды выполняются из постоянного worktree. Исходник извлекается только из тега. Временные каталоги используются исключительно для изолированных тестовых данных, продуктовый результат там не хранится.

Swift-воспроизведение P1, IO, process runner и миграции:

```python
# Запуск: python3 /путь/к/сохраненному/этому-фрагменту.py
import pathlib, subprocess, tempfile
src = subprocess.check_output(['git','show',
    '9a33b651:tools/print-agent/wms_print_direct_macos.swift'], text=True)
root = pathlib.Path(tempfile.mkdtemp(prefix='wms625-astra-repro-'))
harness = r'''
let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
defer { try? FileManager.default.removeItem(at: dir) }
let body: [String:Any] = ["idempotencyKey":"scan-a", "imageDataUrl":"data:image/png;base64," + pngPrefix.base64EncodedString(), "widthMm":58, "heightMm":40]
var calls = 0
private let a = try Printer(directory: dir, submit: {_,_,_,_ in calls += 1; throw PrintError.message("injected pre-submit failure")}, queue:{"fake"})
do { _ = try a.printJob(body) } catch { print("first:",error) }
private let b = try Printer(directory: dir, submit: {_,_,_,_ in calls += 1; return "fake-1"}, queue:{"fake"})
do { _ = try b.printJob(body) } catch { print("after restart:",error) }
print("submit calls:",calls)
let ioDir=dir.appendingPathComponent("io")
var ioCalls=0
private let c=try Printer(directory:ioDir,submit:{_,_,_,_ in ioCalls += 1; return "fake-2"},queue:{"fake"})
try FileManager.default.removeItem(at:ioDir)
try Data().write(to:ioDir)
do { _ = try c.printJob(body) } catch { print("IO failure:",error) }
try FileManager.default.removeItem(at:ioDir)
try FileManager.default.createDirectory(at:ioDir,withIntermediateDirectories:true)
do { _ = try c.printJob(body) } catch { print("IO repaired:",error) }
print("OS calls after repair:",ioCalls)
let start=Date()
private let slow=try run("/bin/sh",["-c","trap '' TERM; sleep 1"],timeout:0.2)
print("0.2s timeout elapsed:",Date().timeIntervalSince(start),slow.timedOut)
private let noisy=try run("/bin/sh",["-c","head -c 200000 /dev/zero"],timeout:0.2)
print("noisy timedOut:",noisy.timedOut,"bytes:",noisy.output.utf8.count)
let oldDir=dir.appendingPathComponent("old")
try FileManager.default.createDirectory(at:oldDir,withIntermediateDirectories:true)
let oldHash=SHA256.hash(data:pngPrefix).map{String(format:"%02x",$0)}.joined()
try JSONSerialization.data(withJSONObject:["scan-a":["hash":oldHash,"receipt":"fake-42"]]).write(to:oldDir.appendingPathComponent("direct-jobs.json"))
private let old=try Printer(directory:oldDir,submit:{_,_,_,_ in "never"},queue:{"fake"})
do { print(try old.printJob(body)) } catch { print("legacy:",error) }
'''
(root/'repro.swift').write_text(src[:src.rfind('\ndo {\n')] + harness)
subprocess.run(['swiftc',str(root/'repro.swift'),'-o',str(root/'repro')],check=True)
subprocess.run([str(root/'repro')],check=True)
```

Наблюдённые результаты: после restart — «Задание уже передавалось», `submit calls: 1`; после исправления IO — тот же отказ, `OS calls after repair: 0`; timeout 0.2s завершился ~1.07s; большой stdout дал `timedOut: true`, 65536 bytes; legacy receipt — «Содержимое этого задания изменилось».

Python/Windows без win32/принтера, с подменённым submit:

```python
import subprocess,tempfile,pathlib,sys
root=pathlib.Path(tempfile.mkdtemp(prefix='wms625-python-repro-'))
for name in ('wms_print_direct.py','wms_print_runtime.py','wms_print_agent.py'):
    (root/name).write_bytes(subprocess.check_output(['git','show','9a33b651:tools/print-agent/'+name]))
sys.path.insert(0,str(root))
import wms_print_direct as m
body={'idempotencyKey':'scan-a','imageDataUrl':'data:image/png;base64,iVBORw0KGgo=','widthMm':58,'heightMm':40}
calls=[]
def fail(data):
    calls.append('pre-submit failure')
    raise ValueError('injected driver failure BEFORE StartDoc')
for submit in (fail,lambda data:calls.append('submitted') or 'fake-1'):
    try: m.Printer(root/'jobs',submit=submit).print(body)
    except Exception as e: print(e)
print(calls)
```

Наблюдались первый инъецированный отказ, затем «Задание уже передавалось», `calls == ['pre-submit failure']`. Это проверка общей логики Python, не реального Windows DC.

Браузерное хранение, TypeScript из точного релиза:

```javascript
// node; библиотека TypeScript берётся из существующих зависимостей основного checkout.
const cp=require('child_process'), vm=require('vm');
const ts=require('/Users/deniscivkunov/Projects/WMS/frontend/node_modules/typescript');
const src=cp.execFileSync('git',['show','9a33b651:frontend/src/screens/v2/fbsScanAutoPrint.ts'],{encoding:'utf8'});
const out=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const exp={};
vm.runInNewContext(out,{exports:exp,require:()=>({}),atob,window:{localStorage:{getItem:()=>null,setItem:()=>{throw Error('QuotaExceededError')},removeItem:()=>{}}}});
let id=0;
const claim=()=>exp.claimFbsPendingProductScan('test-token','supply','barcode',{printQr:true,printChz:false,reprintChz:false},()=>`request-${++id}`);
console.log(claim().idempotencyKey,claim().idempotencyKey);
```

Фактический вывод: `request-1 request-2`. Следствие для server selection установлено чтением точного кода выше; интеграционный DB-тест этой цепочки в рамках начального ревью не выполнялся.

## Заключение

Система .4 предотвращает некоторые дубли, но не выполняет требование восстановления каждого неуспешного результата: нет исходного задания, наблюдаемой истории очереди и восстановления связи с потерянным браузерным ключом. Исправление только таймаута либо только локального hash-журнала недостаточно. Выводы о причинах конкретных ночных пропусков остаются открытыми до read-only проверки рабочего журнала и сопоставления с WMS. Следующая независимая проверка должна пройти по исправленному diff и каждому сценарию выше; это заключение не является приёмкой будущей реализации.
