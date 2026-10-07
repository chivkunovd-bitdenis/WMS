# Единственная коррекция после whole-package review

Независимое завершённое заключение **033a5bcedaa6c680947d0c9ff411ec328d9574d1 — FAIL** сохранено неизменным в истории и `docs/reviews/WMS-652-final-source-review-acf-20261007.md`. Оно подтвердило сохранность всех прежних путей/кейсов/report semantics, merged product P и пять новых Git/API tests. Единственный дефект: новый batch report был ошибочно записан как `pg/662-batch.xml`.

Исправлена только эта новая policy suite: **`release-postgres/662-batch.xml`**, ровно как в настоящем existing producer и upload/download. Existing upload двух путей имеет общий корень RUNNER_TEMP и сохраняет `release-postgres`; backend aggregate не переименовывает его. Case ID, assertions, producer, mandatory job, bytes protected sources и прежние reports не изменены.

Прямое свежее поручение владельца, переданное модератором `/root`: **«НЕ запускать независимое ревью однострочного исправления662receiptpath»**; требуется ревью собранного пакета, затем адресная проверка исправления и publication/main pin/CI. Это явное исключение для одной подтверждённой технической строки, не отмена CI или остальных защит. Отдельный reviewer PASS не получен и не выдумывается. Исторический FAIL остаётся FAIL.

`probe.json` — настоящий результат контролируемой проверки artifact path через неизменный `verify_reports`: тестовая XML-копия под фактическим producer path читается успешно с тем же обязательным ID, прежний `pg/` путь по-прежнему явно отказывает. Это проверка проводки на синтетическом XML, **не новый PG/CI receipt**. Настоящий PG и весь backend/full CI остаются обязательными в последующем запуске.

Разрешение продолжить SOURCE release основано на завершённом whole-package review и устранении его единственного дефекта по прямому поручению владельца. Source-binding metadata сохраняет исходный verdict FAIL вместе с owner-authorized correction; его нельзя читать как новый independent PASS всего исправленного SOURCE. Product P остаётся неизменным и отдельно подтверждённым review scope. Main pin/production здесь не выполнялись.
