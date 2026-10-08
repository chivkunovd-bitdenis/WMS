# Native print join proof — af5

This proof was captured from product/runtime source SHA `af5b5aa15210167ee1f943943871f6052150c791`. `source-identity.json` records that the product tree used by the runner matched that SHA. The later test-and-requirements-only commit `c3518d47ac009f407b41bad2998d2ca2238b8b6d` does not change runtime code.

The ordinary manual picking-list scenario produced six handler-emulated sink jobs; the grouped scenario (`group-r2`) produced six. `native-final-joins.json` records each captured input, order/job identity, rendered PNG hash, handler SQLite receipt and sink PNG hash. All twelve joins passed exact identity/hash comparison, and all rendered, handler and sink PNG hashes agree within each join. The handler identity fingerprint is recorded in that JSON.

The print handler was an emulated local sink. Physical printer output and paper were **not tested**.
