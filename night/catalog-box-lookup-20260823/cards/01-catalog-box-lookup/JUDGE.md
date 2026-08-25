# UX-вердикт · 01-catalog-box-lookup

ВЕРДИКТ: НАХОДКИ 20

Вердикт роли: `BLOCKED`.

Живой стенд не поднялся. По прямому ограничению запуска адрес стенда и порты не
разыскивались, поэтому открыть `/app/ff/products`, выполнить кейсы и получить снимки
было невозможно. Это блокировка продуктовой валидации, а не подтверждённый дефект
интерфейса.

## Находки

### Стоп

1. `S-16-TC-001`, зона макета 01 «Вход на экран — раздел свёрнут»: снимок живого
   экрана отсутствует, поэтому исходное состояние раздела и строку сканера подтвердить
   нельзя. [Запись кликера об отсутствии снимка](</Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/CLICKS.md>).
2. `S-16-TC-002`, зоны макета 02 и 04 «Обычный список» и «Первая загрузка»: снимок
   отсутствует, поэтому порядок объектов и пять скелетных строк не подтверждены.
   [Запись кликера об отсутствии снимка](</Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/CLICKS.md>).
3. `S-16-TC-003`, зона макета 02 «Обычный список — короб раскрыт»: снимок состава
   короба отсутствует, поэтому колонки, товарные строки и текущий остаток не подтверждены.
   [Запись кликера об отсутствии снимка](</Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/CLICKS.md>).
4. `S-16-TC-004`, зона макета 02, раскрывающиеся строки объектов: снимок после открытия
   второго объекта отсутствует, поэтому правило одного раскрытого объекта не подтверждено.
   [Запись кликера об отсутствии снимка](</Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/CLICKS.md>).
5. `S-16-TC-005`, зона макета 09 «Пустой короб»: снимок пустого состояния отсутствует,
   поэтому текст и отсутствие изменяющих действий не подтверждены.
   [Запись кликера об отсутствии снимка](</Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/CLICKS.md>).
6. `S-16-TC-006`, зона макета 03 «Грузоместо раскрыто»: снимок отсутствует, поэтому
   состояние без состава и набор метаданных не подтверждены.
   [Запись кликера об отсутствии снимка](</Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/CLICKS.md>).
7. `S-16-TC-007`, зона макета 07 «Успешный точный скан»: снимок отсутствует, поэтому
   автоматическое раскрытие, прокрутка, состав и готовность поля к следующему скану не
   подтверждены. [Запись кликера об отсутствии снимка](</Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/CLICKS.md>).
8. `S-16-TC-008`, зона макета 10 «Полностью разложенный короб»: снимок адресного
   результата отсутствует, поэтому спокойное состояние без исторического состава не
   подтверждено. [Запись кликера об отсутствии снимка](</Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/CLICKS.md>).
9. `S-16-TC-009`, зона макета 11 «Завершённое грузоместо»: снимок отсутствует, поэтому
   адресный результат без состава и статус-чипа не подтверждён.
   [Запись кликера об отсутствии снимка](</Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/CLICKS.md>).
10. `S-16-TC-010`, зона заголовков объектов в макете 02: снимок многоскладского состояния
    отсутствует, поэтому условная подпись склада не подтверждена.
    [Запись кликера об отсутствии снимка](</Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/CLICKS.md>).
11. `S-16-TC-011`, зона каталога и смежная приёмка: снимки до и после просмотра
    отсутствуют, поэтому отсутствие побочных изменений приёмки визуально не подтверждено.
    [Запись кликера об отсутствии снимка](</Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/CLICKS.md>).
12. `S-16-TC-012`, зона раздела и сканера под ролью сотрудника: снимок отсутствует,
    поэтому доступ без права приёмки и отсутствие изменяющих команд не подтверждены.
    [Запись кликера об отсутствии снимка](</Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/CLICKS.md>).
13. `S-16-TC-013`, зона успешного адресного результата: снимок после двух быстрых разных
    сканов отсутствует, поэтому защита от позднего ответа не подтверждена.
    [Запись кликера об отсутствии снимка](</Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/CLICKS.md>).
14. `S-16-TC-014`, зона успешного адресного результата: снимок после повторного скана
    отсутствует, поэтому отсутствие дубликата и сохранение фокуса не подтверждены.
    [Запись кликера об отсутствии снимка](</Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/CLICKS.md>).
15. `S-16-TC-015`, зоны макета 06 и 07 «Ошибка списка» и «Успешный точный скан»:
    снимок совместного состояния отсутствует, поэтому независимость результатов не
    подтверждена. [Запись кликера об отсутствии снимка](</Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/CLICKS.md>).
