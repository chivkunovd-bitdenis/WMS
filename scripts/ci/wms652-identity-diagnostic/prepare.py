"""Generate untracked sibling copies. Reverse every insertion to prove exact bytes."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

SOURCE = "4c532f0cccfb8f99b34d68d9630a3763038fbc5f"
ROOT = Path(__file__).resolve().parents[3]
PREFIX = "frontend/tests-e2e/wms652-critical/"
BROWSER = PREFIX + "browser.mjs"
HERE = Path(__file__).resolve().parent
RUNNER = ROOT / (PREFIX + "browser.identity-diagnostic.untracked.mjs")
OBSERVER = ROOT / (PREFIX + "identity-observer.untracked.mjs")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def sha(data):
    return hashlib.sha256(data).hexdigest()


INSERTIONS = [
    (b"// WMS652 critical real-screen contracts.",
     b"import { createErrorContextObserver } from './identity-observer.untracked.mjs';\nconst errorContext=createErrorContextObserver();\n"),
    (b"      if (msg.id) {", b"      if (msg.error || msg.method) errorContext.message(this,msg);\n"),
    (b"  await writeFile(`${dir}/cdp-transport.json`",
     b"  await writeFile(`${dir}/error-context.json`,errorContext.serialize(cdp,report));\n"),
]


def transform(original):
    generated = original
    for anchor, insertion in INSERTIONS:
        if generated.count(anchor) != 1:
            raise ValueError(f"Expected one insertion anchor: {anchor!r}")
        generated = generated.replace(anchor, insertion + anchor, 1)
    recovered = generated
    for anchor, insertion in reversed(INSERTIONS):
        recovered = recovered.replace(insertion + anchor, anchor, 1)
    if recovered != original:
        raise ValueError("Reverse insertion failed byte equality")
    return generated, recovered


def verify_source():
    # Every original non-document file, including all product, frozen tests,
    # fixtures, lockfiles, policy and scripts, must equal exact failed etalon.
    # The isolated CI override is the sole original non-document exception.
    def tree(ref):
        return {line.split(b"\t", 1)[1].decode(): line.split(b"\t", 1)[0].decode()
                for line in git("ls-tree", "-rz", ref).split(b"\0") if line}
    source_tree, head_tree = tree(SOURCE), tree("HEAD")
    checked, local_hashes = {}, {}
    for name, binding in source_tree.items():
        if name.startswith("docs/") or name == ".github/workflows/ci.yml":
            continue
        if head_tree.get(name) != binding:
            raise ValueError(f"Source mismatch at HEAD: {name}")
        path = ROOT / name
        if path.is_file():
            data = path.read_bytes()
            blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            if blob != binding.split()[-1]:
                raise ValueError(f"Working file mismatch: {name}")
            local_hashes[name] = sha(data)
        checked[name] = binding
    for name in head_tree.keys() - source_tree.keys():
        if not name.startswith(("docs/", "scripts/ci/wms652-identity-diagnostic/")):
            raise ValueError(f"Unexpected non-document addition: {name}")
    return checked, local_hashes


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    bindings, hashes = verify_source()
    original = git("show", f"{SOURCE}:{BROWSER}")
    generated, recovered = transform(original)
    cases = json.loads((ROOT / (PREFIX + "cases.json")).read_text())
    if len(cases) != 43 or len(set(cases)) != 43:
        raise ValueError("Expected exact 43 unique frozen browser cases")
    for path in [RUNNER, OBSERVER]:
        if git("ls-files", "--", str(path.relative_to(ROOT))).strip():
            raise ValueError("Generated copy must be untracked")
        if path.exists():
            raise ValueError(f"Refusing to overwrite generated copy: {path}")
    observer = (HERE / "error-context.mjs").read_bytes()
    RUNNER.write_bytes(generated)
    OBSERVER.write_bytes(observer)
    (out / "frozen-browser-source.mjs").write_bytes(original)
    (out / "generated-browser.mjs").write_bytes(generated)
    (out / "generated-observer.mjs").write_bytes(observer)
    shell_source = git("show", f"{SOURCE}:scripts/ci/run_critical_fbs_browser.sh")
    old = b"node frontend/tests-e2e/wms652-critical/browser.mjs"
    new = b"node frontend/tests-e2e/wms652-critical/browser.identity-diagnostic.untracked.mjs"
    if shell_source.count(old) != 1:
        raise ValueError("Expected sole original browser invocation")
    shell_copy = shell_source.replace(old, new, 1)
    shell_path = ROOT / "scripts/ci/run_critical_fbs_browser.observed.untracked.sh"
    if shell_path.exists() or git("ls-files", "--", str(shell_path.relative_to(ROOT))).strip():
        raise ValueError("Refusing to overwrite shell copy")
    shell_path.write_bytes(shell_copy)
    (out / "original-shell.sh").write_bytes(shell_source)
    (out / "generated-shell.sh").write_bytes(shell_copy)
    receipt = {"source": SOURCE, "diagnostic_head": git("rev-parse", "HEAD").decode().strip(), "mode": "focused-error-context",
               "source_git_bindings": bindings, "source_sha256": hashes, "cases": cases, "insertions": len(INSERTIONS),
               "source_browser_sha256": sha(original), "reverse_recovered_sha256": sha(recovered),
               "reverse_byte_equal": recovered == original, "generated_browser_sha256": sha(generated),
               "generated_observer_sha256": sha(observer), "runner": str(RUNNER.relative_to(ROOT)),
               "observer": str(OBSERVER.relative_to(ROOT)), "source_shell_sha256": sha(shell_source),
               "generated_shell_sha256": sha(shell_copy), "shell_reverse_byte_equal": shell_copy.replace(new, old, 1) == shell_source}
    (out / "preparation.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: v for k, v in receipt.items() if k not in ["source_git_bindings", "source_sha256", "cases"]}, indent=2))


if __name__ == "__main__":
    main()
