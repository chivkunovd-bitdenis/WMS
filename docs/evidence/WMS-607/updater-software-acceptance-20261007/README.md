# WMS-607: ограниченная программная приёмка обновлятора — 07.10.2026

**SOFTWARE PASS для U-C1–U-C8; выпуск и доставка WMS-607 не приняты.**
Исходный аналитик `artmaks_test_contract` недоступен (agent thread limit).
По прямому поручению владельца/ведущего работает отдельный replacement analyst
Sol6.1/high `01a11390-1014-76a0-9302-fbe0fd46ed1f`, ранее принявший HTTP756.
Он не автор updater-контрактов, реализации или независимого ревью.

Основание — неизменённые R-U1–R-U8/U-C1–U-C10 и сохранённое поручение подготовить
Mac-команду обновления с сохранением предыдущей версии и штатными разрешениями.
База приёмки: `49da13fd2a0d22f207818248f274cf5ff400e39f`. Первый продукт
`32c3212406eaf57b904c207bfb45d7acfd25a0b0` дополнен только исправлением
`bdd5a8eee8606d667a90a3b61da299b4097dc877`. Независимый reviewer30ffc сначала
отклонил owned-stop rollback; тот же reviewer в [49da PASS](../updater-stop-rereview-20261007/review.md)
закрыл этот дефект. Историческое отрицательное ревью не объявляется положительным.

[probe.py](probe.py) проверяет только Git bytes/сохранённые XML/JSON;
[source-probe.json](source-probe.json) связывает точные три product blobs,
замороженные контракты a40/040e, манифесты, 18 raw records и точные suite IDs.
Сохранённые результаты на исправленном исходнике: original updater10 PASS
103.310s; additive stop4 PASS; old ArtMaks6/resolver5/native3/HTTP5 =19 PASS
50.669s, везде 0 FAIL/ERROR/SKIP. Независимый reviewer отдельно получил4 PASS.
До коррекции stop4 дал2 содержательных RED/2 preservation PASS. До первой
реализации updater10 имел8 missing-entry FAIL/2 preservation PASS; это отсутствие
реализации, не поведенческое воспроизведение восьми дефектов.

| Требование → критерий | Сохранённый фактический результат | Вердикт |
| --- | --- | --- |
| R-U1 → U-C1 | Intel/ARM/Rosetta выбор; unsupported отказ до замены | Программно подтверждено на OS fixtures |
| R-U2 → U-C2 | Проверка закреплённых checksum/source/runtime/arch, повреждённого ZIP/download/self-test до остановки | Программно подтверждено; актуальные public artifacts ещё отсутствуют |
| R-U3 → U-C3 | Архив сохраняет bytes/modes/links; отказ места/архива сохраняет app; повтор не затирает предыдущий | Программно подтверждено |
| R-U4 → U-C4 | Чужой процесс не сигналится; health200 другого executable не считается успехом | Программно подтверждено, включая additive foreign control |
| R-U5 → U-C5 | Application-only rollback сохраняет current journal; TERM error/survivor сохраняют target/previous/backup/intent/transaction | Программно подтверждено, включая две прежние RED |
| R-U6 → U-C6 | Повтор, concurrent/interrupted update и confirmed stop восстанавливаются без потери архивов/журнала | Программно подтверждено, включая additive successful-stop control |
| R-U5/R-U6/R-U8 → U-C7 | Публичная .4/current receipt и unknown сохраняются; updater/replay/unknown не отправляют новое задание | Программно подтверждено на реальном журнале с изолированным внешним submit |
| R-U7 → U-C8 | Нет смены безопасности/принтера/установки зависимостей; permission failure сообщает штатный шаг и сохраняет восстановление | Программно подтверждено на command fixtures |
| R-U7 → U-C9; R-U8 → U-C10 | Клиентские разрешения, установленный exact target и физическая58×40/читаемыйQR | Не проверено; отдельные ручные этапы |

CLI выполняет настоящий shell и операции с временными ZIP/каталогами; hardware,
download/process/start/signature/extraction границы контролируются fixtures.
Фиксированное dc652 в их build.json — fixture metadata, не SHA нового пакета.
Native-start receipt использует настоящий скомпилированный Swift с изолированными
lp/lpstat и app-support: startup/readiness0 submits, explicit scan1 fake submit,
старое saved задание остаётся saved. Swift/build равны версии32c321 и не изменены
P1-коррекцией. Это не клиентская установка или CUPS/бумага.

Прежние принятые P-A5/P-A6 на dc652/756 сохранены. Для немедленного отдельного
package CI предлагается точный опубликованный HEAD этой docs-only ветки
`codex/wms607-updater-software-acceptance-20261007`: его продуктовые bytes равны
принятому bdd5a8, а сохранённый SHA сообщается при handoff. Новый ARM/Intel пакет
должен получить именно этот source_commit и реальные archive/binary checksums.
Локальный ARM32c321 содержит старый updater и не является финальным.

Actual package CI, оба публичных immutable URL/manifest, readback пакетов,
клиентская установка, U-C9/U-C10/P-A7 и Telegram остаются pending. После получения
пакетов допустима отдельная приёмка артефактов без повторения неизменённых тестов.
Новые тесты/сборка/browser/install/provider/printer/messages здесь не выполнялись;
652/common/main/etalon/production и чужие worktrees не изменены.

Проверка документа точным checker49da против own base49da выполнена один раз:
exit1 только из-за шести referenced test paths, отсутствующих в sparse filesystem.
Все шесть существуют в HEAD Git ([readback](document-check.json)); ошибок заполненности
вердиктов/заключения или изменения контракта не выдано. Проверка в полном checkout
и финальный CI ещё не выполнены; локальный checker не объявляется PASS.
