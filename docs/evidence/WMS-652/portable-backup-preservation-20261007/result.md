# WMS-652: portable backup preservation serialization

Same separate testwriter, clean base
`7bbfafc68ef0834746e63f12a49db31a1977f030`; fresh origin/etalon AGENTS and testwriter
skill read. No nested agents. Only the boundary test and this new directory change.

The readonly actual Linux shard1 log from fullCI37548248403 attempt1 on mergeac845
shows Python3.11.16 rejecting the preservation hash. `before-linux.log` preserves
that raw excerpt; `serialization-proof.json` records its original log hash/path.
The full run remains FAILED and was not retried. This is not a changed assertion:
before editing, the same23 unchanged AST assertions produce
`ddbfe3e8447dd54825fadf01f437a1adb6fa18f2ed583f58172cb1ed962fc3da` with Python3.14's
default show_empty=False, and
`0632023b3ebea0de566823f112e6a1eeca5b5222a3cfd538d5624da1d4d81408` with explicit
show_empty=True—exactly the actual Linux3.11 result. Ten assertion dumps differ
only in serialization; the proof includes the first short/full pair.

The correction feature-detects show_empty using inspect.signature, explicitly
requests the full representation when supported, otherwise retains the legacy
default. It requires **one hardcoded0632023 hash**. It does not accept both hashes,
derive a baseline from the candidate or remove the23-count/seven-parameter check.

```sh
python3 -B docs/evidence/WMS-652/portable-backup-preservation-20261007/preservation-proof.py
```

`after-target.log`: the **actual preservation function**, compiled from its AST
with real stdlib modules and original SOURCE binding, passes on Python3.14.3.
No copied algorithm, pytest/conftest import or backup/Docker action is executed.
`negative-copy.log`: the same function rejects an automatically removed untracked
original-source copy with `assert stop < dump` changed to `assert stop <= dump`.
All23 assertions remain, and the failure occurs at the hardcoded hash assertion,
not setup/count. `target-results.json` records the execution and mutation hashes.
No existing Python3.11 executable was found on PATH/common installation paths;
the legacy hash is supported by the saved actual Linux execution, not a new3.11 run.

`byte-ast-proof.json` proves the original backup file,23 assertions/seven parameters
and all five gate variants' body/decorators remain unchanged. All six boundary
case IDs and the first two preservation assertions remain. The prior883 reference,
40df raster and8e029 CryptoPro title corrections are untouched. No original fixture,
product/script/CI/policy/requirements/backlog changes, install/build/browser/deploy
or full backend/other14-case rerun occurred. Eight small evidence files are saved.
Independent review, distinct analytical delta and final SOURCE/policy approval
remain separate; no self-acceptance, pin activation or fullCI success is claimed.
