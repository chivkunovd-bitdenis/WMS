"""Prove green preservation cases reject broad retirement in a temporary source COPY."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[4]
evidence = Path(__file__).resolve().parent
browser = root / 'frontend/tests-e2e/wms652-critical/browser.mjs'
original = browser.read_bytes()
anchor = 'msg.error ? p.reject(Error(JSON.stringify(msg.error))) : p.resolve(msg.result)'
assert original.decode().count(anchor) == 1
mutated = original.decode().replace(anchor,
    'msg.error ? p.resolve({retired:true,nativeError:msg.error}) : p.resolve({retired:true,nativeResult:msg.result})')
with tempfile.TemporaryDirectory(prefix='.cdp-source-copy-', dir=evidence) as directory:
    copy = Path(directory) / 'browser.mjs'
    copy.write_text(mutated)
    preload = Path(directory) / 'redirect.cjs'
    preload.write_text("const fs = require('node:fs');\nconst {fileURLToPath} = require('node:url');\nconst read = fs.readFileSync;\n"
        + f"const target={json.dumps(str(browser))}, copy={json.dumps(str(copy))};\n"
        + "fs.readFileSync = function(path,...args){const name=path instanceof URL?fileURLToPath(path):String(path);return read.call(this,name===target?copy:path,...args);};\n"
        + "require('node:module').syncBuiltinESMExports();\n")
    command = ['node', '--require', str(preload), '--test', '--test-reporter=tap',
               '--test-name-pattern=CDP[34]', 'frontend/tests-e2e/wms652-cdp-cancellation.test.mjs']
    result = subprocess.run(command, cwd=root, capture_output=True, text=True)
    (evidence / 'mutation-preservation.tap').write_text(result.stdout + result.stderr)
    assert result.returncode == 1 and '# fail 2' in result.stdout and '# pass 0' in result.stdout
    assert 'unproven/other transport failures stay rejected' in result.stdout
    assert 'navigation alone does not retire a live interception' in result.stdout
assert browser.read_bytes() == original
(evidence / 'mutation-result.json').write_text(json.dumps({
    'mutation': 'Real CDP source-copy native reply branch resolves both errors and valid results as retired.',
    'original_sha256': hashlib.sha256(original).hexdigest(),
    'mutated_copy_sha256': hashlib.sha256(mutated.encode()).hexdigest(),
    'reproduce': 'python3 -B docs/evidence/WMS-652/cdp-cancellation-test-contract-20261007/mutation-proof.py',
    'pass': 0, 'fail': 2, 'skipped': 0, 'exit_code': result.returncode,
    'tracked_browser_unchanged': True, 'temporary_copy_removed': True,
}, indent=2) + '\n')
print('Copy-only broad retirement rejected by CDP3/CDP4;2 meaningful FAIL,0 setup errors; tracked browser unchanged.')
