import { afterEach, expect, it, vi } from 'vitest'
import { PDFDocument } from 'pdf-lib'
import { buildFbsPdfPrintTape } from './fbsPdfPrintTape'

afterEach(() => vi.unstubAllGlobals())

it('prints Ozon PDF pairs in box order as one document, preserving page sizes and copies', async () => {
  const first = await PDFDocument.create()
  first.addPage([58, 40])
  first.addPage([58, 41])
  const second = await PDFDocument.create()
  second.addPage([60, 40])
  second.addPage([60, 41])
  const files = new Map([
    ['box-1', await first.save()],
    ['box-2', await second.save()],
  ])
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({
    ok: true,
    arrayBuffer: async () => files.get(url),
  })))

  const blob = await buildFbsPdfPrintTape(['box-1', 'box-2'], 2)
  const tape = await PDFDocument.load(await blob.arrayBuffer())

  expect(blob.type).toBe('application/pdf')
  expect(tape.getPages().map((page) => [page.getWidth(), page.getHeight()])).toEqual([
    [58, 40], [58, 41], [58, 40], [58, 41],
    [60, 40], [60, 41], [60, 40], [60, 41],
  ])
  expect(fetch).toHaveBeenCalledTimes(2)
})
