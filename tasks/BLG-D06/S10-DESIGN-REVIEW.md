# S10 DESIGN_REVIEW - BLG-D06

Role: `pipeline-product`
Reviewed input: `tasks/BLG-D06/S09-UX-CONTRACT.md`
Canon: `docs/product/UX_CANON_RU.md`
Verdict: `DESIGN_REWORK`
Return stage: `S09 UX_CONTRACT_AND_MOCKUPS`

## Decision

The business direction is valid: ordinary work should exclude products whose
archive marker is the `OLD/` prefix, while history remains reachable only after
an explicit operator choice. The supplied S09 artifact cannot be approved as a
design contract because it is a generic template rather than a mockup of that
operator flow. It does not establish what will be visible, where the change
lives, or how an operator can safely reveal and identify archived products.

## Blocking findings

### DR-1 - The changed screen and zone are not identified

S09 says only that confusion must be removed "from the card" and then describes
an unspecified screen. It does not bind the change to any route, registry screen
or product-picker surface. The repository registry identifies at least the
catalog route `/app/catalog/products` as screen `S-01`, while the backlog wording
also refers to ordinary lists and search. Without an explicit surface inventory,
S18 cannot know whether this is one catalog filter or a rule shared with product
selection dialogs, and S25 cannot know which complete operator flow to accept.

Required S09 rework: name every affected screen/dialog and its exact touched
zone. For each other product list or picker, state explicitly whether it is in
scope or unchanged and why. Do not imply a migration of an entire legacy screen
when only a new filter zone is required; this follows canon section 8 and R-37.

### DR-2 - There is no concrete filter contract or mockup

The artifact never names the visible control, label, options, default value or
reset behavior. It does not say whether the explicit archive mode means
"all products" or "archived only", how it combines with text search, or whether
the default is restored after navigation/reload. The generic list of
`SelectField`, `CheckboxField` and `TabsBar` leaves three materially different
designs open. That is not a reviewable mockup and violates canon R-03, which
requires filters in one predictable zone above the table.

Required S09 rework: choose one existing ui-kit control and provide its exact
Russian label, options and default. Show the filter zone in the default state
and after the explicit archive choice, including combination with search,
clear/reset, navigation and reload. State whether hidden archived rows affect
counts or pagination visible on the screen.

### DR-3 - Archived products are not identifiable when revealed

The stated warehouse risk is accidental selection of an obsolete card, but S09
does not show how a revealed archived row differs from an active row. It also
does not define whether the literal `OLD/` prefix is the only visible signal or
whether an existing neutral/status treatment is needed. Row fill cannot be used
for this purpose under R-11, and color cannot invent a fourth meaning under
R-16. Approving the current text would preserve the original selection risk in
the explicit archive mode.

Required S09 rework: give a concrete archived-row example with long product
name and identifiers, preserving the canonical fixed columns. Name the exact
existing ui-kit component used for any archive indicator. If the prefix alone
is intentionally sufficient, state that decision and show it in the mockup. If
the kit cannot express the approved indicator, return a typed
`DESIGN_SYSTEM_GAP` instead of authorizing local styling.

### DR-4 - Required states are generic and do not describe this flow

S09 copies success, forbidden, partial, repeat and cancel boilerplate but does
not show the states that this read/search flow actually needs. In particular,
it does not distinguish: no active products exist; active products exist but
the current query matches only hidden archives; archive mode has no results;
loading; catalog/search failure; long data; and narrow viewport. The current
empty text could make a hidden archived match look like missing data, while a
generic error cannot be checked against R-21 through R-23.

Required S09 rework: provide concrete wide and narrow textual mockups for
default, archive-visible, loading, each relevant empty result, and failure.
Specify fixed column widths, truncation/full-value access, horizontal overflow
where needed, and stable filter placement. Mark genuinely irrelevant states as
not applicable with a reason instead of filling them with unrelated behavior.

### DR-5 - The ui-kit mapping is a component inventory, not a zone mapping

S09 declares nearly the entire kit as allowed, including print, dangerous
actions, scanner, modal, menus, quantity cells and status components, although
the artifact does not require those elements. Pipeline S09 requires components
to be named by actual screen zone, and canon section 8 forbids adding an element
without a task for it. The current list neither proves that the needed control
exists nor detects a real design-system gap.

Required S09 rework: replace the allow-list with a zone-by-zone mapping limited
to elements visible in the proposed change. Verify the selected component
against its actual exported contract in `frontend/src/ui-kit/index.ts`. Preserve
unrelated legacy zones and declare `DESIGN_SYSTEM_GAP` only if the concrete
approved design cannot be assembled from the existing kit.

## Re-review acceptance

S10 may approve after a revised S09 supplies a surface inventory, one explicit
filter model, exact labels and defaults, an identifiable archived-row treatment,
task-specific states, wide/narrow mockups, and a truthful ui-kit zone mapping.
If deciding the affected search surfaces requires a behavior/API contract, the
owning controller role must add or route that work before design approval; S10
does not make that BA or architecture decision.

No owner decision is required to correct these design-contract defects. This
review did not change runtime code, API/data behavior, pipeline files, deploy,
production, WB/Ozon systems, credentials or secrets.
