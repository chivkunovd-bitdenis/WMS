# WMS-607: read-only handoff по приложению АртМакс

**Готового обновления с последней исправленной Direct Mac-версией не найдено.**
Проверка 07.10.2026 ограничена Git-источниками, документацией и текущей публичной
GitHub release/CI metadata. Продукт, локальные процессы, принтеры и Telegram не
менялись. Исправление/сборка установщика в этой сессии не выполнялись.

Точный последний инцидент — `ed05387190c0b50829ec1e0f3698c9bd8dabe273`,
`docs/evidence/wms607-artmaks/diagnosis.md`, дополнение `docs/requirements/WMS-607.md`.
Речь точно о Mac; архитектура и установленная у клиента Python/Swift-версия
не установлены. Исправление Swift defaultPrinter отделяет stderr от имени очереди,
проверяет очередь до записи задания и различает ошибки с ограниченными ожиданиями.
Сохранены 5 целевых regression PASS, 40 frontend PASS и проход настоящий HTTP →
Swift → CUPS → IPP-эмулятор с декодированным QR. Причина именно на клиентском Mac
не доказана; физическая бумага не проверена; клиенту исправление не установлено.
Opus проверял диагноз/план, а финальный diff отдельным review не закрыт.

Текущие публичные Direct-пакеты:

| Пакет | Git source | ZIP SHA256 | Состояние |
|---|---|---|---|
| Mac ARM stable `2026.09.30.4` | `9a33b651c309796707053e1056c7f80dff7194d5` | `962a755b685d839adb545710878218efb7372d0c6cc655aa945fe0c18c4a60ef` | Старее последнего исправления; Intel asset в этом release отсутствует |
| Windows stable `2026.09.30.5` | `1bdd6cdf53960419d62fed6c62870f0cf27ed30d` | `423277f40e3c6064b236c5ae404b2b2c153b6c7f3d640838f938c06d065f6433` | GitHub latest, но это другой OS package |
| Mac ARM RC1 `2026.10.01.1-rc1` | `a8c00ece3a01d9d88ef9187ef897a7e47d78091c` | `2594770c192652d2b8c971babd3752cf610d4a92162908bc2ef53db2c09b7c39` | prerelease, journal/recovery candidate, старее исправления |
| Mac Intel RC1 | тот же source | `b653147c0bc3be093f1e536730660f5e185227df40944c258510050e8e9d1dee` | prerelease, старее исправления |

Latest Console CI [36977521451](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/36977521451)
SUCCESS на `dd4cc8585fa5122518f58e78f72143584338081f` от 02.10: Windows/ARM/Intel
tests, build и unpacked self-test. Все три artifacts пока не expired. Это ещё
более старый source; после RC1 более нового публичного Direct release нет.
CI artifacts требуют GitHub-доступа и не заменяют обычную публичную установку.

[CI 37511672771](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37511672771)
SUCCESS на исправленном `ed053...`, но workflow `print-agent-package.yml`
вызывает **build_package.py** и собирает другой paired WMS-442 runtime.
Он не собирает Swift Direct через **build_console.py**. Нельзя предложить его
macOS/Windows artifacts как пакет с исправлением АртМакс.

Существующие пути: `tools/print-agent/build_console.py`, Swift/Python Direct и
`.github/workflows/print-console-package.yml` создают ZIP с `wms-print`, build.json
и README. Самостоятельного Direct installer/updater/archive/rollback wrapper
в этих путях нет. README-direct местами описывает старый .app/.exe; фактический
Console README требует распаковать **всю папку**, запустить `wms-print`/exe и
оставить окно открытым. WMS-442 NSIS/LaunchAgent installer относится к другому
runtime, настройке серверного подключения и выбранной очереди.

Драфт безопасной будущей команды пока нельзя выдать как готовое обновление:
сначала нужны independently reviewed exact Direct source, соответствующие ARM/
Intel ZIP, immutable tag/download/checksum и architecture клиента. Затем команда
может скачать/проверить ZIP и build.json в staging directory, сохранить прежние
application bytes и заменить их с возможностью отката. Состояние
`~/Library/Application Support/WMS Print/direct` и старые journals не удалять и
не заменять: откат executable не даёт права повторить неизвестную печать.
Запуск ОС/Chrome должен использовать штатные запросы разрешений при первом
действии. В текущем пакете нет Developer ID/notarization; автоматическое отключение
Gatekeeper, blanket xattr removal или установка произвольного драйвера не являются
готовым существующим механизмом. Сам пакет драйвер принтера не поставляет.

Telegram route найден в постоянной worktree `wms639-support-agent`:
`tools/support_agent/support_agent/telegram.py`: Bots.for_chat выбирает owner bot,
TelegramClient.send_message/send_document вызывают штатные API; flush_outbox
сохраняет статус sent и message_id. Чтение только числовой operational metadata
текущего config подтвердило owner_user_id = owner_chat_id = **689889703**.
Секреты не выводились и не управлялись. Отправка разрешена владельцу; клиентский
чат АртМакс не выбран, outbox/API отправки не вызывались. Родитель координирует
последующую отправку и должен проверить sent/message_id после фактической доставки.

Live metadata snapshots сохранены рядом. Новая работа по установщику отложена по
приоритету владельца: сейчас основной незавершённый контур — CI/product release.
