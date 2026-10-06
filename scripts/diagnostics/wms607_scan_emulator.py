"""Opt-in Mac integration: real scan controller -> HTTP -> native helper -> CUPS emulator.
Mock only WMS API dependencies; never touches production, printer settings or real journals.
"""

import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = (
    ROOT / "docs/evidence/wms607-artmaks" / os.environ.get("WMS607_EVIDENCE_SUFFIX", "")
)
KIT = ROOT.parent / "wms631-stand-kit"
with socket.socket() as s:
    s.bind(("127.0.0.1", 17843))  # refuse to replace an existing helper
assert (
    subprocess.check_output(["/usr/bin/lpstat", "-d"], text=True)
    .strip()
    .endswith(": WMS604_Proof")
)
assert (
    subprocess.check_output(["/usr/bin/lpstat", "-v", "WMS604_Proof"], text=True)
    .strip()
    .endswith("ipp://localhost:18631/ipp/print")
)
before = set((KIT / "printer-out").glob("*"))
with tempfile.TemporaryDirectory(prefix="wms607-scan-") as tmp:
    d = Path(tmp)
    source = (ROOT / "tools/print-agent/wms_print_direct_macos.swift").read_text()
    # Isolate only the journal path; all resolver, HTTP and printing code is unchanged.
    source = source.replace(
        'appSupport.appendingPathComponent("WMS Print/direct")',
        "URL(fileURLWithPath: " + json.dumps(str(d / "journal")) + ")",
    )
    swift = d / "helper.swift"
    swift.write_text(source)
    exe = d / "helper"
    subprocess.run(
        ["swiftc", str(swift), "-o", str(exe)], check=True, capture_output=True
    )
    original = (
        ROOT / "frontend/src/screens/v2/fbsSequentialPacking.test.ts"
    ).read_text()
    fixture = original.split("describe('WMS-604 sequential packing'")[0]
    test = ROOT / "frontend/src/screens/v2/wms607.artmaks.emulator.test.ts"
    test.write_text(
        fixture
        + """
import { spawn, type ChildProcess } from 'node:child_process'
import { readFileSync, existsSync } from 'node:fs'
import { once } from 'node:events'
import { printDirectQr } from '../../utils/printDirectQr'
it('ArtMaks: actual helper failure, next barcode blocked, same barcode recovers to emulator', async () => {
  let helper: ChildProcess | undefined
  const stop = async () => { if (helper && helper.exitCode === null) { const ended = once(helper, 'exit'); helper.kill(); await ended } }
  const start = async (fail: boolean) => {
    helper = spawn(process.env.PROBE_EXE!, [], {env: {...process.env, CUPS_SERVER: fail ? '127.0.0.1:18639' : '/private/var/run/cupsd'}})
    await once(helper.stdout!, 'data')
  }
  const {deps, scanner} = fixture()
  const barcode = '9990505160204'
  const key = `artmaks-emulator-${Date.now()}`
  const imageDataUrl = 'data:image/png;base64,' + readFileSync(process.env.PROBE_IMAGE!).toString('base64')
  const input = {idempotencyKey:key, imageDataUrl}
  deps.print = vi.fn(async () => printDirectQr(input))
  try {
    await start(true)
    await scanner.scan(barcode)
    await expect(scanner.scan('valid-kiz')).rejects.toThrow(process.env.EXPECTED_PRINT_ERROR || 'В системе не выбран принтер по умолчанию')
    expect(scanner.view()).toMatchObject({orderId:'1',needsKiz:false})
    expect(deps.pack).not.toHaveBeenCalled()
    expect(existsSync(process.env.PROBE_JOURNAL!)).toBe(false)
    await expect(scanner.scan('2009989263787')).rejects.toThrow('Повторите его штрихкод 9990505160204')
    expect(deps.print).toHaveBeenCalledTimes(1)
    await stop(); await start(false)
    await scanner.scan(barcode)
    expect(deps.pack).toHaveBeenCalledTimes(1)
    expect(deps.bind).toHaveBeenCalledTimes(1)
    expect(deps.select).toHaveBeenCalledTimes(1)
    expect(scanner.hasPending()).toBe(false)
    const before = readFileSync(process.env.PROBE_JOURNAL!, 'utf8')
    await printDirectQr(input)
    expect(readFileSync(process.env.PROBE_JOURNAL!, 'utf8')).toBe(before)
    console.log('REAL_HELPER_JOURNAL', before)
  } finally { await stop() }
}, 30000)
"""
    )
    try:
        env = dict(
            os.environ,
            PROBE_EXE=str(exe),
            PROBE_IMAGE=str(OUT / "emulator-input.png"),
            PROBE_JOURNAL=str(d / "journal/direct-jobs.json"),
        )
        r = subprocess.run(
            ["npx", "vitest", "run", str(test.relative_to(ROOT / "frontend"))],
            cwd=ROOT / "frontend",
            env=env,
            capture_output=True,
            text=True,
            timeout=65,
            check=False,
        )
        (OUT / "scan-emulator-test.log").write_text(r.stdout + r.stderr)
        print(r.stdout + r.stderr)
        assert r.returncode == 0
        (OUT / "scan-emulator-journal.json").write_bytes(
            (d / "journal/direct-jobs.json").read_bytes()
        )
        for _ in range(30):
            created = set((KIT / "printer-out").glob("*")) - before
            if any(p.suffix == ".png" for p in created):
                break
            time.sleep(1)
        assert len([p for p in created if p.suffix == ".pdf"]) == 1, created
        for p in created:
            if p.suffix in (".png", ".pdf", ".json"):
                (OUT / ("scan-" + p.name)).write_bytes(p.read_bytes())
        print("Exactly one emulator PDF and preview:", *[p.name for p in created])
    finally:
        test.unlink(missing_ok=True)
