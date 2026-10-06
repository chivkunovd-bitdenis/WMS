# WMS-607: independent review of the Direct Mac repair

Verdict: **PASS for the bounded technical source delta** at
`de9f31a464fc09df26c6a77b488c904ea3ec19e2`. Prior findings F1 and F2 in
`dfc4c54178063e4ffb3bb24ab3e4d31e1cff51a3` are closed. No new technical blocker
was found in the reviewed delta. This is independent review, not analyst
acceptance, package certification, installation or physical-print confirmation.

The reviewer owns only this evidence branch. The product/test author is a
separate session. Current `origin/etalon:AGENTS.md` was fetched/read; previously
read complete owner/failure libraries remain applicable, particularly preservation
of released behavior and recovery without silently repeating an external action.
Requirements are the existing WMS-607 and frozen ArtMaks continuation at
`58eab40495a96b0d67d02ea6b537c044071cbccf`; no requirements or expectations changed.

## What was independently checked

The actual preservation base is native Direct
`3348db9c61d62dfb8038be3b432a293f27ce9a1e`, which retains the released
`9a33b651c309796707053e1056c7f80dff7194d5` size-aware identity. The Swift diff
against 3348 changes only `run` and `defaultPrinter`. Bytes before `run` and
from `parseReceipt` through the rest of the file are identical. Therefore media
arguments, image/size digest, durable jobs-v2 journal, legacy receipt import and
mirror, unknown outcomes, serialized submissions, linked reprints, HTTP handling
and native self-tests have not been rewritten by this resolver repair.

F1 is closed: the restored submission uses the actual label dimensions, and
the receipt identity includes those dimensions. The frozen test drives the real
public .4 source in one process to write its actual journal, then starts the
candidate twice against the same bytes. It requires the saved receipt with zero
resolver/lp calls. A separate case captures actual lp arguments for 58×40 mm and
one copy; changing the dimensions with the same PNG/key must fail before lp.
These checks would detect the previously lost media/hash behavior.

F2 is closed: each of the three lpstat operations checks `timedOut` before
interpreting its status/output. Queue validation cannot fall through a timeout
to the missing-default message. A general-list timeout also has its own reason.
Every resolver refusal is `PrintError.beforeSubmit`, so the unchanged journal
can persist a known pre-submission failure and safely retry the same key rather
than treat it as an unknown external outcome. The frozen cases exercise actual
child-process timeouts, recovery and restart, requiring precisely one lp call.

The resolver consumes stdout while stderr remains diagnostic output. A parsed
default is validated with `lpstat -p <that-name>`; the general `-p` call only
distinguishes unavailable CUPS from an absent/invalid default. No listed printer
is automatically selected. The original warning, localized-output, malformed
default, inaccessible-service and stale-default regression expectations remain.
The default `run` behavior for non-resolver calls is unchanged.

The four restored dependencies are byte-identical to 3348: CUPS observer,
observer fixture, history page and native runtime tests. Every SHA256 in the
developer's source-provenance file was independently recomputed from Git blobs.
The six-test contract is byte-identical to its test-first commit. An AST comparison
(Python's parsed syntax tree, excluding formatting) confirms all five original
parser test methods and `run_case` are unchanged from ed053. Their adapter uses
the real journal API with a valid PNG; its injected submit boundary and unused
observer stub do not replace resolver behavior. `journal:false` there refers to
the legacy uncertain-job file, not absence of the newer failed-before-submit record.

## Build/runtime boundary

The six added builder lines are inside the macOS branch only. They compile the
restored C observer, link that object and system libcups into the optimized Swift
binary, and include the unchanged history page. This is the same compiler/linker
sequence used by the restored native runtime test. Commands use argument arrays
with checked return codes; there is no shell interpolation or permission bypass.
The Windows build branch, workflow, frontend, backend, guards and scripts are
unchanged from the frozen contract.

The existing builder still refuses dirty package sources, records the actual
HEAD/architecture/Direct runtime in build.json, signs and verifies the native
executable, archives it with ditto, unpacks it, verifies the signature and runs
the unpacked self-test. It does not install Python into the Mac package or disable
macOS protection. This review verifies that source path; it did not run the
builder, inspect a new archive or assert that a released binary has these bytes.

## Evidence read and limits

Committed developer receipts at de9f31a4 were read in full:

| Receipt | Recorded result | What it supports |
|---|---|---|
| frozen-six-green.log | 6/6 OK, 18.925 s | Three timeout/retry branches, actual media arguments, installed receipt/restart, dimension conflict |
| resolver-five-green.log | 5/5 OK, 2.947 s | Existing resolver regressions with unchanged assertions |
| native-runtime-green.log | 3/3 OK, 27.408 s | Optimized native self-test, observer fixture and HTTP/journal recovery including 350 distinct keys sent twice |

The reviewer performed source/hash/AST/scope checks, saved in source-checks.json,
and in-memory Python syntax parsing. No test was rerun, no distribution was built,
no dependencies were added, and no OS queue or operator data was touched.
The saved logs are developer execution evidence; this report does not recast them
as a second independent execution. Observer/native HTTP fixtures are not live
CUPS or paper proof. Earlier ed053 IPP evidence and the historical claimed 40
frontend tests do not prove execution of this corrected candidate; the earlier
review's limitations remain in force.

Before a usable ArtMaks update is claimed, the remaining concrete checks are:

* Analyst acceptance and exact-SHA Direct console package CI for Mac ARM and
  Intel; inspect build.json, architecture, executable/system dependencies,
  history page and unpacked signature/self-test. Publish immutable artifact
  coordinates and an archive checksum; a source hash is not an archive checksum.
* For the update command, detect hardware/compatible architecture, validate the
  artifact before stopping the exact old process, archive its complete bytes and
  metadata without overwriting prior backups, and use staged/atomic replacement
  with rollback on failure. Preserve the persistent journals and uncertain jobs;
  restoring application bytes must not reset print history or silently resubmit.
* Exercise ordinary per-application macOS launch permission and Chrome local
  connection permission. No global protection disable, blanket quarantine
  removal, full-disk-access demand or automatic default-printer change is needed
  by this delta. Verify one controlled request and same-key replay, then keep
  actual client trigger and physical paper confirmation as separate evidence.

No main/production write, package release, client install or Telegram delivery
was performed. The corrected source can proceed to the separate acceptance and
exact-package stages within the existing chain.
