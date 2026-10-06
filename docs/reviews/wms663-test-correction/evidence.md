# WMS-663: независимая коррекция тестового контракта

Исходный контракт: `ae2ebd3d17f4e7364b1b52de4126b8f70937652b`.
Реализация, на которой воспроизведены оба исходных сбоя:
`7d9e9a63c98e654b688687a3bb2c60782469fbc5`.
Отдельный коммит коррекции только двух тестовых файлов:
`76f2162e22f1aa9e33a336b01109882d8a8969c6`.

Владелец прямо поручил заменяющему независимому тестировщику исправить две
латентные ошибки фикстуры/выбора элемента. Разработчик эти исправления не вносил.
SKILL.md не читались, дочерние агенты не запускались. Продуктовый код, требования,
guards и чужие отчёты не изменялись и не включались в коммит коррекции.

## Почему это коррекция области теста без ослабления

Backend RED: `expire_all()` оставляет ORM-атрибуты истёкшими; синхронное чтение
`order.tenant_id` при подготовке аргументов вызывает MissingGreenlet ещё до
публичного resume. Теперь оба скалярных UUID сохранены до expire_all. Сам
expire_all, публичный вызов, checking → accepted, точные значения документов
и проверка единственного /set сохранены.

DOM RED: глобальный поиск первого «Сохранить» выбирал существующую отключённую
кнопку даты отгрузки. Теперь оба клика выбирают существующую кнопку ГТД/РНПТ
по доступному aria-label, включающему SKU 663001 и экземпляр 1. Отключённые
элементы не отфильтровываются: если целевая кнопка ошибочно disabled, проверка
по-прежнему упадёт. Не изменены задержки, ввод, PUT payload, expected_version 4/5,
gtd_invalid, сохранённый ввод и свободная навигация.

Сравнение AST Python с исходным контрактом подтвердило неизменность всех 44
assert. Сравнение выражений expect через TypeScript parser подтвердило
неизменность всех 16 DOM-ожиданий. Состав тестов не менялся, skip не добавлены.

## Проверки и границы

Все provider calls тестов — FakeMarketplaceTransport, база — изолированная
SQLite из штатной conftest. Production, внешние отгрузки/вывод/подписи и секреты
не затрагивались. Максимум два тестовых worker одновременно, каждый запуск
использовал одного. Полные suites, deploy, merge и приёмка не выполнялись.

Backend: исходный целевой тест RED (exit 1), после коррекции полный файл
WMS-663 GREEN (exit 0): 16 passed / 1 skipped. Skip — существующая проверка
гонки, требующая PostgreSQL; её повтор в этой коррекции не выполнялся.
`ruff check backend/tests/test_wms663_customs_documents_contract.py` — PASS;
`git diff --check` — PASS. DOM: исходный C16 RED (exit 1). Повторный прогон после коррекции остановлен
с SIGTERM в пределах заданного владельцем бюджета 8 минут: спустя более
4 минут он оставался на сборке зависимостей, до запуска теста. GREEN для
замороженного C16 не подтверждён и остаётся обязательным следующим шагом.

## Условие CI для коррекции

Прочитана функция reviewed_contract_correction в scripts/ci/check_task_documents.py.
Коррекционный commit обязан менять ровно перечисленные frozen-файлы и только
часть исходного контракта. Этот commit меняет два теста из трёх исходных файлов;
документ evidence сохраняется отдельным последующим коммитом.

Контроллеру после отдельного независимого Astra high PASS нужно сохранить
`docs/reviews/contract-corrections/WMS-663.json`: task, contract_commit,
correction_commit, files и review с model=gpt-6-astra, effort=high, verdict=PASS.
В этом отчёте такой PASS не заявляется, реестр/чужой review не создаются.
Проверка документов остаётся красной: отсутствуют вердикты C1–C19 и реестр
коррекции. Также выведена независимая ошибка документа WMS-675; она вне владения
этого тестировщика. Ниже сохранён настоящий вывод.

