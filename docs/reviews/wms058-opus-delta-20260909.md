# WMS-058 — Opus delta review 39c84d09 (superseded by callback correction)

Actual CLI: claude-opus-4-7, effort max; session4a26b04b-0320-44f7-9938-c38793d43bcb.
This read-only result is preserved unchanged below. It is NOT acceptance of39c84d09:
section6 incorrectly assumes the captured parent callback uses the current document.
Independent Astra traced the real stale closure and the author reproduced it in Chrome.
Final patcha8053cf9 removes all three obsolete callbacks; integrated candidateb09b7d9f.
The final tiny patch is being re-reviewed separately. Browser staging GREEN is also
required. Opus did not run tests or browser checks.

---

Изучил всё, что нужно. Пишу вердикт.

---

## Вердикт по фиксу WMS-058 (`39c84d09`) — **чисто, блокеров нет**

Дельта строго ограничена одним компонентом `frontend/src/screens/ff/FfMarketplaceUnloadBoxAddDialog.tsx`, бэк/FBS/дизайн/упаковка не тронуты. Фикс закрывает подтверждённый P1 сохранения источника через окно подтверждения, и делает это тем архитектурным способом, который перечислен в постановке. Ниже — доказательства по каждому обязательному требованию с точными строками.

### 1. Тело запроса неизменно от EXECUTION до retry

`runScan` (line 416-593) на входе снимает снапшот источника через `const selected = sourceRef.current` (line 438) и собирает локальный `scanBody` (line 421-445) с `container_kind/container_id/storage_location_id`, которые были в `sourceRef.current` **на момент старта элемента очереди** — не при постановке в очередь, но и не при retry. Замыкание `postScan` (line 447-456) сериализует `body` в JSON внутри вызова, а retry (line 473) выполняется через `{ ...scanBody, allow_over_plan: true }` — spread делает копию, `scanBody` в замыкании не мутируется, изменяется только один флаг. Никакого повторного чтения `sourceRef.current` перед retry нет, значит подмена источника через новый скан контейнера между 422 и подтверждением технически невозможна.

### 2. Очередь блокируется до решения оператора

Ожидание вставлено внутрь того же `runScan`, а не через возврат с последующим повторным `enqueueScan`, как было раньше. `const confirmed = await new Promise<boolean>((resolve) => { overPlanDecisionRef.current = resolve; setReadyBoxOverPlanOpen(true) })` (line 468-471) удерживает выполнение элемента очереди, а `scanQueueRef.current = job.catch(() => undefined)` в `enqueueScan` (line 598) — это единственный способ добавить следующий элемент. Поскольку `runScan` не возвращается пока promise не резолвится, `scanQueueRef.current.then(...)` следующего элемента ждёт того же обещания. Пришедший на сканер контейнер B при активном подтверждении по P действительно ждёт в очереди, не выполняется, и не может изменить ни `sourceRef`, ни `scanBody` уже отправляемого P.

### 3. Cancel / Esc / close backdrop / X кнопка

Проверил все четыре пути закрытия модалки:
- Кнопка «Отмена» (line 892) → `resolveOverPlan(false)`.
- Клавиша Escape / клик по backdrop через `Dialog.onClose` (line 881) → `resolveOverPlan(false)`.
- Кнопка «Добавить всё» (line 897) → `confirmReadyBoxOverPlan` → `resolveOverPlan(true)` (line 619-621).
- Закрытие внешнего диалога через `closeDialog` (line 337-347) → тоже вызывает `resolveOverPlan(false)` вдобавок к бампу сессии.

Сам `resolveOverPlan` (line 210-215) атомарен: сначала считывает `overPlanDecisionRef.current`, тут же обнуляет ref, закрывает модалку, потом вызывает захваченный `resolve?.(...)`. Двойной вызов безопасен — promise резолвится один раз, второй вызов не имеет захваченного `resolve`. После `confirmed = false` в `runScan` идёт `if (!confirmed || !isCurrent()) return` (line 472) — retry POST не выполняется, элемент очереди отпускает следующего. Ожидающий на очереди новый скан начинает исполняться в чистом виде, без наследования состояния предыдущего.

