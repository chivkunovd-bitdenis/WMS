ux-architect: CONTRACT.md: карточке с экраном нельзя поставить МАКЕТ: НЕ НУЖЕН
 не дублируется | R-10, R-35 |
| Зоны S-03, S-14 и S-15 не меняются | R-01, R-04, R-07, R-13 |

`MOCKUP.html` не нужен: карточка backend-only. Недостающих элементов ui-kit нет.

Дальше передать `screen-dev`: для карточки 01 ожидается нулевой frontend-дифф.

Сохранить результат коммитом не удалось: песочница запрещает создание `index.lock` в служебном каталоге Git. Поэтому артефакт локально реализован, но не зафиксирован SHA.
2026-08-22T11:48:53.958802Z  WARN codex_sandboxing::violation: recorded sandbox violation: resource=filesystem backend=seatbelt reason=operation_not_permitted path=unknown
