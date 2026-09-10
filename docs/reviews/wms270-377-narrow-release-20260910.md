# WMS-270/377: отдельный кандидат входа и сетевых портов

Продолжена существующая ветка feat/wms270-login-and-ports от4a7d0c3f. Merge3c4665d3 сохраняет production Ozon eaa6ae9aecee875c50b31afa6b2cc224bb57d043 и ранее выпущенный mobile backend. Ветка не создана заново от default main.

Из coordinator f0bd66a2 перенесены только принятые prod-update.sh, verify-wms-host-network.py, manual deploy workflow и два целевых файла тестов. Авторизация и proxy config совпадают с ранее принятым срезом. Отличия auth_service от широкого coordinator касаются только невыпущенных WMS-062/default warehouse и WMS-325/staff audit; они намеренно не включены в этот отдельный выпуск.

App delta против production ограничен auth.py, auth_service.py и новым login_rate_limit.py. Новых миграций, frontend application изменений, stock/cancel/packing/inventory/chat нет. Никакой спорный WMS-111/112 срез не переносится; они STOP, происхождение owner requirement не доказано. Эта ветка не является выпуском общей415/416 партии.

Текущий статус: интеграция подготовлена; scoped checks выполняются. Commit/push, CI, exact deploy SHA и реальная проверка HTTPS/client IP/закрытия8088/15174 должны быть дописаны по факту. Секреты и клиентские складские данные не менялись.
