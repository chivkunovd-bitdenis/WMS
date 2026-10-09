// Demo only. Both routes read the very same snapshot of box contents.
export type PackingRow = { boxBarcode: string; productBarcode: string; quantity: number }
export type Snapshot = { shipment: string; seller: string; supply: string; rows: PackingRow[] }

const esc = (value: string) => value.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' }[c]!))
const encoder = new TextEncoder()
const crc32 = (bytes: Uint8Array) => {
  let crc = 0xffffffff
  for (const byte of bytes) {
    crc ^= byte
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0)
  }
  return (crc ^ 0xffffffff) >>> 0
}
function zip(files: Record<string, string>) {
  const local: Uint8Array[] = [], central: Uint8Array[] = []
  let offset = 0, centralSize = 0
  for (const [name, content] of Object.entries(files)) {
    const n = encoder.encode(name), data = encoder.encode(content), crc = crc32(data)
    const header = new Uint8Array(30 + n.length), h = new DataView(header.buffer)
    h.setUint32(0, 0x04034b50, true); h.setUint16(4, 20, true); h.setUint32(14, crc, true)
    h.setUint32(18, data.length, true); h.setUint32(22, data.length, true); h.setUint16(26, n.length, true)
    header.set(n, 30); local.push(header, data)
    const directory = new Uint8Array(46 + n.length), d = new DataView(directory.buffer)
    d.setUint32(0, 0x02014b50, true); d.setUint16(4, 20, true); d.setUint16(6, 20, true)
    d.setUint32(16, crc, true); d.setUint32(20, data.length, true); d.setUint32(24, data.length, true)
    d.setUint16(28, n.length, true); d.setUint32(42, offset, true); directory.set(n, 46)
    central.push(directory); offset += header.length + data.length; centralSize += directory.length
  }
  const end = new Uint8Array(22), e = new DataView(end.buffer)
  e.setUint32(0, 0x06054b50, true); e.setUint16(8, central.length, true); e.setUint16(10, central.length, true)
  e.setUint32(12, centralSize, true); e.setUint32(16, offset, true)
  return new Blob([...local, ...central, end] as BlobPart[], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
}
export function packingXlsx(snapshot: Snapshot) {
  const main = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
  const rows: (string | number)[][] = [['ШК товара', 'Количество', 'ШК короба'], ...snapshot.rows.map(r => [r.productBarcode, r.quantity, r.boxBarcode])]
  const sheet = (data: (string | number)[][]) => `<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="${main}"><cols><col min="1" max="1" width="24" customWidth="1"/><col min="2" max="2" width="26" customWidth="1"/><col min="3" max="3" width="28" customWidth="1"/></cols><sheetData>${data.map((r, i) => `<row r="${i + 1}">${r.map((v, j) => typeof v === 'number' ? `<c r="${String.fromCharCode(65 + j)}${i + 1}"><v>${v}</v></c>` : `<c r="${String.fromCharCode(65 + j)}${i + 1}" t="inlineStr"><is><t>${esc(v)}</t></is></c>`).join('')}</row>`).join('')}</sheetData></worksheet>`
  return zip({
    '[Content_Types].xml': '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
    '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
    'xl/workbook.xml': `<workbook xmlns="${main}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Состав коробов" sheetId="1" r:id="rId1"/><sheet name="Демонстрационные данные" sheetId="2" r:id="rId2"/></sheets></workbook>`,
    'xl/_rels/workbook.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>',
    'xl/worksheets/sheet1.xml': sheet(rows),
    'xl/worksheets/sheet2.xml': sheet([['Макет', 'Не загружать в рабочий кабинет WB'], ['Отгрузка', snapshot.shipment], ['Селлер', snapshot.seller], ['Поставка WB', snapshot.supply], ['Шаблон', 'Демонстрационный, совместимость с WB не проверена']]),
  })
}
export function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob), anchor = document.createElement('a')
  anchor.href = url; anchor.download = name; anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 30000)
}
