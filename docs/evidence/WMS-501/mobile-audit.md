# WMS-501 — аудит Android / ТСД

21.09.2026. Проверен отдельный репозиторий `/Users/deniscivkunov/Projects/WMS/mobile`, ветка `feat/mobile-tsd-redesign`, SHA **69caa22b3d2d0e715966776d0edb2cec92723696**. До и после Git status одинаков: untracked `.DS_Store`, `android/.kotlin/`; продукт не изменялся. Это отдельный SHA от backend/web baseline `3e125074`.

После прямого уточнения владельца прежняя остановка отменена. Актуальные global/project AGENTS и постановка WMS-501 прочитаны; PROGRESS прочитан с редактированием строк о секретах до tool output. Значения не использовались и не переносятся в отчёт. Предыдущее ограничение scanning-audit.md «mobile не проверен» **замещается этим дополнением**.

**Мобильный путь теряет часть быстрой серии при заполнении буферов.** В настоящем коде компонентов воспроизведены потеря сканов, обрезание штрихкода после паузы 80 мс, завершение приёмки раньше очереди, старое количество с успешной вспышкой после ошибки перечитывания и разлогинивание нового сотрудника запоздавшим 401 старой сессии. Выполнены **70 тестов: 63 существующих + 7 аудиторских, 0 failures/errors**. Один новый тест, `delayedHttp401FromAInvalidatesNewSessionB`, использует настоящий Retrofit/OkHttp HTTP на localhost MockWebServer; остальные — реальные компоненты с управляемым расписанием корутин и подменённым API. Это не измерение Android UI, production DB или сети склада.

## Окружение и воспроизведение

`adb` отсутствовал в PATH, использован `/opt/homebrew/share/android-commandlinetools/platform-tools/adb devices -l`: подключённых устройств нет. Найдены сохранённые AVD `personal_google_play`, `wms_tsd`, но работающего эмулятора нет. Сохранённые пользовательские данные AVD и рабочие устройства не менялись. Выполнены JVM и localhost HTTP проверки; camera/device/instrumentation проверки не выполнялись.

Из `mobile/android`:

```text
./gradlew testDebugUnitTest --offline --console=plain
./gradlew testDebugUnitTest --offline --console=plain --init-script <audit-checkout>/docs/evidence/WMS-501/mobile-audit.init.gradle --tests ru.wms.tsd.audit.MobileAuditReproTest
./gradlew testDebugUnitTest --offline --console=plain --init-script <audit-checkout>/docs/evidence/WMS-501/mobile-audit.init.gradle
```

Первый прогон: BUILD SUCCESSFUL in 27s; 7 repro: 5s; полный прогон с repro: 4s. Это время Gradle, не задержки продукта. Артефакты: `mobile-repro-sources/MobileAuditReproTest.kt`, `mobile-audit.init.gradle`, `mobile-existing-tests.txt`, `mobile-repro-results.txt`, `mobile-all-tests.txt`, `mobile-junit-summary.txt`. Init-script добавляет внешнюю source directory только на запуск; мобильные build/source files не редактировались. Generated API берётся из `android/app/libs/wms-api-generated.jar` (`app/build.gradle.kts:51`); поля scan-model дополнительно проверены javap.

## Реестр всех текущих mobile-потоков

Пути ниже относительно `mobile/android/app/src/main/java/ru/wms/tsd`.

