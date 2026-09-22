import type { FailedRow } from './data'

function escapePdfText(input: string): string {
  return input.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)')
}

function transliterate(input: string): string {
  const map: Record<string, string> = {
    А: 'A', Б: 'B', В: 'V', Г: 'G', Д: 'D', Е: 'E', Ё: 'E', Ж: 'Zh',
    З: 'Z', И: 'I', Й: 'Y', К: 'K', Л: 'L', М: 'M', Н: 'N', О: 'O',
    П: 'P', Р: 'R', С: 'S', Т: 'T', У: 'U', Ф: 'F', Х: 'Kh', Ц: 'Ts',
    Ч: 'Ch', Ш: 'Sh', Щ: 'Shch', Ъ: '', Ы: 'Y', Ь: '', Э: 'E', Ю: 'Yu',
    Я: 'Ya',
    а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh',
    з: 'z', и: 'i', й: 'y', к: 'k', л: 'l', м: 'm', н: 'n', о: 'o',
    п: 'p', р: 'r', с: 's', т: 't', у: 'u', ф: 'f', х: 'kh', ц: 'ts',
    ч: 'ch', ш: 'sh', щ: 'shch', ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu',
    я: 'ya',
    '«': '"', '»': '"', '—': '-', '–': '-', '…': '...', '№': 'No.',
    '×': 'x',
  }
  return input.replace(/[\s\S]/g, (ch) => {
    if (map[ch] != null) return map[ch]
    const code = ch.charCodeAt(0)
    if (code >= 0x20 && code <= 0x7e) return ch
    return '?'
  })
}

function stableHash(input: string): number {
  let hash = 5381 >>> 0
  for (let i = 0; i < input.length; i++) {
    hash = (Math.imul(hash, 33) ^ input.charCodeAt(i)) >>> 0
  }
  return hash
}

function moduleFilled(seed: number, i: number, j: number, size: number): boolean {
  if (i === 0) return true
  if (j === 0) return true
  if (i === size - 1) return j % 2 === 0
  if (j === size - 1) return i % 2 === 0
  let h = seed
  h = Math.imul(h ^ i, 2654435761) >>> 0
  h = Math.imul(h ^ j, 2246822519) >>> 0
  h = Math.imul(h + (i * j + 17), 40503) >>> 0
  return (h & 1) === 1
}

function buildLabelPageContent(row: FailedRow, pageIndex: number, pageTotal: number): string {
  const seed = stableHash(row.markingCode)
  const modules = 20
  const cell = 8
  const dmSize = modules * cell
  const dmX = 118
  const dmY = 300

  const labelX = 97
  const labelY = 170
  const labelW = 400
  const labelH = 500
  const stripeH = 50
  const stripeY = labelY + labelH - stripeH

  const rightX = dmX + dmSize + 22
  const rightTopY = dmY + dmSize - 10

  let out = ''
  out += 'q\n'

  // Yellow warning stripe
  out += '0.98 0.86 0.44 rg\n'
  out += `${labelX} ${stripeY} ${labelW} ${stripeH} re f\n`
  // Warning text
  out += '0.42 0.19 0.04 rg\n'
  out += `BT\n/F2 14 Tf\n${labelX + 16} ${stripeY + 26} Td\n(TESTOVAYA ETIKETKA - NE SKANIROVAT) Tj\nET\n`
  out += `BT\n/F1 10 Tf\n${labelX + 16} ${stripeY + 10} Td\n(TEST LABEL - DO NOT SCAN) Tj\nET\n`

  // Label border and stripe separator
  out += '0 0 0 rg\n'
  out += '0.8 w\n'
  out += `${labelX} ${labelY} ${labelW} ${labelH} re S\n`
  out += '0.75 0.75 0.75 RG\n'
  out += '0.4 w\n'
  out += `${labelX} ${stripeY} m ${labelX + labelW} ${stripeY} l S\n`

  // DataMatrix modules
  out += '0 0 0 rg\n'
  for (let i = 0; i < modules; i++) {
    for (let j = 0; j < modules; j++) {
      if (!moduleFilled(seed, i, j, modules)) continue
      const x = dmX + i * cell
      const y = dmY + j * cell
      out += `${x} ${y} ${cell} ${cell} re f\n`
    }
  }
  out += '0.4 0.4 0.4 rg\n'
  out += `BT\n/F1 8 Tf\n${dmX} ${dmY - 14} Td\n(DataMatrix (test, ne sozdaet realnyy kod)) Tj\nET\n`

  // Right text (header split over two lines to keep a safe right margin inside the label)
  out += '0 0 0 rg\n'
  out += `BT\n/F2 12 Tf\n14 TL\n${rightX} ${rightTopY} Td\n(NEPODGRUZHENNAYA) Tj\nT*\n(ETIKETKA) Tj\nET\n`
  out += `BT\n/F1 11 Tf\n14 TL\n${rightX} ${rightTopY - 34} Td\n`
  out += `(GTIN:    ${escapePdfText(transliterate(row.syntheticGtin))}) Tj T*\n`
  out += `(Artikul: ${escapePdfText(transliterate(row.syntheticVendorCode))}) Tj T*\n`
  out += `(Razmer:  ${escapePdfText(transliterate(row.syntheticSize))}) Tj T*\n`
  out += `(List:    ${pageIndex} iz ${pageTotal}) Tj\nET\n`

  // Marking code footer
  out += '0.15 0.15 0.15 rg\n'
  out += `BT\n/F2 9 Tf\n${labelX + 12} ${labelY + 42} Td\n(KIZ (test, ASCII):) Tj\nET\n`
  out += '0 0 0 rg\n'
  out += `BT\n/F1 10 Tf\n${labelX + 12} ${labelY + 26} Td\n(${escapePdfText(transliterate(row.markingCode))}) Tj\nET\n`

  // Prototype footnote
  out += '0.5 0.5 0.5 rg\n'
  out += `BT\n/F1 8 Tf\n${labelX + 12} ${labelY + 12} Td\n(WMS-476 prototype - ne dlya skanirovaniya) Tj\nET\n`

  out += 'Q\n'
  return out
}

