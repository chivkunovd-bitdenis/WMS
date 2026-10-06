#!/usr/bin/env python3
"""WMS-604: explicit, reversible marking-flag correction for received clothing.

Uses the existing production SSH/psql path, never reads or prints credentials.
Preview is read-only. Apply requires an unchanged saved manifest and exact count.
Only products.requires_honest_sign is updated; no stock or provider operations.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone


CATEGORIES = (
    "Блузки",
    "Водолазки",
    "Жакеты",
    "Жилеты",
    "Костюмы",
    "Куртки",
    "Леггинсы",
    "Лонгсливы",
    "Лонгсливы для малышей",
    "Носки для малышей",
    "Палантины",
    "Пальто",
    "Пиджаки",
    "Платья",
    "Пуховики",
    "Свитшоты",
    "Шорты",
    "Юбки",
    "Шарфы",
)


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


ELIGIBLE = """
SELECT DISTINCT p.id FROM products p
JOIN inbound_intake_lines l ON l.product_id=p.id
JOIN inbound_intake_requests r ON r.id=l.request_id AND r.tenant_id=p.tenant_id
WHERE r.operation_type='inbound'
  AND r.status IN ('sorting','done','verified','posted')
  AND r.verified_at IS NOT NULL AND l.actual_qty>0
  AND p.category IN ({categories})
""".format(categories=",".join(map(literal, CATEGORIES)))

PREVIEW = """
WITH eligible AS ({eligible})
SELECT COALESCE(jsonb_agg(row_data ORDER BY row_data->>'tenant_id',row_data->>'id'),'[]')
FROM (
 SELECT jsonb_build_object(
  'id',p.id,'tenant_id',p.tenant_id,'tenant_name',t.name,'seller_id',p.seller_id,
  'name',p.name,'sku_code',p.sku_code,'category',p.category,
  'requires_honest_sign',p.requires_honest_sign,
  'other_fields_hash',md5((to_jsonb(p)-'requires_honest_sign')::text)
 ) AS row_data
 FROM products p JOIN eligible e ON e.id=p.id JOIN tenants t ON t.id=p.tenant_id
) rows;
""".format(eligible=ELIGIBLE)


def query(host, sql):
    result = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            host,
            "docker exec -i wms_prod-db-1 psql -U postgres -d wms -X -qAt --set ON_ERROR_STOP=1",
        ],
        input=sql,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        # SQL contains only explicit product IDs and hashes, never credentials/KIZ.
        raise RuntimeError(
            f"psql failed ({result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip()


def read_preview(host):
    return json.loads(query(host, "BEGIN READ ONLY;\n" + PREVIEW + "\nCOMMIT;"))


def digest(rows):
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def save(path, value):
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["preview", "apply", "verify", "rollback-sql"])
    parser.add_argument("--host", default="root@194.87.96.144")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--expected-changes", type=int)
    args = parser.parse_args()
    if args.mode == "preview":
        rows = read_preview(args.host)
        save(
            args.manifest,
            {
                "task": "WMS-604",
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "host": args.host,
                "categories": list(CATEGORIES),
                "rows_sha256": digest(rows),
                "rows": rows,
            },
        )
        print(
            json.dumps(
                {
                    "eligible": len(rows),
                    "changes": sum(not r["requires_honest_sign"] for r in rows),
                }
            )
        )
        return
    manifest = json.loads(args.manifest.read_text())
    rows = manifest["rows"]
    assert manifest["host"] == args.host and manifest["rows_sha256"] == digest(rows)
    changed = [r for r in rows if not r["requires_honest_sign"]]
    ids = ",".join(literal(r["id"]) + "::uuid" for r in changed)
    assert ids, "Empty change set"
    if args.mode == "rollback-sql":
        # Saved for explicit recovery only; never runs a rollback automatically.
        print("-- WMS-604 recovery: review current changes before executing.\nBEGIN;")
        for row in changed:
            print(
                "UPDATE products SET requires_honest_sign=false WHERE id="
                + literal(row["id"])
                + "::uuid AND tenant_id="
                + literal(row["tenant_id"])
                + "::uuid AND requires_honest_sign=true"
                + " AND md5((to_jsonb(products)-'requires_honest_sign')::text)="
                + literal(row["other_fields_hash"])
                + ";"
            )
        print("COMMIT;")
        return
    if args.mode == "apply":
        assert args.report is not None and not args.report.exists(), (
            "New report path required"
        )
        assert args.expected_changes == len(changed), (
            "Exact expected change count required"
        )
        assert read_preview(args.host) == rows, "Preview changed; stop and recalculate"
        values = ",".join(
            "("
            + literal(r["id"])
            + "::uuid,"
            + literal(r["tenant_id"])
            + "::uuid,"
            + literal(r["other_fields_hash"])
            + ")"
            for r in changed
        )
        sql = f"""
