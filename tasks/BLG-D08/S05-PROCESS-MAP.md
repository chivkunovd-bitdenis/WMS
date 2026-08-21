# S05 PROCESS_MAP - BLG-D08

## Scope and evidence correction

Backlog item `BLG-D08`: "Удалить или реально подключить мёртвый экран FfFbsPickList".

The backlog's starting observation is partially stale. `FfFbsPickList` has no
independent route or direct application entry point, but it is not imported
only by a test: `FfFbsSupplyDrawer` imports it and opens it from the
`Лист подбора` button. This map therefore decides whether that embedded
consumer represents a product role worth retaining.

Repository evidence used for this decision:

| Evidence | Observed fact | Process consequence |
| --- | --- | --- |
| `frontend/src/screens/v2/FfFbsSupplyDrawer.tsx:50,267,555-562,616-622` | The drawer is the only consumer: it owns `pickOpen`, exposes `Лист подбора`, and renders the dialog for the current `supplyId`. | The component is an embedded legacy action, not a standalone screen needing a route. |
| `frontend/src/screens/v2/FfFbsPickList.tsx:41-50,69-96,126-143` | It reads a picking list, saves collected/packed marks only to browser `localStorage`, and can request order stickers. | Its marks are not operational evidence and it mixes picking, packing, and sticker actions in one local dialog. |
| `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx:1026-1048` | The current FBS workspace presents picking as a server-backed operation: confirm a location, scan a product, then proceed to packing; it also owns printing the picking list. | The warehouse process already has an authoritative surface without this dialog. |
| `frontend/src/screens/v2/fbsApi.ts:538-577` and `FfFbsSupplyWorkspace.tsx:1032-1048` | The workspace starts supply work and records location/product scans through API calls; its text explicitly states that progress is stored on the server. | A second client-local progress model must not be kept as an alternative process. |

No live marketplace, production data, secret, or external API evidence is
needed for this code-cleanup decision.

## Current process

### Actor, entry point, and action

An FBS fulfilment operator opens an existing supply in `FfFbsSupplyDrawer` and
presses `Лист подбора`. The drawer opens `FfFbsPickList` for that supply. There
is no route, menu item, or other application consumer for the dialog.

### Data and observable behavior

1. The dialog requests `GET /operations/fbs-supplies/{id}/picking-list` and
   displays item quantity, article, and product name.
2. The operator can flag an article as collected or packed. Those flags are
   keyed by article and supply only in browser `localStorage`; another operator
   or device cannot treat them as warehouse state.
3. The operator can request FBS order stickers from the same dialog.
4. Closing the dialog cancels only the local view. Reopening reloads the list
   and restores whatever marks remain in that browser. API failure clears the
   displayed list and shows an error; an empty response renders an empty table.

This is a reachable UI path, but it is not a coherent operational process:
the same supply can instead be picked in `FfFbsSupplyWorkspace`, whose scan
sequence and persisted progress are the authoritative process.

## Target process and decision

**Decision: remove `FfFbsPickList` as a legacy embedded action; do not add a
new route or otherwise promote it to a separate screen.**

The operator's target process is:

1. Open the existing FBS supply workspace.
2. Start work for the supply, confirm a storage location, and scan products.
3. Observe server-backed picking progress and, when it is complete, continue
   to the existing packing stage.
4. Print the picking list from the workspace when a paper list is needed.

The later implementation must remove the drawer button/import/rendering and
the `FfFbsPickList` implementation, plus only the tests, generated inventory
entries, or references that name that removed component. It must not remove or
alter the workspace's server-backed picking, packing, or printing flow.

### Success, empty, error, repeat, and cancel states

- Success: the legacy dialog no longer presents local collected/packed marks;
  the operator has one authoritative FBS picking path in the workspace.
- Empty: when a supply has no pickable items, the workspace remains the place
  that explains the state; removal must not create a blank legacy dialog.
- Error: failures of the authoritative workspace API remain visible in that
  workspace. BLG-D08 must not hide or reinterpret them.
- Repeat: reopening or moving to another browser/device observes the same
  server-backed picking state, not a per-browser `localStorage` copy.
- Cancel: closing or leaving the workspace does not create a local substitute
  state and does not change a supply merely by viewing it.

## Boundaries for S06

S06 must classify the legacy drawer integration and component for removal, and
classify the existing workspace picking/printing process for reuse. It must
verify exact references before implementation; this S05 map authorizes no
runtime edit and no new screen.

## S05 verdict

`PROCESS_MAP_READY`: BLG-D08 now has a task-specific current-to-target process,
names `FfFbsSupplyDrawer` as the actual consumer, and records the
evidence-backed remove decision.
