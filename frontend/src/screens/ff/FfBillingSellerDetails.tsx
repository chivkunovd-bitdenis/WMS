import { Box, Link, Stack } from '@mui/material'
import { Link as RouterLink } from 'react-router-dom'
import {
  CheckboxInput,
  DataTable,
  ErrorNotice,
  MoneyCell,
  QtyCell,
  SecondaryAction,
  StatusChip,
  TextCell,
} from '../../ui-kit'

const MOSCOW_TIME_ZONE = 'Europe/Moscow'

export type SellerReportEntry = {
  id: string
  kind: 'operation_fact' | 'legacy_billing'
  occurred_at: string
  service_code: string
  item_quantity: number | null
  source_type: string
  source_id: string
  source_target: { kind: 'inbound'; source_id: string } | { kind: 'route'; to: string } | null
  document_number: string | null
  product_name: string | null
  sku: string | null
  result: 'completed' | 'reversed' | 'not_billable' | 'unpriced'
  unit?: string | null
  rate_kopecks?: number | null
  amount_kopecks?: number | null
  billing_ledger_entry_id?: string
  invoice_history?: { state: 'known'; count: number } | { state: 'unknown' }
}

export type StorageReportRow = {
  kind: 'storage'
  date_from: string
  date_to: string
  liter_days: number
  status: 'calculated' | 'missing_dimensions'
  amount_kopecks?: number
  calculation_token: string
}

export type SellerReportDetails = {
  seller_id: string
  seller_name: string
  entries: SellerReportEntry[]
  storage_row: StorageReportRow | null
  next_cursor: string | null
}

/**
 * Строка раскрывашки: документ селлера либо одна агрегированная строка хранения.
 *
 * Обе живут в ОДНОЙ таблице с одной шапкой. Две таблицы со своими шапками под
 * строкой селлера оператор читает как два разных отчёта и теряет, к чему они
 * относятся.
 */
type DetailRow =
  | { kind: 'storage'; id: 'storage'; storage: StorageReportRow }
  | { kind: 'document'; id: string; entry: SellerReportEntry }

const serviceLabels: Record<string, string> = {
  inbound: 'Приёмка',
  marketplace_outbound: 'Отгрузка',
  packing: 'Упаковка',
  packaging: 'Упаковка',
  fbs_pick: 'Подбор FBS',
  picking: 'Подбор',
  return: 'Возврат',
  storage: 'Хранение',
  storage_liter_day: 'Хранение',
}

const sourceTypeLabels: Record<string, string> = {
  inbound_intake: 'Приёмка',
  marketplace_unload: 'Разгрузка',
}

function formatMoscowDateTime(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone: MOSCOW_TIME_ZONE,
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(value))
}

function formatMoscowDate(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', { timeZone: MOSCOW_TIME_ZONE }).format(new Date(value))
}

/** Почему операцию нельзя выбрать в счёт. Молчащий серый квадрат бесполезен. */
export function selectionReason(entry: SellerReportEntry): string | undefined {
  if (!entry.billing_ledger_entry_id) {
    return 'Документ ещё не начислен — счёт собирается из начислений'
  }
  if (entry.result === 'unpriced') return 'Нет ставки — задайте тариф в настройках'
  if (entry.result === 'not_billable') return 'Документ не тарифицируется'
  if (entry.result === 'reversed') return 'Сторно попадёт в счёт вместе со своим начислением'
  return undefined
}

