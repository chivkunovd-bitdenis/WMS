# WMS-418: production-выпуск подтверждён

Первым отдельным выпуском по прямому поручению владельца выложен фильтр включённой публикации остатков WB/Ozon. PR216: https://github.com/chivkunovd-bitdenis/WMS/pull/216 . Штатный CI34462815600 полностью SUCCESS: https://github.com/chivkunovd-bitdenis/WMS/actions/runs/34462815600 . Reviewed app SHA05ddd738; PR head44f52743 содержит только последующие docs. Точный merged/deployed SHA **120b106cc3f47dd28fa499e094c7cde83e8a6b40**.

Перед merge повторно проверены server/origin etalon=eaa6ae9a, exact PR head и все3 завершённых SUCCESS checks. Deploy PID29106 завершился0. Скрипт повторно проверил server base и exact origin head, чистое tracked дерево и ровно3 app-файла. Сборка и up --no-deps затронули только api/web. Оба контейнера запущены10.09.2026 10:05:28UTC; worker/beat сохранили старые images и старт09:11:20UTC. Auth, сети, секреты и клиентские настройки не менялись. Alembic0257 до/после; DDL не запускался.

После deploy независимо проверены оба API-файла в контейнере: products.py2211c3dea261011553fc23ed013726fcc3b25d751b5ff1399c11d4bb432700a4 и seller_wb_catalog_service.pyf1a55da663a70420bc2701297803e470492f697afc6fb06936f55322c0c569ef совпадают с Git120b106c. API image7c8c3003…, web image71ef6744…. Public index.html SHA2569f76bedda6166a2fdf606f95929d671f1c46a8b210db909b8d7ac9e47e99b173 и /assets/FfProductsCatalogScreen-BtQM_qNc.js SHA2564a248324d3f6eebc4d4550313d1e41dc4200cba75ba3d611c04ba7245eaf4822 совпали с файлами web-контейнера.

Публичные HTTPS /, /seller/, /api/health, /api/openapi.json —200. OpenAPI теперь содержит stock_publication со значениями wb/ozon/both/any/none; до deploy параметра не было. Полный машиночитаемый proof: artifacts/wms415-astra-takeover-20260910/resumed/wms418-production-verification-20260910.json. Проверка TLS не выключалась: локальный Pythonurllib не имел настроенного issuer-store, использован обычный системный curl с проверкой сертификата.

Исходную ручную UI-приёмку root см. wms418-manual-catalog-20260910.md; reviewer подтвердил сохранность реализации при переносе. Координатор открыл production /app/ff/products в Chrome663118697 и увидел форму входа; это не собственная приёмка фильтра в авторизованном production-каталоге. Клиентские галки ради проверки не менялись. Непроверенные личные клики не заявляются.

WMS111/112 STOP сохранён, их исполняемый срез не переносился. Остальные415/416 продолжаются отдельно; следующий разрешённый auth270/ports377 PR215 уже имеет зелёный CI, но на момент этого отчёта НЕ deployed.
