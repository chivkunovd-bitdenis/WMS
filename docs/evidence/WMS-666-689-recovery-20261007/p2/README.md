# P2 print compatibility verification

Product commit: `d420f8db1e7d69212ad2ea4529a02044689363b0`. Its sole product change permits wrapping order references in the existing picking table column; column widths, order text and explicit line breaks remain unchanged.

The original exact WMS-657 C5 geometry has one overflowing order-reference cell (90px client width, 96px scroll width), recorded in `657-negative-geometry.json`. With P2, all six unchanged WMS-657 tests pass. The local combined run also passes two WMS-673 input tests and explicitly skips its three rendered PDF checks; Linux CI supplies the PDF checks.

`chrome-headless-once.py` is the local macOS execution adapter used via `WMS_PRINT_CHROMIUM`: it returns complete real Chromium DOM output and terminates only its own process group after complete output. It does not modify DOM, assertions or test cases. Linux CI does not use this adapter. The exact local output is preserved in `pdf-local.log`.

The isolated unchanged WMS-684 PDF tests both pass (`684-isolated.log`), as do TypeScript and the production frontend build. The previous full CI failure under unrestricted parallelism remains a failure; the next full run restores the previously used `--maxWorkers=2` cap without changing timeouts or assertions.

Release remains pending final P2 browser scenarios, controlled source binding, full CI and actual deployment.
