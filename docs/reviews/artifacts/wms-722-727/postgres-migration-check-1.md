# WMS-722 · миграция 20261009_0722 на настоящем PostgreSQL (09.10.2026)

Выполнил помощник ведущего (Haiku) по поручению ведущего; локальный PostgreSQL 17 (/tmp:5432), отдельные базы
wms722_mig_check_1009 и wms722_mig_check2_1009 (после проверки удалены), alembic из worktree на 5d98a41c9.

| Шаг | Результат |
|---|---|
| upgrade 20261007_2303 | FK: fbs_order_picks / fbs_order_product_picks → NOT NULL, ON DELETE CASCADE; withdrawal_items → NOT NULL, NO ACTION |
| вставка заказа, picks, product_picks, withdrawal_items со ссылкой на поставку | COMMIT |
| upgrade 20261009_0722 | все три FK nullable, ON DELETE SET NULL; данные на месте |
| DELETE поставки | строки истории сохранились со ссылкой NULL, заказ на месте с пустой поставкой |
| downgrade при строках с NULL | отказ: RuntimeError «Cannot restore required supply references with detached history»; ревизия осталась 0722, FK прежние |
| downgrade без строк с NULL | прошёл, FK вернулись точно к исходным (NOT NULL, CASCADE, CASCADE, NO ACTION) |
| повторный upgrade | прошёл |
| пустая база: upgrade head | 204 шага, alembic heads — одна голова 20261009_0722 |

Выводы для выпуска: после первого реального удаления пустой поставки откат схемы потребует решения о строках истории
(миграция их намеренно не удаляет). Пустоту поставки база не контролирует — это делает сервис (тесты WMS-722).
Не проверено: сбой посреди ALTER, объём и время на боевых данных.
