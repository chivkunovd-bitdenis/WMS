import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

// WMS-406: local operational export. Never commit the source JSON or workbook.
const [sourcePath, outputPath] = process.argv.slice(2);
assert(sourcePath && outputPath, 'Pass source JSON and output XLSX paths');
const source = JSON.parse(await fs.readFile(sourcePath, 'utf8'));
const rows = source.rows;
assert(Array.isArray(rows) && rows.length > 0);
assert.equal(rows.length, source.count);
assert.equal(new Set(rows.map(row => String(row.order_wb))).size, rows.length);
const totalQuantity = rows.reduce((sum, row) => sum + row.quantity, 0);
assert.equal(totalQuantity, source.quantity);
const start = Date.parse(`${source.period_from}T00:00:00+03:00`);
const end = Date.parse(`${source.period_to}T00:00:00+03:00`) + 86400000;
for (const row of rows) {
  const moment = Date.parse(row.handed_over_msk);
  assert(Number.isFinite(moment) && start <= moment && moment < end);
  assert(Number.isSafeInteger(row.quantity) && row.quantity > 0);
}
rows.sort((a, b) => Date.parse(a.handed_over_msk) - Date.parse(b.handed_over_msk)
  || String(a.order_wb).localeCompare(String(b.order_wb), 'en', { numeric: true }));
const text = value => {
  const result = value == null ? '' : String(value);
  return result.startsWith('=') ? `'${result}` : result;
};
const values = rows.map(row => [
  text(row.order_wb),
  // Excel has no timezone. Encode Moscow wall-clock time as a typed date.
  new Date(Date.parse(row.handed_over_msk) + 3 * 3600000),
  row.quantity, text(row.product), text(row.article), text(row.barcode),
  text([row.supply_number, row.supply_wb].filter(Boolean).join(' / ')),
]);
const last = 7 + rows.length;
const workbook = Workbook.create();
const sheet = workbook.worksheets.add('Отгруженные заказы');
sheet.showGridLines = false;
sheet.tabColor = '#34495E';
sheet.getRange(`A1:G${last}`).format.font = { name: 'Arial', size: 10, color: '#20252B' };
sheet.getRange(`A1:G${last}`).format.verticalAlignment = 'center';
sheet.getRange('A2').values = [['Loviana — отгруженные заказы WB FBS']];
sheet.getRange('A2').format.font = { name: 'Arial', size: 14, bold: true };
const ruDate = value => value.split('-').reverse().join('.');
sheet.getRange('A3').values = [[`${ruDate(source.period_from)}–${ruDate(source.period_to)} включительно (МСК)`]];
sheet.getRange('A4').values = [['Заказов']];
sheet.getRange('B4').formulas = [[`=COUNTA(A8:A${last})`]];
sheet.getRange('C4').values = [['Штук']];
sheet.getRange('D4').formulas = [[`=SUM(C8:C${last})`]];
sheet.getRange('A4:D4').format.font.bold = true;
sheet.getRange('A5').values = [['Источник: WMS, успешная передача поставки WB.']];
sheet.getRange('A5').format.font = { name: 'Arial', size: 10, italic: true, color: '#65717C' };
sheet.getRange('A7:G7').values = [['Заказ WB', 'Передан, дата и время МСК', 'Кол-во, шт.', 'Товар', 'Артикул', 'Штрихкод', 'Поставка']];
sheet.getRange(`A8:G${last}`).values = values;
for (const column of ['A', 'E', 'F', 'G']) sheet.getRange(`${column}8:${column}${last}`).setNumberFormat('@');
sheet.getRange(`B8:B${last}`).setNumberFormat('dd.mm.yyyy hh:mm:ss');
sheet.getRange(`C8:C${last}`).setNumberFormat('#,##0');
sheet.getRange('B4').setNumberFormat('#,##0');
sheet.getRange('D4').setNumberFormat('#,##0');
const widths = { A: 17, B: 26, C: 12, D: 44, E: 23, F: 21, G: 40 };
for (const [column, width] of Object.entries(widths)) sheet.getRange(`${column}1:${column}${last}`).format.columnWidth = width;
sheet.getRange(`A8:G${last}`).format.rowHeight = 30;
sheet.getRange(`D8:G${last}`).format.wrapText = true;
sheet.getRange(`A8:A${last}`).format.horizontalAlignment = 'left';
sheet.getRange(`C8:C${last}`).format.horizontalAlignment = 'right';
sheet.getRange('A7:G7').format = {
  fill: '#34495E', font: { name: 'Arial', size: 10, bold: true, color: '#FFFFFF' },
  horizontalAlignment: 'center', verticalAlignment: 'center', rowHeight: 30,
};
sheet.getRange('A2:G2').format.rowHeight = 24;
sheet.freezePanes.freezeRows(7);
sheet.freezePanes.freezeColumns(1);
const table = sheet.tables.add(`A7:G${last}`, true, 'LovianaOrders');
table.style = 'TableStyleMedium2';
table.showFilterButton = true;
workbook.recalculate();
assert.equal(sheet.getRange('B4').values[0][0], source.count);
assert.equal(sheet.getRange('D4').values[0][0], source.quantity);
const errors = await workbook.inspect({
  kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!',
  options: { useRegex: true, maxResults: 20 }, maxChars: 1000,
});
console.log(errors.ndjson);
console.log((await workbook.inspect({ kind: 'table', range: `'Отгруженные заказы'!A4:D4`, include: 'values,formulas', tableMaxRows: 1, tableMaxCols: 4, maxChars: 1500 })).ndjson);
await fs.mkdir(path.dirname(outputPath), { recursive: true });
const preview = await workbook.render({ sheetName: sheet.name, range: 'A1:G17', scale: 1.5, format: 'png' });
await fs.writeFile(`${outputPath}.preview.png`, new Uint8Array(await preview.arrayBuffer()));
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
console.log(JSON.stringify({ rows: rows.length, quantity: totalQuantity, outputPath, firstDate: rows[0].handed_over_msk, lastDate: rows.at(-1).handed_over_msk }));
