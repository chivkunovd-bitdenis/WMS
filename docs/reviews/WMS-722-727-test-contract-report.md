# WMS-722/723/724/726/727 — отчёт тестировщика до реализации

Контракт подготовлен локально в текущем worktree. Коммит и push намеренно не выполнялись по прямому поручению владельца; ведущему предстоят отдельные коммиты по задачам. Это отчёт о тестах до кода, а не приёмка, независимое ревью, CI или деплой.

Исходная ветка: `feat/wms722-727-fbs-supply-card`; исходный SHA: `436c90fe60ee276540df772de64cb2e0c9ee3ab4`. До правок дерево было чистым. AGENTS.md, навык тестировщика, пять постановок и библиотека сбоев прочитаны. Локальный AGENTS.md совпал по SHA-256 с доступным origin/etalon; обновить remote было невозможно из-за запрета записи FETCH_HEAD в общий каталог Git.

Среда: подключённые node_modules, vitest/jsdom, проектный Python и изолированная SQLite. Известные целевые пробелы до первого прогона: отсутствие удаления, обеих новых кнопок, сохранённые «Состав»/дата/календарный источник FBS. Полный набор существующих тестов не запускался; его красные результаты неизвестны. Playwright и браузеры не использовались. Импорт типов из FfPackagingPage в DOM-тестах изолирован, чтобы не втягивать ненужный экран; операции карточки выполняет реальный компонент, HTTP и печатающее окно/устройство представлены контролируемыми внешними границами.

Проверены 106 отдельных параметризованных случаев: 29 зелёных, 77 красных. В адресных наборах нет постоянно отключённых тестов. Фильтры -t/-k использовались только для диагностических повторов и временной порчи; исключённые фильтром случаи не засчитываются как выполненные в таком повторе.

| Задача | UI/контроллер: зелёные | UI/контроллер: красные | Сервер: зелёные | Сервер: красные |
|---|---:|---:|---:|---:|
| WMS-722 | 0 | 7 | 0 | 14 |
| WMS-723 | 9 | 15 | 8 | 0 |
| WMS-724 | 0 | 13 | 2 | 0 |
| WMS-726 | 2 | 13 | 0 | 2 |
| WMS-727 | 0 | 11 | 8 | 2 |

## Как доказана польза зелёных проверок

После каждой временной порчи восстановлены исходные байты продуктовых файлов. Содержательные падения получены при отключении открытия истории, выдаче пустого листа и неверного количества, потере сохранённой вкладки и позднего этапа, включении добавления в закрытый WB, пропуске сохранения связи добавленного заказа, снятии границы клиента и ложном успешном ответе недопустимому добавлению.

Для коробов тесты поймали изменение упаковки WB/количества Ozon, попытку повторной вставки назначений и снятие проверки конфликта пакетного назначения. Для дат — потерю даты FBO, отказ от сохранения даты МП и отключение расчёта отсечки FBS. Для скана — устаревшие настройки после отказа и новый ключ повторной печати. Эти изменения не оставлены в продукте.

Не засчитаны диагностические опыты, где правка затронула старый одноимённый маршрут вместо batch-add, один снятый барьер остался защищён соседними проверками либо возникла ошибка отступа. Последний опыт повторён на точном цикле и дал ожидаемые падения двух проверок сохранности. Тестовые ожидания ради зелёного результата не менялись.

## Границы доказательства

Дальнейшие действия DOM-сценариев за отсутствующими новыми кнопками заблокированы текущим продуктом: их объявления не означают успешного прохождения сохранения, отмены или позднего ответа. Серверные сценарии соответствующих операций запускаются независимо. Ручные C8 (722/726), C7 (723/724) и C9 (727), физические этикетки, PostgreSQL и живые маркетплейсы не проверены. Конкурентные проверки выполнены на заданной владельцем SQLite.

Противоречий Cn требованиям Rn и автоматом недоказуемых согласованных проверок не найдено. В постановках изменён исключительно столбец «Тест» всех 34 автоматических проверок; ручные строки, «Вердикт», «Заключение» и прочий исходный текст сохранены.

Общие фикстуры (подготовка данных и контролируемые внешние границы) находятся в `backend/tests/fbs_supply_card_fixture.py` и `frontend/src/screens/v2/fbsSupplyCard.contract-fixture.tsx`. В них нет тестов разных задач; файлы самих тестов разделены по WMS. Эти два помощника нужны нескольким контрактам и должны попасть в Git вместе с первым использующим их коммитом.

## WMS-722