## Точный diff отдельного коммита

```diff
diff --git a/backend/tests/test_wms663_customs_documents_contract.py b/backend/tests/test_wms663_customs_documents_contract.py
index 5fb61d0c5..4e1aff5a8 100644
--- a/backend/tests/test_wms663_customs_documents_contract.py
+++ b/backend/tests/test_wms663_customs_documents_contract.py
@@ -357,12 +357,13 @@ async def test_wms663_explicit_choice_is_saved_exactly_and_resumes_after_restart
     assert target["is_rnpt_absent"] is True
     assert _result_value(result, "state") == "checking"
 
+    tenant_id, order_id = order.tenant_id, order.id
     db_session.expire_all()
     resume = _operation("resume_exemplar_document_check", _ResumeDocuments)
     resumed = await resume(
         db_session,
-        tenant_id=order.tenant_id,
-        order_id=order.id,
+        tenant_id=tenant_id,
+        order_id=order_id,
         provider=OzonMarketplaceProvider(transport=transport),
         client_id="client",
         api_key="key",
diff --git a/frontend/src/screens/v2/FfFbsSupplyWorkspace.wms663.dom.test.tsx b/frontend/src/screens/v2/FfFbsSupplyWorkspace.wms663.dom.test.tsx
index 21baad524..8548a75eb 100644
--- a/frontend/src/screens/v2/FfFbsSupplyWorkspace.wms663.dom.test.tsx
+++ b/frontend/src/screens/v2/FfFbsSupplyWorkspace.wms663.dom.test.tsx
@@ -273,7 +273,7 @@ describe('WMS-663 · явный ГТД/РНПТ у экземпляра Ozon', (
 
     setInput(gtd!, '001/ABC-09')
     expect(absent!.checked).toBe(false)
-    await act(async () => button('Сохранить')!.click())
+    await act(async () => document.querySelector<HTMLButtonElement>('button[aria-label="Сохранить ГТД / РНПТ · SKU 663001 · экземпляр 1"]')!.click())
     await settle()
 
     expect(requests).toContainEqual({
@@ -293,7 +293,7 @@ describe('WMS-663 · явный ГТД/РНПТ у экземпляра Ozon', (
     expect(input('Номер ГТД · SKU 663001 · экземпляр 1')!.value).toBe('001/ABC-09')
 
     setInput(input('Номер ГТД · SKU 663001 · экземпляр 1')!, '001/ABC-10')
-    await act(async () => button('Сохранить')!.click())
+    await act(async () => document.querySelector<HTMLButtonElement>('button[aria-label="Сохранить ГТД / РНПТ · SKU 663001 · экземпляр 1"]')!.click())
     await settle()
     expect(requests).toContainEqual({
       method: 'PUT',
```

## Backend RED

Команда: `cd backend && /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest tests/test_wms663_customs_documents_contract.py::test_wms663_explicit_choice_is_saved_exactly_and_resumes_after_restart -n 1 -q`.

