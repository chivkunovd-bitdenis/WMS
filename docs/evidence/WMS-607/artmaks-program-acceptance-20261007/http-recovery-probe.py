"""One bounded analyst acceptance probe: existing legacy-browser /print shape.
Real candidate HTTP/resolver/Printer; only OS commands and storage are isolated.
"""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SOURCE_COMMIT = "de9f31a464fc09df26c6a77b488c904ea3ec19e2"
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8//8/AwMDEwMDAwMDAwAkBgMB/DXemwAAAABJRU5ErkJggg=="
with tempfile.TemporaryDirectory(prefix="wms607-acceptance-http-") as directory:
    root = Path(directory)
    queue_ready = root / "queue-ready"
    calls = root / "commands.jsonl"
    calls.write_text("")
    lpstat = root / "lpstat"
    lpstat.write_text(
        "#!"
        + sys.executable
        + "\n"
        + r"""
import json, os, sys
from pathlib import Path
root = Path(os.environ['WMS_ACCEPTANCE_ROOT'])
with (root/'commands.jsonl').open('a') as out: out.write(json.dumps(['lpstat']+sys.argv[1:])+'\n')
if not (root/'queue-ready').exists(): sys.exit(1)
print('system default destination: Label_Printer' if sys.argv[1:] == ['-d'] else 'printer Label_Printer is idle')
"""
    )
    lp = root / "lp"
    lp.write_text(
        "#!"
        + sys.executable
        + "\n"
        + r"""
import json, os, sys
from pathlib import Path
with (Path(os.environ['WMS_ACCEPTANCE_ROOT'])/'commands.jsonl').open('a') as out: out.write(json.dumps(['lp']+sys.argv[1:])+'\n')
print('request id is Label_Printer-41 (1 file)')
"""
    )
    lpstat.chmod(0o700)
    lp.chmod(0o700)
    source = subprocess.check_output(
        [
            "git",
            "show",
            SOURCE_COMMIT + ":tools/print-agent/wms_print_direct_macos.swift",
        ],
        text=True,
    )
    source = source.replace('"/usr/bin/lpstat"', json.dumps(str(lpstat))).replace(
        '"/usr/bin/lp"', json.dumps(str(lp))
    )
    source = source.replace(
        "FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]",
        'URL(fileURLWithPath: ProcessInfo.processInfo.environment["WMS_ACCEPTANCE_ROOT"]!)',
    )
    source += '\n@_cdecl("wms_cups_observe")\nfunc acceptanceObserve(_ queue: UnsafePointer<CChar>, _ receipt: UnsafePointer<CChar>, _ title: UnsafePointer<CChar>) -> Int32 { return 1 }\n'
    probe = root / "probe.swift"
    probe.write_text(source)
    executable = root / "probe"
    subprocess.run(
        ["swiftc", str(probe), "-o", str(executable)],
        check=True,
        capture_output=True,
        timeout=60,
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [str(executable)],
        env={
            **os.environ,
            "WMS_ACCEPTANCE_ROOT": str(root),
            "WMS_PRINT_PORT": str(port),
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    def request(path, body=None):
        req = Request(
            base + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "X-WMS-Print": "1",
                "Origin": "https://wms.sellerfocus.pro",
            },
        )
        try:
            with urlopen(req, timeout=25) as response:
                return {"http": response.status, "body": json.load(response)}
        except HTTPError as error:
            with error:
                return {"http": error.code, "body": json.load(error)}

    result = {
        "source_commit": SOURCE_COMMIT,
        "transport": "legacy POST /print, no protocolVersion or retry endpoint, as current printDirectQr.ts",
    }
    try:
        for _ in range(100):
            try:
                result["initial_health"] = request("/health")
                break
            except OSError:
                time.sleep(0.03)
        body = {
            "idempotencyKey": "same-scan",
            "imageDataUrl": "data:image/png;base64," + PNG,
            "widthMm": 58,
            "heightMm": 40,
        }
        result["before_restore"] = request("/print", body)
        queue_ready.touch()
        result["same_scan_after_restore"] = request("/print", body)
        result["same_scan_second_repeat"] = request("/print", body)
        result["new_scan_after_restore"] = request(
            "/print", {**body, "idempotencyKey": "other-scan"}
        )
        result["commands"] = [
            json.loads(line) for line in calls.read_text().splitlines()
        ]
        result["same_scan_detail"] = request("/jobs/same-scan")
        result["journal"] = json.loads(
            (root / "WMS Print/direct/direct-jobs.json").read_text()
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        process.terminate()
        process.wait(timeout=3)
        process.stderr.close()
