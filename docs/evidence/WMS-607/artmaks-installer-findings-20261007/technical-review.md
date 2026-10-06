# WMS-607: независимое техническое ревью ArtMaks resolver delta

**CHANGES REQUIRED для выпуска Direct Mac.** Проверена точная дельта
`ed05387190c0b50829ec1e0f3698c9bd8dabe273` относительно её родителя; новый
product source в этой сессии не создавался. Нужны исправление конкретной ветки
таймаута и перенос resolver delta на актуальный отдельно проверенный Direct
runtime. Сборка всей старой ветки ed053 как обновления небезопасна для сохранения
уже опубликованного поведения.

Перед ревью прочитаны текущий origin/etalon AGENTS, обе библиотеки owner-cases
и failure-cases целиком и весь WMS-607 с последним уточнением ArtMaks. Применимы
сохранение действующих исправлений при выпуске, проверка исходного действия
после отказа, отсутствие дубликатов при потере ответа и разделение очереди/PDF/
физической бумаги. Пользователь не разрешал этой сессии сборку, запуск на складе
или отправку сообщений. Работа выполнена в прежней чистой worktree; результат
содержит только review evidence.

## F1 · P1: whole-source ed053 возвращает более старую печать

Публичный Mac ARM stable `wms-print-direct-v2026.09.30.4` собран из
`9a33b651c309796707053e1056c7f80dff7194d5` и уже передаёт размер WMS через
`media=Custom.WxHmm`. В ed053 Swift-источнике эти `labelSize`, `printArguments`
и размер в hash отсутствуют. Сравнение именно этого файла с публичным stable
имеет 31 insertions/62 deletions. Это не новое удаление в узкой ed053 parent diff,
а подтверждённое несовпадение его старой базы с выпущенной программой.

В ed053 `submitToDefaultPrinter` строка109 передаёт только fit-to-page/copies;
`Printer.printJob` строка165 хеширует только PNG. После замены установленной
9a33 программы на этот whole-source исчезнет job-specific 58×40 media. При
повторе прежнего ключа/PNG сохранённый size-aware hash не совпадёт с bare PNG hash
и строка170 отвергнет прежнюю квитанцию как изменённое содержимое. Возможность
безопасно продолжить попытку нельзя подтверждать five new tests: они создают
пустое состояние старого формата и не проверяют installed-version upgrade.

Минимальное исправление выпуска: перенести только resolver changes на выбранный
актуальный reviewed Direct source, сохранить media/size-aware identity и ранее
принятые journal/recovery функции; предъявить точный новый SHA и проверку совместимости
с существующим состоянием. Release/tag/build нельзя выбирать только по имени WMS Print.

## F2 · P2: timeout новой проверки очереди выдаётся за отсутствие default

В exact ed053 строка80 `lpstat -p name` имеет timeout5. На `queue.timedOut=true`
строка81 просто продолжает в общий `lpstat -p` (84). Если тот успешно вернёт список,
строка88 сообщает, что macOS не определила принтер по умолчанию, хотя корректное
имя уже получено и именно его проверка не завершилась вовремя. Это source-proven
control-flow, не новый выполненный fault injection. Для timeout общего списка
строка85 тоже объединяет timedOut с недоступностью; первая `lpstat -d` имеет
отдельную timeout-причину. Последнее incident R12 требует не смешивать эти исходы.

Нужен адресный контракт задержки проверки найденной очереди (и общего списка),
затем отдельный timeout outcome до persist/submit с возможностью того же retry.
Все пять нынешних cases отвечают немедленно; эту ветку они не покрывают.
Технические таймауты или перезапуск не должны очищать job с неизвестным исходом.

## Что существующие доказательства подтверждают

Внутри узкой resolver delta stderr отделён от stdout только для чтения default;
остальные вызовы run сохраняют прежнюю семантику через default argument=true.
Распознанное имя проверяется read-only командой существующей очереди. Не меняются
default ОС, права, драйвер, очередь другого оператора и нет fallback на первый
найденный принтер. `Printer` вызывает queue до создания StoredJob/его persist,
так что known pre-submit failure не загрязняет неизвестным заданием будущий retry.
Прежняя блокировка, возврат сохранённой квитанции и запрет повторной отправки
неизвестного исхода в узком parent diff не менялись.

Сохранённый `resolver-before.log`: пять cases, четыре целевых FAIL и один PASS;
`resolver-after.log`: пять PASS. Тест собирает настоящие resolver/Printer из Swift
до HTTPRequest, заменяет только lpstat executable и submit внешнюю границу.
Он покрывает warning stderr, локализованный default, error text вместо queue,
недоступный CUPS и устаревший default, затем same-key retry/replay с submits=1.
Это достаточный targeted RED→GREEN для этих пяти причин, не полная проверка CLI,
всех timeout branches, установленного пакета или migration существующих journals.

