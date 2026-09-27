import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Box } from '@mui/material'
import { apiUrl } from '../../../api'
import { ErrorNotice } from '../../../ui-kit'
import { WarehouseMapTree } from '../../ff/warehouse-map/WarehouseMapTree'
import { WarehouseMapWarehouseSwitch } from '../../ff/warehouse-map/WarehouseMapWarehouseSwitch'
import { WarehouseMapMoveDialog, type MoveIntent } from '../../ff/warehouse-map/WarehouseMapMoveDialog'
import { WarehouseMapHistoryDialog } from '../../ff/warehouse-map/WarehouseMapJournal'
import { BoxLabelPrintDialog } from '../../../components/BoxLabelPrintDialog'
import { InventoryCountDialog } from '../../ff/inventory/InventoryCountDialog'
import { allExpandableKeys, buildRows, EMPTY_FILTERS, type MapRow } from '../../ff/warehouse-map/WarehouseMapRows'
import { UNASSIGNED_ID, UNASSIGNED_LABEL, type WarehouseMapData } from '../../ff/warehouse-map/WarehouseMapTypes'
import { mapErrorMessage, placeOf, useWarehouseMapActions, type LoadOptions } from '../../ff/warehouse-map/useWarehouseMapActions'
import type { ProductCardLocationWarehouse } from './productCardTypes'

// WMS-490 D5: «в точности структура нашего склада… тот же самый фронт
// абсолютно, тот же самый дизайн, один в один» (решение 6, R10–R11) — та же
// таблица-дерево «Карты склада» (`WarehouseMapTree` + `buildRows`), те же окна
// перемещения, истории, печати ШК ячейки и пересчёта, тот же переключатель
// складов. Сам компонент дерева не меняется и не оборачивается в свою
// прокрутку (решение 12): при длинных названиях он прокручивается по
// горизонтали своей рамкой `DataTable`, как на «Карте склада».
//
// Отличие от страницы «Карта склада» только в данных: склад грузится с
// фильтром по этому товару (`?product_id=`, кусок D1), список складов —
// только те, где товар лежит (`locationWarehouses` из `/products/{id}/card`),
// и нет тулбара, фильтров, сканера, журнала перемещений и создания
// ячеек/складов — их этот экран не показывает (R13: ничего лишнего).

const EMPTY_MAP: WarehouseMapData = {
  warehouses: [],
  sellers: [],
  categories: [],
  cells: [],
  unassigned: [],
  journal: [],
}

type IntentTarget = Pick<MapRow, 'key' | 'id' | 'kind' | 'placeLabel'>
const UNASSIGNED_TARGET: IntentTarget = {
  key: UNASSIGNED_ID,
  id: UNASSIGNED_ID,
  kind: 'unassigned',
  placeLabel: UNASSIGNED_LABEL,
}

type Props = {
  productId: string
  token: string
  authHeaders: (t: string) => Record<string, string>
  /** Склады, где у товара есть остаток или незавершённая приёмка (из `/products/{id}/card`, D1). */
  locationWarehouses: ProductCardLocationWarehouse[]
  /**
   * Товара с таким id больше нет — вкладка должна уметь сообщить об этом
   * наверх (R16). У этого эндпойнта нет отдельного кода «товар не найден» —
   * товар без размещения (или уже удалённый) просто даёт пустую карту
   * («Товара нет на складе»), а настоящее удаление ловит основной запрос
   * карточки (D3). Проп остаётся ради общей сигнатуры вкладок.
   */
  onNotFound: () => void
  /** Пересчёт на вкладке меняет остаток — карточка должна перечитать шапку и «Движения» (R11). */
  onStockChanged: () => void
}

