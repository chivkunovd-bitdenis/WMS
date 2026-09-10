"""Change only the synthetic emulator label; restore it after scoped UI checks."""
from pathlib import Path
import hashlib
import json
import sqlite3
import sys

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / 'wms363-astra-20260910'
connection = sqlite3.connect(FIXTURE / 'emulator.sqlite')
rows = connection.execute('''select a.storage_path,a.id,o.id from fbs_print_assets a
join fbs_orders o on o.id=a.fbs_order_id
join users u on u.tenant_id=o.tenant_id
where u.email='wms363-emulator@example.com' and o.external_order_id='363-TEST-0'
''').fetchall()
assert len(rows) == 1
root = (FIXTURE / 'fixture-data').resolve()
label = (root / rows[0][0]).resolve()
assert label.is_relative_to(root) and label.suffix == '.pdf'
backup = HERE / 'fixture-original.bin'
mode = sys.argv[1]
if mode == 'restore':
    assert backup.is_file()
    label.write_bytes(backup.read_bytes())
else:
    if not backup.exists():
        original = label.read_bytes()
        assert original.startswith(b'%PDF') and len(original) < 16384
        backup.write_bytes(original)
    if mode == 'oversize':
        original = backup.read_bytes()
        with label.open('wb') as stream:
            stream.write(original)
            remaining = 17 * 1024 * 1024 - len(original)
            while remaining:
                count = min(remaining, 8192)
                stream.write(b' ' * count)
                remaining -= count
    elif mode == 'pdf32':
        import fitz
        import random
        randomizer = random.Random(363)
        with fitz.open() as pdf:
            for index in range(32):
                page = pdf.new_page(width=164.4, height=113.4)
                page.insert_text((8, 12), f'SYNTHETIC PAGE {index + 1}', fontsize=8)
                shape = page.new_shape()
                for y in range(20):
                    for x in range(30):
                        rect = fitz.Rect(7+x*5, 17+y*4, 11+x*5, 20+y*4)
                        shape.draw_rect(rect)
                        shade = randomizer.random()
                        shape.finish(color=None, fill=(shade, shade, shade))
                shape.commit()
            data = pdf.tobytes(deflate=True)
        assert len(data) < 16 * 1024 * 1024
        label.write_bytes(data)
    else:
        raise ValueError('Expected oversize, pdf32 or restore')
digest = hashlib.sha256(label.read_bytes()).hexdigest()
connection.execute("update fbs_print_assets set status='ready', checksum=?, error_code=NULL, error_message=NULL where id=?", ('sha256:' + digest, rows[0][1]))
connection.execute("update fbs_orders set sticker_status='ready' where id=?", (rows[0][2],))
connection.commit()
print(json.dumps({'mode': mode, 'bytes': label.stat().st_size, 'sha256': hashlib.sha256(label.read_bytes()).hexdigest()}))
