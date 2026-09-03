import { useCallback, useEffect, useState } from 'react'
import { Box, Stack, Typography } from '@mui/material'
import ExpandMore from '@mui/icons-material/ExpandMore'
import {
  ActionGroup,
  AppDialog,
  DangerAction,
  DataTable,
  ErrorNotice,
  FilterBar,
  formatMoney,
  IconAction,
  MoneyCell,
  PrintAction,
  SecondaryAction,
  SelectInput,
  StatusChip,
  TextCell,
} from '../../ui-kit'
import { buildInvoicePrintHtml as buildPrintDocument, type PrintProfile } from './invoicePrint'

const MOSCOW_TIME_ZONE = 'Europe/Moscow'

export const CANCEL_INVOICE_ERROR_MESSAGE =
  'Отмена не подтверждена. Проверьте статус счёта перед повторной попыткой.'

type Seller = { id: string; name: string }
type ProfileSnapshot = Record<string, string | null | undefined>

/** Строка истории: старый месячный счёт и новый лежат в одной таблице. */
export type InvoiceHistoryRow = {
  id: string
  origin: 'legacy' | 'v2'
  number: string
  seller_id: string
  seller_name: string
  issued_at: string
  period_start: string | null
  period_end: string | null
  creation_mode: 'monthly' | 'manual' | 'selected_operations'
  status: 'issued' | 'cancelled'
  total_amount_kopecks: number
}

/** Открытый счёт, приведённый к одному виду независимо от эпохи. */
export type OpenedInvoice = {
  id: string
  origin: 'legacy' | 'v2'
  number: string
  status: 'issued' | 'cancelled'
  issued_at: string | null
  periodLabel: string
  seller_name: string
  total_amount_kopecks: number
  ff_profile?: ProfileSnapshot
  seller_profile?: ProfileSnapshot
  lines: Array<{ id: string; description: string; total_amount_kopecks: number }>
}

const profileFieldLabels: Record<string, string> = {
  legal_name: 'Юридическое наименование',
  inn: 'ИНН',
  kpp: 'КПП',
  bank_name: 'Название банка',
  bik: 'БИК',
  settlement_account: 'Расчётный счёт',
  correspondent_account: 'Корреспондентский счёт',
}

const serviceLabels: Record<string, string> = {
  inbound: 'Приёмка',
  marketplace_outbound: 'Отгрузка',
  storage_liter_day: 'Хранение',
}

export function formatMoscowDate(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', { timeZone: MOSCOW_TIME_ZONE }).format(new Date(value))
}

/**
 * Одна колонка «Период» на обе эпохи.
 *
 * Старый счёт всегда покрывает календарный месяц, новый — произвольный
 * интервал, а ручной вообще не имеет периода. Показываем то, что есть, не
 * притворяясь, что у ручного счёта период всё-таки был.
 */
export function formatInvoicePeriod(
  start: string | null,
  end: string | null,
  mode: InvoiceHistoryRow['creation_mode'],
): string {
  if (!start || !end) return 'Без периода'
  if (mode === 'monthly') {
    const [year, month] = start.split('-').map(Number)
    if (year && month) {
      return new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' }).format(
        new Date(year, month - 1, 1),
      )
    }
  }
  return `${formatMoscowDate(start)} — ${formatMoscowDate(end)}`
}

export function profileRows(
  profile: ProfileSnapshot | undefined,
  fallback: string,
): Array<[string, string]> {
  const rows = Object.entries(profile ?? {})
    .filter(([key, value]) => Boolean(profileFieldLabels[key] && value))
    .map(([key, value]) => [profileFieldLabels[key], String(value)] as [string, string])
  return rows.length ? rows : [['Наименование', fallback]]
}

/**
 * Печатная форма счёта. Вёрстка одна на все окна — в `invoicePrint.ts`.
 *
 * Здесь только перевод счёта в её язык: у нового счёта позиции идут одной
 * суммой, без количества и цены, поэтому лишние колонки в документе не
 * появляются вовсе, а не стоят прочерками.
 */
export function buildInvoicePrintHtml(invoice: OpenedInvoice): string {
  return buildPrintDocument({
    number: invoice.number,
    dateLabel: invoice.issued_at ? `от ${formatMoscowDate(invoice.issued_at)}` : '',
    periodLabel: invoice.periodLabel,
    supplierName: 'Фулфилмент',
    payerName: invoice.seller_name,
    supplier: (invoice.ff_profile ?? {}) as PrintProfile,
    payer: (invoice.seller_profile ?? {}) as PrintProfile,
    lines: invoice.lines.map((line) => ({
      description: line.description,
      amount: formatMoney(line.total_amount_kopecks),
    })),
    total: formatMoney(invoice.total_amount_kopecks),
    totalKopecks: invoice.total_amount_kopecks,
  })
}