Все 21 случая красные: в API нет DELETE самой поставки (405), в карточке нет «Удалить поставку». Контракт охватывает оба маркетплейса, все пять статусов пустой поставки, пустые вспомогательные записи, связанные заказы включая отменённые, общее сборочное задание, сохранность учёта, повтор, гонку с добавлением и доступ. У C3 последующий переход к пустой поставке подготовлен через штатный сервис detach_cancelled_order_from_supply; на текущем коде выполнение останавливается раньше, на отсутствующем удалении.

Файлы:

- [backend/tests/test_wms722_supply_delete.py](/Users/deniscivkunov/Projects/WMS/.worktrees/wms722-727-supply-card/backend/tests/test_wms722_supply_delete.py)
- [frontend/src/screens/v2/FfFbsSupplyWorkspace.wms722.dom.test.tsx](/Users/deniscivkunov/Projects/WMS/.worktrees/wms722-727-supply-card/frontend/src/screens/v2/FfFbsSupplyWorkspace.wms722.dom.test.tsx)
- [docs/requirements/WMS-722.md](/Users/deniscivkunov/Projects/WMS/.worktrees/wms722-727-supply-card/docs/requirements/WMS-722.md)

Имена тестов (полные развёрнутые UI-имена также записаны в столбце «Тест» постановки):

- `backend/tests/test_wms722_supply_delete.py::test_c1_local_delete_disappears_from_worklists_and_old_id`
- `backend/tests/test_wms722_supply_delete.py::test_c2_empty_auxiliary_records_do_not_block_any_status`
- `backend/tests/test_wms722_supply_delete.py::test_c3_every_linked_order_blocks_direct_deletion`
- `backend/tests/test_wms722_supply_delete.py::test_c4_empty_deletion_preserves_neighbor_orders_stock_reserves_and_movements`
- `backend/tests/test_wms722_supply_delete.py::test_c5_duplicate_and_concurrent_deletes_are_idempotent`
- `backend/tests/test_wms722_supply_delete.py::test_c7_unauthenticated_and_foreign_tenant_cannot_delete`
- `backend/tests/test_wms722_supply_delete.py::test_c5_adding_and_deleting_share_one_consistent_outcome`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms722.dom.test.tsx::C1 deletes an empty %s card from every working stage and closes after success`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms722.dom.test.tsx::C3 disables deletion with a linked %s order`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms722.dom.test.tsx::C6 preserves card on refusal and confirms missing card after a lost successful reply`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms722.dom.test.tsx::C6 late deletion of A cannot close or change B`

## WMS-723

15 случаев красные: «Состав» остался, начальное/сохранённое composition не заменяется подбором, общего добавления на трёх рабочих вкладках нет. Отдельно Ozon на старом «Составе» предлагает активное добавление, хотя сервер его отклоняет. 17 случаев зелёные: история/состав и количество листа, сохранение допустимых вкладок и поздних этапов, запрет добавления в закрытые WB, реальное добавление и независимое чтение связи, повтор без дубля, отказ и восстановление, границы клиента/площадки.

Файлы:

- [backend/tests/test_wms723_add_orders.py](/Users/deniscivkunov/Projects/WMS/.worktrees/wms722-727-supply-card/backend/tests/test_wms723_add_orders.py)
- [frontend/src/screens/v2/FfFbsSupplyWorkspace.wms723.dom.test.tsx](/Users/deniscivkunov/Projects/WMS/.worktrees/wms722-727-supply-card/frontend/src/screens/v2/FfFbsSupplyWorkspace.wms723.dom.test.tsx)
- [docs/requirements/WMS-723.md](/Users/deniscivkunov/Projects/WMS/.worktrees/wms722-727-supply-card/docs/requirements/WMS-723.md)

Имена тестов (полные развёрнутые UI-имена также записаны в столбце «Тест» постановки):

