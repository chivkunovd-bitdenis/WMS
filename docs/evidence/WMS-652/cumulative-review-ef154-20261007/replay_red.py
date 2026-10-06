"""Run the new positive frozen contracts against the previous PASS source."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import types
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
FIXTURE = ROOT / '.review-fixture-ef154'
sys.path.insert(0, str(FIXTURE))

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, FIXTURE / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def previous(path, name):
    module = types.ModuleType(name)
    module.__file__ = str(FIXTURE / path)
    raw = subprocess.check_output(['git', '-C', str(ROOT), 'show', '65049df62d2bac87932fc5349f6326caec43dea5:' + path])
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module

docs = load('scripts/ci/test_check_task_documents.py', 'review_red_docs')
promote = load('scripts/ci/tests/test_promote_guards.py', 'review_red_promote')
docs.checker = previous('scripts/ci/check_task_documents.py', 'review_previous_checker')
docs.GitTests.current_integration_checker = staticmethod(lambda: docs.checker)
promote.promoter = previous('scripts/ci/promote_guards.py', 'review_previous_promoter')
names = ['test_legacy_wms654_exact_files_ledger_keeps_accepted_report_without_report_commit',
         'test_wms658_published_exact_chain_with_own_test_links_is_accepted',
         'test_wms681_published_two_by_two_exact_chain_is_accepted',
         'test_protected_wms687_expanded_inbound_reference_uses_exact_receipt_case',
         'test_protected_wms687_expanded_return_reference_uses_exact_receipt_case',
         'test_wms680_owner_semantic_and_fixture_matrix_is_registered_exactly']
suite = unittest.TestSuite(docs.GitTests(name) for name in names)
suite.addTest(promote.PromoteGuardsTests('test_protected_wms687_each_uses_the_two_exact_executed_case_ids'))
with (HERE / 'independent-red.log').open('w') as output:
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
assert result.testsRun == 7 and len(result.failures) + len(result.errors) == 7
print('Confirmed RED: all seven new positive contracts reject previous 65049 implementation')
