"""WMS-387: anonymize personal fields in the destination, preserving goods/orders."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine, text
from app.core.settings import settings

assert settings.database_url.split('@')[-1] == 'db:5432/wms', 'Training DB required'
assert settings.wildberries_marketplace_api_base == 'http://wb-emulator:8000', 'Local emulator required'
engine = create_engine(settings.database_url.replace('+psycopg_async', '+psycopg'))
login = json.loads(Path('/training/private/training-login.json').read_text())
PRIVATE_FIELDS = {'inn', 'kpp', 'bank_name', 'bik', 'settlement_account', 'correspondent_account'}


def fingerprint(c, table):
    rows = c.execute(text(f'SELECT row_to_json(t)::text FROM "{table}" t ORDER BY id')).scalars()
    digest = hashlib.sha256()
    for row in rows:
        digest.update(row.encode())
        digest.update(b'\n')
    return digest.hexdigest()


with engine.begin() as c:
    c.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
    assert c.execute(text('SELECT count(*) FROM users WHERE email=:email'), {'email': login['email']}).scalar_one() == 1
    protected = ['products', 'fbs_orders', 'fbs_order_products', 'inventory_balances', 'inventory_movements']
    before = {table: fingerprint(c, table) for table in protected}
    columns = c.execute(text("""SELECT table_name,column_name,data_type FROM information_schema.columns
        WHERE table_schema='public' AND data_type IN ('text','character varying','json','jsonb')""")).all()
    pks = dict(c.execute(text("""SELECT tc.table_name,kcu.column_name FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name
            AND tc.table_schema=kcu.table_schema
        WHERE tc.table_schema='public' AND tc.constraint_type='PRIMARY KEY'""")).all())
    tables = sorted(pks)
    counts = {table:c.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one() for table in tables}
    replacements = {}
    emails = {}
    for uid, email in c.execute(text('SELECT id,email FROM users')):
        new = email if email == login['email'] else f'user-{str(uid)[:12]}@example.com'
        emails[str(uid)] = new
        if email != new:
            replacements[email] = new
    for sid, name in c.execute(text('SELECT id,name FROM sellers')):
        if name != 'Эмулятор WB':
            replacements[name] = f'Учебный селлер {str(sid)[:8]}'
    for tid, name, slug in c.execute(text('SELECT id,name,slug FROM tenants')):
        replacements[name] = 'Учебный WMS' if str(tid) == login['tenant_id'] else f'Учебная организация {str(tid)[:8]}'
        if slug:
            replacements[slug] = f'training-{str(tid)[:8]}'
    for (name,) in c.execute(text('SELECT legal_name FROM billing_profiles WHERE legal_name IS NOT NULL')):
        if name:
            replacements[name] = 'Учебная организация'
    # Match complete names/addresses so short demo names cannot alter SKU fragments.
    pattern = re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(k) for k in sorted(replacements, key=len, reverse=True)) + r')(?!\w)')

    def scrub(value):
        if isinstance(value, dict):
            return {k: ('' if k in PRIVATE_FIELDS else 'Учебная организация' if k == 'legal_name' else scrub(v))
                    for k,v in value.items()}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        if isinstance(value, str):
            return pattern.sub(lambda m: replacements[m.group()], value)
        return value

    changed = Counter()
    for table, column, kind in columns:
        if table not in pks or column == pks[table] or 'token' in column or 'secret' in column or 'password' in column:
            continue
        pk = pks[table]
        for key, value in c.execute(text(f'SELECT "{pk}","{column}" FROM "{table}" WHERE "{column}" IS NOT NULL')).all():
            if table == 'users' and column == 'email':
                updated = emails[str(key)]
            elif table == 'billing_profiles' and column in PRIVATE_FIELDS:
                updated = ''
            elif table == 'billing_profiles' and column == 'legal_name':
                updated = 'Учебная организация'
            else:
                updated = scrub(value)
            if updated == value:
                continue
            parameter = json.dumps(updated, ensure_ascii=False) if kind in ('json','jsonb') else updated
            expr = f'CAST(:value AS {kind})' if kind in ('json','jsonb') else ':value'
            c.execute(text(f'UPDATE "{table}" SET "{column}"={expr} WHERE "{pk}"=:key'), {'value':parameter,'key':key})
            changed[f'{table}.{column}'] += 1
    after = {table:fingerprint(c, table) for table in protected}
    assert before == after, 'Goods, orders or inventory changed; rolling back'
    assert counts == {table:c.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one() for table in tables}
    remaining = c.execute(text("SELECT count(*) FROM users WHERE email NOT LIKE '%@example.com'")).scalar_one()
    assert remaining == 0
print(json.dumps({'changed_fields': changed, 'unchanged_tables': len(tables),
                  'protected_table_hashes': after, 'historic_contact_emails_remaining': remaining}, indent=2))
