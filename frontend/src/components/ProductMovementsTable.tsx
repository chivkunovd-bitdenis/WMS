import { Link } from '@mui/material'
import { Link as RouterLink } from 'react-router-dom'
import { DataTable, QtyCell, TextCell } from '../ui-kit'

// WMS-490 D4: таблица движений вынесена из «Остатки и движения»
// (`FfReportsPage.tsx`) без единого изменения — тот же набор колонок, ширин
// и ссылок на документы, тот же вид строки. Отчёт (раскрытие товара и вида
// движения) и вкладка «Движения» карточки товара используют один компонент,
// чтобы историчность остатка не расходилась между двумя местами (AGENTS.md §3,
// решение 9 в docs/requirements/WMS-490.md).
export type MovementDocument = {
  kind: 'inbound' | 'marketplace_unload' | 'fbs_supply' | 'fbs_order'
  id: string
  number: string
} | null

export type MovementRow = {
  id: string
  at: string
  operation: string
  quantity: number
  product_id?: string | null
  product_name?: string | null
  sku_code?: string | null
  document: MovementDocument
}

type Props = {
  rows: MovementRow[]
  loading?: boolean
  /** Колонка «Товар» — нужна там, где строки нескольких товаров лежат вместе (раскрытие по виду движения в отчёте). */
  showProduct?: boolean
  /** Открыть документ приёмки — сама таблица его не рисует. */
  onOpenInbound?: (id: string) => void
  emptyTitle: string
  testId: string
}

export function ProductMovementsTable({
  rows,
  loading = false,
  showProduct = false,
  onOpenInbound,
  emptyTitle,
  testId,
}: Props) {
  return (
    <DataTable<MovementRow>
      columns={[
        {
          key: 'at',
          header: 'Когда',
          width: 190,
          render: (move) => (
            <TextCell value={new Date(move.at).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' })} width={160} />
          ),
        },
        ...(showProduct
          ? [
              {
                key: 'product',
                header: 'Товар',
                width: 260,
                render: (move: MovementRow) => <TextCell value={move.product_name ?? '—'} width={250} />,
              },
            ]
          : []),
        { key: 'operation', header: 'Движение', width: 260, render: (move: MovementRow) => <TextCell value={move.operation} /> },
        {
          key: 'document',
          header: 'Документ',
          width: 200,
          render: (move: MovementRow) => {
            const doc = move.document
            if (!doc) return <TextCell value="—" />
            if (doc.kind === 'inbound') {
              return (
                <Link component="button" type="button" sx={{ textAlign: 'left' }} onClick={() => onOpenInbound?.(doc.id)}>
                  {doc.number}
                </Link>
              )
            }
            if (doc.kind === 'marketplace_unload') {
              return (
                <Link component={RouterLink} to={`/app/ff/mp-shipments?open_mp=${doc.id}`} sx={{ textAlign: 'left' }}>
                  {doc.number}
                </Link>
              )
            }
            if (doc.kind === 'fbs_supply') {
              return (
                <Link component={RouterLink} to={`/app/ff/fbs?supply_id=${doc.id}`} sx={{ textAlign: 'left' }}>
                  {doc.number}
                </Link>
              )
            }
            return <TextCell value={doc.number} />
          },
        },
        { key: 'qty', header: 'Штук', align: 'right', width: 110, render: (move: MovementRow) => <QtyCell value={move.quantity} /> },
      ]}
      rows={rows}
      getRowKey={(move) => move.id}
      loading={loading}
      empty={{ title: emptyTitle }}
      testId={testId}
    />
  )
}
