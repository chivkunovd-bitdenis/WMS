# WMS-661 · RED до механического переноса продукта

Контракт: `9121085109c8caa53f7d0d2ad7d9ebd93b1d7028`.
Продукт полностью совпадает с `8cd8db61598e6c80c91d7eff13301230a4ca6102`:
`git diff 8cd8db61598e6c80c91d7eff13301230a4ca6102 -- tools/support_agent/support_agent`
пуст. Два тестовых blob совпадают с окончательным db5, ожидания не изменены.

Команда из tools/support_agent (без записи bytecode и pytest cache):
`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_wms661_precreation_search.py tests/test_wms661_minimal_support.py -q --tb=short -p no:cacheprovider`

Код выхода: 1. Совпали все шесть исходных содержательных RED C1–C6;
56 GREEN. Не падения исправленного installed_paraphrase, не ошибки окружения.

```text
FFFFFF........................................................           [100%]
=================================== FAILURES ===================================
_______ test_c1_synonymous_new_source_reuses_canonical_task_before_draft _______
tests/test_wms661_precreation_search.py:372: in test_c1_synonymous_new_source_reuses_canonical_task_before_draft
    assert_reused(env)
tests/test_wms661_precreation_search.py:357: in assert_reused
    assert_search_before_record(env)
tests/test_wms661_precreation_search.py:352: in assert_search_before_record
    assert max(context + searches + backlog + docs) < record, (
E   AssertionError: ('current-task/backlog search and candidate reads must precede even unconfirmed task_record', [('task_record', {'chat_...'offset': 0, 'path': 'docs/KANONICHESKIY_BACKLOG.md'}), ('read_file', {'path': 'docs/requirements/WMS-9001.md'}), ...])
E   assert 6 < 0
E    +  where 6 = max(((([2, 6] + [3]) + [4]) + [5]))
_________ test_c2_backlog_only_candidate_is_read_outside_recent_tasks __________
tests/test_wms661_precreation_search.py:378: in test_c2_backlog_only_candidate_is_read_outside_recent_tasks
    env.run()
tests/test_wms661_precreation_search.py:332: in <lambda>
    env.run = lambda: agent.run_topic_turn(topic, {"id": 106, "kind": "input"}, source)
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
support_agent/agent_coordinator.py:248: in run_topic_turn
    result = self.llm.agent_turn(
tests/test_wms661_precreation_search.py:251: in agent_turn
    assert env.candidate_title in payload, "read_context(ticket_id=31) omitted selected candidate"
E   AssertionError: read_context(ticket_id=31) omitted selected candidate
E   assert 'Показывать причину непризнанного скана при упаковке FBS' in '{"messages": [{"id": 101, "source": "telegram", "chat_id": 900, "msg_id": "101", "role": "owner", "author_id": "42", ...pic_key": "old-scan-reason", "version": "old-version", "owner_approval": {"version": "old-version"}}}}], "memory": {}}'
E    +  where 'Показывать причину непризнанного скана при упаковке FBS' = namespace(store=<tests.test_wms661_precreation_search.MemoryStore object at 0x10a4282d0>, cfg=Config(state_dir='/priva...y_to': None, 'ticket_id': None, 'revision': 0}, run=<function scenario.<locals>.make.<locals>.<lambda> at 0x10a45d4e0>).candidate_title
__ test_c3_independent_new_request_creates_one_confirmed_bundle_after_search ___
tests/test_wms661_precreation_search.py:385: in test_c3_independent_new_request_creates_one_confirmed_bundle_after_search
    assert_search_before_record(env)
tests/test_wms661_precreation_search.py:352: in assert_search_before_record
    assert max(context + searches + backlog + docs) < record, (
E   AssertionError: ('current-task/backlog search and candidate reads must precede even unconfirmed task_record', [('task_record', {'chat_...'offset': 0, 'path': 'docs/KANONICHESKIY_BACKLOG.md'}), ('read_file', {'path': 'docs/requirements/WMS-9001.md'}), ...])
E   assert 6 < 0
E    +  where 6 = max(((([2, 6] + [3]) + [4]) + [5]))
___________ test_c4_shared_supply_object_different_action_can_be_new ___________
tests/test_wms661_precreation_search.py:398: in test_c4_shared_supply_object_different_action_can_be_new
    assert_search_before_record(env)
tests/test_wms661_precreation_search.py:352: in assert_search_before_record
    assert max(context + searches + backlog + docs) < record, (
E   AssertionError: ('current-task/backlog search and candidate reads must precede even unconfirmed task_record', [('task_record', {'chat_...'offset': 0, 'path': 'docs/KANONICHESKIY_BACKLOG.md'}), ('read_file', {'path': 'docs/requirements/WMS-9001.md'}), ...])
E   assert 6 < 0
E    +  where 6 = max(((([2, 6] + [3]) + [4]) + [5]))
_________ test_c5_large_backlog_candidate_after_first_window_is_reused _________
tests/test_wms661_precreation_search.py:410: in test_c5_large_backlog_candidate_after_first_window_is_reused
    env.run()
tests/test_wms661_precreation_search.py:332: in <lambda>
    env.run = lambda: agent.run_topic_turn(topic, {"id": 106, "kind": "input"}, source)
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
support_agent/agent_coordinator.py:248: in run_topic_turn
    result = self.llm.agent_turn(
tests/test_wms661_precreation_search.py:251: in agent_turn
    assert env.candidate_title in payload, "read_context(ticket_id=31) omitted selected candidate"
E   AssertionError: read_context(ticket_id=31) omitted selected candidate
E   assert 'Показывать причину непризнанного скана при упаковке FBS' in '{"messages": [{"id": 101, "source": "telegram", "chat_id": 900, "msg_id": "101", "role": "owner", "author_id": "42", ...pic_key": "old-scan-reason", "version": "old-version", "owner_approval": {"version": "old-version"}}}}], "memory": {}}'
E    +  where 'Показывать причину непризнанного скана при упаковке FBS' = namespace(store=<tests.test_wms661_precreation_search.MemoryStore object at 0x10a4069e0>, cfg=Config(state_dir='/priva...y_to': None, 'ticket_id': None, 'revision': 0}, run=<function scenario.<locals>.make.<locals>.<lambda> at 0x10a3bab90>).candidate_title
______ test_c6_actual_topic_instructions_require_search_before_even_draft ______
tests/test_wms661_precreation_search.py:422: in test_c6_actual_topic_instructions_require_search_before_even_draft
    assert_instruction_contract(system)
tests/test_wms661_precreation_search.py:69: in assert_instruction_contract
    assert normative, "loaded instructions lack mandatory current-task AND canonical-backlog search BEFORE creation"
E   AssertionError: loaded instructions lack mandatory current-task AND canonical-backlog search BEFORE creation
E   assert []
=========================== short test summary info ============================
FAILED tests/test_wms661_precreation_search.py::test_c1_synonymous_new_source_reuses_canonical_task_before_draft
FAILED tests/test_wms661_precreation_search.py::test_c2_backlog_only_candidate_is_read_outside_recent_tasks
FAILED tests/test_wms661_precreation_search.py::test_c3_independent_new_request_creates_one_confirmed_bundle_after_search
FAILED tests/test_wms661_precreation_search.py::test_c4_shared_supply_object_different_action_can_be_new
FAILED tests/test_wms661_precreation_search.py::test_c5_large_backlog_candidate_after_first_window_is_reused
FAILED tests/test_wms661_precreation_search.py::test_c6_actual_topic_instructions_require_search_before_even_draft
6 failed, 56 passed in 0.44s
```
