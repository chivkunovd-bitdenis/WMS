import { useMemo, useState } from 'react'
import { Box, Popover, Stack, Typography } from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import {
  DataTable,
  MoneyCell,
  QtyCell,
  SecondaryAction,
  StatusChip,
  formatMoney,
  type Column,
} from '../../../ui-kit'
import type { AppliedRate, SellerRow } from './stub'

type Level = 'seller' | 'service' | 'document'

type Row = {
  key: string
  level: Level
  title: string
  subtitle: string | null
  documentCount: number | null
  itemQuantity: number | null
  totalKopecks: number | null
  rates: AppliedRate[]
  note: string | null
  expandable: boolean
  expanded: boolean
}

const RATE_KIND_TITLE: Record<AppliedRate['kind'], string> = {
  product: 'Цена товара',
  seller: 'Ставка селлера',
  common: 'Общая ставка',
}

/** Одно число, если ставка одна; иначе честно говорим, что она смешанная. */
function rateSummary(rates: AppliedRate[]): { label: string; mixed: boolean } {
  if (rates.length === 0) return { label: '—', mixed: false }
  const distinct = new Set(rates.map((one) => one.rateKopecks))
  if (distinct.size === 1) return { label: formatMoney(rates[0].rateKopecks), mixed: false }
  const min = Math.min(...rates.map((one) => one.rateKopecks))
  const max = Math.max(...rates.map((one) => one.rateKopecks))
  return { label: `${formatMoney(min)} — ${formatMoney(max)}`, mixed: true }
}

function buildRows(data: SellerRow[], open: Set<string>): Row[] {
  const rows: Row[] = []
  for (const seller of data) {
    const sellerOpen = open.has(seller.id)
    rows.push({
      key: seller.id,
      level: 'seller',
      title: seller.seller,
      subtitle: seller.notBillable > 0 ? `не тарифицируется: ${seller.notBillable}` : null,
      documentCount: seller.documentCount,
      itemQuantity: seller.itemQuantity,
      totalKopecks: seller.totalKopecks,
      rates: [],
      note: seller.services.length === 0 ? 'За период операций не было' : null,
      expandable: seller.services.length > 0,
      expanded: sellerOpen,
    })
    if (!sellerOpen) continue
    for (const service of seller.services) {
      const serviceOpen = open.has(service.id)
      rows.push({
        key: service.id,
        level: 'service',
        title: service.service,
        subtitle: null,
        documentCount: service.documentCount,
        itemQuantity: service.itemQuantity,
        totalKopecks: service.totalKopecks,
        rates: service.rates,
        note: service.note ?? null,
        expandable: service.documents.length > 0,
        expanded: serviceOpen,
      })
      if (!serviceOpen) continue
      for (const doc of service.documents) {
        rows.push({
          key: doc.id,
          level: 'document',
          title: doc.number ?? 'За период',
          subtitle: doc.date,
          documentCount: null,
          itemQuantity: doc.itemQuantity,
          totalKopecks: doc.totalKopecks,
          rates: doc.rates,
          note: doc.note ?? null,
          expandable: false,
          expanded: false,
        })
      }
    }
  }
  return rows
}

function allKeys(data: SellerRow[]): string[] {
  const keys: string[] = []
  for (const seller of data) {
    keys.push(seller.id)
    for (const service of seller.services) keys.push(service.id)
  }
  return keys
}

