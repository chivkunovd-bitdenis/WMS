import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

// WMS-536 · отгрузка на маркетплейс: какие поля ищут товар единым поиском,
// а какие товар не ищут вовсе. Экран слишком велик для отдельного рендера,
// поэтому проверяется проводка; сам поиск покрыт productScanResolver.test.ts.

const source = readFileSync(new URL('./FfSuppliesShipmentsPage.tsx', import.meta.url), 'utf8')

function slice(from: string, to: string): string {
  const start = source.indexOf(from)
  const end = source.indexOf(to, start + from.length)
  expect(start).toBeGreaterThan(-1)
  expect(end).toBeGreaterThan(start)
  return source.slice(start, end)
}

describe('WMS-536 · S-OUT-03 «Добавить по ШК» в плане отгрузки', () => {
  const addLine = slice('const addMpLineByBarcode = async', 'useBarcodeScanner({')

  it('ищет товар единым поиском по каталогу селлера, а не прежним поиском первого товара', () => {
    expect(source).not.toContain('resolveProductIdByBarcode')
    expect(source).not.toContain("utils/resolveProductByBarcode'")
    expect(addLine).toContain('const index = catalogProductScanIndex(rows)')
  })

  it('сканер сначала ищет исходные символы, латиница по клавишам — только запасной кандидат (R7)', () => {
    expect(addLine).toContain('resolveProductScan(index, wedgeRaw, { layoutCandidate: code })')
    expect(addLine).toContain(': resolveProductScan(index, code)')
    const planScanner = slice('useBarcodeScanner({', 'useBarcodeScanner({\n    enabled:\n')
    expect(planScanner).toContain("mpUnloadTab === 'plan'")
    expect(planScanner).toContain('void addMpLineByBarcode(code, scan.raw)')
    // Ручное поле и кнопка раскладку не исправляют: без второго аргумента.
    expect(source.match(/void addMpLineByBarcode\(\)/g)).toHaveLength(2)
  })

  it('неоднозначный код останавливает добавление до любого запроса (R2)', () => {
    const ambiguous = addLine.indexOf("productLookup.status === 'ambiguous'")
    expect(ambiguous).toBeGreaterThan(-1)
    expect(addLine.slice(ambiguous, ambiguous + 200)).toContain('setModalError(PRODUCT_SCAN_AMBIGUOUS_MESSAGE)')
    expect(addLine.indexOf("method: 'DELETE'")).toBeGreaterThan(ambiguous)
    expect(addLine.indexOf('postMpLine(')).toBeGreaterThan(ambiguous)
    expect(addLine).toContain("setModalError('Товар не найден по штрихкоду или артикулу.')")
  })
})

describe('WMS-536 · S-OUT-04 присоединение готового короба не ищет товар', () => {
  it('принимает только WHB-/INB- без единого поиска товара', () => {
    const attach = slice('const requestAttachBoxScan = (rawInput?: string) => {', 'const confirmAttachBox = async')
    expect(attach).toContain("!raw.startsWith('WHB-') && !raw.startsWith('INB-')")
    expect(attach).not.toContain('resolveProductScan')
    const packagingScanner = slice("mpUnloadTab === 'packaging' &&", 'const applyMpProductPicker')
    expect(packagingScanner).toContain('requestAttachBoxScan(code)')
    expect(packagingScanner).not.toContain('resolveProductScan')
  })
})
