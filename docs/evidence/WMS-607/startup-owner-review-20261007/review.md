# WMS-607: independent startup-owner source review, 07.10.2026

Source verdict: **PASS for the bounded startup correction** at
`7bbcdd8a8aba9fd44dd4ee4ce2dbdee5af26b880`. Developer compatibility receipts were
read and verified before publishing this evidence. This is independent technical
review, not analytical acceptance or package/customer proof.

Same distinct Sol 6.1/high reviewer session
`01a11370-eea3-7533-a616-2943d59a7bca` authored neither WMS-607 product nor tests.
Before source: accepted `a04a7b35f1e866c1283bdc46fff2d41eaf68b4d6`. Separate frozen
startup contract: `7b94a8dd0f1d6a772272930df3894d3ccd299686`. Fresh origin/etalon
AGENTS was read; whole owner/failure libraries and developer handoff guidance
already read in this same review session were reused. No separate reviewer skill
was invented. This review does not change prior owned-stop P1 closure49da.

## Source behavior and preservation

Product commit changes only `tools/print-agent/update_macos_direct.sh`, seven
insertions and three deletions. `health_ok` preserves `owned_pid` return status
rather than collapsing status2 to1. Status2 is established by the existing
ownership check before health200/readiness could be considered. `start_owned`
captures that status in the `else` branch and immediately returns failure with
an accurate foreign-owner diagnostic, before the next child probe, sleep or poll.
It sends no signal to the observed owner. Ordinary no-owner/readiness failure
remains status1 and follows existing warmup; actual owned health/readiness status0
remains successful. No broad error suppression or health200-only acceptance was
introduced.

Reversing only those exact three edits reproduces the **whole** previous updater.
All stop/rollback, archive/journal, ownership matching, native readiness and
startup timing code outside the changed block is unchanged. The comparison from
a04 to7bbc contains only the additive frozen test/evidence and updater. Old14+19
modules, builder, whole Swift and requirements remain byte exact. Frozen new3,
all helpers and 15-second test deadline are unchanged; no expectations, delays,
timeouts, retry or business state were weakened.

## Independent actual targeted check

Only the exact new three-case frozen module was run here:

```sh
WMS607_START_OWNER_RAW=docs/evidence/WMS-607/startup-owner-review-20261007/raw python3 -B tools/print-agent/test_macos_direct_updater_start_owner_contract.py --report docs/evidence/WMS-607/startup-owner-review-20261007/startup-owner.xml
```

**3 PASS, zero FAIL/ERROR/SKIP.** Exact IDs, source/test hashes, raw events, XML and
log are retained here. The module executes actual committed shell functions and
JSON helper. lsof/ps/curl/readiness/launcher replies are controlled; its harmless
FIFO launcher remains a real subprocess for the unchanged builtin kill-0 probe.
Temporary files/journal/intent are real. No native application, listener, host
Library, CUPS or physical printer is used.

Confirmed foreign mode reports failure on its first ownership observation with
no later startup poll/sleep, curl health, readiness or signal; files and recovery
intent remain unchanged. Owned healthy mode verifies the controlled health JSON
and readiness and succeeds. No-owner warming mode retains one startup wait then
owned validation/success. The before-code raw report was read: actual **1 target
behavioral FAIL + 2 preservation PASS**, no setup/error/skip; foreign mode then
had50 foreign polls/50 sleeps rather than immediate refusal. Purposeful frozen
positive mutation controls remain unchanged. Bash syntax passed without execution
of the complete updater.

## Receipt boundary and next ownership

Published developer receipt commit `7cf184f80846eb500753998b27d8b04d04c0a536`
was read through the same named source-fix branch and verified against its remote
head. Saved suites: new3 PASS, rollback4 PASS, updater10 PASS, existing19 PASS,
all zero failure/error/skip. Exact XML IDs match the unchanged frozen contracts
and previous nineteen baseline. New3/rollback4/ten CLI raw records bind the
actual corrected shell or unchanged Swift and exact test hashes; all five HTTP
raw records bind unchanged Swift. The saved precode1 RED/2 PASS is also checked
against before-source bytes. Actual logs were read; none of the old33 ran again
in this reviewer worktree. These are local controlled software receipts, not a
new ARM/Intel package or client installation claim. No CPU/timing cause is inferred
for any prior Intel timeout.

No old native33 repetition, build, package CI, browser, customer Library, provider,
printer, deployment, secrets or messages occurred in this review. Source3PASS
is not an ARM/Intel archive/install/physical-paper result. Distinct analyst and
integrator own acceptance, new exact SOURCE/harness pins and actual architecture
verification; the separate sender owns authorized ArtMaks instructions. No chat
resolution or client messaging was performed here.

Only this evidence directory is authored. Product/tests/requirements/workflows,
WMS-652/common, main/etalon, other worktrees and existing stash
`b396ded869bc8932ad25dc448b5f7163aa62a2f7` are preserved.
