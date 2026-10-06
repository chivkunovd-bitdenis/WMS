import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

// This remains a DOM-contract test: it guards the selectors and labelled
// controls consumed by the local browser scenario. Keeping it source-level
// avoids mounting the 3,400-line page and makes the pre-code RED attributable
// to the missing product behaviour rather than an unrelated page bootstrap.
const source = readFileSync(new URL('./FfSuppliesShipmentsPage.tsx', import.meta.url), 'utf8')

describe('WMS-679 · MP-отгрузка WB: контракт документа до реализации', () => {
  it('C13: выгрузка находится у коробов WB, не подменяет импорт и не закрывает документ', () => {
    expect(source).toContain('data-testid="ff-mp-boxes-accordion"')
    expect(source).toContain('data-testid="ff-mp-import-boxes"')
    expect(source).toContain('data-testid="ff-mp-wb-fbw-export"')
    expect(source).toContain('Скачать XLSX для WB')
    expect(source).not.toContain('Этикетка WB готова')
  })

  it('C9: ошибка и устаревший ответ экспорта остаются в контексте открытого документа', () => {
    expect(source).toContain('wbFbwExportRequests')
    expect(source).toContain('data-testid="ff-mp-wb-fbw-export-error"')
    expect(source).toContain('data-testid="ff-mp-wb-fbw-export"')
  })

  it('C10: печать legacy INB не называется этикеткой приёмки WB', () => {
    expect(source).toContain("title: 'Внутренний ШК WMS'")
    expect(source).toContain("layout: 'internalBox'")
    expect(source).toContain('data-testid={`ff-mp-box-print-${box.id}`}')
    expect(source).not.toContain('Печать этикетки WB')
  })
})