| Поток | Вход → обработка → HTTP/сохранение → UI |
|---|---|
| Hardware broadcast | `core/scanner/HardwareBroadcasts.kt:16–32,57–80`: Urovo, Zebra DataWedge, Chainway, Honeywell, Newland, ATOL SMART.Slim и DEV_SCAN → parseHardwareBroadcast → ScannerManager. MainActivity регистрирует receiver onStart, снимает onStop. Receiver EXPORTED без permission; DEV_SCAN не ограничен DEBUG. |
| Keyboard wedge | `WedgeKeyAccumulator.kt:22–78`, `MainActivity.kt:62`: dispatchKeyEvent → unicodeChar buffer → Enter → ScannerManager. Минимум 4 символа; любой разрыв >60мс сбрасывает префикс. Символы продолжают попадать в UI; поглощается только Enter. Tab/idle completion и RU→LAT как в web отсутствуют. Специального GS-handler нет; физическая передача GS не проверена. |
| Камера | `CameraScannerSheet.kt:143–214,277`: CameraX single-thread analyzer KEEP_ONLY_LATEST → ML Kit EAN/UPC/Code128/39/QR/DataMatrix → первый найденный barcode → ScannerManager(CAMERA). Cooldown 2000мс на любые коды, зелёная рамка до подтверждения downstream. unbindAll при dispose и ошибка поверх камеры присутствуют. |
| Общий ввод | `ScannerManager.kt:14–22`: trim → MutableSharedFlow(replay=0, extraBufferCapacity=1), tryEmit result игнорируется → LaunchedEffect.collect на трёх рабочих screens → VM.onScan. Отсутствующий/занятый collector не имеет durable queue. |
| B1 очередь приёмок | `InboundListScreen.kt:40–53`: GET всех inbound requests → локальный фильтр submitted/receiving → сортировка. Scanner collector отсутствует, камера выключена. Init load и LifecycleResumeEffect снова вызывают загрузку. |
| B2 короба | `InboundBoxesScreen.kt`, `InboundBoxesViewModel.kt`: ручное создание/просмотр/печать/выбор короба → API → initialBoxId передаётся в B3. Отдельной подписки scannerManager нет. |
| B3 товар в короб | `InboundReceivingViewModel.kt:61,101,201–262`: Channel16 → локальное распознавание известного короба → POST boxes/open + GET request; товар → POST boxes/{box}/scan + GET **всего** request. Worker ждёт обе операции; success flash после POST, количество обновляется GET. |
| B3 россыпь | `InboundReceivingViewModel.kt:231–247`: тот же Channel → POST receiving/scan → success flash → GET всего request. Изменённая строка из POST не применяется к quantity. Нет UUID события и recovery journal. |
| B3 ручной факт/закрытие | `InboundReceivingViewModel.kt:114–198`: PATCH lines/actual, PUT box/lines/product, close box, complete-receiving → refresh/onDone. Отдельные coroutine launch обходят scanQueue; complete/выход не ждут её. |
| C1 список сортировки | `SortingListScreen.kt:45–57`: GET всех inbound requests → локальный фильтр sorting/verified + remaining>0. Scanner collector отсутствует. |
| C2 сортировка | `SortingViewModel.kt:65,102,220–249`: Channel16 → локальное определение короба/ячейки → target/pendingLocation. Подтверждение: box putaway POST либо loose GET distribution-lines → merge → PUT списка → GET request + GET distribution. Скан только выбирает контекст; размещение — подтверждением. Товар россыпью выбирается руками. |
| D1 очередь отгрузок | `OutboundListScreen.kt:40–55`: GET marketplace-unload requests → локальный фильтр confirmed/collecting; scanner collector отсутствует. |
| D2/D3 сборка | `OutboundAssemblyViewModel.kt:71–124,280–334`: Channel16; известный свой короб выбирается локально; ячейка/товар/готовый короб → POST boxes/{box}/scan. Ячейка обновляет локальный контекст; товар/ready_box → GET unload + GET packaging/by-unload + GET packaging/id при наличии задачи. До 1 POST+3 GET перед следующим scan. |
| Упаковка/ship | `OutboundAssemblyViewModel.kt:159–275`: ручной выбор строки → pack progress/confirm packed/complete packaging; ship → обработка расхождения. Самостоятельного scan КИЗ/упаковки нет. packBusy защищает packing mutation, но close/ship не входят в scanner queue. |
| Home/auth и отсутствующие функции | `Navigation.kt` содержит home/inbound/sorting/outbound; Home делает два GET для счётчиков. Login password → auth/login, PIN → локальный SavedStaff. Самостоятельных FBS, inventory, scan/resolve, reprint ЧЗ и warehouse-map scanner routes в этом checkout нет. Документный prototype и другие Git-ветки не являются текущими функциями приложения. |

Channel/SharedFlow живут в RAM, persistent offline-очереди нет. ViewModelScope отменяется при уничтожении владельца экрана. Повтор конкретной бизнес-мутации с тем же UUID отсутствует; apiCall преобразует исключение в «Нет связи с сервером». Это не означает, что транспорт OkHttp никогда не переподключается: explicit business retry/idempotency policy отсутствует, transport defaults её не заменяют.