`fixed/emulator-result.json` source_sha256
`462e5a33020226b31c88098d527d04ebfe70af238d873f51889936b53bec09c3`
совпадает с actual Git blob ed053 Swift. Реальный lpstat/CUPS/IPP-проход показывает
pre-submit отказ без журнала, восстановление той же попытки и прежнюю квитанцию
при replay. `fixed/scan-emulator-test.log` содержит один успешный тест настоящего
scanner controller → printDirectQr → HTTP → собранный Swift → CUPS/IPP. API WMS
здесь fixture, журнал изолирован; select/bind/pack по одному, ровно один PDF.
Три сохранённых raster QR decode результата совпадают с исходным test_id.

40 frontend PASS указаны в diagnosis/requirements, но отдельного raw 40-case
журнала в exact `docs/evidence/wms607-artmaks` нет. В независимой сессии это
прямо обозначено как author-reported result, а не собственный 40-case прогон.
Frontend/backend product delta ed053 parent→commit пуста; широкий набор в этой
сессии не требуется. После формирования другого integration source сохранённые
доказательства должны быть привязаны к нему по неизменным зависимостям либо
адресно повторены там, где реализация изменилась.

Совокупность этих данных подтверждает конкретные исправленные parser/pre-submit
дефекты и восстановление controlled scan до IPP. Она не определяет причину на
клиентском Mac, его installed version/architecture, бумагу/драйвер Xprinter,
работу скачанного пакета или успешную установку у ArtMaks.

## Остальные конкретные блокеры Direct-релиза

CI37511672771 на ed053 действительно зелёный, но print-agent-package.yml вызывает
build_package.py с paired runtime. Это не пакет Swift Direct. Правильный Console
build_console.py для интегрированного исправления ARM/Intel и соответствующий
immutable public artifact/checksum пока не предъявлены. Последние найденные
public Direct RC1 a8c00 и Console CI dd4cc старее ed053. После закрытия F1/F2 нужны
независимое ревью нового exact delta, применимая приёмка, правильная package CI
и явная граница физического подтверждения. Telegram-доставка сама это не заменяет.

## Минимальные проверки будущей команды updater

1. **Выбор и проверка пакета.** На macOS ARM/Intel, включая Rosetta shell, выбрать
   нужный native artifact; unknown OS/architecture отказ до изменений. Скачать
   immutable reviewed source/tag URL, проверить pinned SHA256, build.json
   source_commit/runtime=direct/architecture и actual executable architecture.
   Wrong checksum/SHA/runtime/corrupt ZIP отказ до остановки старой программы.
   Проверить распакованный self-test и отсутствие вложенного Python; без установки
   Python/Homebrew/компиляторов на компьютер оператора.
2. **Архив и состояние.** Сохранить полную прежнюю application directory с build
   metadata/правами/ссылками в уникальный архив, проверить возможность восстановления.
   Повтор команды/существующий archive не затирает единственную предыдущую копию.
   Временный файл либо нехватка диска не меняют текущую программу. Journals,
   labels, квитанции и unknown jobs не удаляются и не откатываются вместе с бинарником;
   проверить same-key receipt replay и unknown outcome после upgrade/downgrade.
3. **Точный процесс и rollback.** До замены установить, что порт17843 принадлежит
   именно обновляемому executable, а не paired helper/чужому процессу. Не kill по
   одному общему имени. Штатно завершить только свой процесс, заменить staging
   package без частичного дерева, запустить и сверить фактическую версию/health.
   Если запуск/права не прошли — восстановить прежние application bytes; не заявлять
   обновление при оставшемся старом процессе и не создавать повторную печать.
4. **Штатные разрешения.** На чистом профиле сохранить macOS Gatekeeper и Chrome
   local-network protection: предложить разрешение только выбранного проверенного
   executable при первом запуске и HTTPS→localhost запросе. Ранее разрешённый
   запуск не требует повторной общей настройки. Нет spctl disable, blanket xattr
   removal, Full Disk Access, глобальных исключений либо изменения default printer.
   Apple описывает отдельное Open Anyway после первого заблокированного запуска:
   [официальная инструкция](https://support.apple.com/en-us/102445).
5. **Выход после установки.** Один controlled QR → exact default queue → receipt;
   повтор same UUID после перезапуска не добавляет второй job. Существующая ошибка
   default/CUPS оставляет retry возможным и точное сообщение, без ложного success.
   Отдельно бумага нужного размера, одно физическое число копий и чтение QR на
   клиентском принтере; эта проверка остаётся явной операторской приёмкой.

Пункты выше — минимальная постановка проверок, не написанный/прошедший updater.
Драйвер конкретного принтера устанавливается штатно и не подменяется ZIP программы.
Запрет пробелов в queue name сверён с CUPS именами destination, а не с названием
модели в UI: [официальный lpadmin](https://openprinting.github.io/cups/doc/man-lpadmin.html).
В этой сессии ничего не собиралось, зависимости не ставились, CI не dispatchился,
принтер/ОС/Telegram не изменялись; 652/672 принадлежат другим исполнителям.
