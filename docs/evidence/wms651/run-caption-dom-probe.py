"""One-off analyst evidence; does not change product, existing tests or guards.

Reuse the existing scan DOM fixture and helpers to mount the actual component.
Keep the generated harness within the evidence directory and remove it on exit.
Run from any directory: python3 docs/evidence/wms651/run-caption-dom-probe.py
"""

from pathlib import Path
import json
import os
import re
import signal
import subprocess
import tempfile


repo = Path(__file__).resolve().parents[3]
frontend = repo / "frontend"
fixture = frontend / "src/screens/v2/FfFbsSupplyWorkspace.scan.dom.test.tsx"
prefix = fixture.read_text().split("describe('WMS-575", 1)[0]
if "async function openPackingTab" not in prefix:
    raise RuntimeError("Existing fixture structure changed; inspect before rerunning")

# Resolve existing relative imports/mocks from their original directory.
prefix = re.sub(
    r"(['\"])(\.{1,2}/[^'\"]+)\1",
    lambda match: json.dumps(str((fixture.parent / match[2]).resolve())),
    prefix,
)
case = """
it('analyst WMS-651: actual component DOM shows the existing fixture counts', async () => {
  const initial = workspace()
  expect(initial.progress).toMatchObject({ packed: 0, total: 2 })
  await openPackingTab(initial)
  const caption = Array.from(document.querySelectorAll('p')).find(
    (node) => node.textContent?.includes('Обработано'),
  )
  expect(caption).toBeDefined()
  expect(caption!.textContent).toContain('Обработано 0 из 2')
  expect(caption!.textContent).toContain('Напечатано')
  expect(caption!.textContent).not.toContain('упаковано')
  expect(caption!.className).toContain('MuiTypography-body2')
  expect(document.querySelector('[data-testid="fbs-packing-select-all"]')).not.toBeNull()
  console.log('ACTUAL COMPONENT DOM:', caption!.outerHTML)
})
"""

with tempfile.TemporaryDirectory(prefix=".caption-dom-", dir=Path(__file__).parent) as tmp:
    folder = Path(tmp)
    (folder / "node_modules").symlink_to(frontend / "node_modules", target_is_directory=True)
    harness = folder / "caption.dom.test.tsx"
    harness.write_text(prefix + case)
    config = folder / "config.mjs"
    config.write_text(
        "export default "
        + json.dumps({
            "root": str(frontend),
            "esbuild": {"jsx": "automatic"},
            "test": {
                "environment": "jsdom",
                "include": [str(harness)],
                "testTimeout": 8000,
                "hookTimeout": 8000,
                "maxWorkers": 1,
                "minWorkers": 1,
            },
        })
    )
    process = subprocess.Popen(
        ["node", "node_modules/vitest/vitest.mjs", "run", "--config", str(config)],
        cwd=frontend,
        start_new_session=True,
    )
    try:
        code = process.wait(timeout=40)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        print("DOM probe: stopped at 40-second wall limit; no PASS result", flush=True)
        code = 124
    raise SystemExit(code)
