"""Prove preservation assertions using an automatically removed, untracked copy.

Only the exact utility read is redirected. Tracked product/test bytes never change.
Run from repository root: python3 docs/evidence/WMS-672/raster-resource-test-contract-20261007/mutation-proof.py
"""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[4]
evidence = Path(__file__).resolve().parent
utility = root / 'frontend/src/utils/printBarcodeLabel.ts'
test = root / 'frontend/tests-e2e/wms672-raster-resource.test.mjs'
original = utility.read_bytes()
anchor = 'const decodeImages = async () => {'
assert original.decode().count(anchor) == 1
replacement = anchor + "\n      images[0].style.imageRendering = 'auto' // purposeful leaked preparation style"
mutated = original.decode().replace(anchor, replacement)
with tempfile.TemporaryDirectory(prefix='.source-copy-', dir=evidence) as directory:
    copy = Path(directory) / 'printBarcodeLabel.ts'
    copy.write_text(mutated)
    preload = Path(directory) / 'redirect.cjs'
    preload.write_text(
        "const fs = require('node:fs');\n"
        "const {fileURLToPath} = require('node:url');\n"
        "const read = fs.readFileSync;\n"
        f"const target = {json.dumps(str(utility))};\n"
        f"const copy = {json.dumps(str(copy))};\n"
        "fs.readFileSync = function(path, ...args) {\n"
        "  const name = path instanceof URL ? fileURLToPath(path) : String(path);\n"
        "  return read.call(this, name === target ? copy : path, ...args);\n"
        "};\n"
        "require('node:module').syncBuiltinESMExports();\n"
    )
    command = ['node', '--require', str(preload), '--test', '--test-reporter=tap',
               '--test-name-pattern=RR[23]', str(test.relative_to(root))]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True)
    (evidence / 'mutation-style-leak.tap').write_text(result.stdout + result.stderr)
    assert result.returncode == 1, 'preservation corruption must fail'
    assert 'restore every original inline style exactly' in result.stdout
    assert '# pass 0' in result.stdout and '# fail 2' in result.stdout
assert utility.read_bytes() == original, 'tracked utility must remain unchanged'
(evidence / 'mutation-result.json').write_text(json.dumps({
    'mutation': 'leak image-rendering:auto on first original image after DOM snapshot',
    'target': str(utility.relative_to(root)),
    'copy_only': True, 'copy_automatically_removed': True,
    'original_sha256': hashlib.sha256(original).hexdigest(),
    'mutated_copy_sha256': hashlib.sha256(mutated.encode()).hexdigest(),
    'reproduce': 'python3 docs/evidence/WMS-672/raster-resource-test-contract-20261007/mutation-proof.py',
    'node_command': 'node --require <untracked-copy-reader.cjs> --test --test-reporter=tap --test-name-pattern=RR[23] frontend/tests-e2e/wms672-raster-resource.test.mjs',
    'exit_code': result.returncode, 'pass': 0, 'fail': 2,
    'failure_reason': 'restore every original inline style exactly',
    'tracked_utility_unchanged': True,
}, indent=2) + '\n')
print('Copy-only style-leak mutation: RR2 and RR3 fail on exact style restoration; tracked utility unchanged.')
