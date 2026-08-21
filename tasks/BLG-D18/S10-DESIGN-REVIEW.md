# S10 DESIGN_REVIEW - BLG-D18

Role: `pipeline-product`
Agent: `codex-pipeline-product-blg-d18-s10`
Model policy: `gpt-5.6-sol` / `expensive`
Reviewed input: `tasks/BLG-D18/S09-UX-CONTRACT.md`
Canon: `docs/product/UX_CANON_RU.md`
Verdict: `DESIGN_REWORK`
Return stage: `S09 UX_CONTRACT_AND_MOCKUPS`

## Decision

The operator outcome is valid: a manually entered marking code must not look
absent merely because the printed text leaves `I`, `l`, `1`, `O`, and `0`
ambiguous; the interface must expose candidate matches without changing the
stored code.

The supplied S09 artifact cannot be approved. It is a generic ui-kit inventory
and state checklist, not a reviewable mockup of this search flow. It does not
identify the screen, define the visible search/result behavior, or show how an
operator distinguishes an exact match from candidates produced by ambiguous
characters.

## Blocking design findings

### DR-1 - The affected screen and zone are not identified

S09 refers to removing confusion "from the card" but names no registry screen,
route, actor surface, or touched zone. The repository currently has at least two
plausible manual-diagnostics surfaces: screen `S-07` at
`/app/ff/honest-sign/ledger` with `Поиск КМ`, and screen `S-08` at
`/app/ff/honest-sign/pool/:poolId` with `Хвост КМ`. These are materially
different scopes and result sets.

Required S09 rework: name the exact registry screen, route, actor role and
touched zones. State explicitly whether the other marking-code search surfaces
remain unchanged or must share the same behavior. Preserve untouched legacy
zones; do not imply a whole-screen redesign for a search-zone change (canon
section 8 and R-37).

### DR-2 - There is no concrete search or candidate-result mockup

The text does not define an input label, trigger, clear/reset behavior, minimum
query, or the result composition. It does not show the central product promise:
which original stored value is displayed, which typed value matched it, and why
the row is a candidate rather than an exact match. Without that distinction an
operator can mistake a visually similar code for the requested code, while a
silent normalization would violate the requirement to preserve the original.

Required S09 rework: provide exact Russian labels and wide/narrow textual
mockups for (a) an exact match, (b) no exact match plus one candidate, (c)
multiple candidates, and (d) no match. Every candidate must show the unchanged
stored value and a clear neutral explanation of the ambiguous positions or
pairs used to find it. Define ordering when exact and candidate matches coexist,
and specify the safe action, if any, available from a result row. Row fill may
not encode match type under R-11, and color may not invent a new state meaning
under R-16.

### DR-3 - Long marking codes and ambiguous glyphs are not designed

The task exists because glyphs are hard to distinguish, yet S09 provides no
representative long code, fixed column widths, truncation rule, full-value
access, copy behavior, horizontal overflow, or narrow-viewport treatment. A
generic `TextCell` declaration does not prove that the operator can inspect the
original code and the differing characters without losing context. Wrapped
headers are forbidden by R-36.

Required S09 rework: include representative long values containing both
ambiguity groups, fixed-width result columns, full-value access and copy
behavior, and an explicit narrow-viewport composition with no overlap. State
how the differing positions remain inspectable without changing the stored
value or relying on row color alone.

### DR-4 - Required states are boilerplate rather than this flow

S09 copies generic success, forbidden, partial, repeat and cancel statements,
including duplicate-prevention language for a read-only search, but omits the
states the operator will actually encounter. It does not distinguish an empty
dataset from a query with no exact result, multiple ambiguous candidates, a
loading search, a failed search, or insufficient permission. Therefore R-21,
R-22 and R-23 cannot be judged.

Required S09 rework: define task-specific loading, exact result, candidate-only,
multiple-candidate, no-result, empty-source, error, forbidden, long-data and
narrow-viewport states. Use `TableSkeletonBody` for table loading,
`EmptyState` for a truthful empty/no-result instruction, and `ErrorNotice` only
for a real blocking error. Mark partial, repeat and cancel as not applicable if
the chosen flow has no corresponding operation.

### DR-5 - Scanner and keyboard behavior are left contradictory

The backlog describes manual diagnostics from printed characters. S09 lists
`ScannerLine` but never says whether the field accepts typing, paste, scanner
input, or all three, nor what Enter does. If the screen listens to the scanner,
R-25 requires a visible scanner-active line; if it does not, showing scanner
status would be false noise.

Required S09 rework: declare the supported input methods, focus behavior,
Enter/search behavior and whether scanner listening is in scope. Include
`ScannerLine` only when the screen actually listens to scanner input.

### DR-6 - The ui-kit mapping is the whole catalog, not a zone mapping

S09 allows almost every exported component, including print, dangerous
actions, quantity cells, tabs, menus and dialogs, although none is required by
the mockup. This defeats the S09 design-system check and conflicts with canon
section 8, which forbids visible elements without a task.

Required S09 rework: replace the allow-list with a zone-by-zone mapping limited
to visible elements in the selected design. Verify each component against
`frontend/src/ui-kit/index.ts`. If the approved ambiguity explanation cannot be
expressed by the current kit, declare a typed `DESIGN_SYSTEM_GAP` with the exact
zone and required props instead of authorizing local styling.

## Input integrity note

The S09 receipt exists and is the controller's accepted predecessor, but its
`output_hashes` object is empty. The current Markdown was reviewed directly as
the practical stage input; a revised S09 handoff should bind the exact artifact
version so a later S10 verdict cannot silently apply to changed text.

## Re-review acceptance

S10 may approve after S09 supplies one explicit affected-surface inventory,
task-specific wide and narrow mockups, exact labels and interaction behavior,
an inspectable exact-versus-candidate result model, truthful states, and a
minimal ui-kit zone mapping. The stored KIZ must remain visibly unchanged.

No owner decision is required for these design-contract corrections. This
review did not change runtime code, API/data behavior, pipeline files, deploy,
production, WB/Ozon systems, credentials or secrets.
