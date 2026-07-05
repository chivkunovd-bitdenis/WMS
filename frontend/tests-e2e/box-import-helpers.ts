import { execFileSync } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const BOX_IMPORT_BAD_XLSX = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  'fixtures',
  'box-import-bad-columns.xlsx',
);

type CombainRow = { barcode: string; qty: number; address: string };

/** Minimal xlsx for «Штрих-код комбайн» (requires openpyxl — installed with backend deps). */
export function writeCombainXlsx(outPath: string, rows: CombainRow[]): void {
  const payload = JSON.stringify(rows);
  const py = `
import json, sys
from openpyxl import Workbook
rows = json.loads(sys.argv[1])
wb = Workbook()
ws = wb.active
ws.append(['Штрих-код', 'Кол-во', 'Адрес'])
for r in rows:
    ws.append([r['barcode'], r['qty'], r['address']])
wb.save(sys.argv[2])
`;
  execFileSync('python3', ['-c', py, payload, outPath], {
    stdio: 'pipe',
  });
}

export function tempCombainXlsx(rows: CombainRow[]): string {
  const dir = mkdtempSync(path.join(tmpdir(), 'wms-box-import-'));
  const out = path.join(dir, 'boxes.xlsx');
  writeCombainXlsx(out, rows);
  return out;
}
