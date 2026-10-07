# WMS-652 passive workspace fetch/context preparation

Isolated branch codex/wms652-workspace-runtime-context-diagnostic, from published
91f8b74b77d62b13670e8e5baf52e13ca8379b4c. Last actual run37574399962 remains
43PASS/nonreproduction, with7364 focused drops; no fix or historical cause proven.
No additional Chrome source research/downloads. Existing source evidence unchanged.

Only two setup commands added: Runtime.addBinding and
Page.addScriptToEvaluateOnNewDocument. The latter installs a Proxy around native
fetch in each new document. Reflect.apply invokes native once with unchanged
thisArg/args, then returns the EXACT original Promise. Only the target synthetic
origin/workspace pathname is observed; primitive string and native Request/URL
inputs are supported without coercing arbitrary inputs or inspecting init.
Headers/signal/input/result/body are untouched. No controller/abort/request marker,
header/wait/barrier, extra Runtime.evaluate or Fetch.getResponseBody. The legacy
query helper remains inert; it is neither copied/imported nor invoked by this mode.

Each observed call carries a document UUID and serial, safe pathname/module stack;
completion side branch reports fulfilled or rejected/error name. Native bindingCalled
executionContextId binds that JS call to its actual Runtime context; context creation
supplies unique context ID/default frame, destruction/clear are retained. Stack keeps
only fake-origin src/assets module paths and line/column, no URL queries or values.
Observer exceptions are caught and cannot alter native throw/rejection/Promise.
The side branch observes settlement and necessarily marks a rejection observed;
product Promise/await behavior is preserved, but instrumentation can perturb timing.

Narrow collector retains context/frame-loader fields, original navigate/DOM-readiness
send/reply identities and boolean readiness (no expression), target paused identity,
target Network request/terminal identity, and exact original native error identity
with send/current reply context and exact paused-record indices. No huge general
Network or Runtime payload. Original full transport remains untouched and strict;
original errors/unknown ownership are not retired or filtered. Call-to-context is
native-bound; call-to-FetchID remains UNKNOWN without a direct native discriminator.
Concurrent same-URL calls cannot be assigned by URL/time. Even a sole candidate or
nearby loader/context boundary is not declared a cause or exact request owner.

Shared100k event/64MiB limits use real UTF8 bytes of serialized narrow records plus
separators, a small summary reserve and exact final-file validation, honest drops,
original/document pending commands and retained calls without a terminal. Pending
call reconstruction is only from retained observations; drops make it incomplete.
Final trimming explicitly marks pending-call state unknown. No huge conservative
Network-event estimates or duplicate native success/send logs.

15 synthetic controls PASS: old full5 and focused4 remain byte-identical, new6
cover unchanged native this/args/Promise/error, observer throw on completion and
original driver ingress/send, no body/header/signal reads, binding context/privacy/
ambiguity, exact bytes/caps, and only the two setup commands. No actual browser,
installation/fullCI/dispatch was run locally. Node/shell syntax passes.

copy-proof/preparation.json verifies2546 original bindings and1835 locally available
source hashes against exact4c532f0cccfb8f99b34d68d9630a3763038fbc5f. All43 original
cases, bodies/routes/assertions/delays and finite native forwarding remain byte-exact:
five insertion reversals recover browser SHA256
24f146ba0e038645114edb882a85686dc834f8c338d1324c10426b7648bd6dd6. Exact default
Request-only pattern pinned; original600s shell changes solely runner path.
Preparation receipt identifies the base HEAD; CI regenerates it with actual run HEAD.
Generated runtime siblings stay untracked; recoverable copies and hashes saved here.

Manual CI override has one complete43 job, Ubuntu24.04/Node24.21.0/
Playwright1.56.1/Chrome141; branch/ref/attempt1 guard. Integrator alone assesses the
published ref and dispatches. Product, protected fixtures/policy/tests, common/607,
main/production and handling/migration code unchanged. Another PASS is nonreproduction.
Actual failure plus exact native request/document ownership remains the discriminator;
no cancellation/retirement approval follows from this preparation.
