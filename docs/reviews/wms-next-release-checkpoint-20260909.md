# WMS release checkpoint — 09.09.2026, 07:32 MSK

The WMS-058/084/277/395 release is deployed to production. Do not redeploy the
old candidate or repeat completed CI/reviews. Production is
743a794bf0ee9e20cccf7f87c05138b035604ec9 (PR207); staging is
1a508b98c01d55e3462f104c1523f4ff6721704d (PR208). Both match application/test code
of b09b7d9fd87cb18b5ce34e5d6c7ca848d81f4ad0.

CI34308619194 and34308639195 passed:2234passed49skipped1xfailed. Final Opus
claude-opus-4-7 effortmax and independent Astra adjudication are finished.
The confirmed over-plan source race and stale callback were fixed in39c84d09
and a8053cf9. Actual staging Chrome GREEN verified immutable sourceA,
queuedB waiting, exactly one A-1 movement and unchangedB. OwnMP000042 was
cancelled normally. Do not repeat this or the earlier084 A500043→B500044 setup.

Production proof: wms-next-production-743a794b-20260909.json. All428 runtime
Python files in api/worker/beat matchGit; webimage matchesbuild; migration0257;
servicesrunning/restarts0. DB andRedis remained the existing11Augustcontainers,
healthy. Freshbackup before-release-b09b7d9f-20260909,392M, restore-list checked.
Startup logs at07:11 had noERROR/Traceback/CRITICAL. Public Chrome login and
recovery pages passed, reportproduction-public-smoke-20260909.md. This was
unauthenticated and is NOT protected productionFBS browser acceptance.

Final scheduled import is verified: taskfaf2efe5-ca95-478d-abc2-55c9d0de8afc,
07:17–07:27MSK,23sellerimportsOK/5previousWB401,summaryandsucceeded recorded.
Both previousSKUfailedsellers nowcompleted; this does not prove everyhistorical
SKUunchanged. FBSautopoll/reconcile succeeded duringimport, twoDBsnapshots had
0blocks/0longtransactions. No manualsync. Evidencewms277-postrelease-20260909.md.
PublicproductionChrome passedlogin/recovery with0JSerrors and0mutationattempts.

Mobile401offlinecheck foundJDK17/SDK35but noGradle8.11.1distribution or modules-2
cache; only~495MiBfree, so no downloads/compilation/signing/publication performed.
Reportwms401-mobile-offline-check-20260909.md. Next boundedparallelwork: Astrahigh
mobile_publish_ci derives minimumbackendcontract for397 from exactOpus399mocks,
withoutchangingdesignorapplication; report-only, nonewentitiescreatedyet.

Canonical statuses and all reports are published in codex/wms396-stage,
currently documents ahead of the frozen production branch. Do not move the
production branch merely to republish reports or rerunfullCI. Rootcheckout has
unrelated dirtybilling/frontendfiles, unchanged. Emulator has44orders and no
volume: do not restart or restore old42backup. QA084 finalBbinding remains.

Not complete: historical013needs billingdate/rates;047specific historicalstock
apply not authorized;048currentowneroflostunitnotproven;275physicalTSD/load
notverified. Mobile401localdfcb762 is not published and physicalacceptance is
missing; tracked signingkey discovered earlier must not be published/changed
withoutdirectauthorization. LAN402 is a designcontract with an unresolved
printer-agent binding decision. Chat399Opusmockups exist, backend397notconnected.
Do not call all40or theseparallelfeatures production-ready.

Automationwms-40-staging remainsACTIVE every20minutes in the same thread.
Packaging is onlyaflag, noinventory/reservationeffects/navigationblockers;
frontendesignunchanged. Continue autonomous work where evidence/authorization
allows, keep meaningful notifications only, and preserve precise status limits.