```text
bringing up nodes...
bringing up nodes...

F                                                                        [100%]
=================================== FAILURES ===================================
____ test_wms663_explicit_choice_is_saved_exactly_and_resumes_after_restart ____
[gw0] darwin -- Python 3.14.3 /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python

db_session = <sqlalchemy.ext.asyncio.session.AsyncSession object at 0x11180b4d0>

    @pytest.mark.asyncio
    async def test_wms663_explicit_choice_is_saved_exactly_and_resumes_after_restart(
        db_session: AsyncSession,
    ) -> None:
        """C1/C2/C6/C13: explicit values survive readback; blank is not absent."""
        order, _, _ = await _seed_order(db_session)
        transport = _transport()
        transport.endpoint_response_queues["/v5/fbs/posting/product/exemplar/status"] = [
            {
                "posting_number": POSTING_NUMBER,
                "status": "validation_in_process",
                "products": [],
            },
            {
                "posting_number": POSTING_NUMBER,
                "status": "ship_available",
                "products": [
                    {
                        "product_id": SKU_ONE,
                        "exemplars": [
                            {
                                "exemplar_id": 81,
                                "gtd": "001/ABC-09",
                                "is_gtd_absent": False,
                                "rnpt": "",
                                "is_rnpt_absent": True,
                                "gtd_check_status": "",
                                "rnpt_check_status": "",
                                "gtd_error_codes": [],
                                "rnpt_error_codes": [],
                            }
                        ],
                    }
                ],
            },
        ]
        save = _operation("save_exemplar_documents", _SaveDocuments)
    
        result = await save(
            db_session,
            tenant_id=order.tenant_id,
            order_id=order.id,
            product_id=SKU_ONE,
            exemplar_id=81,
            gtd="001/ABC-09",
            is_gtd_absent=False,
            rnpt=None,
            is_rnpt_absent=True,
            expected_version=None,
            provider=OzonMarketplaceProvider(transport=transport),
            client_id="client",
            api_key="key",
        )
    
        set_payloads = [
            payload
            for path, payload in transport.endpoint_calls
            if path == "/v6/fbs/posting/product/exemplar/set"
        ]
        assert len(set_payloads) == 1
        target = next(
            exemplar
            for product in set_payloads[0]["products"]
            if product["product_id"] == SKU_ONE
            for exemplar in product["exemplars"]
            if exemplar["exemplar_id"] == 81
        )
        assert target["gtd"] == "001/ABC-09"
        assert target.get("is_gtd_absent") is not True
        assert target.get("rnpt") in {None, ""}
        assert target["is_rnpt_absent"] is True
        assert _result_value(result, "state") == "checking"
    
        db_session.expire_all()
        resume = _operation("resume_exemplar_document_check", _ResumeDocuments)
        resumed = await resume(
            db_session,
>           tenant_id=order.tenant_id,
                      ^^^^^^^^^^^^^^^
            order_id=order.id,
            provider=OzonMarketplaceProvider(transport=transport),
            client_id="client",
            api_key="key",
        )

tests/test_wms663_customs_documents_contract.py:364: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/orm/attributes.py:569: in __get__
    return self.impl.get(state, dict_)  # type: ignore[no-any-return]
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/orm/attributes.py:1096: in get
    value = self._fire_loader_callables(state, key, passive)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/orm/attributes.py:1126: in _fire_loader_callables
    return state._load_expired(state, passive)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/orm/state.py:828: in _load_expired
    self.manager.expired_attribute_loader(self, toload, passive)
../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/orm/loading.py:1674: in load_scalar_attributes
    result = load_on_ident(
../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/orm/loading.py:510: in load_on_ident
    return load_on_pk_identity(
../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/orm/loading.py:695: in load_on_pk_identity
    session.execute(
../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/orm/session.py:2373: in execute
    return self._execute_internal(
../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/orm/session.py:2271: in _execute_internal
    result: Result[Any] = compile_state_cls.orm_execute_statement(
../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/orm/context.py:306: in orm_execute_statement
    result = conn.execute(
../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/engine/base.py:1421: in execute
    return meth(
../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/sql/elements.py:526: in _execute_on_connection
    return connection._execute_clauseelement(
../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/engine/base.py:1643: in _execute_clauseelement
    ret = self._execute_context(
../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/engine/base.py:1848: in _execute_context
    return self._exec_single_context(
../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/engine/base.py:1988: in _exec_single_context
    self._handle_dbapi_exception(
../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/engine/base.py:2368: in _handle_dbapi_exception
    raise exc_info[1].with_traceback(exc_info[2])
../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/engine/base.py:1969: in _exec_single_context
    self.dialect.do_execute(
../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/engine/default.py:952: in do_execute
    cursor.execute(statement, parameters)
../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/dialects/sqlite/aiosqlite.py:183: in execute
    self._adapt_connection._handle_exception(error)
../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/dialects/sqlite/aiosqlite.py:343: in _handle_exception
    raise error
../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/dialects/sqlite/aiosqlite.py:160: in execute
    _cursor: AsyncIODBAPICursor = self.await_(self._connection.cursor())  # type: ignore[arg-type] # noqa: E501
                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

awaitable = <aiosqlite.context.Result object at 0x1125cb160>

    def await_only(awaitable: Awaitable[_T]) -> _T:
        """Awaits an async function in a sync method.
    
        The sync method must be inside a :func:`greenlet_spawn` context.
        :func:`await_only` calls cannot be nested.
    
        :param awaitable: The coroutine to call.
    
        """
        # this is called in the context greenlet while running fn
        current = getcurrent()
        if not getattr(current, "__sqlalchemy_greenlet_provider__", False):
            _safe_cancel_awaitable(awaitable)
    
>           raise exc.MissingGreenlet(
                "greenlet_spawn has not been called; can't call await_only() "
                "here. Was IO attempted in an unexpected place?"
            )
E           sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called; can't call await_only() here. Was IO attempted in an unexpected place? (Background on this error at: https://sqlalche.me/e/20/xd2s)

../../../backend/.venv/lib/python3.14/site-packages/sqlalchemy/util/_concurrency_py3k.py:123: MissingGreenlet
=============================== warnings summary ===============================
app/main.py:19
app/main.py:19
  /Users/deniscivkunov/Projects/WMS/.worktrees/wms662-663-priority/backend/app/main.py:19: StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead.
    from app.api.billing_profile_marketplace import router as billing_profile_marketplace_router

<frozen importlib._bootstrap>:491
<frozen importlib._bootstrap>:491
<frozen importlib._bootstrap>:491
<frozen importlib._bootstrap>:491
  <frozen importlib._bootstrap>:491: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:491
<frozen importlib._bootstrap>:491
<frozen importlib._bootstrap>:491
<frozen importlib._bootstrap>:491
  <frozen importlib._bootstrap>:491: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

<frozen importlib._bootstrap>:491
<frozen importlib._bootstrap>:491
  <frozen importlib._bootstrap>:491: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_wms663_customs_documents_contract.py::test_wms663_explicit_choice_is_saved_exactly_and_resumes_after_restart
1 failed, 12 warnings in 10.09s
```