- `backend/tests/test_wms723_add_orders.py::test_c2_c6_editable_wb_add_readback_and_repeat_have_one_link`
- `backend/tests/test_wms723_add_orders.py::test_c5_ineligible_status_or_marketplace_cannot_add`
- `backend/tests/test_wms723_add_orders.py::test_c5_foreign_and_incompatible_orders_do_not_change_supplies`
- `backend/tests/test_wms723_add_orders.py::test_c6_wb_refusal_preserves_link_and_retry_uses_readback`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms723.dom.test.tsx::C1 removes composition for %s and preserves order identities on refresh`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms723.dom.test.tsx::C2 adds from common actions in %s on %s without moving stage`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms723.dom.test.tsx::C3 retains common history and picking-list contents for %s`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms723.dom.test.tsx::C4 restores %s and keeps WB navigation through reread`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms723.dom.test.tsx::C4 retains late server stage %s without a saved choice`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms723.dom.test.tsx::C5 does not offer working add-orders for %s %s`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms723.dom.test.tsx::C6 retains rejected add selection and isolates a late response from another supply`

## WMS-724

13 UI-случаев красные: редактор даты, колонка списка и FBS-запрос календаря остались. Сценарий добавления на упаковке также зависит от WMS-723. Два серверных случая зелёные: сохранение/чтение дат FBO и отгрузки на маркетплейс; совместимые историческая дата FBS, дедлайн, резерв и расчёт отсечки организации.

Файлы:

- [backend/tests/test_wms724_dates.py](/Users/deniscivkunov/Projects/WMS/.worktrees/wms722-727-supply-card/backend/tests/test_wms724_dates.py)
- [frontend/src/screens/v2/FfFbsSupplyWorkspace.wms724.dom.test.tsx](/Users/deniscivkunov/Projects/WMS/.worktrees/wms722-727-supply-card/frontend/src/screens/v2/FfFbsSupplyWorkspace.wms724.dom.test.tsx)
- [docs/requirements/WMS-724.md](/Users/deniscivkunov/Projects/WMS/.worktrees/wms722-727-supply-card/docs/requirements/WMS-724.md)

Имена тестов (полные развёрнутые UI-имена также записаны в столбце «Тест» постановки):

- `backend/tests/test_wms724_dates.py::test_c6_fbo_and_marketplace_dates_still_save_and_read`
- `backend/tests/test_wms724_dates.py::test_c5_c6_fbs_stored_date_deadlines_and_cutoff_stay_compatible`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms724.dom.test.tsx::C1 %s date=%s has no editor or ghost dirty state but guards real box drafts`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms724.dom.test.tsx::C2 %s empty=%s keeps aligned supply rows without planned date`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms724.dom.test.tsx::C3 removes FBS calendar requests across months while retaining FBO and MP links`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms724.dom.test.tsx::C4 FBS-only and empty month keep the ordinary calendar grid without an FBS loader`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms724.dom.test.tsx::C5 opening adding and switching stages never clears stored date deadlines or order facts`

## WMS-726

15 случаев красные: нет «Выбрать без ЧЗ», включая общий путь сборки; API не передаёт известность требований Ozon и необходимость ЧЗ второй позиции. Два самостоятельных случая контроллера скана зелёные: снятая после отказа галка прекращает печать; оставленная галка повторяет прежний ключ печати и завершает упаковку один раз. Для проекции существующих фактов контракт использует metadata.requirements_known и positions[].requires_honest_sign; это поля ответа, а не новая бизнес-сущность или статус.

Файлы:

- [backend/tests/test_wms726_ozon_marking_projection.py](/Users/deniscivkunov/Projects/WMS/.worktrees/wms722-727-supply-card/backend/tests/test_wms726_ozon_marking_projection.py)
- [frontend/src/screens/v2/FfFbsSupplyWorkspace.wms726.dom.test.tsx](/Users/deniscivkunov/Projects/WMS/.worktrees/wms722-727-supply-card/frontend/src/screens/v2/FfFbsSupplyWorkspace.wms726.dom.test.tsx)
- [frontend/src/screens/v2/fbsSequentialPacking.wms726.test.ts](/Users/deniscivkunov/Projects/WMS/.worktrees/wms722-727-supply-card/frontend/src/screens/v2/fbsSequentialPacking.wms726.test.ts)
- [docs/requirements/WMS-726.md](/Users/deniscivkunov/Projects/WMS/.worktrees/wms722-727-supply-card/docs/requirements/WMS-726.md)

Имена тестов (полные развёрнутые UI-имена также записаны в столбце «Тест» постановки):

- `backend/tests/test_wms726_ozon_marking_projection.py::test_c3_workspace_projects_known_empty_versus_unknown_requirements`
- `backend/tests/test_wms726_ozon_marking_projection.py::test_c3_workspace_projects_marked_second_position`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms726.dom.test.tsx::C1 replaces WB selection using metadata product and task requirements, including IMEI UIN`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms726.dom.test.tsx::C2 cleared and skipped codes never turn required products into plain products, skipped=%s`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms726.dom.test.tsx::C4 repeats only selection for %s and still permits manual checkboxes`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms726.dom.test.tsx::C5 new selection and manual selection feed identical ordered print requests without CHZ issuance`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms726.dom.test.tsx::C6 after rejected print the next selection uses current ids and current layout`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms726.dom.test.tsx::C7 reread and another card use only current ids without automatically adding checkboxes`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms726.dom.test.tsx::C3 Ozon selects only known plain whole postings, including all positions, and preserves manual unknown choice`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms726.dom.test.tsx::C7 assembly registration keeps independent selectors for two seller blocks`
- `frontend/src/screens/v2/fbsSequentialPacking.wms726.test.ts::C6 scan retry after unchecking QR completes once without stale printing and accepts another order`
- `frontend/src/screens/v2/fbsSequentialPacking.wms726.test.ts::C6 checked QR retry retains operation identity and packs only once`

