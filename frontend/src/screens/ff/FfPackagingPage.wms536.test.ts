import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { PRODUCT_SCAN_AMBIGUOUS_MESSAGE } from '../../utils/productScanResolver'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

// WMS-536 · S-PACK-01 упаковка: товар по коду ищет сервер среди строк задания.
// Экран отправляет код как есть и показывает смысл неоднозначности (R2).

const source = readFileSync(new URL('./FfPackagingPage.tsx', import.meta.url), 'utf8')

describe('WMS-536 · S-PACK-01 скан товара в задании упаковки', () => {
  it('поле по-прежнему отправляет серверу только сам код', () => {
    const submit = source.slice(
      source.indexOf('const submitScanner = async'),
      source.indexOf('const submitManualQty = async'),
    )
    expect(submit).toContain('const barcode = scannerValue.trim()')
    expect(submit).toContain('`/operations/packaging-tasks/${task.id}/scan`')
    expect(submit).toContain('body: JSON.stringify({ barcode })')
    expect(submit).toContain('setError(await readPackagingApiErrorMessage(res))')
    expect(submit).not.toContain('resolveProductScan')
  })

  it('неоднозначный код от сервера показывается общим текстом, без своего перевода', async () => {
    const messages = source.slice(
      source.indexOf('const PACKAGING_API_MESSAGES_RU'),
      source.indexOf('async function readPackagingApiErrorMessage'),
    )
    expect(messages).not.toContain('barcode_ambiguous')
    const reader = source.slice(
      source.indexOf('async function readPackagingApiErrorMessage'),
      source.indexOf('export function FfPackagingTaskPanel'),
    )
    expect(reader).toContain('const message = await readApiErrorMessage(res)')
    // Ответ упаковки: код и серверный текст; и голый код — оба дают общий текст.
    const structured = new Response(
      JSON.stringify({ detail: { code: 'barcode_ambiguous', message: 'текст сервера' } }),
      { status: 409 },
    )
    const plain = new Response(JSON.stringify({ detail: 'barcode_ambiguous' }), { status: 409 })
    expect(await readApiErrorMessage(structured)).toBe(PRODUCT_SCAN_AMBIGUOUS_MESSAGE)
    expect(await readApiErrorMessage(plain)).toBe(PRODUCT_SCAN_AMBIGUOUS_MESSAGE)
  })
})
