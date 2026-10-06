# WMS-681: ограниченное CUA-доказательство C9–C11

07.10.2026, фактический UI-проход Chrome/CUA на текущем реальном `FfFbsSupplyWorkspace`, теме `muiTheme` и исходных стилях. Проверенный product SHA `de76be359ea4c02a0ee70aa204eae2e853c47b1f`, HEAD до evidence `087378be51a5940f5e8099dbe0b6cefb2b6ed2cb`; diff компонента относительно product пуст. Прочитаны актуальные требования C9/C10/C11, `.agent-runs/progress.json`, свежие `review_r6_final.result.md` и `review-r6-final-handoff.md`: адресный независимый R6/C10 PASS подтверждён, старый FAIL не использован. Независимое ревью не заменялось этой ролью.

Это только UI-evidence для принимающего аналитика, не полный вердикт задачи. Product/tests/requirements не изменены. Существующий Vite16811 возобновлён; исходные baseline.html/browser-entry.tsx не переписаны. Отдельная сцена `/.agent-runs/cua681.html?mode=...` повторяет существующий harness с искусственными API-ответами, управляемым поздним ответом и явно подписанными изображениями. POST выполняются только в локальном mock-fetch; настоящие WB/production endpoints не вызываются. Пустые демо-короба/заказы не используются как доказательство реального состава или сохранности production-данных.

## Что видно в существующем интерфейсе

| Сценарий | Фактическое действие и результат | Доказательство |
|---|---|---|
| C9 single | У непривязанного короба нажата прежняя «QR»: 1 POST retry-qr, свежий ответ со связью и asset; штатное «Проверка перед печатью», готово1, GET только указанного сервером asset. Новые UI-экраны не добавлены | 01-single-preview.png, single.dom.txt |
| C9 group | Пять непривязанных коробов → «Печать всех QR (5)»: 1 POST retry-qr получает свежий групповой snapshot; 5 asset GET и готово5 в прежнем preview. Факт одного внешнего WB create этим UI mock не доказывается; это отдельная backend проверка | 02-bulk-five-preview.png, bulk.dom.txt |
| C10 durable partial | Первый retry сохраняет искусственный A1 и возвращает504; приложение вызывает обычный GET workspace, пробует второй короб и опять перечитывает snapshot. В preview только A1, A2 asset не запрошен; видимая причина «WB не ответил…», «Не получены QR1коробов; печатаются остальные1». POST boxes/create отсутствует | 03-partial-one-preview.png, partial.dom.txt |
| C10 zero/retry | При отказе и нуле готовых остаётся ошибка на поставке, preview не открывается. Следующий явный повтор получает ready asset и открывает штатный preview с1макетом | 04-zero-error.png, 05-zero-retry-preview.png, zero-error.dom.txt, zero-retry.dom.txt |
| C11 bulk A→B | Запрос retryA удержан самой QA-сценой. Видимой QA-кнопкой без remount переключён тот же компонент на supplyB, затем возвращён захваченный ответA. Заголовок/составB сохранены, чужой preview не открыт, assetGETA нет | 06-late-a-b.png, late-bulk.dom.txt |
| C11 single A→B | Та же контролируемая последовательность после одиночной «QR». ОтветA не открыл preview и не запросил его asset после B | 07-late-single-a-b.png, late-single.dom.txt |
| C11 Ozon | Готовая искусственная PDF-этикетка через прежнюю «Собрать и получить этикетку» открывает обычный preview с заголовком «Печать этикетки отправления Ozon» и предупреждением об исходных PDF-страницах. Только assetGET; retry-qr не вызывается | 08-ozon-existing-preview.png, ozon.dom.txt, synthetic-ozon-preview.pdf |

Изображения WB специально содержат `SYNTHETIC QA681 / NOT A REAL WB LABEL`; они не являются валидными QR WB. Ozon PDF тоже помечен как искусственный. Проверен выбор серверного asset/готовность/контекст и отображение ошибочного результата, а не подлинность этикетки маркетплейса. Кнопки «Печать», «Подтвердить нанесение» и «Передать…» не нажимались. Системная печать при locked macOS не запускалась, C13 бумага/привязка настоящих WB QR не закрыты.

C6 PostgreSQL multi-worker, серверная идемпотентность, production restore/deploy/served SHA не исследовались этим UI-проходом. Также здесь не воспроизведены отдельные runtime ошибки recovery GET, чужой supply response или гонка тихого refresh. Эти границы не подменены прошедшим CUA. Итоговые требования и acceptance verdict заполняет назначенный аналитик через координатора.

## Воспроизведение и handoff

Исходники QA-сцены сохранены как `.txt`: разместить `qa-browser-entry.tsx.txt` в `frontend/.agent-runs/browser-entry-cua.tsx`, `qa-index.html.txt` как `frontend/.agent-runs/cua681.html`, PDF как `frontend/.agent-runs/ozon-fixture.pdf`. Запустить существующий Vite из frontend с `--host127.0.0.1 --port16811 --strictPort`; URL `http://127.0.0.1:16811/.agent-runs/cua681.html?mode=single`, modes bulk/partial/zero/late/ozon. В late сначала QR/массовая кнопка, потом видимые QA-кнопки открытияB и возвращенияA. Это воспроизводимая app-owned test control, не скрытая evaluate-инъекция. Реальные компоненты не модифицированы.

Собственные Chrome-вкладки закрыты, viewport не менялся. Vite оставлен исключительно для передачи этой же сцены принимающему аналитику; ведущему переданы session/PID, чтобы остановить его после передачи. Полная приёмка или выпуск здесь не объявляются.