### 4. Смена request / box / token / readOnly / unmount

Один общий контроллер сессии инвалидирует всё это единообразно. `useEffect(() => {…}, [open, requestId, boxId, readOnly, token])` (line 217-232) на каждый чих deps делает три вещи, которые вместе гарантируют полную отмену старой сессии:

Инкрементирует `scanSessionRef.current` (line 219, 228). Все in-flight `runScan` захватили конкретное значение сессии как аргумент и на каждой границе `await` дёргают `isCurrent()` (line 417), которое сверяет захваченную сессию с текущей — при бампe возвращает false и приводит к раннему `return` без setState. Проверок `isCurrent()` в `runScan` шесть: перед `setError` (line 418), после первого POST (line 458), после чтения 422-refusal (line 464), после promise подтверждения (line 472), после retry POST (line 474), после чтения OK-body (line 496), плюс `errText` (line 569) и `catch` (line 591). Ни один setState/`sourceRef` update внутри `runScan` (`setActiveContainer`, `setActiveLocationId`, `setActiveLocationCode`, `sourceRef.current = …`, `setPickOptions`, `setLastScannedProductId`, `setError`, `setReadyBoxOverPlanOpen`, `onProductScanned`) не выполнится с чужой сессией.

Сбрасывает `scanQueueRef.current = Promise.resolve()` (line 220). Старая цепочка обещаний продолжает исполнение (их нельзя магически отменить), но новые сканы не встают за ней — `enqueueScan` (line 595-600) чейнится на новой пустой очереди. Старые элементы завершаются как no-op из-за session mismatch.

Через cleanup `overPlanDecisionRef.current?.(false)` (line 229) резолвит любое повисшее ожидание. Так модалка не остаётся открытой между сменами request/box/token/readOnly, и `runScan`, застрявший на `await new Promise`, обязательно проснётся с `confirmed=false` и вернётся до `postScan`. `readOnly=true` дополнительно приведёт к `scanOpenRef.current = open && !readOnly = false` (line 218), окончательно отсекая любые новые операции даже если бы попытались.

`closeDialog` (line 337-347) делает то же самое синхронно ещё до того, как `open` изменит значение и запустит cleanup useEffect — двойная страховка: сначала руками бампает сессию и резолвит promise, затем зовёт `onClose()`, что вызывает `setBoxAddDialogBoxId(null)` в родителе (`FfSuppliesShipmentsPage.tsx:3336`), это размонтирует компонент, и cleanup ещё раз бампает сессию и резолвит promise (безопасно идемпотентно). Родитель монтирует компонент только когда `boxAddDialogBoxId && boxById.get(...)` (line 3332-3333) — то есть закрытие диалога это именно unmount, а следующее открытие — mount свежего инстанса с новыми `useRef`, никакого state bleed между инстансами быть не может по природе React refs.

### 5. Очередь A потом P всё ещё видит A, никакой утечки состояния между документами

Проследил цепочку с оригинальным замером времени: `enqueueScan(A)` (line 595-600) создаёт `job1 = scanQueueRef.then(() => runScan(A, session))`, следующий `enqueueScan(P)` создаёт `job2 = job1.then(() => runScan(P, session))`. Порядок исполнения microtask: `runScan(A)` полностью завершается (включая присвоение `sourceRef.current = { A_loc, A }` в line 504 и внутренние setStates) до старта `runScan(P)`, потому что `.then()` на promise чейнит колбэк на завершение предыдущего. Когда `runScan(P)` начинает исполнение (line 438), `selected = sourceRef.current` уже равен A. `scanBody` строится с A, POST уходит с A. Это ровно тот инвариант «уже поставленный в очередь товар после ещё не завершившегося скана A увидит A», который в отчёте.

Про утечку между документами — компонент один, монтируется однократно на выбранный box (line 3334 в FfSuppliesShipmentsPage). При закрытии unmount, при повторном открытии — новый инстанс, все `useRef` инициализируются нулями заново, `useState` — своими defaults. Нет ни статических переменных модуля, ни глобального стора, через который старая сессия могла бы дотянуться до новой. Даже если старый in-flight `runScan` разрешится после mount новой сессии, он работает через свои захваченные ref-объекты (те же, которые уже помечены как stale), плюс `onUpdated` он вызывает у родителя, не касаясь новой инстанции компонента напрямую.

