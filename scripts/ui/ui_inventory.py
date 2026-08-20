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
FRONTEND = ROOT / "frontend"
REGISTRY = FRONTEND / "screens.registry.json"
SKIP_DIRS = {"ui-kit"}

STR = r"""['"]([^'"\n]{1,60})['"]"""

UI_KIT_COMPONENTS = {
    "ActionGroup": {
        "source": "frontend/src/ui-kit/Actions.tsx",
        "zone": "панель действий",
        "purpose": "Группа действий одной панели с ровной высотой и шириной кнопок.",
        "required_props": [],
        "optional_props": ["children"],
    },
    "ActionMenu": {
        "source": "frontend/src/ui-kit/Menu.tsx",
        "zone": "панель действий",
        "purpose": "Меню вторичных действий строки или документа.",
        "required_props": ["title", "options"],
        "optional_props": ["testId"],
    },
    "CheckboxField": {
        "source": "frontend/src/ui-kit/Forms.tsx",
        "zone": "фильтры/форма",
        "purpose": "Канонический флажок формы.",
        "required_props": ["label", "checked", "onChange"],
        "optional_props": ["disabled", "testId"],
    },
    "DangerAction": {
        "source": "frontend/src/ui-kit/Actions.tsx",
        "zone": "панель действий",
        "purpose": "Опасное действие: удаление, отмена, потеря данных.",
        "required_props": ["children"],
        "optional_props": ["disabledReason"],
    },
    "DataTable": {
        "source": "frontend/src/ui-kit/DataTable.tsx",
        "zone": "таблица",
        "purpose": "Единственная каноническая таблица WMS.",
        "required_props": ["columns", "rows", "getRowKey"],
        "optional_props": ["loading", "hasDiscrepancy", "empty", "testId"],
    },
    "EmptyState": {
        "source": "frontend/src/ui-kit/States.tsx",
        "zone": "состояния",
        "purpose": "Пустое состояние с действием или понятной подсказкой.",
        "required_props": ["title"],
        "optional_props": ["hint", "action", "testId"],
    },
    "ErrorNotice": {
        "source": "frontend/src/ui-kit/States.tsx",
        "zone": "состояния",
        "purpose": "Ошибка в теле экрана на языке склада.",
        "required_props": ["children"],
        "optional_props": ["testId"],
    },
    "FilterBar": {
        "source": "frontend/src/ui-kit/FilterBar.tsx",
        "zone": "фильтры",
        "purpose": "Панель поиска и фильтров над таблицей.",
        "required_props": ["search", "onSearchChange"],
        "optional_props": ["searchPlaceholder", "children", "testId"],
    },
    "IconAction": {
        "source": "frontend/src/ui-kit/Actions.tsx",
        "zone": "панель действий",
        "purpose": "Иконка-действие с обязательной подсказкой.",
        "required_props": ["title", "children"],
        "optional_props": ["testId", "onClick", "disabledReason"],
    },
    "MarkChip": {
        "source": "frontend/src/ui-kit/StatusChip.tsx",
        "zone": "статус/признак",
        "purpose": "Значок-признак товара, например ЧЗ.",
        "required_props": ["code", "hint"],
        "optional_props": ["testId"],
    },
    "ModalDialog": {
        "source": "frontend/src/ui-kit/Dialog.tsx",
        "zone": "модалка",
        "purpose": "Канонический диалог подтверждения или формы.",
        "required_props": ["open", "title", "onClose"],
        "optional_props": ["description", "children", "actions", "testId"],
    },
    "PlanFactCell": {
        "source": "frontend/src/ui-kit/Cells.tsx",
        "zone": "таблица",
        "purpose": "Ячейка план/факт с явным превышением.",
        "required_props": ["fact", "plan"],
        "optional_props": [],
    },
    "PrimaryAction": {
        "source": "frontend/src/ui-kit/Actions.tsx",
        "zone": "панель действий",
        "purpose": "Главное действие экрана или блока.",
        "required_props": ["children"],
        "optional_props": ["disabledReason"],
    },
    "PrintAction": {
        "source": "frontend/src/ui-kit/Actions.tsx",
        "zone": "панель действий",
        "purpose": "Единый вид печати в строке или панели.",
        "required_props": ["what", "placement"],
        "optional_props": ["onClick", "disabledReason", "testId"],
    },
    "ProductCell": {
        "source": "frontend/src/ui-kit/Cells.tsx",
        "zone": "таблица",
        "purpose": "Ячейка товара: фото и SKU, без склеивания артикулов.",
        "required_props": ["sku"],
        "optional_props": ["photo"],
    },
    "QtyCell": {
        "source": "frontend/src/ui-kit/Cells.tsx",
        "zone": "таблица",
        "purpose": "Числовая ячейка с табличными цифрами.",
        "required_props": ["value"],
        "optional_props": ["muted"],
    },
    "ScannerLine": {
        "source": "frontend/src/ui-kit/ScannerLine.tsx",
        "zone": "сканер",
        "purpose": "Строка состояния сканера.",
        "required_props": ["active", "expects"],
        "optional_props": ["testId"],
    },
    "ScreenHeader": {
        "source": "frontend/src/ui-kit/States.tsx",
        "zone": "шапка",
        "purpose": "Название экрана и одна строка назначения.",
        "required_props": ["title"],
        "optional_props": ["purpose"],
    },
    "ScreenSection": {
        "source": "frontend/src/ui-kit/Layout.tsx",
        "zone": "каркас",
        "purpose": "Единый outlined-блок для рабочей зоны экрана.",
        "required_props": ["children"],
        "optional_props": ["testId"],
    },
    "ScreenShell": {
        "source": "frontend/src/ui-kit/Layout.tsx",
        "zone": "каркас",
        "purpose": "Внешний каркас экрана с рабочей шириной WMS.",
        "required_props": ["children"],
        "optional_props": ["testId"],
    },
    "SecondaryAction": {
        "source": "frontend/src/ui-kit/Actions.tsx",
        "zone": "панель действий",
        "purpose": "Вторичное действие рядом с главным.",
        "required_props": ["children"],
        "optional_props": ["disabledReason"],
    },
    "SelectField": {
        "source": "frontend/src/ui-kit/Forms.tsx",
        "zone": "фильтры/форма",
        "purpose": "Канонический выпадающий список.",
        "required_props": ["value", "options", "onChange"],
        "optional_props": ["label", "testId"],
    },
    "StatusChip": {
        "source": "frontend/src/ui-kit/StatusChip.tsx",
        "zone": "статус/признак",
        "purpose": "Канонический статус документа или строки.",
        "required_props": ["label"],
        "optional_props": ["tone", "hint", "testId"],
    },
    "TableSkeletonBody": {
        "source": "frontend/src/ui-kit/States.tsx",
        "zone": "таблица",
        "purpose": "Скелетон загрузки строк таблицы.",
        "required_props": ["columns"],
        "optional_props": ["rows"],
    },
    "TabsBar": {
        "source": "frontend/src/ui-kit/Forms.tsx",
        "zone": "навигация/вкладки",
        "purpose": "Канонические вкладки внутри рабочего экрана.",
        "required_props": ["value", "tabs", "onChange"],
        "optional_props": ["testId"],
    },
    "TextCell": {
        "source": "frontend/src/ui-kit/Cells.tsx",
        "zone": "таблица",
        "purpose": "Текстовая ячейка с подсказкой полного значения.",
        "required_props": ["value"],
        "optional_props": ["width"],
    },
    "TextInput": {
        "source": "frontend/src/ui-kit/Forms.tsx",
        "zone": "фильтры/форма",
        "purpose": "Каноническое поле ввода.",
        "required_props": [],
        "optional_props": ["label", "value", "onChange", "testId"],
    },
    "ToolbarLine": {
        "source": "frontend/src/ui-kit/Layout.tsx",
        "zone": "панель действий",
        "purpose": "Строка действий или вкладок над рабочей зоной.",
        "required_props": ["children"],
        "optional_props": ["testId"],
    },
}