## WMS-727

13 случаев красные: 11 UI-сценариев не находят «Добавить все»; два настоящих конкурентных серверных сценария получают необработанный IntegrityError уникальности вместо управляемого отказа 409. Восемь серверных случаев зелёные: назначение сохраняет количество/учёт/коды/упаковку, повтор не создаёт дубль, спорный пакет атомарен, независимое чтение после отброшенного успешного ответа позволяет безопасный повтор.

Файлы:

- [backend/tests/test_wms727_box_assignment.py](/Users/deniscivkunov/Projects/WMS/.worktrees/wms722-727-supply-card/backend/tests/test_wms727_box_assignment.py)
- [frontend/src/screens/v2/FfFbsSupplyWorkspace.wms727.dom.test.tsx](/Users/deniscivkunov/Projects/WMS/.worktrees/wms722-727-supply-card/frontend/src/screens/v2/FfFbsSupplyWorkspace.wms727.dom.test.tsx)
- [docs/requirements/WMS-727.md](/Users/deniscivkunov/Projects/WMS/.worktrees/wms722-727-supply-card/docs/requirements/WMS-727.md)

Имена тестов (полные развёрнутые UI-имена также записаны в столбце «Тест» постановки):

- `backend/tests/test_wms727_box_assignment.py::test_c2_c4_assignment_preserves_order_quantity_stock_reserve_codes_and_packing`
- `backend/tests/test_wms727_box_assignment.py::test_c7_repeated_same_box_assignment_has_one_membership`
- `backend/tests/test_wms727_box_assignment.py::test_c7_conflicting_batch_is_atomic`
- `backend/tests/test_wms727_box_assignment.py::test_c7_simultaneous_boxes_have_one_winner_without_partial_items`
- `backend/tests/test_wms727_box_assignment.py::test_c8_readback_after_lost_reply_then_repeat_does_not_duplicate`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms727.dom.test.tsx::C1 WB fills full unassigned maxima twice despite a partial draft and search, without writes`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms727.dom.test.tsx::C2 WB confirms only edited full draft and recalculates remaining without changing packing metadata`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms727.dom.test.tsx::C3 cancelling the filled dialog does not save or print and reopening starts empty`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms727.dom.test.tsx::C4 Ozon uses the existing shipment even while searching for the other shipment`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms727.dom.test.tsx::C5 empty Ozon box honors current selection or original first order, manual=%s`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms727.dom.test.tsx::C5 already assembled Ozon shipment is never made assignable by add-all`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms727.dom.test.tsx::C6 %s neither saves an empty set nor merges unrelated unknown products`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms727.dom.test.tsx::C8 refusal retains draft and late response cannot replace another supply`

## Команды адресного прогона

Фронт: из `frontend` — `npx vitest run` с пятью файлами `FfFbsSupplyWorkspace.wmsNNN.dom.test.tsx`; отдельно `src/screens/v2/fbsSequentialPacking.wms726.test.ts`. Ограничение двух исполнителей для общего адресного прогона сохраняет ресурсы среды.

Сервер: из `backend` — `/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -q` с пятью `tests/test_wmsNNN_*.py`, `-p no:cacheprovider`. После переноса общих фикстур повторены только затронутые добавление WB и гонка удаления; после улучшения сбора конкурентных результатов — только две гонки коробов. Ruff выполнен только для новых Python-файлов.

Финальная проверка diff подтвердила полный откат продуктовых файлов и неизменность всех байтов постановок, кроме столбца «Тест». Все ссылки проверены по фактически собранным именам Vitest и функциям pytest. `git diff --check` и адресный Ruff прошли.

Точные команды для повторения текущего контракта (из соответствующего каталога):

```sh
npx vitest run src/screens/v2/FfFbsSupplyWorkspace.wms722.dom.test.tsx src/screens/v2/FfFbsSupplyWorkspace.wms723.dom.test.tsx src/screens/v2/FfFbsSupplyWorkspace.wms724.dom.test.tsx src/screens/v2/FfFbsSupplyWorkspace.wms726.dom.test.tsx src/screens/v2/FfFbsSupplyWorkspace.wms727.dom.test.tsx src/screens/v2/fbsSequentialPacking.wms726.test.ts --maxWorkers=2
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -q tests/test_wms722_supply_delete.py tests/test_wms723_add_orders.py tests/test_wms724_dates.py tests/test_wms726_ozon_marking_projection.py tests/test_wms727_box_assignment.py -p no:cacheprovider
```