## Находки

**M1, P1, воспроизведено: буферы молча теряют события.** ScannerManager.kt:15,21 игнорирует отказ tryEmit. Test `managerDropsBurstWhenCollectorHasNotResumed`: подписанный collector, 20 submit до его следующего исполнения → один доставленный код. Это управляемое расписание JVM, а не утверждение о постоянной потере 95% сканов. Все три VM используют Channel16 и игнорируют trySend: receiving:61,101–103; sorting:65,102–103; outbound:71,121–123. Test `receivingQueueSilentlyDropsBeyondSixteenPending`: первый POST задержан, 30 onScan → после release 17 POST, **13 событий отсутствуют**, уведомления об отказе нет; 18 GET request включают начальный. Нужны явное принятие/pending/error и сохранность accepted-event; увеличение буфера лишь отодвинет предел.

**M2, P1, воспроизведено: 80мс внутри скана обрезают штрихкод.** WedgeKeyAccumulator.kt:59–63 очищает префикс. Test `wedgeSingleEightyMillisecondGapEmitsTruncatedBarcode`: `4630452635503`, одна пауза 80мс после первых трёх символов, прочие интервалы 10мс → callback **0452635503**. Это тот класс неисправности, который web уже исправлял. Нужен контракт целой scanner пачки/суффикса, проверенный на устройстве.

**M3, P1, воспроизведён порядок API: complete обгоняет очередь.** InboundReceivingViewModel.confirmComplete:187–198 не синхронизирован с Channel. Test `completeDoesNotWaitForInflightOrQueuedScans`: задержан первый scan response, второй в очереди; complete/onDone происходят до обоих scan responses. Backend подменён: тест доказывает отсутствие client drain, но не фактическую потерю записи в БД. После выхода scope может отменить хвост; позднюю мутацию сервер может отклонить по статусу. Аналогично вне очереди closeBox, manual absolute quantities, outbound ship. Нужен барьер accepted events перед завершением/сменой контекста.

**M4, P1, воспроизведено реальным localhost HTTP: старый 401 разлогинивает нового сотрудника.** ApiProvider.kt:34 захватывает token A, после response401 вызывает notifySessionExpired без identity (:42–43); AuthManager.kt:59–63 инвалидирует текущую B. Test `delayedHttp401FromAInvalidatesNewSessionB`: реальный Retrofit/OkHttp request A дошёл до MockWebServer и задержан; logout→PIN B; сервер вернул 401 A → B=null, вызван invalidateToken(B). Ещё один unit test подтверждает переход состояния. Это межсессионный отказ, **не доказанная утечка товаров**. Нужно сверять captured identity с текущей при expiry.

**M5, P2, воспроизведено: success flash со старым количеством после отказа GET.** ReceivingVM:238–241 выставляет успех после POST, refresh:267–272 игнорирует неуспех. Test `refreshFailureKeepsOldFactWithSuccessFlash`: POST возвращает qty2, follow-up GET бросает IOException; UI state qty1, flashSuccess, loadError=null. Backend подменён, клиентское противоречие доказано. Оператор может повторить scan. Нужно использовать changed row или честно показывать неполученный readback.

**M6, P2, код: камера ограничивает любой новый код паузой 2 секунды.** CameraScannerSheet.kt:207–210 не сравнивает barcode. Другой товар за это время подавлен, тот же неподвижный barcode через 2с снова передан; cooldown не различает удержание этикетки и новую штуку того же SKU. Зелёная рамка — распознавание до приёма очередью/commit. Это свойство кода, не измеренная скорость ML Kit. Нужна определённая семантика нового физического события.

**M7, P1, код + backend repro S2: сортировка пишет старый полный snapshot после отказа свежего чтения.** SortingVM:165–168 при network/non-2xx GET берёт st.distLines, затем :192–194 PUT заменяет весь список. Даже успешный GET не атомарен с PUT. Existing SortingViewModelTest проверяет успешный fresh merge, не отказ/двух сотрудников. Удаление чужой незавершённой строки уже воспроизведено backend тестом scanning-repros.py; конкретный mobile GET-failure path проверен кодом, не device-e2e. Требуется version/expected snapshot или атомарное изменение строки, без fallback на stale overwrite.