export function buildFailedCodesPdf(rows: FailedRow[]): Blob {
  const encoder = new TextEncoder()
  const chunks: string[] = []
  let position = 0
  const push = (chunk: string) => {
    chunks.push(chunk)
    position += encoder.encode(chunk).byteLength
  }

  const offsets: number[] = []
  const writeObject = (id: number, body: string) => {
    offsets[id] = position
    push(`${id} 0 obj\n${body}\nendobj\n`)
  }

  push('%PDF-1.4\n%\xE2\xE3\xCF\xD3\n')

  const pageCount = rows.length
  const pageIds: number[] = []
  const contentIds: number[] = []
  for (let index = 0; index < pageCount; index++) {
    pageIds.push(5 + 2 * index)
    contentIds.push(6 + 2 * index)
  }

  writeObject(1, '<< /Type /Catalog /Pages 2 0 R >>')
  writeObject(
    2,
    `<< /Type /Pages /Count ${pageCount} /Kids [${pageIds
      .map((id) => `${id} 0 R`)
      .join(' ')}] >>`,
  )
  writeObject(3, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>')
  writeObject(
    4,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>',
  )

  for (let index = 0; index < pageCount; index++) {
    const row = rows[index]
    if (!row) continue
    const rawContent = buildLabelPageContent(row, index + 1, pageCount)
    const streamBody = rawContent.endsWith('\n') ? rawContent.slice(0, -1) : rawContent
    const contentLength = encoder.encode(streamBody).byteLength
    writeObject(
      pageIds[index]!,
      '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] ' +
        `/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> ` +
        `/Contents ${contentIds[index]!} 0 R >>`,
    )
    writeObject(
      contentIds[index]!,
      `<< /Length ${contentLength} >>\nstream\n${streamBody}\nendstream`,
    )
  }

  const objectCount = 4 + 2 * pageCount
  const xrefOffset = position
  let xref = `xref\n0 ${objectCount + 1}\n0000000000 65535 f \n`
  for (let id = 1; id <= objectCount; id++) {
    xref += `${String(offsets[id]).padStart(10, '0')} 00000 n \n`
  }
  push(xref)
  push(
    `trailer\n<< /Size ${objectCount + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`,
  )

  return new Blob(chunks, { type: 'application/pdf' })
}

export function downloadBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  setTimeout(() => URL.revokeObjectURL(url), 0)
}
