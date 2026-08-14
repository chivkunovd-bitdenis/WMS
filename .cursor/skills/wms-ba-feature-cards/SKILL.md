---
name: wms-ba-feature-cards
description: >-
  Обязательный BA-слой WMS gate: превращает любую задачу или поток требований в
  атомарные feature cards до Product review и разработки. Используется для любой
  WMS-задачи, если пользователь прямо не объявил emergency production hotfix.
---

# WMS BA Feature Cards

## Когда включать

Включай перед Product Agent и разработкой для любой WMS-задачи: баг, UI, backend,
процесс, FBS/FBO/WB/MP, приемка, отгрузка, упаковка, каталог, остатки, печать,
deploy/release или изменение видимого поведения.

Не классифицируй задачу как способ обхода gate. Любой вход превращается в
feature cards.

## Источники

1. `AGENTS.md`.
2. `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`.
3. `docs/MVP_DECISIONS_RU.md`.
4. Связанные текущие экраны, API и документы, если они нужны для понимания
   текущего поведения.

## Задача

Сформировать файл:

```text
docs/feature-gates/<YYYY-MM-DD>-<short-slug>/FEATURE_CARDS_RU.md
```

Код не менять. Dev tasks не писать. Техническое решение не проектировать глубже,
чем нужно для понимания границ.

## Карточка

```yaml
feature_id:
title:
source_task:
business_goal:
warehouse_user:
real_world_scenario:
current_problem:
target_process:
screen_or_flow:
primary_action:
secondary_actions:
required_visible_data:
explicitly_unnecessary_data:
success_state:
error_state:
empty_state:
roles_permissions:
tenant_seller_warehouse_scope:
external_dependencies:
business_assumptions:
open_questions:
status: BA_READY | BA_REWORK | BA_BLOCKED
```

Каждая карточка должна быть атомарной: один складской смысл, один основной
экран/процесс, один будущий Product verdict.
