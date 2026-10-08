"""WMS-710 C15: исключение «только для Империи ФФ» заметно в проекте (R12).

Проверка наличия, а не смысла: есть запись в реестре клиентских исключений,
в коде у признака есть ссылка на реестр, а в AGENTS.md и CLAUDE.md одна и та же
строка со ссылкой на реестр. Файлы AGENTS.md и CLAUDE.md обязаны совпадать.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = REPO_ROOT / "docs" / "KLIENTSKIE_ISKLYUCHENIYA.md"
REGISTRY_NAME = "KLIENTSKIE_ISKLYUCHENIYA"
IMPERIYA_UUID = "7b98a8aa-c03c-4649-9677-a645be45c622"
CODE_ROOTS = (REPO_ROOT / "backend" / "app", REPO_ROOT / "frontend" / "src")


def test_client_exception_registry_has_imperiya_entry() -> None:
    assert REGISTRY.is_file(), "нет реестра docs/KLIENTSKIE_ISKLYUCHENIYA.md"
    text = REGISTRY.read_text(encoding="utf-8")
    assert IMPERIYA_UUID in text
    assert "Империя ФФ" in text
    assert "WMS-710" in text
    assert "снять" in text.lower(), "в записи нет условия снятия исключения"


def test_code_comment_points_to_registry() -> None:
    referencing = [
        path
        for root in CODE_ROOTS
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".py", ".ts", ".tsx"}
        and REGISTRY_NAME in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert referencing, "в коде нет комментария со ссылкой на реестр исключений"


def test_agents_and_claude_carry_the_same_registry_line() -> None:
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    claude = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert agents == claude, "AGENTS.md и CLAUDE.md должны совпадать побайтно"
    assert any(REGISTRY_NAME in line and "Империи" in line for line in agents.splitlines())
