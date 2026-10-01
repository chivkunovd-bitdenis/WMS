# WMS-625 — независимое ревью реализации

## Статус

**Приёмочный PASS не выдан.** Это накопительный отчёт независимого Astra high ревьюера. Первый ограниченный проход проверил frontend commit `26852c080eae266a763a919ffec7fbf74aa1f048`, diff от `0fdd308b`. Runtime на момент прохода ещё разрабатывался. Известное исполнителю завершение исходной попытки через явно связанную дочернюю допечатку не оценивалось как окончательный дефект до предъявления финального коммита.

Правила основного checkout, постановка, библиотеки owner/failure cases прочитаны ранее. Повторная проверка неизменённого кода без новых оснований не выполняется. Точное исходное ревью релиза .4 находится в `WMS-625-review-astra.md`; этот файл его не заменяет.

## Frontend 26852c08: подтверждённые дефекты

### F1, P1 — GET 404 разрешает вторую копию после уже сохранённой receipt

`frontend/src/utils/durableDirectQr.ts:115–123` после GET404 отправляет `/print`, если серверный claim ещё не started. Он не учитывает уже сохранённый `attempt.result.receipt` и не хранит до POST отдельную долговечную границу «отправка начата».

Воспроизведение на точном транспилированном исходнике: первая попытка GET404 → POST accepted/queue-1 → receipt сохраняется. Далее моделируется неуспешный `markStarted` до server commit. Вторая попытка видит GET404 (журнал native отсутствует/другая установка) и снова делает POST; счётчик отправок становится 2, `queue-1` перезаписывается на `queue-2`. Backend ещё не started, поэтому `requireExisting=true` этот сценарий не защищает. При потере самого POST-ответа проблема шире: в браузере вообще нет признака, что внешняя отправка могла начаться.

Ожидание: известная receipt или неизвестный исход уже начатой отправки вместе с отсутствием native-задания не разрешают новую копию автоматически. Различить новую первую отправку и повтор ранее отправлявшегося задания. Совместимость с legacy helper, у которого любой GET404, требует явного распознавания возможностей/идентичности helper; простой GET404 не доказывает безопасный повтор.

Передано ведущему для frontend-разработчика. **Статус: исправление ещё не проверено.**

### F2, P1 — указатель selection всё ещё теряется между вкладками

`frontend/src/screens/v2/fbsScanAutoPrint.ts:123–152` и функции `updateFbsPendingProductScan`/`completeFbsPendingProductScan` сохраняют целиком массив через неатомарный read/modify/write localStorage. Новая строгая обработка исключений устраняет quota failure, но не lost update между вкладками одного tenant/user/supply. Атомарная проверка IndexedDB в `durableDirectQr.ts:44–50` относится только к PNG после server selection, не к этому первому указателю.

Исполнен детерминированный schedule на точном исходнике: A получает snapshot пустого массива; B читает пустой массив и сохраняет key-B; A сохраняет key-A поверх него. Обе claim-функции возвращают допустимые ключи для последующих server select, но сохранён только key-A. После потери ответа B и reload прежняя reservation B не восстанавливается через ключ. Такое же whole-array обновление/удаление может стереть соседнюю незавершённую попытку.

Ожидание: атомарно сохранить каждую selection до server request и не терять её при создании/завершении в соседней вкладке. Решение не должно превращать две отдельные вещи в один отсканированный экземпляр либо автоматически захватывать чужую операцию. Проверить создание двух попыток и complete одной при существующей другой. Детерминированная модель interleaving подтверждает алгоритмический дефект; два настоящих browser renderer процесса этим проходом не запускались.

Передано ведущему для frontend-разработчика. **Статус: исправление ещё не проверено.**

### F3, P2 — JSON с невалидной receipt принимается как успех

`durableDirectQr.ts:103` делает TypeScript cast без runtime-проверки, `133` проверяет лишь truthiness. Ответ HTTP200 `{"status":"accepted","receipt":{"error":"not a receipt"}}` приводит к успешному завершению dispatch, после чего caller может поставить started и pack. Исполняемый тест на точном commit подтвердил это.

Ожидание: валидировать тип и непустое значение receipt, форму объекта и обязательные поля современного протокола. Legacy-ответ допускается по распознанному контракту, а не как произвольный truthy JSON. Неизвестный/повреждённый ответ не завершает заказ. Это проверка устойчивости границы протокола; реальный runtime не обвиняется в выдаче такого ответа без наблюдения.

Передано ведущему для frontend-разработчика. **Статус: исправление ещё не проверено.**

## Что подтверждено чтением реализации

PNG, размеры и контекст сохраняются до native-вызова. IndexedDB-запись ожидает завершения транзакции; compare-and-write одного ключа находится в одной readwrite-транзакции. Возврат принятого результата также сохраняется до server started/pack. Подмена сохранённого изображения/размеров не проходит. tenant/user/supply/order/scan/barcode проверяются при восстановлении. Обычный QR/ЧЗ получил только необязательный callback reconcileStarted, включённый для последовательной массовой сборки. Это положительные свойства кода, а не общий PASS.

