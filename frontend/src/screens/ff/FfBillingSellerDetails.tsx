import { useState } from 'react'
import type { ReactNode } from 'react'
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
  /** Только у заказов FBS: «Передан ВБ» или «ВБ получил». */
  fbs_status_label?: string | null
  /** Сумма посчитана по тарифу на дату операции, а не взята из начисления. */
  priced_live?: boolean
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
 * Раскрывашка селлера — два уровня: раздел услуги, внутри него документы.
 *
 * Плоский список документов, где приёмка, отгрузка и упаковка идут вперемешку,
 * не отвечает на главный вопрос экрана — «сколько я беру с этого селлера за
 * отгрузки». Поэтому сверху лежат разделы с итогом и ставкой, а документы
 * прячутся на уровень ниже, под свой раздел.
 */
type SectionRow =
  | { kind: 'service'; id: string; label: string; entries: SellerReportEntry[] }
  | { kind: 'storage'; id: 'storage'; storage: StorageReportRow }

type DocumentRow =
  | { kind: 'document'; id: string; entry: SellerReportEntry }
  | { kind: 'storagePeriod'; id: 'storage-period'; storage: StorageReportRow }

/** Порядок разделов — по ходу работы склада, а не по алфавиту. */
const SECTION_ORDER = ['inbound', 'packing', 'fbs', 'marketplace_outbound', 'picking', 'return', 'other']

const sectionLabels: Record<string, string> = {
  inbound: 'Приёмка',
  packing: 'Упаковка',
  fbs: 'FBS',
  marketplace_outbound: 'Отгрузка',
  picking: 'Подбор',
  return: 'Возврат',
  storage: 'Хранение',
  other: 'Прочие услуги',
}

/** Коды услуг с бэкенда сводим в разделы: `packing` и `packaging` — одно и то же. */
function sectionKey(serviceCode: string): string {
  if (serviceCode === 'packing' || serviceCode === 'packaging') return 'packing'
  if (serviceCode === 'fbs_pick' || serviceCode === 'fbs_order') return 'fbs'
  if (serviceCode === 'storage' || serviceCode === 'storage_liter_day') return 'storage'
  if (sectionLabels[serviceCode]) return serviceCode
  return 'other'
}

const sourceTypeLabels: Record<string, string> = {
  inbound_intake: 'Приёмка',
  marketplace_unload: 'Отгрузка',
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
    return entry.priced_live
      ? 'Сумма посчитана по тарифу на дату операции. В счёт документ попадёт, когда по нему пройдёт начисление'
      : 'Документ ещё не начислен — счёт собирается из начислений'
  }
  if (entry.result === 'unpriced') return 'Нет ставки — задайте тариф в настройках'
  if (entry.result === 'not_billable') return 'Документ не тарифицируется'
  if (entry.result === 'reversed') return 'Сторно попадёт в счёт вместе со своим начислением'
  return undefined
}

/** Начисления раздела, которые можно положить в счёт. */
export function billableIds(entries: SellerReportEntry[]): string[] {
  return entries
    .filter((entry) => !selectionReason(entry) && entry.billing_ledger_entry_id)
    .map((entry) => entry.billing_ledger_entry_id as string)
}

function sumItems(entries: SellerReportEntry[]): number {
  return entries.reduce((sum, entry) => sum + (entry.item_quantity ?? 0), 0)
}

function sumAmount(entries: SellerReportEntry[]): number | null {
  const priced = entries.filter((entry) => typeof entry.amount_kopecks === 'number')
  if (!priced.length) return null
  return priced.reduce((sum, entry) => sum + (entry.amount_kopecks ?? 0), 0)
}

/**
 * Ставка раздела. Если внутри документы шли по разным ставкам — одну цифру
 * показывать нельзя, она соврёт; тогда ставка живёт только у документов.
 */
function sectionRate(entries: SellerReportEntry[]): number | null {
  const rates = new Set(
    entries
      .map((entry) => entry.rate_kopecks)
      .filter((rate): rate is number => typeof rate === 'number'),
  )
  return rates.size === 1 ? ([...rates][0] ?? null) : null
}