## Backend GREEN

Команда: `cd backend && /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest tests/test_wms663_customs_documents_contract.py -n 1 -q`.

```text
bringing up nodes...
bringing up nodes...

.....s...........                                                        [100%]
=============================== warnings summary ===============================
app/main.py:19
app/main.py:19
  /Users/deniscivkunov/Projects/WMS/.worktrees/wms662-663-priority/backend/app/main.py:19: StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead.
    from app.api.billing_profile_marketplace import router as billing_profile_marketplace_router

<frozen importlib._bootstrap>:491
<frozen importlib._bootstrap>:491
<frozen importlib._bootstrap>:491
<frozen importlib._bootstrap>:491
  <frozen importlib._bootstrap>:491: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:491
<frozen importlib._bootstrap>:491
<frozen importlib._bootstrap>:491
<frozen importlib._bootstrap>:491
  <frozen importlib._bootstrap>:491: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

<frozen importlib._bootstrap>:491
<frozen importlib._bootstrap>:491
  <frozen importlib._bootstrap>:491: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
16 passed, 1 skipped, 12 warnings in 8.39s
```

## DOM RED

Команда: `cd frontend && npx vitest run src/screens/v2/FfFbsSupplyWorkspace.wms663.dom.test.tsx --maxWorkers=1 --minWorkers=1`.