Контроллер удерживает выбранный заказ после ошибки печати, повторно использует прежний scan UUID и переданные размеры, не продолжает pack на canceled/aborted/held/stopped/unknown. При server started новый callback запрашивает native, вместо прежнего безусловного пропуска печати. Проверка явного linked-child результата отложена до финального frontend/native контракта.

## Воспроизводимые проверки

Все три проверки выполнялись вне production, без системного принтера. Node загружал TypeScript из существующих зависимостей основного checkout, а код — через `git show 26852c08:<path>`, поэтому параллельные незакоммиченные изменения исполнителя не влияли на результат.

```javascript
// Запустить через node из task worktree.
const cp=require('child_process'), vm=require('vm');
const ts=require('/Users/deniscivkunov/Projects/WMS/frontend/node_modules/typescript');
function load(path, extra={}) {
  const src=cp.execFileSync('git',['show',`26852c08:${path}`],{encoding:'utf8'}), exp={};
  vm.runInNewContext(ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,
    {exports:exp,require:()=>({}),AbortSignal,fetch,Date,Set,Error,JSON,atob,...extra});
  return exp;
}
(async()=>{
  const qr=load('frontend/src/utils/durableDirectQr.ts');
  const rows=new Map(), store={get:async k=>structuredClone(rows.get(k)),put:async a=>rows.set(a.input.idempotencyKey,structuredClone(a))};
  const input={idempotencyKey:'scan-a',imageDataUrl:'png',widthMm:58,heightMm:40,context:{tenantId:'t',userId:'u',supplyId:'s',orderId:'o',scanId:'scan-a',barcode:'460',marketplace:'wildberries',wbOrderId:1}};
  let posts=0;
  const io={fetch:async(_url,init)=>init.method==='GET'?new Response('{}',{status:404}):new Response(JSON.stringify({idempotencyKey:'scan-a',status:'accepted',receipt:`queue-${++posts}`})),wait:async()=>{},polls:0};
  await qr.dispatchDurableQr(input,store,io);
  console.log('F1 receipt first:',rows.get('scan-a').result.receipt);
  // markStarted fails before server commit; native next GET has no retained job.
  await qr.dispatchDurableQr(input,store,io);
  console.log('F1 POST count:',posts,'receipt second:',rows.get('scan-a').result.receipt);
  await qr.dispatchDurableQr(input,store,{...io,fetch:async()=>new Response(JSON.stringify({status:'accepted',receipt:{error:'not a receipt'}}))});
  console.log('F3 invalid object receipt accepted');
  let raw=null,interleave=null;
  const storage={getItem:()=>{const snapshot=raw,f=interleave;interleave=null;f?.();return snapshot},setItem:(_key,value)=>{raw=value},removeItem:()=>{raw=null}};
  const scans=load('frontend/src/screens/v2/fbsScanAutoPrint.ts',{window:{localStorage:storage}}), prefs={printQr:true,printChz:false,reprintChz:false};
  let b;
  interleave=()=>{b=scans.claimFbsPendingProductScan('token','s:sequential-packing','B',prefs,()=> 'key-B')};
  const a=scans.claimFbsPendingProductScan('token','s:sequential-packing','A',prefs,()=> 'key-A');
  console.log('F2 in-flight keys:',a.idempotencyKey,b.idempotencyKey,'saved:',raw);
})().catch(console.error);
```

Фактический вывод: F1 `queue-1`, затем POST count 2/`queue-2`; F3 функция успешно завершилась с объектом вместо receipt; F2 возвращены key-A и key-B, сохранён массив только с A.

## Браузер и ограничения начального прохода

Предъявлен исполнительский отчёт `WMS-625-browser-evidence.md` и fixture `http://127.0.0.1:16255/tests/browser/wms625-durable-qr.html`, исполняющая actual controller/IndexedDB с явно подменёнными WMS/native API. Ревьюер прочитал fixture, но независимо не подтвердил её live-прохождение: CUA сообщил `Browser is not available: chrome`, inventory `browsers: []`, попытка получить native Chrome завершилась `timeoutReached`. Программные воспроизведения выше выполнены; они не выдаются за browser/physical evidence.

Runtime/combined review, проверка исправлений F1–F3, explicit linked-child recovery, итоговый diff и статус сохранности/публикации будут добавлены после предъявления финальных коммитов. До этого итоговый вердикт остаётся **не завершено, PASS не выдан**.

## Native core: независимый проход 044fb731

Проверены Swift runtime, CUPS observer C, Python/Windows runtime, history.html, сборщик и CI workflow на `044fb73108bf1fd443fe00f5320ac833efe0715d` (основа `1c48f8d4`). Команда `python3 -m unittest test_wms_print_direct test_macos_native -v` из `tools/print-agent` независимо завершилась **32 tests / OK**, 30.204s: 29 Python + 3 компилируемых native. После этого весь неизменённый набор повторно не запускался.