export function FfBillingSellerDetails({
  details,
  loading,
  error,
  includeFinance,
  selectedRootIds,
  onToggleRoot,
  storageSelected,
  onToggleStorage,
  onLoadMore,
  onOpenInbound,
}: {
  details: SellerReportDetails | null
  loading: boolean
  error: boolean
  includeFinance: boolean
  selectedRootIds: string[]
  onToggleRoot: (rootId: string, checked: boolean) => void
  storageSelected: boolean
  onToggleStorage: (checked: boolean) => void
  onLoadMore: (cursor: string) => void
  onOpenInbound: (id: string) => void
}) {
  const rows: DetailRow[] = [
    ...(details?.storage_row
      ? [{ kind: 'storage' as const, id: 'storage' as const, storage: details.storage_row }]
      : []),
    ...(details?.entries ?? []).map((entry) => ({
      kind: 'document' as const,
      id: entry.id,
      entry,
    })),
  ]

  const pickColumn = includeFinance
    ? [
        {
          key: 'pick',
          header: '',
          width: 60,
          render: (row: DetailRow) =>
            row.kind === 'storage' ? (
              <CheckboxInput
                label="Выбрать хранение за период"
                hideLabel
                checked={storageSelected}
                onChange={onToggleStorage}
                disabledReason={
                  row.storage.status === 'missing_dimensions'
                    ? 'Нет габаритов у товара — хранение в счёт не включить'
                    : undefined
                }
                testId="billing-pick-storage"
              />
            ) : (
              <CheckboxInput
                label={`Выбрать документ ${row.entry.document_number ?? ''}`.trim()}
                hideLabel
                checked={selectedRootIds.includes(row.entry.billing_ledger_entry_id ?? '')}
                onChange={(checked) =>
                  onToggleRoot(row.entry.billing_ledger_entry_id ?? '', checked)
                }
                disabledReason={selectionReason(row.entry)}
                testId={`billing-pick-${row.entry.id}`}
              />
            ),
        },
      ]
    : []

  const columns = [
    ...pickColumn,
    {
      key: 'when',
      header: 'Дата',
      width: 190,
      render: (row: DetailRow) => (
        <TextCell
          value={
            row.kind === 'storage'
              ? `${formatMoscowDate(row.storage.date_from)} — ${formatMoscowDate(row.storage.date_to)}`
              : formatMoscowDateTime(row.entry.occurred_at)
          }
        />
      ),
    },
    {
      key: 'document',
      header: 'Документ',
      width: 190,
      render: (row: DetailRow) => (
        <TextCell
          value={
            row.kind === 'storage'
              ? 'За период'
              : [
                  sourceTypeLabels[row.entry.source_type] ?? 'Документ',
                  row.entry.document_number,
                ]
                  .filter(Boolean)
                  .join(' · ')
          }
        />
      ),
    },
    {
      key: 'service',
      header: 'Услуга',
      width: 150,
      render: (row: DetailRow) => {
        if (row.kind === 'storage') return <TextCell value="Хранение" />
        const label = serviceLabels[row.entry.service_code]
        // Сырой код услуги оператору не показываем, но и прочерк молчит о том,
        // что услуга есть, просто без подписи. Код уходит в подсказку.
        return label ? (
          <TextCell value={label} />
        ) : (
          <TextCell
            value="Услуга без подписи"
            hint={`Код услуги «${row.entry.service_code}» не имеет названия в интерфейсе`}
          />
        )
      },
    },
    {
      key: 'quantity',
      header: 'Количество',
      width: 130,
      align: 'right' as const,
      render: (row: DetailRow) =>
        row.kind === 'storage' ? (
          <TextCell value={`${row.storage.liter_days} л·дн`} />
        ) : (
          <QtyCell value={row.entry.item_quantity ?? 0} />
        ),
    },
    {
      key: 'result',
      header: 'Результат',
      width: 170,
      render: (row: DetailRow) => {
        if (row.kind === 'storage') {
          return row.storage.status === 'missing_dimensions' ? (
            <StatusChip
              label="Нет габаритов"
              tone="warn"
              hint="У товара нет габаритов для точного расчёта"
            />
          ) : (
            <StatusChip label="Рассчитано" tone="ok" />
          )
        }
        const presentation = {
          completed: { label: 'Выполнено', tone: 'ok' as const },
          reversed: { label: 'Сторно', tone: 'neutral' as const },
          not_billable: { label: 'Не тарифицируется', tone: 'neutral' as const },
          unpriced: { label: 'Нет ставки', tone: 'warn' as const },
        }[row.entry.result]
        return <StatusChip label={presentation.label} tone={presentation.tone} />
      },
    },
    ...(includeFinance
      ? [
          {
            key: 'rate',
            header: 'Ставка',
            width: 120,
            align: 'right' as const,
            render: (row: DetailRow) => (
              <MoneyCell minor={row.kind === 'storage' ? null : (row.entry.rate_kopecks ?? null)} />
            ),
          },
          {
            key: 'amount',
            header: 'Сумма',
            width: 140,
            align: 'right' as const,
            render: (row: DetailRow) => (
              <MoneyCell
                minor={
                  row.kind === 'storage'
                    ? (row.storage.amount_kopecks ?? null)
                    : (row.entry.amount_kopecks ?? null)
                }
              />
            ),
          },
          {
            key: 'invoiced',
            header: 'Счёт выставлялся',
            width: 160,
            render: (row: DetailRow) => {
              if (row.kind === 'storage') return <TextCell value="—" />
              const history = row.entry.invoice_history
              if (!history || history.state !== 'known') return <TextCell value="—" />
              return <TextCell value={history.count ? `✓ ${history.count}` : '—'} />
            },
          },
        ]
      : []),
    {
      key: 'source',
      header: 'Источник',
      width: 170,
      render: (row: DetailRow) => {
        if (row.kind === 'storage') return <TextCell value="—" />
        const target = row.entry.source_target
        if (target?.kind === 'inbound') {
          return (
            <Link
              component="button"
              type="button"
              sx={{ whiteSpace: 'nowrap' }}
              onClick={() => onOpenInbound(target.source_id)}
            >
              Открыть
            </Link>
          )
        }
        if (target?.kind === 'route') {
          return (
            <Link component={RouterLink} to={target.to} sx={{ whiteSpace: 'nowrap' }}>
              Открыть
            </Link>
          )
        }
        return (
          <TextCell
            value="Недоступен"
            hint="Первоисточник недоступен или не поддерживает переход"
          />
        )
      },
    },
  ]

  return (
    <Box sx={{ p: 2 }} data-testid={`billing-seller-details-${details?.seller_id ?? 'pending'}`}>
      <Stack spacing={1}>
        {error ? (
          <ErrorNotice testId="billing-seller-details-error">
            Не удалось загрузить документы селлера. Сводка сохранена
          </ErrorNotice>
        ) : null}
        <DataTable
          columns={columns}
          rows={rows}
          loading={loading}
          getRowKey={(row) => row.id}
          testId="billing-seller-entries"
          empty={{ title: 'За выбранный период документов нет' }}
        />
        {details?.next_cursor ? (
          <SecondaryAction
            disabledReason={loading ? 'Загрузка документов' : undefined}
            onClick={() => onLoadMore(details.next_cursor as string)}
          >
            Загрузить ещё
          </SecondaryAction>
        ) : null}
      </Stack>
    </Box>
  )
}
