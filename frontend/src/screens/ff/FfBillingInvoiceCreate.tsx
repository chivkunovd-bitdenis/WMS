import { useState } from 'react'
import { Box, Stack, Typography } from '@mui/material'
import DeleteOutlined from '@mui/icons-material/DeleteOutlined'
import {
  ActionGroup,
  AppDialog,
  DataTable,
  ErrorNotice,
  IconAction,
  formatMoney,
  MoneyCell,
  MoneyInput,
  PrimaryAction,
  PrintAction,
  SecondaryAction,
  SelectInput,
  TextCell,
  TextInput,
} from '../../ui-kit'
import { buildInvoicePrintHtml, type OpenedInvoice } from './FfBillingInvoicesPanel'
import { randomId } from '../../utils/randomId'

type Seller = { id: string; name: string }
type ProfileSnapshot = Record<string, string | null | undefined>

type PreviewLine = {
  id: string
  description: string
  unit_price_kopecks: number | null
  total_amount_kopecks: number
  sort_order: number
}

type InvoicePreview = {
  id: string
  seller_id: string
  number: string
  creation_mode: 'manual' | 'selected_operations'
  period_start: string | null
  period_end: string | null
  status: 'issued' | 'cancelled'
  issued_at: string | null
  total_amount_kopecks: number
  ff_profile?: ProfileSnapshot
  seller_profile?: ProfileSnapshot
  lines: PreviewLine[]
}

/** Больше десяти строк ручного счёта контракт не допускает. */
const MANUAL_LINE_LIMIT = 10

type ManualLine = { key: string; description: string; amount: string }

function emptyManualLine(index: number): ManualLine {
  return { key: `line-${index}`, description: '', amount: '' }
}

/**
 * Причины отказа сервера человеческим языком.
 *
 * Код вида `storage_calculation_stale` оператору ничего не говорит: он должен
 * понять, что именно чинить — каталог, тариф или просто обновить отчёт.
 */
const REJECTION_MESSAGES: Record<string, string> = {
  storage_calculation_stale:
    'Расчёт хранения устарел, пока счёт собирался. Обновите отчёт и выберите строку заново',
  storage_missing_dimensions:
    'У товара нет габаритов, поэтому хранение посчитать нельзя. Заполните габариты в каталоге',
  selected_operations_required: 'Выберите операции или заполните строки ручного счёта',
  unpriced_or_cross_seller_chain: 'Среди выбранных операций есть операция без ставки',
  standalone_reversal: 'Сторно нельзя выставить отдельно от своего начисления',
  selected_source_outside_period: 'Выбранная операция не входит в период отчёта',
  selected_source_not_found: 'Выбранная операция больше не доступна. Обновите отчёт',
  manual_line_count: `Ручной счёт содержит от одной до ${MANUAL_LINE_LIMIT} строк`,
  manual_description_required: 'У каждой строки должно быть название услуги',
  invalid_decimal_amount: 'Сумма указывается с точностью до копеек',
  negative_amount: 'Сумма не может быть отрицательной',
  seller_not_found: 'Селлер не найден',
  invalid_date_range: 'Период отчёта задан неверно',
  idempotency_key_payload_mismatch: 'Счёт изменился с момента предпросмотра. Соберите его заново',
}

function rejectionMessage(detail: unknown): string {
  const code = typeof detail === 'string' ? detail : ''
  return REJECTION_MESSAGES[code] ?? 'Счёт не выставлен. Проверьте данные и повторите'
}

function previewToOpened(preview: InvoicePreview, sellerName: string): OpenedInvoice {
  return {
    id: preview.id,
    origin: 'v2',
    number: preview.number,
    status: preview.status,
    issued_at: preview.issued_at,
    periodLabel:
      preview.period_start && preview.period_end
        ? `${preview.period_start} — ${preview.period_end}`
        : 'Без периода',
    seller_name: sellerName,
    total_amount_kopecks: preview.total_amount_kopecks,
    ff_profile: preview.ff_profile,
    seller_profile: preview.seller_profile,
    lines: preview.lines.map((line) => ({
      id: line.id,
      description: line.description,
      total_amount_kopecks: line.total_amount_kopecks,
    })),
  }
}


