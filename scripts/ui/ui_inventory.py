#!/usr/bin/env python3
"""Инвентаризация реальных элементов интерфейса WMS.

Витрина канона не сочиняется руками: она собирается из того, что уже есть в коде.
Скрипт проходит по frontend/src и вынимает фактические подписи чипов, кнопок и плашек
вместе с местом, где они живут. Результат — машиночитаемый JSON и типизированный
модуль для витрины. Появился новый элемент на экране — он попадает сюда следующим прогоном.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / "src"
SKIP_DIRS = {"ui-kit"}

STR = r"""['"]([^'"\n]{1,60})['"]"""


def iter_files():
    for path in sorted(SRC.rglob("*.tsx")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def tag_bodies(text: str, tag: str):
    """Куски исходника от <Tag до конца открывающего тега."""
    for match in re.finditer(rf"<{tag}\b", text):
        start = match.start()
        depth = 0
        for i in range(start, min(len(text), start + 2000)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            elif ch == ">" and depth == 0:
                yield text[start : i + 1]
                break


def label_values(tag_body: str) -> list[str]:
    """Значения атрибута label и только они.

    Без этого в инвентарь попадают data-testid, size и variant — то есть код,
    а не то, что видит оператор. Инвентарь должен содержать подписи, а не мусор.
    """
    match = re.search(r"label=", tag_body)
    if not match:
        return []
    rest = tag_body[match.end() :].lstrip()
    if rest.startswith(('"', "'")):
        quote = rest[0]
        end = rest.find(quote, 1)
        return [rest[1:end]] if end > 1 else []
    if not rest.startswith("{"):
        return []
    depth, chunk = 0, ""
    for ch in rest:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
        chunk += ch
    values = []
    for value in re.findall(STR, chunk):
        text = value.strip()
        # Отсекаем куски выражений вроде «]?.text ??» — это код, а не подпись.
        if not text or "?" in text or text.startswith(("]", ".", "[")):
            continue
        if not text[0].isalpha() and text != "—":
            continue
        values.append(text)
    return values


def collect():
    chips = defaultdict(lambda: {"tones": set(), "files": set()})
    buttons = defaultdict(lambda: {"variants": set(), "files": set()})
    alerts = defaultdict(lambda: {"files": set()})
    statuses = defaultdict(lambda: {"tones": set(), "files": set()})

    for path in iter_files():
        rel = str(path.relative_to(ROOT / "frontend"))
        text = path.read_text(encoding="utf-8", errors="replace")

        for body in tag_bodies(text, "Chip"):
            tone = re.search(rf"color=\{{?{STR}", body)
            tone_value = tone.group(1) if tone else "default"
            for label in label_values(body):
                chips[label]["tones"].add(tone_value)
                chips[label]["files"].add(rel)

        for match in re.finditer(r"<Button\b([^>]*)>([^<>{}]{1,60})</Button>", text, re.S):
            attrs, label = match.group(1), " ".join(match.group(2).split())
            if not label:
                continue
            variant = re.search(rf"variant=\{{?{STR}", attrs)
            color = re.search(rf"color=\{{?{STR}", attrs)
            buttons[label]["variants"].add(
                f"{variant.group(1) if variant else 'text'}/{color.group(1) if color else 'primary'}"
            )
            buttons[label]["files"].add(rel)

        for match in re.finditer(r"<Alert\b([^>]*)>([^<>{}]{1,90})</Alert>", text, re.S):
            attrs, label = match.group(1), " ".join(match.group(2).split())
            sev = re.search(rf"severity=\{{?{STR}", attrs)
            if label:
                alerts[f"{sev.group(1) if sev else 'info'}: {label}"]["files"].add(rel)

        # карты статусов вида { label: 'Собирается', color: 'warning' }
        for match in re.finditer(rf"label:\s*{STR}\s*,\s*color:\s*{STR}", text):
            statuses[match.group(1)]["tones"].add(match.group(2))
            statuses[match.group(1)]["files"].add(rel)

    def pack(store):
        return sorted(
            (
                {
                    "label": label,
                    "tones": sorted(meta.get("tones", [])),
                    "variants": sorted(meta.get("variants", [])),
                    "files": sorted(meta["files"]),
                    "usages": len(meta["files"]),
                }
                for label, meta in store.items()
            ),
            key=lambda item: (-item["usages"], item["label"]),
        )

    return {
        "chips": pack(chips),
        "statuses": pack(statuses),
        "buttons": pack(buttons),
        "alerts": pack(alerts),
    }


def main() -> int:
    data = collect()
    out_json = ROOT / "docs" / "product" / "ui-inventory.json"
    out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    ts = ROOT / "frontend" / "src" / "ui-kit" / "inventory.generated.ts"
    ts.write_text(
        "// СГЕНЕРИРОВАНО scripts/ui/ui_inventory.py — руками не править.\n"
        "// Витрина показывает только то, что реально есть в коде экранов.\n"
        "export type InventoryItem = {\n"
        "  label: string\n  tones: string[]\n  variants: string[]\n  files: string[]\n  usages: number\n}\n\n"
        f"export const INVENTORY = {json.dumps(data, ensure_ascii=False, indent=2)} as const satisfies\n"
        "  Record<'chips' | 'statuses' | 'buttons' | 'alerts', readonly InventoryItem[]>\n",
        encoding="utf-8",
    )

    for kind, items in data.items():
        print(f"{kind}: {len(items)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
