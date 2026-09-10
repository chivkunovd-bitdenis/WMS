import importlib, subprocess, pytest
class BaselineOwnedServices:
    def pytest_configure(self, config):
        for name in ("inbound_intake_service", "inbound_intake_box_service",
                     "marketplace_unload_service", "marketplace_unload_box_service"):
            module = importlib.import_module("app.services." + name)
            source = subprocess.check_output([
                "git", "show", "1b754d83:backend/app/services/" + name + ".py"
            ], text=True)
            exec(compile(source, "baseline-1b754d83/" + name + ".py", "exec"), module.__dict__)
print("Read-only runtime probe: owned services from 1b754d83; checkout files unchanged")
raise SystemExit(pytest.main([
    "-q", "tests/test_inbound_intake_service_be01.py::test_loose_only_receiving_no_boxes",
    "--tb=short"
], plugins=[BaselineOwnedServices()]))