type LegacyLine = { id: string; service_code: string; amount: number | string }
type LegacyInvoice = {
  id: string
  number: string
  period: string
  status: 'issued' | 'cancelled'
  issued_at: string
  seller_name: string
  total_amount: number | string
  ff_profile?: ProfileSnapshot
  seller_profile?: ProfileSnapshot
  lines?: LegacyLine[]
}

type V2Invoice = {
  id: string
  number: string
  status: 'issued' | 'cancelled'
  issued_at: string | null
  period_start: string | null
  period_end: string | null
  creation_mode: InvoiceHistoryRow['creation_mode']
  total_amount_kopecks: number
  ff_profile?: ProfileSnapshot
  seller_profile?: ProfileSnapshot
  lines: Array<{ id: string; description: string; total_amount_kopecks: number }>
}

/** Свести старый счёт к общему виду: суммы там уже в копейках. */
export function legacyToOpened(invoice: LegacyInvoice, row: InvoiceHistoryRow): OpenedInvoice {
  return {
    id: invoice.id,
    origin: 'legacy',
    number: invoice.number,
    status: invoice.status,
    issued_at: invoice.issued_at,
    periodLabel: formatInvoicePeriod(row.period_start, row.period_end, 'monthly'),
    seller_name: invoice.seller_name,
    total_amount_kopecks: Number(invoice.total_amount),
    ff_profile: invoice.ff_profile,
    seller_profile: invoice.seller_profile,
    lines: (invoice.lines ?? []).map((line) => ({
      id: line.id,
      description: serviceLabels[line.service_code] ?? line.service_code,
      total_amount_kopecks: Number(line.amount),
    })),
  }
}

export function v2ToOpened(invoice: V2Invoice, sellerName: string): OpenedInvoice {
  return {
    id: invoice.id,
    origin: 'v2',
    number: invoice.number,
    status: invoice.status,
    issued_at: invoice.issued_at,
    periodLabel: formatInvoicePeriod(invoice.period_start, invoice.period_end, invoice.creation_mode),
    seller_name: sellerName,
    total_amount_kopecks: invoice.total_amount_kopecks,
    ff_profile: invoice.ff_profile,
    seller_profile: invoice.seller_profile,
    lines: invoice.lines,
  }
}

