import { Box, Paper, Stack, Typography } from '@mui/material'
import ArrowBackOutlined from '@mui/icons-material/ArrowBackOutlined'
import { useEffect, useMemo, useState } from 'react'
import {
  ActionGroup,
  CheckboxInput,
  DangerAction,
  ErrorNotice,
  FilterBar,
  IconAction,
  PrimaryAction,
  ReportMetricStrip,
  ScannerField,
  ScreenHeader,
  SecondaryAction,
  SelectInput,
  StatusChip,
  WarningNotice,
} from '../../../ui-kit'
import type { ReportMetricItem, StatusTone } from '../../../ui-kit'
import { CommentField } from './CommentField'
import { applyScan, containerName, type ScanTone } from './InventoryScan'
import { InventoryTree } from './InventoryTree'
import {
  EMPTY_FILTERS,
  buildRows,
  collapseAllKeys,
  facets,
  setActual,
  totals,
  type InvFilters,
  type InvRow,
} from './InventoryRows'
import type { CountStatus, InventoryCount, InventoryNode } from './InventoryTypes'

const STATUS_LABEL: Record<CountStatus, string> = {
  draft: 'Черновик',
  posted: 'Проведён',
  cancelled: 'Отменён',
}

const STATUS_TONE: Record<CountStatus, StatusTone> = {
  draft: 'neutral',
  posted: 'ok',
  cancelled: 'stop',
}

// Русские числительные: «1 движение», «2 движения», «5 движений». Без трёх форм
// экран пишет «создаст 4 движений» и читается как машинный перевод.
function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod100 >= 11 && mod100 <= 14) return `${n} ${many}`
  if (mod10 === 1) return `${n} ${one}`
  if (mod10 >= 2 && mod10 <= 4) return `${n} ${few}`
  return `${n} ${many}`
}

/** Ключи строки тары и всех её родителей, которые надо раскрыть перед прокруткой. */
function containerPathKeys(count: InventoryCount, containerId: string): string[] {
  function find(nodes: InventoryNode[]): string[] | null {
    for (const node of nodes) {
      if (node.kind === 'product') continue
      const key = `${node.kind}:${node.id}`
      if (node.id === containerId) return [key]
      const nested = find(node.children)
      if (nested) return [key, ...nested]
    }
    return null
  }

  for (const cell of count.cells) {
    const nested = find(cell.children)
    if (nested) return [`cell:${cell.id}`, ...nested]
  }
  return []
}

type Props = {
  count: InventoryCount
  loading: boolean
  error: string | null
  /** Что сказали в ответ на сохранение или проведение. */
  note: string | null
  onChange: (next: InventoryCount) => void
  onSave: () => void
  onPost: () => void
  onCancelDocument: () => void
  onCreateContainer?: (kind: 'pallet' | 'box' | 'cargo_place') => void
  onBack: () => void
}


/**
 * Поле сканера со своим состоянием.
 *
 * Раньше значение поля жило в экране пересчёта — том же, что рисует дерево.
 * Сканер печатает штрихкод посимвольно, и каждый символ перерисовывал всё
 * дерево целиком: тринадцать полных перерисовок на один пик. На большом
 * документе это и был «медленный скан». Своё состояние держит набор внутри.
 */
function InventoryScanBox({
  expects,
  error,
  notice,
  onScan,
}: {
  expects: string
  error?: string | null
  notice?: string | null
  onScan: (code: string) => void
}) {
  const [value, setValue] = useState('')
  return (
    <ScannerField
      value={value}
      onChange={setValue}
      onScan={(code) => {
        setValue('')
        onScan(code)
      }}
      expects={expects}
      error={error ?? null}
      notice={notice ?? null}
      testId="inv-scan"
    />
  )
}

