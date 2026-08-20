#!/usr/bin/env python3
"""Реестр экранов WMS: общий язык между человеком и агентами.

Пока у экрана нет кода и списка файлов, фраза «поправь третью колонку» означает
разное для разных агентов, а проверить границы правки нечем. Реестр собирается
из маршрутов приложения, поэтому не разъезжается с кодом.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / "src"

PORTALS = {
    "app": ("ff", SRC / "App.tsx"),
    "seller": ("seller", SRC / "apps" / "seller" / "SellerApp.tsx"),
}
COMPONENT_RE = re.compile(r"<\s*([A-Z][A-Za-z0-9_]*)")


def element_component(tag: str) -> str | None:
    """Первый настоящий экран внутри element={...}.

    Маршруты бывают завёрнуты в проверку прав и тернарник, поэтому
    просто «первый тег после element={» не годится: там сначала идёт условие.
    """
    start = tag.find("element=")
    if start == -1:
        return None
    for name in COMPONENT_RE.findall(tag[start:]):
        if name != "Navigate":
            return name
    return None
PATH_RE = re.compile(r'path="([^"]+)"')


def route_tags(text: str):
    """Тело каждого <Route ...> с учётом вложенного JSX в атрибутах.

    Простой регуляркой это не берётся: внутри element={<Screen />} есть свои «>»,
    поэтому идём по символам и считаем фигурные скобки.
    """
    for match in re.finditer(r"<Route\b", text):
        depth = 0
        for i in range(match.start(), min(len(text), match.start() + 4000)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            elif ch == ">" and depth == 0:
                yield text[match.start() : i + 1]
                break


IMPORT_RE = re.compile(r"""from\s+['"](\.[^'"]+)['"]""")
DEPTH = 2


def component_file(component: str) -> Path | None:
    for path in SRC.rglob("*.tsx"):
        if path.stem == component:
            return path
    return None


def local_imports(path: Path) -> list[Path]:
    """Локальные импорты файла, приведённые к существующим путям."""
    found = []
    for raw in IMPORT_RE.findall(path.read_text(encoding="utf-8", errors="replace")):
        target = (path.parent / raw).resolve()
        for candidate in (
            target.with_suffix(".tsx"),
            target.with_suffix(".ts"),
            target / "index.tsx",
            target / "index.ts",
        ):
            if candidate.exists() and SRC in candidate.parents:
                found.append(candidate)
                break
    return found


def screen_tree(component: str) -> list[str]:
    """Тело экрана: сам компонент плюс то, что он тянет за собой на два уровня.

    Один файл в границах — это неправда: правка каталога почти всегда задевает
    общий диалог печати или ячейки строки товара. Поэтому границы считаются
    по импортам, а какие из них общие — решает уже реестр целиком.
    """
    root = component_file(component)
    if root is None:
        return []
    seen = {root}
    frontier = [root]
    for _ in range(DEPTH):
        nxt = []
        for path in frontier:
            for dep in local_imports(path):
                if dep not in seen and "/ui-kit/" not in str(dep):
                    seen.add(dep)
                    nxt.append(dep)
        frontier = nxt
    return sorted(str(path.relative_to(ROOT / "frontend")) for path in seen)


def collect():
    screens = []
    for portal_key, (portal, entry) in PORTALS.items():
        if not entry.exists():
            continue
        text = entry.read_text(encoding="utf-8", errors="replace")
        for tag in route_tags(text):
            path_match = PATH_RE.search(tag)
            name = element_component(tag)
            if not path_match or not name:
                continue
            path = path_match.group(1)
            if path in {"*", "/"}:
                continue
            files = screen_tree(name)
            if not files:
                continue
            screens.append(
                {
                    "portal": portal,
                    "route": path if path.startswith("/") else f"/{portal_key}/{path}",
                    "component": name,
                    "files": files,
                    # Зоны экрана: словарь, которым агенты и человек называют одно и то же место.
                    "zones": ["шапка", "фильтры", "таблица", "панель действий", "модалка"],
                }
            )

    screens.sort(key=lambda item: (item["portal"], item["route"]))
    for index, screen in enumerate(screens, start=1):
        screen["id"] = f"S-{index:02d}"

    # Файл, который тянут несколько экранов, — общий слой. Правка в нём задевает
    # соседей, поэтому он не попадает в границы молча: его включают в наряд явно.
    owners: dict[str, list[str]] = {}
    for screen in screens:
        for path in screen["files"]:
            owners.setdefault(path, []).append(screen["id"])

    for screen in screens:
        own, shared = [], {}
        for path in screen["files"]:
            if len(owners[path]) == 1:
                own.append(path)
            else:
                shared[path] = owners[path]
        screen["files"] = own
        screen["shared"] = shared
    return screens


def main() -> int:
    screens = collect()
    out = ROOT / "frontend" / "screens.registry.json"
    out.write_text(
        json.dumps({"version": 1, "screens": screens}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"экранов в реестре: {len(screens)}")
    for screen in screens:
        print(f"  {screen['id']}  {screen['portal']:6} {screen['route']:34} {screen['component']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