BEGIN;
SET LOCAL lock_timeout='3s'; SET LOCAL statement_timeout='20s';
CREATE TEMP TABLE marking_expected(id uuid PRIMARY KEY,tenant_id uuid,other_fields_hash text) ON COMMIT DROP;
INSERT INTO marking_expected VALUES {values};
DO $$ BEGIN
 PERFORM p.id FROM products p JOIN marking_expected e ON e.id=p.id FOR UPDATE OF p NOWAIT;
 IF (SELECT count(*) FROM products p JOIN marking_expected e ON e.id=p.id
     WHERE p.tenant_id=e.tenant_id AND NOT p.requires_honest_sign
     AND md5((to_jsonb(p)-'requires_honest_sign')::text)=e.other_fields_hash
     AND p.id IN ({ELIGIBLE})) <> {len(changed)} THEN
   RAISE EXCEPTION 'Candidate scope or values changed';
 END IF;
END $$;
CREATE TEMP TABLE marking_untouched ON COMMIT DROP AS
 SELECT md5(string_agg(p.id::text || ':' || p.requires_honest_sign::text,',' ORDER BY p.id)) AS fingerprint
 FROM products p WHERE p.id NOT IN (SELECT id FROM marking_expected);
UPDATE products SET requires_honest_sign=true WHERE id IN (SELECT id FROM marking_expected);
DO $$ BEGIN
 IF (SELECT count(*) FROM products p JOIN marking_expected e ON e.id=p.id
     WHERE p.requires_honest_sign AND p.tenant_id=e.tenant_id
     AND md5((to_jsonb(p)-'requires_honest_sign')::text)=e.other_fields_hash) <> {len(changed)} THEN
   RAISE EXCEPTION 'Target field readback or unchanged fields failed';
 END IF;
 IF (SELECT md5(string_agg(p.id::text || ':' || p.requires_honest_sign::text,',' ORDER BY p.id))
     FROM products p WHERE p.id NOT IN (SELECT id FROM marking_expected))
    IS DISTINCT FROM (SELECT fingerprint FROM marking_untouched) THEN
   RAISE EXCEPTION 'Noncandidate flag fingerprint changed';
 END IF;
END $$;
COMMIT;
"""
        # No retries: if transport fails, use verify to determine committed state.
        query(args.host, sql)
    current = json.loads(
        query(
            args.host,
            f"""BEGIN READ ONLY;
SELECT jsonb_agg(jsonb_build_object('id',id,'requires_honest_sign',requires_honest_sign,
'other_fields_hash',md5((to_jsonb(p)-'requires_honest_sign')::text)) ORDER BY id)
FROM products p WHERE id IN ({ids}); COMMIT;""",
        )
    )
    expected = {r["id"]: r for r in changed}
    assert len(current) == len(changed)
    assert all(
        r["requires_honest_sign"]
        and r["other_fields_hash"] == expected[r["id"]]["other_fields_hash"]
        for r in current
    )
    summary = {
        "task": "WMS-604",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": manifest["rows_sha256"],
        "eligible": len(rows),
        "changed_and_verified": len(current),
        "already_true": len(rows) - len(current),
        "other_candidate_fields_unchanged": True,
        "tenants": {},
    }
    for row in rows:
        tenant = summary["tenants"].setdefault(
            row["tenant_name"], {"eligible": 0, "changed": 0, "already_true": 0}
        )
        tenant["eligible"] += 1
        tenant["already_true" if row["requires_honest_sign"] else "changed"] += 1
    if args.report:
        save(args.report, summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
