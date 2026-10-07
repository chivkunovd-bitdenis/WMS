# WMS-652: узкая receipt wiring после отдельного RED

Разработчик процесса получил отдельный контракт1ab749+5ca749 и не менял его ожидания. В общей ветке уже существовала wms686-mockup job, поэтому RED возник конкретно из отсутствия настоящего TAPreport, а не только отсутствия job. После исправления Node24 запускает неизменные11 modeltests, пишет настоящийTAP, upload/download привязаны к SHA/run/attempt и job обязательна дляprocess-proof. Missing TAP/upload/download/needs controlled negatives сохранены.

225 protectedpaths /19suites /1161IDs включают все прежние222paths/18suites/1146IDs. Только hashes существующих ci.yml и test_ci_release_additions.py изменены для явно описанного SOURCEupgrade; добавлены2fixtureJSON и исходныйfrozenmodel.test.ts. СтарыеcaseIDs/report formats/exact не удалены/ослаблены. P остаётсяd618, finalfixturepending; никакой самоподписи новойproductbase или mainbootstrap нет. ActualTAP11/11 иJUnit24/24 проходят существующий proof-reader; полный CI/rawproof остального пакета этим не заявлен.

Нужны отдельное независимое ревью данного изменения, finalacceptedproductP и затем точный policySOURCE S. Mainpin/etalon/deploy остаются у ведущего. Дополнительные новые задачи не импортированы. Linux print diagnostic37532590419 выполняется отдельно; егоworkflow не входит в эту ветку.