export function FfInventoryCountScreen({
  count,
  loading,
  error,
  note,
  onChange,
  onSave,
  onPost,
  onCancelDocument,
  onCreateContainer,
  onBack,
}: Props) {
  const [filters, setFilters] = useState<InvFilters>(EMPTY_FILTERS)
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set())
  // Память сканера на одну вещь: какую тару открыли. Пока открыта, пики идут в неё.
  const [openContainerId, setOpenContainerId] = useState<string | null>(null)
  const [scanNote, setScanNote] = useState<{ text: string; tone: ScanTone } | null>(null)
  const [scanFocus, setScanFocus] = useState<{ key: string; request: number } | null>(null)

  useEffect(() => {
    if (!scanFocus) return
    const frame = window.requestAnimationFrame(() => {
      document
        .querySelector<HTMLElement>(`[data-row-key="${scanFocus.key}"]`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [scanFocus])

  function handleScan(code: string) {
    const result = applyScan(count, code, openContainerId)
    setOpenContainerId(result.activeContainerId)
    setScanNote({ text: result.message, tone: result.tone })
    if (result.focusContainerKey && result.activeContainerId) {
      const openKeys = containerPathKeys(count, result.activeContainerId)
      setFilters(EMPTY_FILTERS)
      setCollapsed((current) => {
        const next = new Set(current)
        for (const key of openKeys) next.delete(key)
        return next
      })
      setScanFocus((current) => ({
        key: result.focusContainerKey as string,
        request: (current?.request ?? 0) + 1,
      }))
    }
    if (result.count !== count) onChange(result.count)
  }

  const readOnly = count.status !== 'draft'
  const createContainerDisabledReason = readOnly
    ? 'Документ уже проведён'
    : loading
      ? 'Создание тары выполняется'
      : onCreateContainer
        ? undefined
        : 'Создание тары недоступно'
  const rows = useMemo(() => buildRows(count, filters, collapsed), [count, filters, collapsed])
  const t = useMemo(() => totals(count), [count])
  const { sellers, categories } = useMemo(() => facets(count), [count])

  function toggle(row: InvRow) {
    setCollapsed((current) => {
      const next = new Set(current)
      if (next.has(row.key)) next.delete(row.key)
      else next.add(row.key)
      return next
    })
  }

  function handleActual(row: InvRow, value: number | null) {
    onChange(setActual(count, row.id, value))
  }

  const metrics: ReportMetricItem[] = [
    // Излишек и недостача разведены намеренно. Одно число «итого −119» прячет,
    // что где-то нашли лишнее, а где-то недосчитались: для склада это два разных
    // разговора и две разные причины.
    { key: 'lines', label: 'В документе', value: t.lines, unit: 'строк' },
    { key: 'counted', label: 'Посчитано', value: t.counted, unit: 'строк' },
    { key: 'surplus', label: 'Излишек', value: t.surplus, unit: 'шт' },
    { key: 'shortage', label: 'Недостача', value: t.shortage, unit: 'шт' },
  ]

  const nothingCounted = t.counted === 0
  const postReason = readOnly
    ? 'Документ уже проведён — правки закрыты'
    : nothingCounted
      ? 'Не введено ни одной цифры'
      : undefined

  return (
    <Box sx={{ p: 3 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-start', mb: 1 }}>
        <Box sx={{ pt: 0.5 }}>
          <IconAction title="К списку документов" onClick={onBack} testId="inv-back">
            <ArrowBackOutlined fontSize="small" />
          </IconAction>
        </Box>
        <Box sx={{ flex: 1 }}>
          <ScreenHeader title={`Инвентаризация ${count.number}`} />
        </Box>
      </Stack>

      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', mb: 2, flexWrap: 'wrap' }}>
        <StatusChip
          label={STATUS_LABEL[count.status]}
          tone={STATUS_TONE[count.status]}
          hint={
            count.status === 'draft'
              ? 'Остатки не тронуты. Проведение создаст движения.'
              : count.status === 'posted'
                ? `Проведён ${count.postedAt} · ${count.postedBy}`
                : 'Документ отменён, движений не создавал'
          }
          testId="inv-status"
        />
        <Typography variant="body2" color="text.secondary">
          Создал {count.createdBy}, {count.createdAt}
        </Typography>
      </Stack>

      <Box sx={{ mb: 2 }}>
        <ActionGroup>
          <SecondaryAction
            onClick={() => onCreateContainer?.('box')}
            disabledReason={createContainerDisabledReason}
            data-testid="inv-create-box"
          >
            Создать короб
          </SecondaryAction>
          <SecondaryAction
            onClick={() => onCreateContainer?.('pallet')}
            disabledReason={createContainerDisabledReason}
            data-testid="inv-create-pallet"
          >
            Создать палету
          </SecondaryAction>
          <SecondaryAction
            onClick={() => onCreateContainer?.('cargo_place')}
            disabledReason={createContainerDisabledReason}
            data-testid="inv-create-cargo-place"
          >
            Создать грузоместо
          </SecondaryAction>
        </ActionGroup>
      </Box>

      {/* Свободная строка про причину: «пересорт», «после потопа», «считали вдвоём».
          Пишется при пересчёте и остаётся видной, когда документ откроют потом —
          через месяц цифры без причины ничего не объясняют. */}
      <Box sx={{ maxWidth: 640, mb: 2 }}>
        <CommentField
          value={count.comment}
          onCommit={(comment) => onChange({ ...count, comment })}
          disabled={readOnly}
          helperText={
            readOnly
              ? 'Проведённый документ не правится'
              : 'Зачем считаем и что заметили: пересорт, повреждение, чужой товар'
          }
          testId="inv-comment"
        />
      </Box>

      {error ? <ErrorNotice testId="inv-error">{error}</ErrorNotice> : null}
      {note ? <WarningNotice testId="inv-note">{note}</WarningNotice> : null}
      {t.stale > 0 && !readOnly ? (
        <WarningNotice testId="inv-stale-notice">
          {`По ${plural(t.stale, 'строке', 'строкам', 'строкам')} остаток изменился с момента пересчёта: там прошло движение. При проведении посчитаем от нового остатка — в системе окажется ровно то, что вы насчитали руками.`}
        </WarningNotice>
      ) : null}

      <ReportMetricStrip items={metrics} loading={loading} testId="inv-metrics" />

      {/* Сканер: пикнул тару — она открылась, дальше каждый пик товара кладёт в неё
          штуку. Тара не открыта — считаем то, что лежит в ячейке россыпью. */}
      {!readOnly ? (
        <Box sx={{ maxWidth: 640, mb: 2 }}>
          <InventoryScanBox
            onScan={handleScan}
            expects={
              openContainerId
                ? `товар в ${containerName(count, openContainerId)}`
                : 'ШК тары или товара'
            }
            error={scanNote?.tone === 'error' ? scanNote.text : null}
            notice={scanNote && scanNote.tone !== 'error' ? scanNote.text : null}
          />
        </Box>
      ) : null}

      <FilterBar
        search={filters.query}
        onSearchChange={(query) => setFilters((f) => ({ ...f, query }))}
        searchPlaceholder="Название, артикул или штрихкод"
        searchHelperText="Можно вставить несколько кодов через пробел"
        testId="inv-filters"
        actions={
          <SecondaryAction
            onClick={() =>
              setCollapsed((current) =>
                current.size > 0 ? new Set() : collapseAllKeys(count),
              )
            }
            data-testid="inv-collapse-all"
          >
            {collapsed.size > 0 ? 'Раскрыть всё' : 'Свернуть всё'}
          </SecondaryAction>
        }
      >
        <SelectInput
          label="Селлер"
          value={filters.seller}
          onChange={(seller) => setFilters((f) => ({ ...f, seller }))}
          options={sellers.map((s) => ({ value: s, label: s }))}
          emptyLabel="Все селлеры"
          testId="inv-filter-seller"
        />
        <SelectInput
          label="Категория"
          value={filters.category}
          onChange={(category) => setFilters((f) => ({ ...f, category }))}
          options={categories.map((c) => ({ value: c, label: c }))}
          emptyLabel="Все категории"
          testId="inv-filter-category"
        />
        <CheckboxInput
          label="Только незакрытые"
          checked={filters.onlyPending}
          onChange={(onlyPending) => setFilters((f) => ({ ...f, onlyPending }))}
          helperText="Спрятать то, где уже сошлось"
          testId="inv-filter-pending"
        />
      </FilterBar>

      <InventoryTree
        rows={rows}
        loading={loading}
        readOnly={readOnly}
        highlightedKey={scanFocus?.key}
        empty={{
          title: 'В документе нет строк',
          hint: 'Либо отбор ничего не нашёл, либо документ наполнен пустым местом.',
        }}
        onToggle={toggle}
        onActual={handleActual}
      />

      {/* Панель действий прилеплена к нижнему краю: пересчёт длинный, и кнопка
          «Провести» не должна уезжать под сгиб на середине списка. */}
      <Paper
        variant="outlined"
        sx={{
          position: 'sticky',
          bottom: 0,
          mt: 2,
          px: 2,
          py: 1.5,
          display: 'flex',
          alignItems: 'center',
          gap: 2,
          flexWrap: 'wrap',
          zIndex: 2,
        }}
        data-testid="inv-actions"
      >
        <Typography variant="body2" color="text.secondary" sx={{ flex: 1, minWidth: 220 }}>
          {readOnly
            ? 'Проведённый документ не правится. Ошиблись — заведите новую инвентаризацию.'
            : `Посчитано ${t.counted} из ${t.lines}. Проведение создаст ${plural(t.discrepancies, 'движение', 'движения', 'движений')}.`}
        </Typography>
        {!readOnly ? (
          <DangerAction onClick={onCancelDocument} data-testid="inv-cancel-doc">
            Отменить документ
          </DangerAction>
        ) : null}
        <SecondaryAction
          onClick={onSave}
          disabledReason={readOnly ? 'Документ уже проведён' : undefined}
          data-testid="inv-save"
        >
          Сохранить
        </SecondaryAction>
        <PrimaryAction onClick={onPost} disabledReason={postReason} data-testid="inv-post">
          Провести
        </PrimaryAction>
      </Paper>
    </Box>
  )
}
