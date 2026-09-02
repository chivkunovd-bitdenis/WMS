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
  ScreenHeader,
  SecondaryAction,
  SelectInput,
  StatusChip,
  WarningNotice,
} from '../../../ui-kit'
import type { ReportMetricItem, StatusTone } from '../../../ui-kit'
import { CommentField } from './CommentField'
import {
  applyScan,
  cellLabel,
  containerName,
  NOTHING_OPEN,
  type ScanOpenPlace,
  type ScanTone,
} from './InventoryScan'
import { InventoryScanField } from './InventoryScanField'
import { containerContents } from './containerContents'
import { printContainerContents } from './printContainerContents'
import { randomId } from '../../../utils/randomId'
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
import type { CountStatus, InventoryCount } from './InventoryTypes'

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

type Props = {
  count: InventoryCount
  loading: boolean
  error: string | null
  /** Что сказали в ответ на сохранение или проведение. */
  note: string | null
  /**
   * Изменение документа. Второй аргумент — строка, которую тронул оператор:
   * по нему страница понимает, что именно отправлять на сервер, и не пишет
   * поверх работы второго кладовщика в том же документе.
   */
  onChange: (next: InventoryCount, touchedLineId?: string) => void
  onSave: () => void
  onPost: () => void
  onCancelDocument: () => void
  /**
   * Сколько сканов находок ещё не доставлено на сервер.
   *
   * Пока их больше нуля, документ проводить нельзя: проведение зафиксирует
   * остаток без того, что оператор уже отсканировал, а вернуться в проведённый
   * документ невозможно.
   */
  pendingFound?: number
  onCreateContainer?: (kind: 'pallet' | 'box' | 'cargo_place') => void
  /** Записать находку: товар лежит там, где по учёту его нет. */
  onFound?: (place: {
    barcodes: string[]
    cellId: string | null
    containerKind: 'pallet' | 'box' | 'cargo_place' | null
    containerId: string | null
    scanId: string
  }) => void
  onBack: () => void
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
  pendingFound = 0,
  onCreateContainer,
  onFound,
  onBack,
}: Props) {
  const [filters, setFilters] = useState<InvFilters>(EMPTY_FILTERS)
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set())
  // Память сканера: что сейчас открыто — тара и/или ячейка. Пики идут туда.
  const [openPlace, setOpenPlace] = useState<ScanOpenPlace>(NOTHING_OPEN)
  const [scanNote, setScanNote] = useState<{ text: string; tone: ScanTone } | null>(null)
  const [scanFocus, setScanFocus] = useState<{ key: string; request: number } | null>(null)

  useEffect(() => {
    if (!scanFocus) return
    const frame = window.requestAnimationFrame(() => {
      document
        .querySelector<HTMLElement>(`[data-row-key="${scanFocus.key}"]`)
        ?.scrollIntoView({ behavior: 'auto', block: 'center' })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [scanFocus])

  function handleScan(code: string) {
    const result = applyScan(count, code, openPlace)
    setOpenPlace(result.open)
    setScanNote({ text: result.message, tone: result.tone })
    if (result.focusRowKey) {
      const openKeys = result.focusPathKeys ?? []
      setFilters((current) => current === EMPTY_FILTERS ? current : EMPTY_FILTERS)
      setCollapsed((current) => {
        const next = new Set(current)
        let changed = false
        for (const key of openKeys) changed = next.delete(key) || changed
        return changed ? next : current
      })
      const focusKey = result.focusRowKey
      setScanFocus((current) => current?.key === focusKey ? current : ({
        key: focusKey,
        request: (current?.request ?? 0) + 1,
      }))
    }
    if (result.found) {
      // Идентификатор скана рождается здесь, на одном пике. Если ответ не
      // доедет и оператор пикнет ещё раз, это будет уже другой скан — а вот
      // повтор этого же запроса сервер узнает и не посчитает дважды.
      onFound?.({ ...result.found, scanId: randomId() })
    }
    if (result.count !== count) {
      const touched = result.focusRowKey?.startsWith('product:')
        ? result.focusRowKey.slice('product:'.length)
        : undefined
      onChange(result.count, touched)
    }
  }

  // Явная кнопка рядом со сканером: не у каждого оператора под рукой штрихкод
  // открытой тары, а совет «закройте тару» без способа закрыть — издевательство.
  function closeOpenPlace() {
    if (openPlace.containerId) {
      const name = containerName(count, openPlace.containerId)
      setOpenPlace({ containerId: null, cellId: openPlace.cellId })
      setScanNote({ text: `Закрыли ${name}. Пики идут россыпью в эту ячейку.`, tone: 'ok' })
      return
    }
    if (!openPlace.cellId) return
    setOpenPlace(NOTHING_OPEN)
    setScanNote({ text: 'Ячейка закрыта.', tone: 'ok' })
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
    onChange(setActual(count, row.id, value), row.id)
  }

  // Опись печатается из документа, каким он на экране сейчас: кладовщик клеит
  // её сразу после пересчёта короба, до сохранения и проведения.
  function handlePrintContents(row: InvRow) {
    const contents = containerContents(count, row.id)
    if (!contents) return
    printContainerContents({
      contents,
      documentNumber: count.number,
      documentDate: count.createdAt,
    })
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
    : pendingFound > 0
      ? `Ещё не сохранено находок: ${pendingFound}. Дождитесь отправки`
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
          штуку. Тара не открыта — считаем то, что лежит в ячейке россыпью.

          Блок прилеплен к верхнему краю. Документ по складу — это сорок тысяч
          пикселей: скан уводит экран к найденной строке вниз, а ответ сканера
          («короб открыт», «1 из 5») остаётся наверху, за кадром. Оператор пикает
          и не видит ничего — ровно то, что на складе называют «система не
          реагирует». Пока поле видно всегда, ответ виден всегда. */}
      {!readOnly ? (
        <Box
          sx={{
            maxWidth: 640,
            mb: 2,
            position: 'sticky',
            top: 0,
            zIndex: 3,
            backgroundColor: 'background.default',
            pt: 1,
          }}
        >
          <InventoryScanField
            onScan={handleScan}
            expects={
              openPlace.containerId
                ? `товар в ${containerName(count, openPlace.containerId)}`
                : openPlace.cellId
                  ? `товар россыпью в ячейке ${cellLabel(count, openPlace.cellId)}`
                  : 'ШК ячейки, тары или товара'
            }
            error={scanNote?.tone === 'error' ? scanNote.text : null}
            notice={scanNote && scanNote.tone !== 'error' ? scanNote.text : null}
            testId="inv-scan"
          />
          {openPlace.containerId || openPlace.cellId ? (
            <Box sx={{ mt: 1 }}>
              <SecondaryAction onClick={closeOpenPlace} data-testid="inv-close-container">
                {openPlace.containerId ? 'Закрыть тару' : 'Закрыть ячейку'}
              </SecondaryAction>
            </Box>
          ) : null}
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
        onPrintContents={handlePrintContents}
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
