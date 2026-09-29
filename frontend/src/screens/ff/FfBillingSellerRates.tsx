import { useEffect, useState } from 'react'
import { DataTable, ErrorNotice, MoneyCell, TextCell } from '../../ui-kit'
import { formatMoscowDate } from './FfBillingScreen'

/**
 * Вкладка «Ставки» кабинета селлера (WMS-549, R7).
 *
 * Действующие сейчас ставки: одна строка «Все товары» на услугу (тот же
 * приоритет, что и при начислении) и отдельные строки на его товары. Второго
 * независимого расчёта нет — сервер отдаёт готовый список без периода и фильтров.
 */

type SellerBillingRate = {
  service_code: string
  unit: string
  rate_kopecks: number
  valid_from_at: string
  product_id: string | null
  product_sku: string | null
  product_name: string | null
}

const serviceLabels: Record<string, string> = {
  inbound: 'Приёмка',
  marketplace_outbound: 'Отгрузка',
  packing: 'Упаковка',
  return: 'Возврат',
  storage: 'Хранение',
  fbs_order: 'FBS',
}

// Те же сокращения, что и в печатной форме счёта (invoicePrint.ts).
const unitLabels: Record<string, string> = { document: 'док.', item: 'шт.', liter_day: 'л·дн' }

const columns = [
  {
    key: 'service',
    header: 'Услуга',
    width: 160,
    render: (row: SellerBillingRate) => <TextCell value={serviceLabels[row.service_code] ?? row.service_code} />,
  },
  {
    key: 'target',
    header: 'На что',
    width: 320,
    render: (row: SellerBillingRate) => (
      <TextCell
        value={row.product_id ? `${row.product_sku ?? ''} · ${row.product_name ?? ''}` : 'Все товары'}
        width={300}
      />
    ),
  },
  {
    key: 'rate',
    header: 'Ставка, ₽',
    width: 130,
    align: 'right' as const,
    render: (row: SellerBillingRate) => <MoneyCell minor={row.rate_kopecks} />,
  },
  {
    key: 'unit',
    header: 'Ед.',
    width: 90,
    render: (row: SellerBillingRate) => <TextCell value={unitLabels[row.unit] ?? row.unit} />,
  },
  {
    key: 'validFrom',
    header: 'Действует с',
    width: 150,
    render: (row: SellerBillingRate) => <TextCell value={formatMoscowDate(row.valid_from_at)} />,
  },
]

export function FfBillingSellerRates({ token }: { token: string }) {
  const [rows, setRows] = useState<SellerBillingRate[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    let alive = true
    setLoading(true)
    setError(false)
    fetch('/api/seller-billing/rates', { headers: { Authorization: `Bearer ${token}` }, signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error('seller-billing-rates')
        return response.json() as Promise<{ rates: SellerBillingRate[] }>
      })
      .then((data) => { if (alive) setRows(data.rates) })
      .catch((reason: unknown) => { if (alive && (reason as Error).name !== 'AbortError') setError(true) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false; controller.abort() }
  }, [token])

  return (
    <>
      {error ? (
        <ErrorNotice testId="billing-rates-error">Не удалось загрузить ставки. Повторите попытку</ErrorNotice>
      ) : null}
      <DataTable
        columns={columns}
        rows={rows}
        loading={loading}
        getRowKey={(row) => `${row.product_id ?? 'all'}-${row.service_code}`}
        testId="billing-rates-table"
        empty={{ title: 'Ставок нет' }}
      />
    </>
  )
}
