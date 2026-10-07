# WMS-607 isolated Mac package workflow

This packaging override is never merged into WMS release or main. It uses the registered ci.yml dispatch surface because default main has no print-console-package.yml file. The two existing Mac runner architectures and actual build_console.py remain unchanged.

Checkout uses an explicit accepted full SOURCE SHA input, recorded separately from the immutable harness SHA/run/attempt. Each architecture executes the frozen ten updater, four rollback and nineteen preserved native/HTTP/resolver cases; raw JUnit identities must exactly match their accepted baseline receipts and have no failure/error/skip. It then calls the existing native console builder, verifies ad-hoc codesign, actual architecture, unpacked self-test and archive build.json/source/updater bytes, and saves actual archive SHA256 plus raw results. No product, tests, requirements, secrets, production environment or installation actions change.

YAML, every bash block and both inline Python blocks passed syntax checks. Actual Mac CI has not run and archives do not exist yet. Independent bounded harness review and distinct software acceptance precede one dispatch. The requested SOURCE will be the analyst-published exact accepted commit; source checkout is explicit, never inferred from latest or a mutable branch. Public release and immutable manifest are separate later results.
