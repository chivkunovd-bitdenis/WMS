# WMS-374 — дополнительные факты оркестратора для арбитража

Это отдельная проверка после получения второго отчёта; первому и второму
независимым ревьюерам эти наблюдения не передавались. Никакие настройки,
остатки или заказы этим чтением не изменены.

05.09.2026 в 19:39:59 UTC (22:39:59 МСК) на production выполнен read-only SQL
к существующим привязкам Ozon, связям товаров и правилам. Получена одна строка:

| Поле | Значение |
|---|---|
| seller | ИП Горячкина Т.И. |
| external_warehouse_id | 1020005028840530 |
| served | true |
| stock_sync_enabled | true |
| last_sync_status | error |
| last_error_code | product_mapping_missing |
| last_sync_at | 2026-09-05 19:37:33.955778+00 |
| активных связанных товаров Ozon | 10 |
| из них fbs_percent IS NULL AND fbs_units_mode IS NOT TRUE | 7 |

SQL:
```sql
SELECT s.name,b.external_warehouse_id,b.served,b.stock_sync_enabled,
       b.last_sync_status,b.last_error_code,b.last_sync_at,
       count(l.id) AS linked_products,
       count(l.id) FILTER (
           WHERE p.fbs_percent IS NULL AND p.fbs_units_mode IS NOT TRUE
       ) AS linked_without_rule
FROM fbs_warehouse_bindings b
JOIN sellers s ON s.id=b.seller_id
LEFT JOIN product_marketplace_links l
  ON l.tenant_id=b.tenant_id AND l.seller_id=b.seller_id
 AND l.marketplace='ozon' AND l.is_active
LEFT JOIN products p ON p.id=l.product_id
WHERE b.marketplace='ozon' AND b.is_active
GROUP BY s.name,b.id;
```

Оркестратор непосредственно прочитал sync_ozon_stocks: общий набор товаров,
amounts.get(product.id,0), затем append в stocks; и publish_amounts_for_binding:
товары без правила исключаются из словаря. Это подтверждает применимость
кодового сценария к текущей конфигурации. SQL НЕ доказывает:
- прежнее ненулевое значение в Ozon;
- факт принятия Ozon конкретных нулевых строк;
- число потерянных продаж или момент изменения внешнего остатка.

Арбитру: не принимать утверждение второго отчёта «любое положительное число
в этом SQL — уже сработало» как доказательство внешнего эффекта. Аналогично
применённая миграция0252 сама по себе не доказывает ошибку переноса на конкретных
пулах. Отделить кодовый дефект, достижимую конфигурацию и доказанный инцидент.
Проверь severity самостоятельно, не считай авторский ярлык P0 автоматически
подтверждённым.