export function BillingReportScreen({ data }: { data: SellerRow[] }) {
  const [open, setOpen] = useState<Set<string>>(() => new Set(allKeys(data)))
  const [ratesAt, setRatesAt] = useState<{ el: HTMLElement; rates: AppliedRate[] } | null>(null)

  const rows = useMemo(() => buildRows(data, open), [data, open])
  const everythingOpen = open.size >= allKeys(data).length

  function toggle(key: string) {
    setOpen((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const columns: Column<Row>[] = [
    {
      key: 'title',
      header: 'Селлер · услуга · документ',
      width: 420,
      render: (row) => (
        <Stack
          direction="row"
          spacing={1}
          sx={{ alignItems: 'center', pl: row.level === 'seller' ? 0 : row.level === 'service' ? 3 : 6 }}
        >
          <Box
            component={row.expandable ? 'button' : 'span'}
            onClick={row.expandable ? () => toggle(row.key) : undefined}
            data-testid={row.expandable ? `billing-toggle-${row.key}` : undefined}
            sx={{
              display: 'inline-flex',
              alignItems: 'center',
              border: 0,
              p: 0,
              bgcolor: 'transparent',
              cursor: row.expandable ? 'pointer' : 'default',
              color: 'text.secondary',
              width: 20,
            }}
          >
            {row.expandable ? (
              row.expanded ? (
                <ExpandMoreIcon fontSize="small" />
              ) : (
                <ChevronRightIcon fontSize="small" />
              )
            ) : null}
          </Box>
          <Stack spacing={0}>
            <Typography
              variant="body2"
              sx={{ fontWeight: row.level === 'seller' ? 700 : row.level === 'service' ? 600 : 400 }}
            >
              {row.title}
            </Typography>
            {row.subtitle ? (
              <Typography variant="caption" color="text.secondary">
                {row.subtitle}
              </Typography>
            ) : null}
          </Stack>
          {row.note ? <StatusChip label={row.note} tone="neutral" /> : null}
        </Stack>
      ),
    },
    {
      key: 'documents',
      header: 'Документов',
      width: 130,
      align: 'right',
      render: (row) => (row.documentCount == null ? null : <QtyCell value={row.documentCount} />),
    },
    {
      key: 'items',
      header: 'Штук',
      width: 110,
      align: 'right',
      render: (row) => (row.itemQuantity == null ? null : <QtyCell value={row.itemQuantity} />),
    },
    {
      key: 'rate',
      header: 'Ставка',
      width: 200,
      align: 'right',
      render: (row) => {
        if (row.level === 'seller' || row.rates.length === 0) return null
        const summary = rateSummary(row.rates)
        return (
          <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', justifyContent: 'flex-end' }}>
            <Typography variant="body2">{summary.label}</Typography>
            <Box
              component="button"
              onClick={(event: React.MouseEvent<HTMLElement>) =>
                setRatesAt({ el: event.currentTarget, rates: row.rates })
              }
              data-testid={`billing-rates-${row.key}`}
              aria-label="Из чего сложилась ставка"
              sx={{
                display: 'inline-flex',
                border: 0,
                p: 0,
                bgcolor: 'transparent',
                cursor: 'pointer',
                color: summary.mixed ? 'warning.main' : 'text.secondary',
              }}
            >
              <InfoOutlinedIcon fontSize="small" />
            </Box>
          </Stack>
        )
      },
    },
    {
      key: 'total',
      header: 'Сумма',
      width: 160,
      align: 'right',
      render: (row) => <MoneyCell minor={row.totalKopecks} />,
    },
  ]

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
        <SecondaryAction
          onClick={() => setOpen(everythingOpen ? new Set() : new Set(allKeys(data)))}
          data-testid="billing-toggle-all"
        >
          {everythingOpen ? 'Свернуть всё' : 'Развернуть всё'}
        </SecondaryAction>
      </Stack>

      <DataTable
        columns={columns}
        rows={rows}
        getRowKey={(row) => row.key}
        testId="billing-report-table"
        empty={{ title: "За период начислений нет", hint: "Выберите другой период." }}
      />

      <Popover
        open={ratesAt !== null}
        anchorEl={ratesAt?.el ?? null}
        onClose={() => setRatesAt(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        <Stack spacing={1} sx={{ p: 2, minWidth: 320 }}>
          <Typography variant="subtitle2">Из чего сложилась ставка</Typography>
          {(ratesAt?.rates ?? []).map((rate, index) => (
            <Stack
              key={`${rate.kind}-${rate.subject}-${index}`}
              direction="row"
              spacing={2}
              sx={{ justifyContent: 'space-between' }}
            >
              <Stack spacing={0}>
                <Typography variant="body2">{rate.subject}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {RATE_KIND_TITLE[rate.kind]}
                </Typography>
              </Stack>
              <Stack spacing={0} sx={{ textAlign: 'right' }}>
                <Typography variant="body2">{formatMoney(rate.rateKopecks)}</Typography>
                <Typography variant="caption" color="text.secondary">
                  за {rate.quantity.toLocaleString('ru-RU')} шт
                </Typography>
              </Stack>
            </Stack>
          ))}
          <Typography variant="caption" color="text.secondary">
            Приоритет: цена товара, затем ставка селлера, затем общая.
          </Typography>
        </Stack>
      </Popover>
    </Stack>
  )
}
