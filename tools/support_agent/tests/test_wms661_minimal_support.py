"""C7, one-off WMS-661 scope check with synthetic unsafe mutations.

Checks product/config delta against the installed reviewed base. This bounded
static check is not independent review and cannot prove arbitrary code safe.
"""
from __future__ import annotations

import ast
import re
import subprocess
from collections import Counter
from pathlib import Path

import pytest

BASE = "8cd8db61598e6c80c91d7eff13301230a4ca6102"
ROOT = Path(__file__).resolve().parents[3]
RUNTIME = "tools/support_agent/support_agent"
PAID_METHODS = {"ask", "ask_json", "agent_turn", "responses", "chat_completion"}


def features(source: str) -> Counter[str]:
    tree = ast.parse(source)
    result: Counter[str] = Counter()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if re.search(r"\b(?:CREATE\s+TABLE|ALTER\s+TABLE)\b", node.value, re.I):
                result["database schema"] += 1
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            if any(term in name.lower() for term in ("embedding", "vectorstore", "vector_store")):
                result["embedding/vector infrastructure"] += 1
            if isinstance(node.func, ast.Attribute) and node.func.attr in PAID_METHODS:
                result["paid model invocation"] += 1
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names]
            if isinstance(node, ast.ImportFrom):
                names.append(node.module or "")
            if any(re.search(r"(?:sentence_transformers|chromadb|faiss|pinecone|pgvector)", name)
                   for name in names):
                result["embedding/vector infrastructure"] += 1
    return result


def assert_minimal_support(delta: dict[str, tuple[str, str]]) -> None:
    violations = []
    for path, (before, after) in delta.items():
        if path.endswith(".py"):
            new = features(after or "") - features(before or "")
            violations.extend(f"{path}: added {name}" for name in new)
            if not before and re.search(r"(?:search_service|dedup_service|embedding|vector)", Path(path).stem):
                violations.append(f"{path}: separate search infrastructure")
        elif Path(path).name.startswith("requirements") or path.endswith("pyproject.toml"):
            added = set(after.splitlines()) - set(before.splitlines())
            if any(re.search(r"sentence-transformers|chromadb|faiss|pinecone|pgvector", line, re.I)
                   for line in added):
                violations.append(f"{path}: added vector/search dependency")
    assert not violations, "WMS-661 must use existing instructions/tools without extra infrastructure: " + "; ".join(violations)


def git(*args: str, allow_missing: bool = False) -> str:
    run = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    if allow_missing and run.returncode:
        return ""
    assert run.returncode == 0, run.stderr
    return run.stdout


def test_c7_actual_delta_uses_existing_tools_without_new_paid_or_schema_work() -> None:
    paths = set(git("diff", "--name-only", BASE, "--", RUNTIME,
                    "tools/support_agent/requirements.txt", "tools/support_agent/pyproject.toml").splitlines())
    # Include untracked production files, not only diff of already tracked code.
    paths.update(git("ls-files", "--others", "--exclude-standard", "--", RUNTIME).splitlines())
    delta = {}
    for path in paths:
        current = ROOT / path
        delta[path] = (git("show", f"{BASE}:{path}", allow_missing=True),
                       current.read_text(encoding="utf-8") if current.is_file() else "")
    assert_minimal_support(delta)


@pytest.mark.parametrize("unsafe", [
    'def dedup(db):\n    db.execute("CREATE TABLE task_vectors (id INTEGER)")\n',
    'def dedup(llm):\n    return llm.ask_json("dedup", "extra paid request")\n',
    'def dedup(client):\n    return client.embeddings.create(input="new task")\n',
    'import chromadb\n',
])
def test_c7_synthetic_unsafe_addition_is_detected(unsafe: str) -> None:
    with pytest.raises(AssertionError, match="added"):
        assert_minimal_support({f"{RUNTIME}/agent_tools.py": ("", unsafe)})


def test_c7_necessary_existing_tool_extension_is_allowed() -> None:
    assert_minimal_support({f"{RUNTIME}/agent_tools.py": (
        'def read_context(store):\n    return store.rows("SELECT * FROM tickets LIMIT 30")\n',
        'def read_context(store, before_id):\n    return store.rows("SELECT * FROM tickets WHERE id<?", (before_id,))\n',
    )})
