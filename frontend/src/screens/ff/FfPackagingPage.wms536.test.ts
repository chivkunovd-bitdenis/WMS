import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

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

  it('неоднозначный код от сервера показывается понятным текстом', () => {
    expect(source).toContain("import { PRODUCT_SCAN_AMBIGUOUS_MESSAGE } from '../../utils/productScanResolver'")
    const messages = source.slice(
      source.indexOf('const PACKAGING_API_MESSAGES_RU'),
      source.indexOf('async function readPackagingApiErrorMessage'),
    )
    expect(messages).toContain('barcode_ambiguous: PRODUCT_SCAN_AMBIGUOUS_MESSAGE')
  })
})
