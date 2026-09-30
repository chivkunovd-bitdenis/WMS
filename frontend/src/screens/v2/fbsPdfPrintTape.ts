import { PDFDocument } from 'pdf-lib'

/** Keep every page of each Ozon label together and in box order. */
export async function buildFbsPdfPrintTape(urls: string[], copies: number): Promise<Blob> {
  const tape = await PDFDocument.create()
  const count = Math.max(1, Math.min(99, Math.trunc(copies) || 1))

  for (const url of urls) {
    const response = await fetch(url)
    if (!response.ok) throw new Error('Не удалось загрузить этикетку Ozon для общей ленты.')
    const source = await PDFDocument.load(await response.arrayBuffer())
    for (let copy = 0; copy < count; copy += 1) {
      const pages = await tape.copyPages(source, source.getPageIndices())
      for (const page of pages) tape.addPage(page)
    }
  }

  const bytes = await tape.save()
  const buffer = new ArrayBuffer(bytes.byteLength)
  new Uint8Array(buffer).set(bytes)
  return new Blob([buffer], { type: 'application/pdf' })
}