```text

 RUN  v3.2.6 /Users/deniscivkunov/Projects/WMS/.worktrees/wms662-663-priority/frontend

 ❯ src/screens/v2/FfFbsSupplyWorkspace.wms663.dom.test.tsx (1 test | 1 failed) 628ms
   × WMS-663 · явный ГТД/РНПТ у экземпляра Ozon > C16: выбор по экземпляру сохраняется, ошибка остаётся в строке и навигация не блокируется 627ms
     → expected [ { method: 'GET', …(2) }, …(1) ] to deep equally contain { method: 'PUT', …(2) }

⎯⎯⎯⎯⎯⎯⎯ Failed Tests 1 ⎯⎯⎯⎯⎯⎯⎯

 FAIL  src/screens/v2/FfFbsSupplyWorkspace.wms663.dom.test.tsx > WMS-663 · явный ГТД/РНПТ у экземпляра Ozon > C16: выбор по экземпляру сохраняется, ошибка остаётся в строке и навигация не блокируется
AssertionError: expected [ { method: 'GET', …(2) }, …(1) ] to deep equally contain { method: 'PUT', …(2) }

- Expected: 
{
  "body": {
    "exemplar_id": 81,
    "expected_version": 4,
    "gtd": "001/ABC-09",
    "is_gtd_absent": false,
    "is_rnpt_absent": false,
    "product_id": 663001,
    "rnpt": null,
  },
  "method": "PUT",
  "path": "/operations/fbs-orders/order-wms663/ozon-exemplar-documents",
}

+ Received: 
[
  {
    "body": null,
    "method": "GET",
    "path": "/operations/packaging-tasks/task-wms663",
  },
  {
    "body": null,
    "method": "GET",
    "path": "/operations/fbs-orders/order-wms663/ozon-exemplar-documents",
  },
]

 ❯ src/screens/v2/FfFbsSupplyWorkspace.wms663.dom.test.tsx:279:22
    277|     await settle()
    278| 
    279|     expect(requests).toContainEqual({
       |                      ^
    280|       method: 'PUT',
    281|       path: DOCUMENTS_PATH,

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯


 Test Files  1 failed (1)
      Tests  1 failed (1)
   Start at  10:11:06
   Duration  136.39s (transform 530ms, setup 0ms, collect 134.99s, tests 628ms, environment 581ms, prepare 61ms)

```

## Проверка документов

Команда: `python3 scripts/ci/check_task_documents.py ae2ebd3d17f4e7364b1b52de4126b8f70937652b^`.

```text
WMS-663: Нет вердикта у проверки: C1
WMS-663: Нет вердикта у проверки: C2
WMS-663: Нет вердикта у проверки: C3
WMS-663: Нет вердикта у проверки: C4
WMS-663: Нет вердикта у проверки: C5
WMS-663: Нет вердикта у проверки: C6
WMS-663: Нет вердикта у проверки: C7
WMS-663: Нет вердикта у проверки: C8
WMS-663: Нет вердикта у проверки: C9
WMS-663: Нет вердикта у проверки: C10
WMS-663: Нет вердикта у проверки: C11
WMS-663: Нет вердикта у проверки: C12
WMS-663: Нет вердикта у проверки: C13
WMS-663: Нет вердикта у проверки: C14
WMS-663: Нет вердикта у проверки: C15
WMS-663: Нет вердикта у проверки: C16
WMS-663: Нет вердикта у проверки: C17
WMS-663: Нет вердикта у проверки: C18
WMS-663: Нет вердикта у проверки: C19
WMS-675: В таблице с колонкой «Класс» нет колонки «Тест».
изменён контракт тестов WMS-663 после его фиксации: backend/tests/test_wms663_customs_documents_contract.py, frontend/src/screens/v2/FfFbsSupplyWorkspace.wms663.dom.test.tsx
```

## DOM после коррекции: не завершён, GREEN не подтверждён

Команда та же, один worker. На момент SIGTERM вывод не содержал результатов тестов.

```text

 RUN  v3.2.6 /Users/deniscivkunov/Projects/WMS/.worktrees/wms662-663-priority/frontend

```
