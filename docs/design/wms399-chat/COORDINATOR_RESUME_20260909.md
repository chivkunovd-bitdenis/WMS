# WMS-399 — продолжение той же авторской сессии Opus

Координатор возобновил работу 09.09.2026 после завершения основного Opus-ревью.
Продолжить именно сессию `8f165d2e-0399-4c15-a9be-cb182241cde4`, модель
`claude-opus-4-7`, усилие `max`, в текущем worktree.

You remain the sole designer and author of ALL prototype React changes. Resume
from your existing work, do not restart or re-read broad project context.
Read OPUS_BRIEF.md and STATUS_RU.md in this directory and your current source.
The existing authoring pause is now explicitly lifted by the coordinator.
You are not alone in the repository: do not revert any other agent's changes.

Write only prototypes/wms399-chat/** and docs/design/wms399-chat/**. Do not
modify EXECUTION_EVIDENCE.json or coordinator reports. Do not read .env,
credentials, secret/key configuration, historical logs, Claude/Codex session
files, backend or unrelated folders. No Bash, shell, network/browser tools,
model delegation, installation, Git, npm installs or generated large assets.
Only Read/Write/Edit/Glob/Grep tools are provided. Read dependency type files
only when necessary, through the existing node_modules link; do not explore
node_modules broadly. Codex will run focused typecheck/build and return any
remaining compiler or runtime errors to you, preserving your design.

Finish these seven missing files, preserving the complete intended product:
SearchScreen, NotificationsScreen, PreferencesScreen, Lightbox,
ParticipantsDrawer, DocumentPickerDialog, ContextPanel. Their actual imports
are in src/App.tsx and src/conversation/ConversationScreen.tsx. Do not remove
imports or substitute dead placeholders to obtain a build.

Existing packages verified now: React19.2.5, MUI9.0.0, TypeScript6.0.2,
Vite8.0.8. CHECKPOINT_TYPECHECK.txt contains the previous compiler errors:
Stack alignItems/justifyContent props, TextField InputProps, Switch inputProps,
Drawer PaperProps, unused actor, and TS6 baseUrl deprecation. Update your own
implementation/configuration for these installed APIs without redesigning.

Finish every promised screen and state with real local interactions: sending,
reply threads, images/files, image viewer, document picker/context, search,
notifications/preferences, role visibility/internal notes, mobile layout,
drafts, errors and retry. Synthetic state only; no backend or live data.
Create DESIGN_HANDOFF_RU.md describing how to open the prototype, routes,
component/tokens/interaction contracts, backend integration boundaries and
honest remaining limits. Requirements must not claim a screen/state exists
unless authored. Do not claim browser verification; Codex performs it later.

Disk remains constrained. Use small source writes, no dependencies or copies.
Finish a complete authoring pass and report actual files and remaining limits.
