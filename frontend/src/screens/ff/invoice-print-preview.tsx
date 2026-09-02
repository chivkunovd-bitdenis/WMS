import { StrictMode, useEffect, useRef } from 'react'
import { createRoot } from 'react-dom/client'

import { buildInvoicePrintHtml } from './invoicePrint'

// Превью печатной формы счёта. Форма живёт в отдельном окне печати, и увидеть
// её иначе можно только выставив настоящий счёт — а смотреть на неё глазами
// надо каждый раз, когда её правят.

const HTML = buildInvoicePrintHtml({
  number: 'СЧ-2026-000117',
  dateLabel: 'от 02.09.2026',
  periodLabel: '01.08.2026 — 31.08.2026',
  supplierName: 'Фулфилмент',
  payerName: 'ООО «Ромашка»',
  supplier: {
    legal_name: 'ООО «Короб ВМС»',
    inn: '7712345678',
    kpp: '771201001',
    bank_name: 'АО «Тинькофф Банк»',
    bik: '044525974',
    settlement_account: '40702810000000012345',
    correspondent_account: '30101810145250000974',
  },
  payer: {
    legal_name: 'ООО «Ромашка»',
    inn: '5024998877',
    kpp: '502401001',
  },
  lines: [
    { description: 'Приёмка товара', quantity: '1 800', unit: 'шт.', price: '3,00 ₽', amount: '5 400,00 ₽' },
    { description: 'Упаковка заказов', quantity: '685', unit: 'шт.', price: '5,00 ₽', amount: '3 425,00 ₽' },
    { description: 'Сборка заказов FBS', quantity: '317', unit: 'шт.', price: '15,00 ₽', amount: '4 755,00 ₽' },
    { description: 'Хранение, литро-дни', quantity: '1 240', unit: 'л·дн', price: '0,50 ₽', amount: '620,00 ₽' },
  ],
  total: '14 200,00 ₽',
  totalKopecks: 1420000,
})

export function InvoicePrintPreview() {
  const frame = useRef<HTMLIFrameElement | null>(null)
  useEffect(() => {
    const document_ = frame.current?.contentDocument
    if (!document_) return
    document_.open()
    document_.write(HTML)
    document_.close()
  }, [])
  return (
    <iframe
      ref={frame}
      title="Печатная форма счёта"
      style={{ width: '100%', height: '100vh', border: 0, background: '#fff' }}
    />
  )
}

type RootHost = HTMLElement & { __previewRoot?: ReturnType<typeof createRoot> }

const container = document.getElementById('root') as RootHost | null
if (container) {
  const root = container.__previewRoot ?? createRoot(container)
  container.__previewRoot = root
  root.render(
    <StrictMode>
      <InvoicePrintPreview />
    </StrictMode>,
  )
}