Исполненный native набор включает 350 заданий/700 конкурентных POST с одинаковыми ключами, чтение исходной PNG после restart, kill дочернего процесса до/после внешней границы, ошибки четырёх этапов записи, восстановление receipt по единственному CUPS job title, защиту от неоднозначного совпадения и повторов. CUPS тест использует подменённые функции библиотеки; системный принтер не вызывается. Python tests используют fake adapter/queue. Реальный Windows kernel, GDI-драйвер, Windows package и физическая этикетка этим прогоном не проверены.

Положительные свойства подтверждены чтением и этими тестами: Swift пишет PNG/отдельную JSON запись через fsync/F_FULLFSYNC/rename, меняет память после завершения записи, удерживает межпроцессный flock на журнале; Python сохраняет BLOB+metadata транзакцией SQLite с synchronous FULL и использует платформенный lock. Worker отправки отделён от HTTP. Receipt теряется безопасно: submitting после crash становится unknown, без автоматического повторного submit. CUPS receipt сверяется вместе с уникальным title, а бумажный статус всегда unconfirmed. Сигнал TERM ограничен grace period и затем KILL, pipe читается параллельно. Старые журналы .3/.4 сохраняются и не выдаются за восстановленные PNG. Отдельный PNG без JSON защищён от повторной постановки после restart.

Дополнительно независимо проверена подозреваемая граница Swift legacy HTTP: fake submit вернул receipt, четвёртая запись (результат) упала; in-memory состояние unknown+receipt. Повтор legacy POST через настоящий handle/socketpair ответил **409**, поскольку storageError правильно остановил повтор. Этот сценарий **не объявлен дефектом**.

### N1, P2 — Windows классифицирует часть ошибок до StartDoc как неизвестную отправку

На `044fb731` `DefaultWindowsAdapter.submit_default:170–182` создаёт image/DC и проверяет страницу до StartDoc. Но `native_operation:1009–1012` считает доказанно неотправленными только ValueError; обычный OSError/pywintypes.error при OpenPrinter/CreateDC идёт в общий неизвестный исход. Родительский `process:709–714` затем сохраняет unknown и запрещает безопасный retry.

Исполненный тест использовал настоящий native_operation и настоящий метод adapter, подменив только `_create_sized_printer_dc` исключением `OSError('OpenPrinter failed before StartDoc')`. Фактический результат `{'error': 'OpenPrinter failed before StartDoc'}`, без beforeSubmit. Реальный StartDoc не вызывался.

Ожидание: классифицировать по пересечённой границе, а не по имени класса исключения. Все достоверные ошибки подготовки до StartDoc — beforeSubmit; начиная с вызова StartDoc — unknown, если нет подтверждённой receipt. Ошибка очистки DC после завершённой отправки не должна разрешать повтор. Передано ведущему. **Исправление ещё не проверено.**

### N2, P1 — повтор потерянного child может создать ещё одну копию

Во время прохода исполнитель самостоятельно обнаружил потерю связи parent→child при повреждении child metadata и начал сохранять `reprintIntentKeys` в parent до создания child. Этот незакоммиченный follow-up проверен отдельно; он не приписывается исходному `044fb731` как реализованный контракт.

В новой версии parent GET корректно выдаёт unknown placeholder при отсутствующем child, а parent retry заблокирован. Однако повтор того же `/reprint` с тем же child key проходил в enqueue и создавал child заново. Временная SQLite DB/fake queue воспроизвели: parent failed_before_submit → explicit child accepted → удаление child row → parent GET unknown placeholder → тот же reprint request → новая внешняя отправка. Фактический счётчик `['child', 'child']`.

Ожидание: сохранённый intent при отсутствующем/повреждённом child не разрешает автоматическое пересоздание того же ключа. Нельзя различить аварийное завершение до создания child и потерю его уже отправленной записи. Нужен сохраняемый unknown/error; новое осознанное решение о копии имеет новый ключ и явное подтверждение риска. Передано ведущему с воспроизводимым результатом. **Исправление ещё не проверено.**

Для нового parent intent также передан риск stale observer: Swift updatedAt точен только до секунды, прежний reconcile сравнивал только время+статус и мог перезаписать intent старым снимком. Разработчик изменяет сравнение на весь StoredJob. Это замечание к текущему follow-up до фиксации окончательного commit, а не повторный дефект уже проверенной неизменённой версии.

### Объединённая миграция: проверить на финальном frontend

Native старые записи .3/.4 возвращает как `legacy:true`, `context:{}`, без изображения и размеров. Frontend `24c3cbf5` считал пустой context несовпадением заказа и отвергал такой ответ. Разработчику передана необходимость явного безопасного legacy контракта: не выдумывать отсутствующие tenant/order/размеры и не выдавать неизвестную запись за новое задание. Окончательный вывод откладывается до новой версии frontend, которая сейчас исправляет F1–F3.

**Итог этого прохода:** существенные прежние разрывы исправлены и положительные тесты воспроизведены. Native PASS и общий PASS пока не выданы: N1/N2, финальный контракт linked-child, изменённый frontend и объединённая миграция требуют адресной повторной проверки.