export function FfBillingInvoicesPanel({
  token,
  sellers = [],
  refreshToken = 0,
}: {
  token: string
  sellers?: Seller[]
  /** Меняется после выставления счёта, чтобы история перечиталась. */
  refreshToken?: number
}) {
  const [sellerId, setSellerId] = useState('all')
  const [status, setStatus] = useState('all')
  const [search, setSearch] = useState('')
  const [rows, setRows] = useState<InvoiceHistoryRow[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [opened, setOpened] = useState<OpenedInvoice | null>(null)
  const [openError, setOpenError] = useState(false)
  const [cancelConfirm, setCancelConfirm] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [cancelError, setCancelError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)

  const resetPaging = useCallback(() => {
    setCursor(null)
    setRows([])
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(false)
    const params = new URLSearchParams({ seller_id: sellerId, status })
    if (search) params.set('number', search)
    if (cursor) params.set('cursor', cursor)
    fetch(`/api/billing/invoices-v2?${params}`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error('billing-invoice-history')
        return response.json() as Promise<{ invoices: InvoiceHistoryRow[]; next_cursor: string | null }>
      })
      .then((data) => {
        // Дозагрузка склеивается по id: повтор страницы не должен раздвоить счёт.
        setRows((current) => {
          if (!cursor) return data.invoices
          const seen = new Set(current.map((row) => row.id))
          return [...current, ...data.invoices.filter((row) => !seen.has(row.id))]
        })
        setNextCursor(data.next_cursor)
      })
      .catch((reason: unknown) => {
        if ((reason as Error).name !== 'AbortError') setError(true)
      })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [cursor, refreshToken, reload, search, sellerId, status, token])

  const openInvoice = async (row: InvoiceHistoryRow) => {
    setOpenError(false)
    setCancelError(null)
    const url =
      row.origin === 'legacy' ? `/api/billing/invoices/${row.id}` : `/api/billing/invoices-v2/${row.id}`
    try {
      const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      if (!response.ok) throw new Error('open-invoice')
      const payload = await response.json()
      setOpened(
        row.origin === 'legacy'
          ? legacyToOpened(payload as LegacyInvoice, row)
          : v2ToOpened(payload as V2Invoice, row.seller_name),
      )
    } catch {
      setOpenError(true)
    }
  }

  const printInvoice = () => {
    if (!opened) return
    const printWindow = window.open('', '_blank')
    if (!printWindow) return
    printWindow.document.write(buildInvoicePrintHtml(opened))
    printWindow.document.close()
    printWindow.print()
  }

  const cancelInvoice = async () => {
    if (!opened) return
    setCancelling(true)
    setCancelError(null)
    const url =
      opened.origin === 'legacy'
        ? `/api/billing/invoices/${opened.id}/cancel`
        : `/api/billing/invoices-v2/${opened.id}/cancel`
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('cancel-invoice')
      setOpened({ ...opened, status: 'cancelled' })
      setCancelConfirm(false)
      resetPaging()
      setReload((value) => value + 1)
    } catch {
      setCancelError(CANCEL_INVOICE_ERROR_MESSAGE)
    } finally {
      setCancelling(false)
    }
  }

  const columns = [
    {
      key: 'number',
      header: 'Номер',
      width: 170,
      render: (row: InvoiceHistoryRow) => <TextCell value={row.number} />,
    },
    {
      key: 'seller',
      header: 'Селлер',
      width: 220,
      render: (row: InvoiceHistoryRow) => <TextCell value={row.seller_name} width={200} />,
    },
    {
      key: 'period',
      header: 'Период',
      width: 210,
      render: (row: InvoiceHistoryRow) => (
        <TextCell value={formatInvoicePeriod(row.period_start, row.period_end, row.creation_mode)} />
      ),
    },
    {
      key: 'issued',
      header: 'Выставлен',
      width: 140,
      render: (row: InvoiceHistoryRow) => <TextCell value={formatMoscowDate(row.issued_at)} />,
    },
    {
      key: 'amount',
      header: 'Сумма',
      width: 150,
      align: 'right' as const,
      render: (row: InvoiceHistoryRow) => <MoneyCell minor={row.total_amount_kopecks} />,
    },
    {
      key: 'status',
      header: 'Статус',
      width: 140,
      render: (row: InvoiceHistoryRow) => (
        <StatusChip
          label={row.status === 'issued' ? 'Выставлен' : 'Отменён'}
          tone={row.status === 'issued' ? 'ok' : 'neutral'}
        />
      ),
    },
    {
      key: 'action',
      header: 'Действие',
      width: 90,
      render: (row: InvoiceHistoryRow) => (
        <IconAction
          title="Открыть счёт"
          testId={`billing-invoice-open-${row.id}`}
          onClick={() => void openInvoice(row)}
        >
          <ExpandMore fontSize="small" />
        </IconAction>
      ),
    },
  ]

  return (
    <>
      <FilterBar
        search={search}
        onSearchChange={(value) => {
          resetPaging()
          setSearch(value)
        }}
        searchPlaceholder="Номер счёта"
        testId="billing-invoices-filter-bar"
      >
        <SelectInput
          label="Селлер"
          value={sellerId}
          onChange={(value) => {
            resetPaging()
            setSellerId(value)
          }}
          options={[
            { value: 'all', label: 'Все селлеры' },
            ...sellers.map((seller) => ({ value: seller.id, label: seller.name })),
          ]}
          testId="billing-seller"
        />
        <SelectInput
          label="Статус"
          value={status}
          onChange={(value) => {
            resetPaging()
            setStatus(value)
          }}
          options={[
            { value: 'all', label: 'Все статусы' },
            { value: 'issued', label: 'Выставлен' },
            { value: 'cancelled', label: 'Отменён' },
          ]}
          testId="billing-status"
        />
      </FilterBar>

      {error ? (
        <ErrorNotice testId="billing-invoices-error">
          Не удалось загрузить счета. Повторите попытку
        </ErrorNotice>
      ) : null}
      {openError ? (
        <ErrorNotice testId="billing-invoice-open-error">
          Не удалось открыть счёт. Список сохранён
        </ErrorNotice>
      ) : null}

      <DataTable
        columns={columns}
        rows={rows}
        loading={loading}
        getRowKey={(row) => row.id}
        testId="billing-invoices-table"
        empty={{
          title: 'Счета ещё не выставлены',
          hint: 'Выставьте счёт на вкладке «Селлеры»',
        }}
      />
      {nextCursor ? (
        <SecondaryAction
          disabledReason={loading ? 'Загрузка счетов' : undefined}
          onClick={() => setCursor(nextCursor)}
        >
          Загрузить ещё
        </SecondaryAction>
      ) : null}

      <AppDialog
        open={Boolean(opened)}
        title={
          <>
            Счёт {opened?.number}{' '}
            {opened ? (
              <StatusChip
                label={opened.status === 'issued' ? 'Выставлен' : 'Отменён'}
                tone={opened.status === 'issued' ? 'ok' : 'neutral'}
              />
            ) : null}
          </>
        }
        onClose={() => setOpened(null)}
        maxWidth="lg"
        testId="billing-invoice-dialog"
        actions={
          <ActionGroup>
            <PrintAction what="счёт" placement="panel" onClick={printInvoice} testId="billing-invoice-print" />
            {opened?.status === 'issued' ? (
              <DangerAction
                onClick={() => {
                  setCancelError(null)
                  setCancelConfirm(true)
                }}
                data-testid="billing-invoice-cancel"
              >
                Отменить счёт
              </DangerAction>
            ) : null}
            <SecondaryAction onClick={() => setOpened(null)}>Закрыть</SecondaryAction>
          </ActionGroup>
        }
      >
        {opened ? (
          <Stack spacing={2}>
            <Typography>
              {opened.periodLabel}
              {opened.issued_at ? ` · Выставлен: ${formatMoscowDate(opened.issued_at)}` : ''}
            </Typography>
            <Stack direction="row" spacing={2}>
              {(
                [
                  ['Получатель', opened.ff_profile, 'Реквизиты ФФ'],
                  ['Плательщик', opened.seller_profile, opened.seller_name],
                ] as const
              ).map(([title, profile, fallback]) => (
                <Box sx={{ flex: 1 }} key={title}>
                  <Typography sx={{ fontWeight: 'bold' }}>{title}</Typography>
                  {profileRows(profile, fallback).map(([label, value]) => (
                    <Typography key={label}>
                      {label}: {value}
                    </Typography>
                  ))}
                </Box>
              ))}
            </Stack>
            <DataTable
              columns={[
                {
                  key: 'service',
                  header: 'Услуга',
                  width: 420,
                  render: (line: OpenedInvoice['lines'][number]) => <TextCell value={line.description} width={400} />,
                },
                {
                  key: 'amount',
                  header: 'Сумма',
                  width: 160,
                  align: 'right' as const,
                  render: (line: OpenedInvoice['lines'][number]) => (
                    <MoneyCell minor={line.total_amount_kopecks} />
                  ),
                },
              ]}
              rows={opened.lines}
              loading={false}
              getRowKey={(line) => line.id}
              testId="billing-invoice-lines"
              empty={{ title: 'Строк счёта нет' }}
            />
            <Typography sx={{ textAlign: 'right', fontWeight: 'bold' }}>
              Итого: {formatMoney(opened.total_amount_kopecks)}
            </Typography>
          </Stack>
        ) : null}
      </AppDialog>

      <AppDialog
        open={cancelConfirm}
        title="Отменить счёт?"
        onClose={() => {
          if (!cancelling) {
            setCancelError(null)
            setCancelConfirm(false)
          }
        }}
        testId="billing-invoice-cancel-dialog"
        actions={
          <ActionGroup>
            <DangerAction
              onClick={() => void cancelInvoice()}
              disabledReason={cancelling ? 'Отмена уже выполняется' : undefined}
              data-testid="billing-invoice-cancel-confirm"
            >
              Отменить счёт
            </DangerAction>
            <SecondaryAction
              onClick={() => {
                setCancelError(null)
                setCancelConfirm(false)
              }}
              disabledReason={cancelling ? 'Дождитесь завершения отмены' : undefined}
            >
              Назад
            </SecondaryAction>
          </ActionGroup>
        }
      >
        <Typography>
          Счёт останется в истории со статусом «Отменён». Это действие нельзя отменить.
        </Typography>
        {cancelError ? (
          <ErrorNotice testId="billing-invoice-cancel-error">{cancelError}</ErrorNotice>
        ) : null}
      </AppDialog>
    </>
  )
}