export function ProductCardLocationTab({
  productId,
  token,
  authHeaders,
  locationWarehouses,
  // Проп остаётся ради общей сигнатуры вкладок (см. комментарий в Props) —
  // этот запрос не умеет отличить «товара нет на складе» от «товара больше
  // нет», поэтому вкладка его не вызывает.
  onNotFound: _onNotFound,
  onStockChanged,
}: Props) {
  const [warehouseId, setWarehouseId] = useState<string | null>(locationWarehouses[0]?.id ?? null)
  const [data, setData] = useState<WarehouseMapData | null>(
    locationWarehouses.length === 0 ? EMPTY_MAP : null,
  )
  const [loading, setLoading] = useState(locationWarehouses.length > 0)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [operationError, setOperationError] = useState<string | null>(null)
  const selectedWarehouseRef = useRef(warehouseId)
  const loadVersionRef = useRef(0)

  // Дерево держит не «что раскрыто», а «что свёрнуто» — как на «Карте
  // склада»: по умолчанию раскрыто всё (R10), и новые узлы после перечитывания
  // карты приезжают уже раскрытыми сами собой.
  const [collapsedKeys, setCollapsedKeys] = useState<Set<string>>(new Set())
  const [carried, setCarried] = useState<MapRow | null>(null)
  const [intent, setIntent] = useState<MoveIntent | null>(null)
  const [historyRow, setHistoryRow] = useState<MapRow | null>(null)
  const [printRow, setPrintRow] = useState<MapRow | null>(null)

  // Список складов пришёл заново (например, карточка перечиталась после
  // пересчёта). Если выбранный склад пропал из списка — переходим на первый
  // доступный, как страница «Карта склада» делает со списком складов
  // организации.
  useEffect(() => {
    const current = selectedWarehouseRef.current
    const next =
      current && locationWarehouses.some((warehouse) => warehouse.id === current)
        ? current
        : (locationWarehouses[0]?.id ?? null)
    if (next === current) return
    loadVersionRef.current += 1
    selectedWarehouseRef.current = next
    setWarehouseId(next)
    setData(next ? null : EMPTY_MAP)
    setLoading(next !== null)
    setLoadError(null)
  }, [locationWarehouses])

  const load = useCallback(
    async (options: LoadOptions = {}): Promise<boolean> => {
      const requestWarehouseId = warehouseId
      const requestVersion = loadVersionRef.current + 1
      loadVersionRef.current = requestVersion

      if (!requestWarehouseId) {
        setData(EMPTY_MAP)
        setLoading(false)
        setLoadError(null)
        if (!options.preserveOperationError) setOperationError(null)
        return true
      }

      setLoading(true)
      setLoadError(null)
      if (!options.preserveOperationError) setOperationError(null)
      try {
        const params = new URLSearchParams({ product_id: productId })
        const res = await fetch(apiUrl(`/warehouses/${requestWarehouseId}/map?${params.toString()}`), {
          headers: { ...authHeaders(token) },
        })
        if (!res.ok) throw new Error(await mapErrorMessage(res))
        const next = (await res.json()) as WarehouseMapData
        if (requestVersion !== loadVersionRef.current) return false
        setData(next)
        return true
      } catch (err) {
        if (requestVersion !== loadVersionRef.current) return false
        setData(null)
        setLoadError(err instanceof Error ? err.message : 'Не удалось загрузить расположение товара.')
        return false
      } finally {
        if (requestVersion === loadVersionRef.current) setLoading(false)
      }
    },
    [authHeaders, token, warehouseId, productId],
  )

  useEffect(() => {
    void load()
  }, [load])

  function selectWarehouse(nextWarehouseId: string) {
    if (nextWarehouseId === selectedWarehouseRef.current) return
    loadVersionRef.current += 1
    selectedWarehouseRef.current = nextWarehouseId
    setWarehouseId(nextWarehouseId)
    setData(null)
    setLoading(true)
    setLoadError(null)
    setOperationError(null)
  }

  const actions = useWarehouseMapActions({
    token,
    warehouseId,
    data,
    setData,
    load,
    onError: setOperationError,
    // R11: проведённый пересчёт меняет остаток — карточка перечитывает шапку и
    // «Движения». Обычное перемещение их не трогает (остаток ≠ расположение),
    // поэтому `onCountPosted` вызывается только отсюда, не из `move`.
    onCountPosted: onStockChanged,
  })

  const expandable = useMemo(() => (data ? allExpandableKeys(data) : new Set<string>()), [data])
  const expandedKeys = useMemo(() => {
    const keys = new Set<string>()
    expandable.forEach((key) => {
      if (!collapsedKeys.has(key)) keys.add(key)
    })
    return keys
  }, [collapsedKeys, expandable])
  const rows = useMemo(
    () => (data ? buildRows(data, { expandedKeys, filters: EMPTY_FILTERS }) : []),
    [data, expandedKeys],
  )
  const rowsByKey = useMemo(() => new Map(rows.map((row) => [row.key, row])), [rows])

  function toggleRow(row: MapRow) {
    setCollapsedKeys((current) => {
      const next = new Set(current)
      if (next.has(row.key)) next.delete(row.key)
      else next.add(row.key)
      return next
    })
  }

  function placeOfRow(row: MapRow): string {
    if (!row.parentKey) return UNASSIGNED_LABEL
    return rowsByKey.get(row.parentKey)?.placeLabel ?? UNASSIGNED_LABEL
  }

  function openIntent(reason: MoveIntent['reason'], row: MapRow, target: IntentTarget) {
    if (target.kind === 'product') return
    setIntent({
      reason,
      row,
      fromLabel: placeOfRow(row),
      toKey: target.key,
      toKind: target.kind,
      toId: target.kind === 'unassigned' ? null : target.id,
      toLabel: target.placeLabel,
    })
  }

  if (loadError) {
    return <ErrorNotice testId="product-card-location-error">{loadError}</ErrorNotice>
  }

  return (
    <Box data-testid="product-card-location-tab">
      {operationError ? (
        <ErrorNotice testId="product-card-location-operation-error">{operationError}</ErrorNotice>
      ) : null}
      {locationWarehouses.length > 1 ? (
        <Box sx={{ mb: 1.5 }}>
          <WarehouseMapWarehouseSwitch
            warehouses={locationWarehouses}
            warehouseId={warehouseId}
            onWarehouseChange={selectWarehouse}
          />
        </Box>
      ) : null}
      <WarehouseMapTree
        rows={rows}
        loading={loading}
        carried={carried}
        highlightedKey={null}
        empty={{ title: 'Товара нет на складе' }}
        onToggle={toggleRow}
        onTakeOff={(row) => openIntent('takeOff', row, UNASSIGNED_TARGET)}
        onDisband={(row) => openIntent('disband', row, UNASSIGNED_TARGET)}
        onHistory={setHistoryRow}
        onPrintCell={setPrintRow}
        onInventory={(row) => void actions.openInventory(row)}
        onDragStart={setCarried}
        onDragEnd={() => setCarried(null)}
        onDrop={(target) => {
          if (!carried) return
          openIntent('move', carried, target)
          setCarried(null)
        }}
      />

      <WarehouseMapMoveDialog
        intent={intent}
        onClose={() => setIntent(null)}
        onConfirm={(confirmed, qty) => {
          actions.move(confirmed, qty)
          setIntent(null)
        }}
      />
      <WarehouseMapHistoryDialog
        title={historyRow ? historyRow.title : null}
        entries={
          historyRow
            ? (data?.journal.filter(
                (entry) =>
                  entry.subject === historyRow.title ||
                  entry.from_label === historyRow.title ||
                  entry.to_label === historyRow.title,
              ) ?? [])
            : []
        }
        onClose={() => setHistoryRow(null)}
      />
      <BoxLabelPrintDialog
        open={printRow !== null}
        title={printRow ? `Печать ШК ячейки ${printRow.title}` : ''}
        description="Выберите размер этикетки. Напечатанное не отменить."
        scope="label"
        onClose={() => setPrintRow(null)}
        onConfirm={(size) => {
          if (printRow) actions.printCell(printRow, size)
          setPrintRow(null)
        }}
        testId="product-card-location-print-dialog"
      />
      <InventoryCountDialog
        open={actions.count !== null}
        title={actions.countTarget?.title ?? ''}
        place={data && actions.countTarget ? placeOf(data, actions.countTarget) : null}
        initialCount={actions.count}
        busy={actions.countBusy}
        onMarkEmpty={(edited, target) => void actions.markEmpty(edited, target)}
        onClose={actions.closeCount}
        onSave={(edited) => void actions.saveCount(edited)}
        onPost={(edited) => void actions.postAndClose(edited)}
      />
    </Box>
  )
}
