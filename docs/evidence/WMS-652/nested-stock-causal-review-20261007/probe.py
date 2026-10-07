"""Offline immutable receipt accounting and bounded native-event reconstruction.
Run from this repository: python3 -B <this-file> > proof.json. No target run.
"""
import collections
import hashlib
import json
import subprocess

SOURCE = "31cd68fd70791a7433562dc2495a7d67e969d840"
DIAGNOSTIC = "447ae9216cfb874bd66136a90d68d404ce3ea307"
FAILED_HEAD = "cbd126200788b87d1a006c5853d8e9560148cd36"
FAILED_MERGE = "8b8f20715528122a7260d650f018a9a8b4bd29e5"
DIR = "docs/evidence/WMS-652/warehouse-sc-sqlite-lock-diagnosis-20261007/"


def git(*args):
    return subprocess.check_output(["git", *args])


def blob(path, ref=SOURCE):
    return git("show", ref + ":" + path)


def sha(data):
    return hashlib.sha256(data).hexdigest()


manifest_raw = blob(DIR + "manifest.json")
manifest = json.loads(manifest_raw)
assert manifest["tested_head"] == DIAGNOSTIC
assert manifest["run"] == 37558149550 and manifest["attempt"] == 1
assert len(manifest["members"]) == 20
for member in manifest["members"]:
    data = blob(DIR + member["path"])
    assert len(data) == member["bytes"] and sha(data) == member["sha256"], member["path"]
paths = git("ls-tree", "-r", "--name-only", SOURCE, DIR).decode().splitlines()
assert set(paths) == {DIR + m["path"] for m in manifest["members"]} | {DIR + "manifest.json"}
assert blob(DIR + "raw/source-sha.txt").decode().strip() == DIAGNOSTIC
assert blob(DIR + "raw/protected-before.sha256") == blob(DIR + "raw/protected-after.sha256")
preparation = json.loads(blob(DIR + "raw/preparation.json"))
closure = preparation["source_closure_exact_failed_merge"]
for ref in (DIAGNOSTIC, FAILED_HEAD, FAILED_MERGE, SOURCE):
    for path, expected in closure.items():
        assert sha(blob(path, ref)) == expected, (ref, path)
    assert git("diff", "--name-only", DIAGNOSTIC, ref, "--", "backend/app") == b""

raw = blob(DIR + "raw/transactions-gw0.jsonl")
events = [json.loads(line) for line in raw.splitlines()]
assert len(raw) == 1805572 and len(events) == 6443
sequence_counts = collections.Counter(e["sequence"] for e in events)
duplicate_labels = {k: v for k, v in sequence_counts.items() if v != 1}
assert duplicate_labels == {2423: 2, 3067: 2, 3796: 2, 4238: 2}
missing_labels = sorted(set(range(1, 6444)) - set(sequence_counts))
assert missing_labels == [2424, 3068, 3797, 4241]
assert all(a["monotonic_ns"] < b["monotonic_ns"] for a, b in zip(events, events[1:]))
completion = json.loads(blob(DIR + "raw/completion-gw0.json"))
assert completion == {"exitstatus": 0, "events": 6443, "bytes": 1805572,
                      "dropped": 0, "active_transactions": {}}
counts = collections.Counter(e["kind"] for e in events)
assert counts["sql-start"] == counts["sql-complete"] == 2360
assert counts["connection-begin"] == counts["pool-checkin"] == 183
assert counts["service-task-launch"] == counts["service-task-settled"] == 36
assert counts["native-sql-error"] == 0
def sql_key(e):
    return (e["connection"], e["transaction"], e["operation"], e["table"])
assert collections.Counter(sql_key(e) for e in events if e["kind"] == "sql-start") == collections.Counter(
    sql_key(e) for e in events if e["kind"] == "sql-complete")
begins = {(e["connection"], e["transaction"]): e for e in events if e["kind"] == "connection-begin"}
checkins = {(e["connection"], e["transaction"]): e for e in events if e["kind"] == "pool-checkin"}
assert len(begins) == len(checkins) == 183 and begins.keys() == checkins.keys()
assert all(begins[k]["sequence"] < checkins[k]["sequence"] for k in begins)
assert {e["launched"]["task"] for e in events if e["kind"] == "service-task-launch"} == {
    e["settled"]["task"] for e in events if e["kind"] == "service-task-settled"}
settings = [e for e in events if e["kind"] == "sqlite-connection-settings"]
assert {e["connection"] for e in settings} == {1, 4, 5, 6}
assert all(e["journal_mode"] == "delete" and e["busy_timeout_ms"] == 5000 for e in settings)

