# WMS-418: перенос в общий кандидат

По передаче root из takeover12:00 перенесён только delta95ab5fc48d0f4c7df808ec8a71d8d231d02e559c: products API, seller_wb_catalog_service, существующий FfProductsCatalogScreen и2 теста. Канон обновлён вручную без старой версии; branch/worktree root не изменялись.

Координатор прочитал код фильтра: используется существующая WB-галка и Ozon с прежним coalesce-наследованием; нулевые остатки не выключают публикацию. Условия применяются в SQL до пагинации, tenant/seller/marketplace/search/category сохраняются; selection и page сбрасываются при новом фильтре. Соседние stock/UI изменения сохранены.

На интеграции выполнены оба целевых HTTP-теста на отдельной учебной PostgreSQL wms415_review397_20260910:2 passed за26.97s. Scoped Ruff PASS, tsc и production build PASS (Vite3.56s, прежнее предупреждение о chunk>500kB). Без клиентских данных и публикаций в маркетплейсы.

Root уже провёл ручные клики в полном App исходной ветки: протокол wms418-manual-catalog-20260910.md. Это его доказательство исходного95ab5fc4; новых ручных кликов coordinator после интеграции нет. Независимое review интеграционного SHA ещё нужно. Production не изменён этим срезом; WMS111/112 STOP не затрагивается.
