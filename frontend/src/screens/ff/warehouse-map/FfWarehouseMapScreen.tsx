import { Box, Paper } from '@mui/material'
import { useMemo, useRef, useState } from 'react'
import { EmptyState, ErrorNotice, PrimaryAction, ScreenHeader } from '../../../ui-kit'
import { WarehouseMapTree } from './WarehouseMapTree'
import { WarehouseMapJournal, WarehouseMapHistoryDialog } from './WarehouseMapJournal'
import { WarehouseMapMoveDialog, type MoveIntent } from './WarehouseMapMoveDialog'
import {
  CreateCellDialog,
  CreateWarehouseDialog,
  WarehouseMapToolbar,
} from './WarehouseMapToolbar'
import { BoxLabelPrintDialog } from '../../../components/BoxLabelPrintDialog'
import type { LabelSize } from '../../../utils/labelSize'
import {
  EMPTY_FILTERS,
  allExpandableKeys,
  buildRows,
  findByBarcode,
  missingTokens,
  type MapFilters,
  type MapRow,
} from './WarehouseMapRows'
import {
  UNASSIGNED_ID,
  UNASSIGNED_LABEL,
  type MovementEntry,
  type WarehouseMapData,
} from './WarehouseMapTypes'

const PURPOSE = 'Что физически лежит на каждой ячейке. Строку можно перетащить на другую ячейку.'
type IntentTarget = Pick<MapRow, 'key' | 'id' | 'kind' | 'placeLabel'>
const UNASSIGNED_TARGET: IntentTarget = {
  key: UNASSIGNED_ID,
  id: UNASSIGNED_ID,
  kind: 'unassigned',
  placeLabel: UNASSIGNED_LABEL,
}

// Карта склада: что физически лежит на каждой ячейке и как это переложить рукой.
// Экран ничего не знает про сервер — он показывает данные и сообщает наверх о
// том, что оператор сделал. Сервер по этому же контракту подключается отдельно.

type Props = {
  data: WarehouseMapData | null
  loading: boolean
  error: string | null
  warehouseId: string | null
  onWarehouseChange: (warehouseId: string) => void
  onMove: (intent: MoveIntent, qty: number) => void
  onCreateCell: (code: string) => void
  onCreateWarehouse: (name: string, code: string) => void
  onPrintCell: (row: MapRow, size: LabelSize) => void
  /** Пересчитать содержимое строки: открыть инвентаризацию по этому объекту. */
  onInventory: (row: MapRow) => void
  /** История одной строки. Пока сервера нет — журнал целиком. */
  historyFor: (row: MapRow) => MovementEntry[]
}