ids = [5693, 5694, 5711, 5712, 5716, 5717, 5718, 5719, 5720, 5722, 5723,
       5724, 5742, 5745, 5746, 5747, 5750, 5751, 5756, 5757, 5760, 5761,
       5868, 5870, 5874, 5883, 5885]
assert all(sequence_counts[n] == 1 for n in ids)
e = {row["sequence"]: row for row in events if row["sequence"] in ids}
producer = json.loads(blob(DIR + "actual-ledger.json"))
assert [e[n] for n in ids] == producer["events"]
for n in (5693, 5694, 5711, 5712, 5716, 5717, 5722, 5760, 5761, 5868, 5870):
    assert e[n]["task"]["task"] == 60 and e[n]["connection"] == 1 and e[n]["transaction"] == 5693
for n in (5745, 5746, 5747, 5750, 5751, 5756, 5757, 5874, 5883, 5885):
    assert e[n]["task"]["task"] == 79 and e[n]["connection"] == 4 and e[n]["transaction"] == 5745
assert e[5694]["session"] == e[5718]["session"] == e[5720]["session"] == 100
assert e[5746]["session"] == 106
assert e[5711]["operation"] == e[5712]["operation"] == "INSERT"
assert e[5711]["table"] == e[5712]["table"] == "inventory_movements"
assert e[5716]["operation"] == e[5717]["operation"] == "RELEASE"
assert e[5718]["kind"] == "session-commit-complete" and e[5720]["nested"] is True
assert e[5719]["task"]["task"] == 60 and e[5719]["launched"]["task"] == 76
assert e[5723]["task"]["task"] == 76 and e[5723]["launched"]["task"] == 77
assert e[5742]["task"]["task"] == 77 and e[5742]["launched"]["task"] == 79
assert e[5724]["task"]["task"] == 77 and e[5724]["connection"] == 5
assert e[5757]["operation"] == e[5874]["operation"] == "UPDATE"
assert e[5757]["table"] == e[5874]["table"] == "fbs_warehouse_bindings"
assert e[5868]["kind"] == e[5883]["kind"] == "connection-commit-start"
assert e[5870]["kind"] == e[5885]["kind"] == "pool-checkin"
update_ms = (e[5874]["monotonic_ns"] - e[5757]["monotonic_ns"]) / 1000000
after_checkin_ms = (e[5874]["monotonic_ns"] - e[5870]["monotonic_ns"]) / 1000000
assert update_ms == 82.15621 and after_checkin_ms == 9.562357
assert "1 passed, 2 warnings in 12.47s" in blob(DIR + "raw/selected.log").decode()
start = events[0]
assert start["worker"] == "gw0"
assert start["collected"] == [preparation["selected_case"]]

compact = []
for n in ids:
    row = e[n]
    compact.append({"seq": n, "mono_ns": row["monotonic_ns"], "kind": row["kind"],
                    "task": row["task"]["task"],
                    **{k: row[k] for k in ("session", "connection", "transaction", "operation", "table", "nested") if k in row},
                    **({"launched_task": row["launched"]["task"]} if "launched" in row else {})})
print(json.dumps({
    "verdict": "PASS measured premature after-SAVEPOINT dispatch and overlapping pending write",
    "common_source": SOURCE, "diagnostic_source": DIAGNOSTIC, "run": 37558149550, "attempt": 1,
    "manifest_sha256": sha(manifest_raw), "manifest_members_verified": 20,
    "transactions_sha256": sha(raw), "coverage": completion, "kind_counts": dict(counts),
    "global_sequence_label_duplicates_outside_target": duplicate_labels,
    "absent_serial_labels_not_proof_of_missing_rows": missing_labels,
    "raw_row_monotonic_times_strictly_increasing": True,
    "all_27_target_labels_unique": True,
    "source_closure_identical_at_diagnostic_failed_head_failed_merge_and_common": closure,
    "WMS_engine_connection_settings": [{k: x[k] for k in ("connection", "journal_mode", "busy_timeout_ms")} for x in settings],
    "foreign_global_session_connections": [2, 3],
    "27_event_ledger_recomputed_equal_to_producer": True, "events": compact,
    "publisher_UPDATE_start_to_complete_ms": update_ms,
    "publisher_complete_after_outer_checkin_ms": after_checkin_ms,
    "native_SQL_errors": 0, "historical_lock_owner": "UNKNOWN",
    "selected_diagnostic": "PASS12.47s; gw0/-n1, preceding selection excluded",
    "observation_limits": "logging and create_task wrapping perturb scheduling; SQL intervals are not native busy-wait measurements",
    "fix_effectiveness_new_SOURCE_or_full_CI_approval": False, "new_target_runs": [],
}, ensure_ascii=False, indent=2))