**M8, P2, код: SavedStaff не связан с сервером.** AuthStore.kt:15–20 хранит email/name/token/PIN; baseUrl отдельно (:41–44), замена staff только по email (:56–59). После успешного password-login на сервер B старый SavedStaff A может остаться; PIN A даст его token, а ApiProvider использует baseUrl B. Это риск пересылки identity не тому серверу/401, **не доказательство tenant bypass**. Реальные токены/внешние серверы не использовались. Требуется origin+identity scope и проверка на fake endpoints.

**M9, P2, код: рабочие scanner broadcasts доступны внешним локальным отправителям.** HardwareBroadcasts.kt:32,68–76: DEV_SCAN в release, receiver EXPORTED без permission. Другое приложение может попытаться послать событие, которое WMS обработает правами вошедшего сотрудника. Эксплуатация на устройстве не выполнялась. Нельзя просто убрать exported: hardware vendor тоже внешний отправитель. Нужен debug-only DEV_SCAN и подходящий vendor permission/allowlist контракт. Это локальная scan injection, не неавторизованный межtenant API доступ.

## Сессии, tenant, один логин и кеш

Рассмотренные scan bodies не задают tenant_id: отправляют document/box/product/location IDs и bearer; actual tenant/seller guards находятся на backend и рассмотрены отдельно в основном isolation report. В APK-прогоне отрицательные A/B tenant HTTP не выполнялись, поэтому отсутствует отдельное подтверждение всего маршрута «устройство→БД».

ApiProvider кеширует Retrofit client/services по baseUrl, не каталог товаров. На каждый запрос interceptor берёт текущую сессию. VM держат document snapshots/active box/location. MainActivity.kt:153–180 на logout убирает AppNavHost и показывает LoginScreen; SavedStaff остаются для PIN. Доказанного чтения товаров чужого tenant в mobile UI не получено; переключение пользователя с ожидающими HTTP требует device/UI проверки, M4 уже доказан на HTTP.

Один login на разных устройствах не разделяет Kotlin очереди — они локальны. Сервер блокирует общий документ/остаток, а не имя login; manual overwrite и snapshot overwrite возникают независимо от совпадения имени. История пишет одного user, физических сотрудников не различить. Generated jar проверен javap: InboundReceivingScanBody/InboundBoxScanBody содержат только barcode, PackProgressIn только quantity; идентичность попытки web draft recovery в mobile не перенесена.

## Ожидания и прошлые исправления

Подтверждены действующие camera unbind/error overlay, fresh GET перед sorting merge, active-box выбор, ATOL parsing, Android7-compatible feedback; existing tests выполнены заново. Но web оптимизация «применить изменённую строку, отложить полный reload» в mobile отсутствует: receiving POST+GET на штуку, outbound product до POST+3GET, sorting loose GET+PUT+2GET. Время последовательных round trips накапливает backlog и приводит к M1. Нагрузка растёт с количеством сканов/устройств; вместимость production не вычислялась.

LineProgressList.kt:63–69 использует LazyColumn с устойчивыми id — полезная виртуализация видимых строк. Полные загрузки/сортировка списка остаются. Home/list скачивают общие очереди до локального фильтра; init+resume дают лишние открытия. В VM нет общего sequence guard для параллельных ручных refresh, поэтому возможен устаревший поздний ответ; отдельный runtime reorder не проверялся.

## Граница результата

Проверены актуальный SHA, весь Navigation/scanner inventory, реальные исходники потоков и auth/cache, выполнены JVM и настоящий localhost HTTP тест. Первоначальная остановка из-за PROGRESS больше не оставляет mobile без аудита.

Отдельно не исполнены физическое camera recognition/vendor firmware, Enter/Tab/GS настоящего ТСД, Android frames/jank и длинный документ в UI, lifecycle/background с очередью, APK A/B-tenant отрицательная матрица, реальный lost-response-after-commit/slow-Wi-Fi. Для них нужен изолированный emulator/device с тестовым backend; JVM результаты не выданы за device-приёмку. Исправления продукта и деплой не выполнялись.
