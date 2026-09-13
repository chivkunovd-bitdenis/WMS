"""Regression checks for the WMS-442 GitHub release workflow."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PUBLISH_SCRIPT = ROOT / "tools/print-agent/publish_release.py"
WORKFLOW = ROOT / ".github/workflows/print-agent-package.yml"
ASSET_NAMES = (
    "WMS-Print-Installation.md",
    "WMS-Print-Setup-Windows-x64.exe",
    "WMS-Print-Setup-Windows-x64.exe.sha256",
    "WMS-Print-SHA256SUMS.txt",
    "WMS-Print-macOS.zip",
    "WMS-Print-macOS.zip.sha256",
)


FAKE_GH = r'''#!/usr/bin/env python3
import json
import os
import shutil
import sys
from pathlib import Path

root = Path(os.environ["FAKE_GH_ROOT"])
state_path = root / "state.json"
state = json.loads(state_path.read_text())
log_path = root / "commands.jsonl"
with log_path.open("a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\n")

arguments = sys.argv[1:]
if arguments[:2] == ["release", "view"]:
    if state.get("release") is None:
        print("not found", file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(state["release"]))
elif arguments[:2] == ["release", "download"]:
    name = arguments[arguments.index("--pattern") + 1]
    directory = Path(arguments[arguments.index("--dir") + 1])
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copy(root / "published" / name, directory / name)
elif arguments[:2] == ["release", "create"]:
    tag = arguments[2]
    commit = arguments[arguments.index("--target") + 1]
    asset_paths = [Path(argument) for argument in arguments[arguments.index("--draft") + 1:]]
    published = root / "published"
    published.mkdir(exist_ok=True)
    for path in asset_paths:
        shutil.copy(path, published / path.name)
    state["release"] = {
        "isDraft": True,
        "targetCommitish": commit,
        "assets": [{"name": path.name} for path in asset_paths],
    }
    state_path.write_text(json.dumps(state))
elif arguments[:2] == ["release", "edit"]:
    state["release"]["isDraft"] = False
    state_path.write_text(json.dumps(state))
else:
    print("unsupported fake gh call", arguments, file=sys.stderr)
    raise SystemExit(2)
'''


class PublishReleaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.assets_dir = self.root / "assets"
        self.assets_dir.mkdir()
        for name in ASSET_NAMES:
            (self.assets_dir / name).write_bytes(f"asset:{name}".encode())
        self.notes_file = self.root / "notes.md"
        self.notes_file.write_text("notes")
        self.fake_bin = self.root / "bin"
        self.fake_bin.mkdir()
        fake_gh = self.fake_bin / "fake-gh.py"
        fake_gh.write_text(FAKE_GH)
        fake_gh.chmod(0o755)
        (self.root / "commands.jsonl").touch()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def set_release(self, *, draft: bool, commit: str = "commit-1", names: tuple[str, ...] = ASSET_NAMES) -> None:
        published = self.root / "published"
        published.mkdir(exist_ok=True)
        for name in names:
            (published / name).write_bytes((self.assets_dir / name).read_bytes())
        (self.root / "state.json").write_text(
            json.dumps({"release": {"isDraft": draft, "targetCommitish": commit, "assets": [{"name": name} for name in names]}})
        )

    def run_publish(self) -> subprocess.CompletedProcess[str]:
        if not (self.root / "state.json").exists():
            (self.root / "state.json").write_text(json.dumps({"release": None}))
        environment = os.environ | {
            "FAKE_GH_ROOT": str(self.root),
            "WMS_PRINT_GH": shlex.join([sys.executable, str(self.fake_bin / "fake-gh.py")]),
        }
        return subprocess.run(
            [
                sys.executable,
                str(PUBLISH_SCRIPT),
                "--tag",
                "wms-print-vtest",
                "--source-commit",
                "commit-1",
                "--assets-dir",
                str(self.assets_dir),
                "--notes-file",
                str(self.notes_file),
            ],
            text=True,
            capture_output=True,
            env=environment,
        )

    def commands(self) -> list[list[str]]:
        return [json.loads(line) for line in (self.root / "commands.jsonl").read_text().splitlines()]

    def test_existing_matching_public_release_is_not_replaced(self) -> None:
        self.set_release(draft=False)

        result = self.run_publish()

        self.assertEqual(result.returncode, 0, result.stderr)
        commands = self.commands()
        self.assertFalse(any(command[:2] in (["release", "create"], ["release", "edit"], ["release", "upload"]) for command in commands))

    def test_different_or_incomplete_public_release_is_left_unchanged(self) -> None:
        self.set_release(draft=False, names=ASSET_NAMES[:-1])

        result = self.run_publish()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to replace", result.stderr)
        self.assertFalse(any(command[:2] in (["release", "create"], ["release", "edit"], ["release", "upload"]) for command in self.commands()))

    def test_matching_names_with_different_content_are_left_unchanged(self) -> None:
        self.set_release(draft=False)
        (self.root / "published" / ASSET_NAMES[0]).write_bytes(b"different published content")

        result = self.run_publish()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("differs from this build", result.stderr)
        self.assertFalse(any(command[:2] in (["release", "create"], ["release", "edit"], ["release", "upload"]) for command in self.commands()))

    def test_new_release_stays_draft_until_complete_bundle_is_verified(self) -> None:
        result = self.run_publish()

        self.assertEqual(result.returncode, 0, result.stderr)
        commands = self.commands()
        create_index = next(index for index, command in enumerate(commands) if command[:2] == ["release", "create"])
        edit_index = next(index for index, command in enumerate(commands) if command[:2] == ["release", "edit"])
        self.assertIn("--draft", commands[create_index])
        self.assertLess(create_index, edit_index)
        self.assertFalse(json.loads((self.root / "state.json").read_text())["release"]["isDraft"])


class WorkflowTriggerTest(unittest.TestCase):
    def test_branch_and_tag_pushes_keep_their_separate_contracts(self) -> None:
        workflow = WORKFLOW.read_text()

        self.assertIn("    branches:\n      - '**'", workflow)
        self.assertIn("    tags:\n      - 'wms-print-v*'", workflow)
        self.assertIn("python tools/print-agent/publish_release.py", workflow)
        self.assertNotIn("gh release upload", workflow)
        self.assertNotIn("--clobber", workflow)


if __name__ == "__main__":
    unittest.main()