def iter_files():
    for path in sorted(SRC.rglob("*.tsx")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def exported_ui_kit_components() -> set[str]:
    index = SRC / "ui-kit" / "index.ts"
    text = index.read_text(encoding="utf-8")
    names: set[str] = set()
    for match in re.finditer(r"export\s+\{([^}]+)\}\s+from", text):
        for raw in match.group(1).split(","):
            name = raw.strip().split(" as ", 1)[0].strip()
            if name:
                names.add(name)
    return names


def screen_map():
    if not REGISTRY.exists():
        return {}
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    files = defaultdict(set)
    for screen in registry.get("screens", []):
        screen_id = screen.get("id")
        if not screen_id:
            continue
        for rel in screen.get("files", []):
            files[rel].add(screen_id)
        for rel, owners in screen.get("shared", {}).items():
            for owner in owners:
                files[rel].add(owner)
    return {rel: sorted(owners) for rel, owners in files.items()}


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
    component_usages = {
        name: {"files": set(), "screen_ids": set(), "observed_props": set(), "usages": 0}
        for name in UI_KIT_COMPONENTS
    }
    screen_ids_by_file = screen_map()

    for path in iter_files():
        rel = str(path.relative_to(FRONTEND))
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

        for component, meta in component_usages.items():
            for body in tag_bodies(text, component):
                meta["files"].add(rel)
                meta["screen_ids"].update(screen_ids_by_file.get(rel, []))
                meta["usages"] += 1
                for prop in re.findall(r"\s([A-Za-z_][\w]*)\s*=", body):
                    meta["observed_props"].add(prop)

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

    exported_components = exported_ui_kit_components()
    missing_metadata = sorted(exported_components - set(UI_KIT_COMPONENTS))
    if missing_metadata:
        raise RuntimeError(f"ui-kit export lacks inventory metadata: {', '.join(missing_metadata)}")

    components = []
    for name in sorted(exported_components):
        declared = UI_KIT_COMPONENTS[name]
        usage = component_usages[name]
        components.append(
            {
                "name": name,
                "source": declared["source"],
                "zone": declared["zone"],
                "purpose": declared["purpose"],
                "required_props": declared["required_props"],
                "optional_props": declared["optional_props"],
                "observed_props": sorted(usage["observed_props"]),
                "files": sorted(usage["files"]),
                "screen_ids": sorted(usage["screen_ids"]),
                "usages": usage["usages"],
            }
        )

    return {
        "chips": pack(chips),
        "statuses": pack(statuses),
        "buttons": pack(buttons),
        "alerts": pack(alerts),
        "components": components,
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
        "export type ComponentInventoryItem = {\n"
        "  name: string\n"
        "  source: string\n"
        "  zone: string\n"
        "  purpose: string\n"
        "  required_props: string[]\n"
        "  optional_props: string[]\n"
        "  observed_props: string[]\n"
        "  files: string[]\n"
        "  screen_ids: string[]\n"
        "  usages: number\n"
        "}\n\n"
        "export type UiInventory = {\n"
        "  chips: readonly InventoryItem[]\n"
        "  statuses: readonly InventoryItem[]\n"
        "  buttons: readonly InventoryItem[]\n"
        "  alerts: readonly InventoryItem[]\n"
        "  components: readonly ComponentInventoryItem[]\n"
        "}\n\n"
        f"export const INVENTORY = {json.dumps(data, ensure_ascii=False, indent=2)} as const satisfies UiInventory\n",
        encoding="utf-8",
    )

    for kind, items in data.items():
        print(f"{kind}: {len(items)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
