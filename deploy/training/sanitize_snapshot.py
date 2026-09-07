#!/usr/bin/env python3
"""Remove source credentials from a pg_dump COPY stream before transferring it."""
import argparse
import gzip
import json
from pathlib import Path

SECRET_COLUMNS = {
    "seller_wildberries_credentials": {
        "content_token_encrypted", "supplies_token_encrypted", "marketplace_token_encrypted",
    },
    "seller_marking_credentials": {"cz_token_enc", "suz_oms_token_enc", "mp_api_key_enc"},
    "marketplace_accounts": {"secret_encrypted"},
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    counts, changed = {}, {}
    table, columns = None, []
    with gzip.open(args.source, "rt") as source, args.destination.open("xb") as target:
        args.destination.chmod(0o600)
        with gzip.open(target, "wt") as output:
            for line in source:
                if line.startswith("COPY public."):
                    table = line.split()[1][7:]
                    columns = line.split("(", 1)[1].split(")", 1)[0].split(", ")
                    counts[table] = 0
                elif line == "\\.\n":
                    table = None
                elif table:
                    counts[table] += 1
                    values = line.rstrip("\n").split("\t")
                    assert len(values) == len(columns), table
                    replacements = {name: "\\N" for name in SECRET_COLUMNS.get(table, set())}
                    if table == "users":
                        # Replaced with fresh bcrypt hashes during private bootstrap,
                        # before any API process is started.
                        replacements["password_hash"] = "training-reset-required"
                    for name, replacement in replacements.items():
                        index = columns.index(name)
                        if values[index] != "\\N":
                            changed[f"{table}.{name}"] = changed.get(f"{table}.{name}", 0) + 1
                        values[index] = replacement
                    line = "\t".join(values) + "\n"
                output.write(line)
    print(json.dumps({"rows": counts, "removed_credentials": changed}, indent=2))


if __name__ == "__main__":
    main()