export function FfWarehouseMapScreen({
  data,
  loading,
  error,
  warehouseId,
  onWarehouseChange,
  onMove,
  onCreateCell,
  onCreateWarehouse,
  onPrintCell,
  onInventory,
  historyFor,
}: Props) {
  // Держим не «что раскрыто», а «что свёрнуто»: владелец просил, чтобы по
  // умолчанию было раскрыто всё, и при таком хранении новые ячейки и короба
  // приезжают уже раскрытыми сами собой, без отдельной синхронизации.
  const [collapsedKeys, setCollapsedKeys] = useState<Set<string>>(new Set())
  const [filters, setFilters] = useState<MapFilters>(EMPTY_FILTERS)
  const [scanValue, setScanValue] = useState('')
  const [scanError, setScanError] = useState<string | null>(null)
  const [scanNotice, setScanNotice] = useState<string | null>(null)
  const [highlightedKey, setHighlightedKey] = useState<string | null>(null)
  const [printRow, setPrintRow] = useState<MapRow | null>(null)
  const tableRef = useRef<HTMLDivElement>(null)
  const [carried, setCarried] = useState<MapRow | null>(null)
  const [intent, setIntent] = useState<MoveIntent | null>(null)
  const [historyRow, setHistoryRow] = useState<MapRow | null>(null)
  const [journalOpen, setJournalOpen] = useState(true)
  const [cellDialogOpen, setCellDialogOpen] = useState(false)
  const [warehouseDialogOpen, setWarehouseDialogOpen] = useState(false)

  const expandable = useMemo(
    () => (data ? allExpandableKeys(data) : new Set<string>()),
    [data],
  )
  const expandedKeys = useMemo(() => {
    const keys = new Set<string>()
    expandable.forEach((key) => {
      if (!collapsedKeys.has(key)) keys.add(key)
    })
    return keys
  }, [collapsedKeys, expandable])

  const rows = useMemo(
    () => (data ? buildRows(data, { expandedKeys, filters }) : []),
    [data, expandedKeys, filters],
  )
  const missing = useMemo(
    () => (data ? missingTokens(data, filters.query) : []),
    [data, filters.query],
  )
  const rowsByKey = useMemo(() => new Map(rows.map((row) => [row.key, row])), [rows])

  const warehouses = data?.warehouses ?? []
  const currentWarehouse = warehouses.find((warehouse) => warehouse.id === warehouseId) ?? null
  const cellCodes = useMemo(() => (data?.cells ?? []).map((cell) => cell.code), [data])
  const allExpanded = collapsedKeys.size === 0

  function toggleRow(row: MapRow) {
    setCollapsedKeys((current) => {
      const next = new Set(current)
      if (next.has(row.key)) next.delete(row.key)
      else next.add(row.key)
      return next
    })
  }

  function handleScan(code: string) {
    setScanValue('')
    if (!data) return
    const hit = findByBarcode(data, code)
    if (!hit) {
      setScanNotice(null)
      setScanError(`Штрихкод ${code} на этом складе не нашёлся`)
      setHighlightedKey(null)
      return
    }
    // Путь к найденному раскрываем принудительно: пикнутый короб не должен
    // остаться спрятанным под свёрнутой ячейкой — ровно это и просили перенести
    // сюда из блока коробов в каталоге.
    setCollapsedKeys((current) => {
      const next = new Set(current)
      hit.ancestorKeys.forEach((key) => next.delete(key))
      return next
    })
    setScanError(null)
    setScanNotice(`${hit.title} — ${hit.placeLabel}`)
    setHighlightedKey(hit.key)
    // Прокрутка после перерисовки: до неё строки найденного ещё нет в разметке.
    window.setTimeout(() => {
      tableRef.current
        ?.querySelector(`[data-row-key="${CSS.escape(hit.key)}"]`)
        ?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }, 0)
  }

  function placeOf(row: MapRow): string {
    if (!row.parentKey) return UNASSIGNED_LABEL
    return rowsByKey.get(row.parentKey)?.placeLabel ?? UNASSIGNED_LABEL
  }

  function openIntent(reason: MoveIntent['reason'], row: MapRow, target: IntentTarget) {
    if (target.kind === 'product') return
    setIntent({
      reason,
      row,
      fromLabel: placeOf(row),
      toKey: target.key,
      toKind: target.kind,
      toId: target.kind === 'unassigned' ? null : target.id,
      toLabel: target.placeLabel,
    })
  }

  if (error) {
    return (
      <Box data-testid="warehouse-map-screen">
        <ScreenHeader title="Карта склада" purpose={PURPOSE} />
        <ErrorNotice testId="warehouse-map-error">{error}</ErrorNotice>
      </Box>
    )
  }

  const noWarehouses = !loading && data !== null && warehouses.length === 0

  return (
    <Box data-testid="warehouse-map-screen">
      <ScreenHeader title="Карта склада" purpose={PURPOSE} />

      {noWarehouses ? (
        <Paper variant="outlined" data-testid="warehouse-map-no-warehouses">
          <EmptyState
            title="Пока нет складов"
            hint="Склад — это здание или зона хранения. Создайте первый, потом добавьте в него ячейки."
            action={
              <PrimaryAction
                onClick={() => setWarehouseDialogOpen(true)}
                data-testid="warehouse-map-create-first-warehouse"
              >
                Создать склад
              </PrimaryAction>
            }
          />
        </Paper>
      ) : (
        <>
          <WarehouseMapToolbar
            warehouses={warehouses}
            warehouseId={warehouseId}
            onWarehouseChange={onWarehouseChange}
            sellers={data?.sellers ?? []}
            categories={data?.categories ?? []}
            filters={filters}
            onFiltersChange={setFilters}
            missing={missing}
            scanValue={scanValue}
            onScanValueChange={(value) => {
              setScanValue(value)
              setScanError(null)
            }}
            onScan={handleScan}
            scanError={scanError}
            scanNotice={scanNotice}
            allExpanded={allExpanded}
            onToggleAll={() =>
              setCollapsedKeys(allExpanded ? new Set(expandable) : new Set())
            }
            toggleAllDisabledReason={
              expandable.size === 0 ? 'Разворачивать пока нечего' : undefined
            }
            onCreateCell={() => setCellDialogOpen(true)}
            onCreateWarehouse={() => setWarehouseDialogOpen(true)}
            createCellDisabledReason={currentWarehouse ? undefined : 'Сначала выберите склад'}
          />

          <Box ref={tableRef}>
          <WarehouseMapTree
            rows={rows}
            loading={loading}
            carried={carried}
            highlightedKey={highlightedKey}
            empty={
              filters.query || filters.seller || filters.category
                ? {
                    title: 'Ничего не нашлось',
                    hint: 'Поищите по названию товара, штрихкоду, номеру короба или коду ячейки.',
                  }
                : {
                    title: 'На складе пока нет ячеек',
                    hint: 'Создайте первую — и раскладывайте на неё товар и короба.',
                    action: (
                      <PrimaryAction
                        onClick={() => setCellDialogOpen(true)}
                        data-testid="warehouse-map-create-first-cell"
                      >
                        Создать ячейку
                      </PrimaryAction>
                    ),
                  }
            }
            onToggle={toggleRow}
            onTakeOff={(row) => openIntent('takeOff', row, UNASSIGNED_TARGET)}
            onDisband={(row) => openIntent('disband', row, UNASSIGNED_TARGET)}
            onHistory={setHistoryRow}
            onPrintCell={setPrintRow}
            onInventory={onInventory}
            onDragStart={setCarried}
            onDragEnd={() => setCarried(null)}
            onDrop={(target) => {
              if (!carried) return
              openIntent('move', carried, target)
              setCarried(null)
            }}
          />
          </Box>

          <WarehouseMapJournal
            entries={data?.journal ?? []}
            loading={loading}
            open={journalOpen}
            onToggle={() => setJournalOpen((open) => !open)}
          />
        </>
      )}

      <WarehouseMapMoveDialog
        intent={intent}
        onClose={() => setIntent(null)}
        onConfirm={(confirmed, qty) => {
          onMove(confirmed, qty)
          setIntent(null)
        }}
      />
      <WarehouseMapHistoryDialog
        title={historyRow ? historyRow.title : null}
        entries={historyRow ? historyFor(historyRow) : []}
        onClose={() => setHistoryRow(null)}
      />
      <CreateCellDialog
        open={cellDialogOpen}
        warehouseName={currentWarehouse?.name ?? ''}
        existingCodes={cellCodes}
        onClose={() => setCellDialogOpen(false)}
        onCreate={(code) => {
          onCreateCell(code)
          setCellDialogOpen(false)
        }}
      />
      <BoxLabelPrintDialog
        open={printRow !== null}
        title={printRow ? `Печать ШК ячейки ${printRow.title}` : ''}
        description="Выберите размер этикетки. Напечатанное не отменить."
        scope="label"
        onClose={() => setPrintRow(null)}
        onConfirm={(size) => {
          if (printRow) onPrintCell(printRow, size)
          setPrintRow(null)
        }}
        testId="warehouse-map-print-dialog"
      />
      <CreateWarehouseDialog
        open={warehouseDialogOpen}
        onClose={() => setWarehouseDialogOpen(false)}
        onCreate={(name, code) => {
          onCreateWarehouse(name, code)
          setWarehouseDialogOpen(false)
        }}
      />
    </Box>
  )
}