/**
 * Редактор строк, введённых человеком. Один и тот же и для пустого счёта, и для
 * строк, добавляемых к выбранным операциям: короба, доставка, разовая работа.
 * `minLines` различает случаи — в пустом счёте должна остаться хотя бы одна
 * строка, а к операциям строки добавляют по желанию, и удалить можно все.
 */
function ManualLinesEditor({
  lines,
  onChange,
  minLines,
  testIdPrefix,
}: {
  lines: ManualLine[]
  onChange: (next: ManualLine[]) => void
  minLines: number
  testIdPrefix: string
}) {
  return (
    <>
      {lines.map((line, index) => (
        <Stack direction="row" spacing={1} key={line.key} sx={{ alignItems: 'flex-start' }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <TextInput
              label="Услуга"
              value={line.description}
              onChange={(value) =>
                onChange(
                  lines.map((item, position) =>
                    position === index ? { ...item, description: value } : item,
                  ),
                )
              }
              testId={`${testIdPrefix}-description-${index}`}
            />
          </Box>
          <Box sx={{ width: 200, flexShrink: 0 }}>
            <MoneyInput
              label="Сумма"
              value={line.amount}
              onChange={(value) =>
                onChange(
                  lines.map((item, position) =>
                    position === index ? { ...item, amount: value } : item,
                  ),
                )
              }
              testId={`${testIdPrefix}-amount-${index}`}
            />
          </Box>
          <IconAction
            title="Удалить строку"
            onClick={() =>
              onChange(
                lines.length > minLines
                  ? lines.filter((_, position) => position !== index)
                  : lines,
              )
            }
            disabledReason={
              lines.length > minLines
                ? undefined
                : 'В счёте должна остаться хотя бы одна строка'
            }
            testId={`${testIdPrefix}-remove-${index}`}
          >
            <DeleteOutlined fontSize="small" />
          </IconAction>
        </Stack>
      ))}
      <SecondaryAction
        onClick={() => onChange([...lines, emptyManualLine(lines.length)])}
        disabledReason={
          lines.length >= MANUAL_LINE_LIMIT
            ? `В счёте не больше ${MANUAL_LINE_LIMIT} добавленных строк`
            : undefined
        }
      >
        Добавить строку
      </SecondaryAction>
    </>
  )
}

export function FfBillingInvoiceCreate({
  token,
  sellers = [],
  sellerId,
  sellerName,
  dateFrom,
  dateTo,
  selectedRootIds,
  includeStorage,
  onIssued,
}: {
  token: string
  sellers?: Seller[]
  /** Селлер открытой детализации; ручной счёт может адресоваться другому. */
  sellerId: string | null
  sellerName: string
  dateFrom: string
  dateTo: string
  selectedRootIds: string[]
  /** Класть ли в счёт хранение за период. Раньше сюда приходил подписанный
   *  токен расчёта, но бэкенд его больше не выдаёт: хранение берётся из ночных
   *  начислений. Пока фронт ждал токен, галочка не доезжала до запроса вовсе. */
  includeStorage: boolean
  onIssued: () => void
}) {
  const [manualOpen, setManualOpen] = useState(false)
  const [manualSeller, setManualSeller] = useState('')
  const [manualLines, setManualLines] = useState<ManualLine[]>([emptyManualLine(0)])
  // Строки, добавляемые к выбранным операциям: короба, доставка, разовая
  // работа. Их нет в начислениях, но выставлять за них второй счёт отдельно —
  // лишняя работа и лишняя бумага для селлера.
  const [extraOpen, setExtraOpen] = useState(false)
  const [extraLines, setExtraLines] = useState<ManualLine[]>([])
  const [preview, setPreview] = useState<InvoicePreview | null>(null)
  const [issued, setIssued] = useState<InvoicePreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [idempotencyKey, setIdempotencyKey] = useState('')

  const hasSelection = selectedRootIds.length > 0 || includeStorage
  const previewSellerName =
    sellers.find((seller) => seller.id === preview?.seller_id)?.name ?? sellerName

  const request = async (path: string, body: unknown, key?: string) => {
    const response = await fetch(`/api/billing/${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        ...(key ? { 'Idempotency-Key': key } : {}),
      },
      body: JSON.stringify(body),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok) throw new Error(rejectionMessage(payload?.detail))
    return payload as InvoicePreview
  }

  const selectedBody = () => ({
    creation_mode: 'selected_operations',
    seller_id: sellerId,
    date_from: dateFrom,
    date_to: dateTo,
    selected_root_ids: selectedRootIds,
    ...(includeStorage ? { include_storage: true } : {}),
    manual_lines: extraLines
      .filter((line) => line.description.trim() && line.amount.trim())
      .map((line) => ({ description: line.description.trim(), amount: line.amount.trim() })),
  })

  const manualBody = () => ({
    creation_mode: 'manual',
    seller_id: manualSeller || sellerId,
    lines: manualLines
      .filter((line) => line.description.trim() || line.amount.trim())
      .map((line) => ({ description: line.description.trim(), amount: line.amount.trim() })),
  })

  const openPreview = async (body: unknown) => {
    setBusy(true)
    setError(null)
    try {
      const result = await request('invoices-v2/preview', body)
      setPreview(result)
      setIssued(null)
      // Ключ идемпотентности живёт от предпросмотра до сохранения: повторное
      // нажатие «Сохранить» не должно порождать второй счёт.
      setIdempotencyKey(randomId())
      setManualOpen(false)
    } catch (reason) {
      setError((reason as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const startIssue = () => {
    setError(null)
    if (hasSelection) {
      if (!sellerId) {
        setError('Откройте операции селлера, чтобы собрать счёт из них')
        return
      }
      void openPreview(selectedBody())
      return
    }
    setManualSeller(sellerId ?? '')
    setManualLines([emptyManualLine(0)])
    setManualOpen(true)
  }

  const save = async () => {
    if (!preview) return
    setBusy(true)
    setError(null)
    try {
      const body = preview.creation_mode === 'manual' ? manualBody() : selectedBody()
      const result = await request('invoices-v2', body, idempotencyKey)
      setIssued(result)
      // Добавленные строки принадлежат выставленному счёту: следующий счёт
      // начинается с чистого листа.
      setExtraLines([])
      onIssued()
    } catch (reason) {
      setError((reason as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const print = () => {
    const source = issued ?? preview
    if (!source) return
    const printWindow = window.open('', '_blank')
    if (!printWindow) return
    printWindow.document.write(buildInvoicePrintHtml(previewToOpened(source, previewSellerName)))
    printWindow.document.close()
    printWindow.print()
  }

  const closePreview = () => {
    setPreview(null)
    setIssued(null)
    setError(null)
  }

  const shown = issued ?? preview
  const manualFilled = manualLines.some((line) => line.description.trim() && line.amount.trim())
  const filledExtraLines = extraLines.filter(
    (line) => line.description.trim() && line.amount.trim(),
  )

  return (
    <>
      <PrimaryAction
        onClick={startIssue}
        disabledReason={busy ? 'Счёт уже собирается' : undefined}
        data-testid="billing-issue-invoice"
      >
        Выставить счёт
      </PrimaryAction>
      {hasSelection ? (
        <SecondaryAction
          onClick={() => {
            setError(null)
            if (extraLines.length === 0) setExtraLines([emptyManualLine(0)])
            setExtraOpen(true)
          }}
          data-testid="billing-extra-lines-open"
        >
          {filledExtraLines.length > 0
            ? `Добавленные строки (${filledExtraLines.length})`
            : 'Добавить строку'}
        </SecondaryAction>
      ) : null}
      {error && !preview && !manualOpen ? (
        <ErrorNotice testId="billing-issue-error">{error}</ErrorNotice>
      ) : null}

      <AppDialog
        open={extraOpen}
        title="Строки к счёту"
        onClose={() => setExtraOpen(false)}
        maxWidth="lg"
        testId="billing-invoice-extra-lines"
        actions={
          <ActionGroup>
            <PrimaryAction onClick={() => setExtraOpen(false)} data-testid="billing-extra-lines-done">
              Готово
            </PrimaryAction>
          </ActionGroup>
        }
      >
        <Stack spacing={2}>
          <Typography>
            Эти строки уйдут в счёт вместе с выбранными операциями. Начислений за ними нет —
            сумму ставите вы: короба, доставка, разовая работа.
          </Typography>
          <ManualLinesEditor
            lines={extraLines}
            onChange={setExtraLines}
            minLines={0}
            testIdPrefix="billing-extra"
          />
        </Stack>
      </AppDialog>

      <AppDialog
        open={manualOpen}
        title="Ручной счёт"
        onClose={() => setManualOpen(false)}
        maxWidth="lg"
        testId="billing-invoice-manual"
        actions={
          <ActionGroup>
            <PrimaryAction
              onClick={() => void openPreview(manualBody())}
              disabledReason={
                !manualFilled ? 'Заполните хотя бы одну строку с названием и суммой' : undefined
              }
              data-testid="billing-manual-preview"
            >
              Предпросмотр
            </PrimaryAction>
            <SecondaryAction onClick={() => setManualOpen(false)}>Назад</SecondaryAction>
          </ActionGroup>
        }
      >
        <Stack spacing={2}>
          <Typography>
            Ручной счёт не отмечает складские операции выставленными: у него нет связи с ними.
          </Typography>
          <SelectInput
            label="Плательщик"
            value={manualSeller}
            onChange={setManualSeller}
            emptyLabel="Выберите селлера"
            options={sellers.map((seller) => ({ value: seller.id, label: seller.name }))}
            testId="billing-manual-seller"
          />
          <ManualLinesEditor
            lines={manualLines}
            onChange={setManualLines}
            minLines={1}
            testIdPrefix="billing-manual"
          />
          {error ? <ErrorNotice testId="billing-manual-error">{error}</ErrorNotice> : null}
        </Stack>
      </AppDialog>

      <AppDialog
        open={Boolean(shown)}
        title={issued ? `Счёт ${issued.number} выставлен` : 'Предпросмотр счёта'}
        onClose={closePreview}
        maxWidth="lg"
        testId="billing-invoice-preview"
        actions={
          <ActionGroup>
            {issued ? null : (
              <PrimaryAction
                onClick={() => void save()}
                disabledReason={busy ? 'Счёт уже сохраняется' : undefined}
                data-testid="billing-invoice-save"
              >
                Сохранить
              </PrimaryAction>
            )}
            <PrintAction
              what="счёт"
              placement="panel"
              onClick={print}
              testId="billing-invoice-preview-print"
            />
            <SecondaryAction onClick={closePreview}>{issued ? 'Закрыть' : 'Назад'}</SecondaryAction>
          </ActionGroup>
        }
      >
        {shown ? (
          <Stack spacing={2}>
            <Typography>
              {issued
                ? 'Счёт сохранён и виден на вкладке «Выставленные счета».'
                : 'До сохранения это ровно тот документ, который будет сохранён.'}
            </Typography>
            <DataTable
              columns={[
                {
                  key: 'service',
                  header: 'Услуга',
                  width: 420,
                  render: (line: PreviewLine) => <TextCell value={line.description} width={400} />,
                },
                {
                  key: 'amount',
                  header: 'Сумма',
                  width: 160,
                  align: 'right' as const,
                  render: (line: PreviewLine) => <MoneyCell minor={line.total_amount_kopecks} />,
                },
              ]}
              rows={shown.lines}
              loading={false}
              getRowKey={(line) => line.id}
              testId="billing-invoice-preview-lines"
              empty={{ title: 'Строк нет' }}
            />
            <Typography sx={{ textAlign: 'right', fontWeight: 'bold' }}>
              Итого: {formatMoney(shown.total_amount_kopecks)}
            </Typography>
            {error ? <ErrorNotice testId="billing-preview-error">{error}</ErrorNotice> : null}
          </Stack>
        ) : null}
      </AppDialog>
    </>
  )
}