### 6. Отправленные запросы нельзя магически отменить

Три места в `runScan` явно обрабатывают stale-успех — когда POST уже ушёл на сервер, сервер закоммитил, но локальная сессия успела инвалидироваться: line 458-461 после первого POST, line 474-477 после retry POST, line 496-499 после парсинга OK-body. Во всех трёх — только `void onUpdated()` (line 459, 475, 497) при `scanRes.ok`, без setState-модификаций и без вмешательства в `sourceRef`. Это честное поведение, помеченное в отчёте: клиент не пытается «отменить» серверную транзакцию (что было бы вранье), а инициирует перечитывание данных у родителя, который сам решает, что показать в текущем контексте. Если родитель уже показывает другой request, `onUpdated` (`loadDocDetail` + `loadPackagingTask` + `onRefreshFfSupplyExtras`) обновит именно текущий, никакого шанса подмешать данные из старого документа нет.

### 7. Упаковка остаётся признаком без побочек

Диф не касается ни `fbs_kiz_service`, ни `fbs_marking_service`, ни `packaging_task_service`, ни какого-либо кода, обслуживающего упаковку. Это исключительно фронтовая модификация одного диалога для сценария подтверждения over-plan в отгрузке `marketplace_unload`. Ни складских списаний, ни резервов, ни навигационных блокеров тут не появилось и не могло — компонент это UI-обёртка над двумя REST-эндпоинтами. Требование сохраняется.

### 8. Никакого редизайна, бэка или FBS-правок

Дельта: `frontend/src/screens/ff/FfMarketplaceUnloadBoxAddDialog.tsx`, `+45/-27` строк, ни один другой файл не изменён (проверил через `tmp/wms058-overplan-review.diff`). Разметка обоих `Dialog`, тексты («Больше, чем в плане» / «В коробе больше товара, чем осталось по плану. Добавить всё содержимое?» / «Отмена» / «Добавить всё»), классы, testid'ы — не тронуты. `useBarcodeScanner` вызывается с теми же условиями (`enabled: open && !readOnly && !readyBoxOverPlanOpen`), только его источник данных теперь не имеет отдельного `pendingReadyBoxBarcode` state — вместо него живёт `overPlanDecisionRef`. Это внутренняя техника промиса ожидания, к дизайну она отношения не имеет.

### Пределы этого ревью

Я проверил только код и предоставленный отчёт `docs/reviews/wms058-overplan-source-20260909.md`. Настоящий регрессионный скрипт `scripts/wms058-overplan-source.cjs` не запускал (только чтение, без команд). Актуальный staging-Chrome прогон не выполнял. Проверка на **реальных** плановых лимитах и реальном железе ТСД остаётся за отдельным исполнителем (в отчёте указан Parfit) — этот вердикт эту проверку не подменяет и не отменяет.

### Косметические наблюдения (не блокирующие)

Текст модалки «В коробе больше товара, чем осталось по плану» технически универсально применим (модалка теперь может открываться не только на whole-box сканах, но и на любых плановых превышениях в этом флоу), — это уже отмечалось как pre-existing wording в предыдущем ревью и явно оставлено вне скоупа. Не защищаю его правку, просто фиксирую, что в этот фикс изменение текста не затесалось.

### Итог

**Кандидат `39c84d09` можно катить.** Исходный P1 закрыт архитектурно (не hotfix-костылём), инварианты сохранения источника, блокировки очереди, инвалидации сессии и отсутствия cross-document утечки подтверждены построчно на текущем чекауте. Обязательных исправлений от меня нет. Единственное, что нельзя подтвердить чтением кода — реальные плановые превышения на боевых данных и физическом сканере: это должно быть отдельно закрыто прогоном на staging по правилу «нажми кнопку сам» перед выкаткой в prod `40b722a4`.