16. `S-16-TC-016`, зоны макета 08 и 07 «Неизвестный ШК» и «Успешный точный скан»:
    снимки последовательных состояний отсутствуют, поэтому восстановление после ошибки
    не подтверждено. [Запись кликера об отсутствии снимка](</Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/CLICKS.md>).
17. `S-16-TC-017`, зоны макета 07 и 10: снимок после полной раскладки и повторного скана
    отсутствует, поэтому отсутствие устаревшего остатка не подтверждено.
    [Запись кликера об отсутствии снимка](</Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/CLICKS.md>).
18. `S-17-TC-001`, смежная зона `/app/ff/reception`: снимок состояния приёмки отсутствует,
    поэтому сохранность открытости, состава и печати после просмотра каталога не
    подтверждена. [Запись кликера об отсутствии снимка](</Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/CLICKS.md>).
19. `S-20-TC-001`, смежная зона `/app/ff/sorting`: снимок результата раскладки
    отсутствует, поэтому переход каталога к актуальному завершённому состоянию не
    подтверждён. [Запись кликера об отсутствии снимка](</Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/CLICKS.md>).
20. `S-19-TC-001`, смежная зона `/app/ff/settings`: снимок проверки роли отсутствует,
    поэтому граница доступа нового чтения не подтверждена.
    [Запись кликера об отсутствии снимка](</Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/CLICKS.md>).

Правило канона к этим двадцати находкам не приписано: на снимках не наблюдалось
нарушение интерфейса, потому что снимков нет. Основание находок — обязательное правило
кейсов: без снимка кейс не считается пройденным. Обязательный каталог доказательств
`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/docs/evidence/01-catalog-box-lookup/`
отсутствует.

### Тормоз

Пусто: живой экран не был открыт, поэтому оценить лишние клики или неясные формулировки
невозможно.

### Хвост

Пусто: живой экран не был открыт, поэтому визуальные отклонения без влияния на сценарий
не проверены.

## Пройденные кейсы

- `S-16-TC-001` → упал на шаге 0: стенд недоступен до открытия каталога.
- `S-16-TC-002` → упал на шаге 0: стенд недоступен до ручного раскрытия.
- `S-16-TC-003` → упал на шаге 0: стенд недоступен до открытия состава.
- `S-16-TC-004` → упал на шаге 0: стенд недоступен до переключения объектов.
- `S-16-TC-005` → упал на шаге 0: стенд недоступен до пустого короба.
- `S-16-TC-006` → упал на шаге 0: стенд недоступен до грузоместа.
- `S-16-TC-007` → упал на шаге 0: стенд недоступен до скана известного короба.
- `S-16-TC-008` → упал на шаге 0: стенд недоступен до скана разложенного короба.
- `S-16-TC-009` → упал на шаге 0: стенд недоступен до скана завершённого грузоместа.
- `S-16-TC-010` → упал на шаге 0: стенд недоступен до многоскладского состояния.
- `S-16-TC-011` → упал на шаге 0: стенд недоступен до проверки неизменности приёмки.
- `S-16-TC-012` → упал на шаге 0: стенд недоступен до проверки роли сотрудника.
- `S-16-TC-013` → упал на шаге 0: стенд недоступен до двух быстрых сканов.
- `S-16-TC-014` → упал на шаге 0: стенд недоступен до повторного скана.
- `S-16-TC-015` → упал на шаге 0: стенд недоступен до совместного состояния ошибки и скана.
- `S-16-TC-016` → упал на шаге 0: стенд недоступен до восстановления после неизвестного кода.
- `S-16-TC-017` → упал на шаге 0: стенд недоступен до повторного скана после раскладки.
- `S-17-TC-001` → упал на шаге 0: стенд недоступен до смежной проверки приёмки.
- `S-20-TC-001` → упал на шаге 0: стенд недоступен до смежной проверки сортировки.
- `S-19-TC-001` → упал на шаге 0: стенд недоступен до смежной проверки роли.

Пройденных кейсов нет.

## Инварианты

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/scripts/ui/invariants.js`
не выполнялся: живой браузерный экран недоступен. Вывода
инвариантов для дословной фиксации нет, поэтому геометрия, наползания, обрезки, окраска
и высоты кнопок не оценивались. Отдельных находок по инвариантам нет, поскольку нет их
вывода.

## Итог

`BLOCKED`: без поднятого стенда и снимков живого экрана независимый продуктовый вердикт
`SCREEN_APPROVED` или `FIXES_REQUIRED` вынести нельзя.
