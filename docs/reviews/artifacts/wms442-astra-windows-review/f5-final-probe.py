"""Frozen F5 API-boundary review; no native printer, scheduler or WMS calls."""
import copy
import json
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
SHA = "e37d21925a4fc614a4843ecf3c95daee0b98e1af"


def frozen_module(name, filename):
    module = types.ModuleType(name)
    module.__file__ = str(ROOT / "tools/print-agent" / filename)
    sys.modules[name] = module
    source = subprocess.check_output(
        ["git", "show", f"{SHA}:tools/print-agent/{filename}"], cwd=ROOT
    )
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


frozen_module("wms_print_agent", "wms_print_agent.py")
runtime = frozen_module("wms442_f5_review", "wms_print_runtime.py")
results = []
for case, copies in [
    ("accepted", 1), ("accepted", 2), ("result_minus_one", 1),
    ("result_zero", 1), ("result_cancel", 1), ("copies_two", 1),
    ("missing_copies_bit", 1), ("missing_devmode", 1),
    ("missing_api", 1), ("api_error", 1),
]:
    events = []
    defaults = types.SimpleNamespace(
        Copies=2, Collate=1, Fields=0, DriverExtra=b"synthetic-private-data"
    )

    def document_properties(hwnd, handle, queue, output, input_, mode):
        events.append("DocumentProperties")
        assert hwnd == 0 and handle == queue == "Принтер склада 58"
        assert output is input_ and mode == 0xA
        assert output.Copies == 1 and output.Fields & 0x100
        assert output.DriverExtra == defaults.DriverExtra
        output.DriverExtra = b"synthetic-driver-merged-data"
        if case == "copies_two":
            output.Copies = 2
        if case == "missing_copies_bit":
            output.Fields &= ~0x100
        if case == "api_error":
            raise OSError("synthetic driver failure")
        return {"result_minus_one": -1, "result_zero": 0,
                "result_cancel": 2}.get(case, 1)

    def create_dc(driver, queue, devmode):
        events.append("CreateDC")
        assert driver == "WINSPOOL" and queue == "Принтер склада 58"
        assert devmode.Copies == 1 and devmode.Fields & 0x100
        assert devmode.DriverExtra == b"synthetic-driver-merged-data"
        return 17

    class DC:
        def GetDeviceCaps(self, key):
            return {88: 203, 90: 203, 110: 464, 111: 320,
                    8: 464, 10: 320, 112: 0, 113: 0}[key]

        def StartDoc(self, name):
            events.append("StartDoc")
            return 442

        def StartPage(self):
            events.append("StartPage")

        def EndPage(self):
            pass

        def EndDoc(self):
            events.append("EndDoc")

        def GetHandleOutput(self):
            return 17

        def DeleteDC(self):
            events.append("DeleteDC")

    printer_api = types.SimpleNamespace(
        OpenPrinter=lambda queue: queue,
        GetPrinter=lambda handle, level: {
            "pDevMode": None if case == "missing_devmode" else copy.deepcopy(defaults)
        },
        ClosePrinter=lambda handle: events.append("ClosePrinter"),
    )
    if case != "missing_api":
        printer_api.DocumentProperties = document_properties
    adapter = runtime.WindowsAdapter({
        "win32print": printer_api,
        "win32gui": types.SimpleNamespace(CreateDC=create_dc),
        "win32ui": types.SimpleNamespace(CreateDCFromHandle=lambda _: DC()),
        "ImageWin": types.SimpleNamespace(Dib=lambda _: types.SimpleNamespace(
            draw=lambda *args: events.append("draw")
        )),
    })
    with patch.object(adapter, "queues", return_value=["Принтер склада 58"]), \
         patch.object(adapter, "_pages", return_value=[(object(), 58, 40)]):
        try:
            outcome = adapter.submit(b"synthetic", "image/png", "Принтер склада 58", copies, 58, 40)
        except (ValueError, OSError) as error:
            outcome = type(error).__name__
    assert defaults.Copies == 2 and defaults.DriverExtra == b"synthetic-private-data"
    assert events.count("ClosePrinter") == 1
    if case == "accepted":
        assert outcome == "windows-442" and events.count("StartPage") == copies
        assert events.index("DocumentProperties") < events.index("CreateDC") < events.index("StartDoc")
    else:
        assert outcome in ("ValueError", "OSError")
        assert "CreateDC" not in events and "StartDoc" not in events
    results.append({"case": case, "copies": copies, "outcome": outcome,
                    "events": events, "global_defaults_unchanged": True})

print(json.dumps({"sha": SHA, "boundary": "Mock Windows APIs; no physical print",
                  "results": results}, indent=2, ensure_ascii=False))