function buildSections(details: SellerReportDetails | null): SectionRow[] {
  const grouped = new Map<string, SellerReportEntry[]>()
  for (const entry of details?.entries ?? []) {
    const key = sectionKey(entry.service_code)
    const bucket = grouped.get(key)
    if (bucket) bucket.push(entry)
    else grouped.set(key, [entry])
  }
  const known = SECTION_ORDER.filter((key) => grouped.has(key)).map((key) => ({
    kind: 'service' as const,
    id: key,
    label: sectionLabels[key] ?? key,
    entries: grouped.get(key) as SellerReportEntry[],
  }))
  // Раздел, которого нет в порядке выше, всё равно должен быть виден: услуга
  // существует и деньги по ней идут, даже если про неё забыли на фронте.
  const rest = [...grouped.keys()]
    .filter((key) => !SECTION_ORDER.includes(key) && key !== 'storage')
    .map((key) => ({
      kind: 'service' as const,
      id: key,
      label: sectionLabels[key] ?? key,
      entries: grouped.get(key) as SellerReportEntry[],
    }))
  const storage: SectionRow[] = details?.storage_row
    ? [{ kind: 'storage' as const, id: 'storage' as const, storage: details.storage_row }]
    : []
  return [...known, ...rest, ...storage]
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
  const [openSections, setOpenSections] = useState<string[]>([])
  const sections = buildSections(details)

  const toggleSection = (row: SectionRow) =>
    setOpenSections((open) =>
      open.includes(row.id) ? open.filter((id) => id !== row.id) : [...open, row.id],
    )

  function documentColumns() {
    return [
      ...(includeFinance
        ? [
            {
              key: 'pick',
              header: '',
              width: 60,
              render: (row: DocumentRow) =>
                row.kind === 'storagePeriod' ? (
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
        : []),
      {
        key: 'when',
        header: 'Дата',
        width: 170,
        render: (row: DocumentRow) => (
          <TextCell
            value={
              row.kind === 'storagePeriod'
                ? `${formatMoscowDate(row.storage.date_from)} — ${formatMoscowDate(row.storage.date_to)}`
                : formatMoscowDateTime(row.entry.occurred_at)
            }
          />
        ),
      },
      {
        key: 'document',
        header: 'Документ',
        width: 260,
        render: (row: DocumentRow) => {
          if (row.kind === 'storagePeriod') return <TextCell value="Хранение за период" />
          // Номер документа уже содержит его вид («Приёмка № 000045»), поэтому
          // подпись типа добавляется только тогда, когда номера нет вовсе.
          const title =
            row.entry.document_number ??
            (sourceTypeLabels[row.entry.source_type] ?? 'Документ без номера')
          const target = row.entry.source_target
          // Номер документа сам и есть переход: отдельная колонка «Открыть»
          // занимала место и заставляла искать глазами вторую точку клика.
          const status = row.entry.fbs_status_label
          // У заказа FBS статус — часть его имени: по нему видно, почему заказ
          // уже в сумме или ещё нет. Отдельной колонкой ради одного раздела
          // таблицу расширять незачем.
          const withStatus = (node: ReactNode) =>
            status ? (
              <Stack spacing={0.5} sx={{ alignItems: 'flex-start' }}>
                {node}
                <StatusChip
                  label={status}
                  tone={status === 'ВБ получил' ? 'ok' : 'neutral'}
                  hint={
                    status === 'ВБ получил'
                      ? 'Wildberries подтвердил приём — заказ тарифицируется'
                      : 'Заказ передан, подтверждения от Wildberries ещё нет'
                  }
                />
              </Stack>
            ) : (
              node
            )
          if (target?.kind === 'inbound') {
            return withStatus(
              <Link
                component="button"
                type="button"
                sx={{ textAlign: 'left' }}
                onClick={() => onOpenInbound(target.source_id)}
              >
                {title}
              </Link>,
            )
          }
          if (target?.kind === 'route') {
            return withStatus(
              <Link component={RouterLink} to={target.to} sx={{ textAlign: 'left' }}>
                {title}
              </Link>,
            )
          }
          return withStatus(
            <TextCell
              value={title}
              hint={
                status ? undefined : 'Первоисточник недоступен или не поддерживает переход'
              }
            />,
          )
        },
      },
      {
        key: 'quantity',
        header: 'Штук',
        width: 130,
        align: 'right' as const,
        render: (row: DocumentRow) =>
          row.kind === 'storagePeriod' ? (
            <TextCell value={`${row.storage.liter_days} л·дн`} />
          ) : (
            <QtyCell value={row.entry.item_quantity ?? 0} />
          ),
      },
      ...(includeFinance
        ? [
            {
              key: 'rate',
              header: 'Ставка',
              width: 120,
              align: 'right' as const,
              render: (row: DocumentRow) => (
                <MoneyCell
                  minor={row.kind === 'storagePeriod' ? null : (row.entry.rate_kopecks ?? null)}
                />
              ),
            },
            {
              key: 'amount',
              header: 'Сумма',
              width: 140,
              align: 'right' as const,
              render: (row: DocumentRow) => (
                <MoneyCell
                  minor={
                    row.kind === 'storagePeriod'
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
              render: (row: DocumentRow) => {
                if (row.kind === 'storagePeriod') return <TextCell value="—" />
                const history = row.entry.invoice_history
                if (!history || history.state !== 'known') return <TextCell value="—" />
                return <TextCell value={history.count ? `✓ ${history.count}` : '—'} />
              },
            },
          ]
        : []),
    ]
  }

  const sectionColumns = [
    ...(includeFinance
      ? [
          {
            key: 'pick',
            header: '',
            width: 60,
            render: (row: SectionRow) => {
              if (row.kind === 'storage') {
                return (
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
                    testId="billing-pick-section-storage"
                  />
                )
              }
              const ids = billableIds(row.entries)
              const allPicked = ids.length > 0 && ids.every((id) => selectedRootIds.includes(id))
              return (
                <CheckboxInput
                  label={`Выбрать весь раздел «${row.label}»`}
                  hideLabel
                  checked={allPicked}
                  onChange={(checked) => ids.forEach((id) => onToggleRoot(id, checked))}
                  disabledReason={
                    ids.length ? undefined : 'В разделе нет начислений, которые можно выставить'
                  }
                  testId={`billing-pick-section-${row.id}`}
                />
              )
            },
          },
        ]
      : []),
    {
      key: 'service',
      header: 'Услуга',
      width: 220,
      render: (row: SectionRow) => (
        <TextCell value={row.kind === 'storage' ? 'Хранение' : row.label} />
      ),
    },
    {
      key: 'documents',
      header: 'Документов',
      width: 130,
      align: 'right' as const,
      render: (row: SectionRow) =>
        row.kind === 'storage' ? (
          <TextCell value="за период" />
        ) : (
          <QtyCell value={row.entries.length} />
        ),
    },
    {
      key: 'items',
      header: 'Штук',
      width: 130,
      align: 'right' as const,
      render: (row: SectionRow) =>
        row.kind === 'storage' ? (
          <TextCell value={`${row.storage.liter_days} л·дн`} />
        ) : (
          <QtyCell value={sumItems(row.entries)} />
        ),
    },
    ...(includeFinance
      ? [
          {
            key: 'rate',
            header: 'Ставка',
            width: 130,
            align: 'right' as const,
            render: (row: SectionRow) => {
              if (row.kind === 'storage') return <TextCell value="—" />
              const rate = sectionRate(row.entries)
              return rate === null ? (
                <TextCell value="разные" hint="Документы раздела прошли по разным ставкам" />
              ) : (
                <MoneyCell minor={rate} />
              )
            },
          },
          {
            key: 'amount',
            header: 'Сумма',
            width: 150,
            align: 'right' as const,
            render: (row: SectionRow) => (
              <MoneyCell
                minor={
                  row.kind === 'storage'
                    ? (row.storage.amount_kopecks ?? null)
                    : sumAmount(row.entries)
                }
              />
            ),
          },
        ]
      : []),
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
          columns={sectionColumns}
          rows={sections}
          loading={loading}
          getRowKey={(row) => row.id}
          testId="billing-seller-sections"
          empty={{ title: 'За выбранный период документов нет' }}
          expand={{
            isExpanded: (row) => openSections.includes(row.id),
            label: (row) =>
              row.kind === 'storage'
                ? 'Показать хранение за период'
                : `Показать документы раздела «${row.label}»`,
            onToggle: toggleSection,
            render: (row) => (
              <Box sx={{ px: 2, py: 1 }}>
                <DataTable
                  columns={documentColumns()}
                  rows={
                    row.kind === 'storage'
                      ? [
                          {
                            kind: 'storagePeriod' as const,
                            id: 'storage-period' as const,
                            storage: row.storage,
                          },
                        ]
                      : row.entries.map((entry) => ({
                          kind: 'document' as const,
                          id: entry.id,
                          entry,
                        }))
                  }
                  loading={false}
                  getRowKey={(documentRow) => documentRow.id}
                  testId={`billing-seller-entries-${row.id}`}
                  empty={{ title: 'В разделе нет документов' }}
                />
              </Box>
            ),
          }}
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
