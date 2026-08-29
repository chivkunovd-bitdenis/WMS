import { useCallback, useEffect, useRef, useState } from 'react'
import { Box } from '@mui/material'
import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { renderBarcodeDataUrl } from '../../../utils/renderBarcodeDataUrl'
import { printBarcodeLabel } from '../../../utils/printBarcodeLabel'
import type { LabelSize } from '../../../utils/labelSize'
import { ErrorNotice } from '../../../ui-kit'
import { FfWarehouseMapScreen } from './FfWarehouseMapScreen'
import { InventoryCountDialog } from '../inventory/InventoryCountDialog'
import { placeOf, targetTitle, type MapInventoryTarget } from '../inventory/fromWarehouseMap'
import {
  createObjectCount,
  postCount,
  postResultNote,
  saveCountActuals,
  type CountObjectType,
} from '../inventory/inventoryCountApi'
import type { InventoryCount } from '../inventory/InventoryTypes'
import type { MoveIntent } from './WarehouseMapMoveDialog'
import type { MapRow } from './WarehouseMapRows'
import type { WarehouseMapData } from './WarehouseMapTypes'
import { applyWarehouseMapIntent } from './warehouseMapState'

// Карта склада, подключённая к серверу.
//
// Принятый экран ничего не знает про сеть: здесь выбирается склад, загружается
// его состав и подтверждаются сделанные оператором перемещения.

function headers(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` }
}

const EMPTY_MAP: WarehouseMapData = {
  warehouses: [],
  sellers: [],
  categories: [],
  cells: [],
  unassigned: [],
  journal: [],
}

const MAP_ERROR_MESSAGES: Record<string, string> = {
  warehouse_not_found: 'Склад не найден или больше недоступен.',
  object_not_found: 'Объект уже переместили или удалили.',
  destination_not_found: 'Место назначения уже недоступно.',
  cell_not_found: 'Ячейка уже недоступна.',
  pallet_not_found: 'Палета уже недоступна.',
  address_storage_disabled: 'Адресное хранение выключено: перемещение по ячейкам недоступно.',
  container_cycle: 'Нельзя положить контейнер внутрь самого себя.',
  invalid_container_destination: 'Этот объект нельзя положить в выбранное место.',
  insufficient_stock: 'На исходном месте уже нет указанного количества товара.',
  pallet_disbanded: 'Эту палету уже расформировали.',
  // Ошибки пересчёта приходят с той же карты, поэтому переводим их здесь же.
  container_has_no_stock: 'В этой таре сейчас пусто — пересчитывать нечего.',
  object_not_available_without_address_storage:
    'Пересчёт по ячейке доступен только при включённом адресном хранении.',
  count_already_posted: 'Этот пересчёт уже проведён.',
}

/** Человеческий текст вместо кода ошибки, пришедшего с сервера. */
function humanError(err: unknown, fallback: string): string {
  const raw = err instanceof Error ? err.message : ''
  return MAP_ERROR_MESSAGES[raw] ?? (raw || fallback)
}

async function mapErrorMessage(res: Response): Promise<string> {
  const message = await readApiErrorMessage(res)
  return MAP_ERROR_MESSAGES[message] ?? message
}

type Props = {
  token: string
  warehouses: Array<{ id: string; name: string }>
}

type LoadOptions = {
  preserveOperationError?: boolean
}

export function FfWarehouseMapPage({ token, warehouses }: Props) {
  const [warehouseId, setWarehouseId] = useState<string | null>(warehouses[0]?.id ?? null)
  const [data, setData] = useState<WarehouseMapData | null>(
    warehouses.length === 0 ? EMPTY_MAP : null,
  )
  const [loading, setLoading] = useState(warehouses.length > 0)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [operationError, setOperationError] = useState<string | null>(null)
  const selectedWarehouseRef = useRef(warehouseId)
  const loadVersionRef = useRef(0)
  // Пересчёт открывается прямо на карте: человек стоит у полки и не должен
  // уходить со страницы, чтобы посчитать один короб.
  const [count, setCount] = useState<InventoryCount | null>(null)
  const [countTarget, setCountTarget] = useState<MapInventoryTarget | null>(null)

  // Список складов в App загружается отдельно и может приехать после первого
  // рендера страницы. Если выбранный склад исчез, переходим на первый доступный.
  useEffect(() => {
    const current = selectedWarehouseRef.current
    const next = current && warehouses.some((warehouse) => warehouse.id === current)
      ? current
      : (warehouses[0]?.id ?? null)
    if (next === current) return
    loadVersionRef.current += 1
    selectedWarehouseRef.current = next
    setWarehouseId(next)
    setData(next ? null : EMPTY_MAP)
    setLoading(next !== null)
    setLoadError(null)
    setOperationError(null)
  }, [warehouses])

  const load = useCallback(async (options: LoadOptions = {}) => {
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
      const res = await fetch(apiUrl(`/warehouses/${requestWarehouseId}/map`), {
        headers: headers(token),
      })
      if (!res.ok) throw new Error(await mapErrorMessage(res))
      const next = (await res.json()) as WarehouseMapData
      if (requestVersion !== loadVersionRef.current) return false
      setData(next)
      return true
    } catch (err) {
      if (requestVersion !== loadVersionRef.current) return false
      setData(null)
      setLoadError(err instanceof Error ? err.message : 'Не удалось загрузить карту склада')
      return false
    } finally {
      if (requestVersion === loadVersionRef.current) setLoading(false)
    }
  }, [token, warehouseId])

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

  async function persistMove(
    requestWarehouseId: string,
    intent: MoveIntent,
    qty: number,
  ) {
    try {
      const disband = intent.reason === 'disband'
      const res = await fetch(
        apiUrl(`/warehouses/${requestWarehouseId}/map/${disband ? 'disband' : 'move'}`),
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...headers(token) },
          body: JSON.stringify(
            disband
              ? { id: intent.row.id }
              : {
                  kind: intent.row.kind,
                  id: intent.row.id,
                  to_kind: intent.toKind,
                  to_id: intent.toId,
                  qty,
                },
          ),
        },
      )
      if (!res.ok) throw new Error(await mapErrorMessage(res))
      if (selectedWarehouseRef.current !== requestWarehouseId) return
      const refreshed = await load({ preserveOperationError: true })
      if (!refreshed && selectedWarehouseRef.current === requestWarehouseId) {
        setOperationError(
          'Перемещение сохранено, но перечитать карту не удалось. Обновите страницу перед следующей операцией.',
        )
      }
    } catch (err) {
      // Пока запрос шёл, оператор мог открыть другой склад. Ошибка старого
      // склада не должна перечитать и заменить уже выбранную карту.
      if (selectedWarehouseRef.current !== requestWarehouseId) return
      setOperationError(
        err instanceof Error ? err.message : 'Не удалось сохранить перемещение',
      )
      // Оптимистическая картинка больше не является доказанной правдой. Убираем
      // её и перечитываем склад; если GET тоже откажет, неверный состав на экране
      // не останется как будто он настоящий.
      setData(null)
      await load({ preserveOperationError: true })
    }
  }

  function move(intent: MoveIntent, qty: number) {
    const requestWarehouseId = selectedWarehouseRef.current
    if (!requestWarehouseId) return
    if (intent.row.kind === 'cell' || intent.row.kind === 'unassigned') return

    setOperationError(null)
    // Сначала меняется управляемое состояние экрана, затем начинается запрос:
    // перетаскивание не ждёт сеть. Журнал здесь не выдумываем — настоящий автор
    // и запись придут с сервера при следующей загрузке карты.
    setData((current) =>
      current
        ? applyWarehouseMapIntent(
            current,
            {
              reason: intent.reason,
              rowKey: intent.row.key,
              rowTitle: intent.row.title,
              fromLabel: intent.fromLabel,
              toKey: intent.toKey,
              toLabel: intent.toLabel,
            },
            qty,
          )
        : current,
    )
    void persistMove(requestWarehouseId, intent, qty)
  }

  async function createCell(code: string) {
    const requestWarehouseId = selectedWarehouseRef.current
    if (!requestWarehouseId) {
      setOperationError('Сначала выберите склад: ячейка создаётся внутри склада.')
      return
    }
    setOperationError(null)
    try {
      const res = await fetch(apiUrl(`/warehouses/${requestWarehouseId}/locations`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers(token) },
        body: JSON.stringify({ code }),
      })
      if (!res.ok) throw new Error(await mapErrorMessage(res))
      await load({ preserveOperationError: true })
    } catch (err) {
      setOperationError(humanError(err, 'Не удалось создать ячейку'))
    }
  }

  async function createWarehouse(name: string, code: string) {
    setOperationError(null)
    try {
      const res = await fetch(apiUrl('/warehouses'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers(token) },
        body: JSON.stringify({ name, code }),
      })
      if (!res.ok) throw new Error(await mapErrorMessage(res))
      const created = (await res.json()) as { id: string }
      // Список складов на карте приезжает вместе с её составом, поэтому просто
      // переключаемся на новый: перечитывание запустит useEffect загрузки.
      selectWarehouse(created.id)
    } catch (err) {
      setOperationError(humanError(err, 'Не удалось создать склад'))
    }
  }

  function printCell(row: MapRow, size: LabelSize) {
    if (!row.barcode) {
      setOperationError('У этой ячейки нет штрихкода — печатать нечего.')
      return
    }
    setOperationError(null)
    printBarcodeLabel({
      title: `Ячейка № ${row.title}`,
      barcode: row.barcode,
      barcodeDataUrl: renderBarcodeDataUrl(row.barcode, { variant: 'storageCell' }),
      labelSize: size,
      layout: 'storageCell',
    })
  }

  /** Виду строки карты соответствует вид объекта пересчёта на сервере. */
  function countObjectType(kind: MapRow['kind']): CountObjectType | null {
    if (kind === 'cell' || kind === 'product') return kind
    if (kind === 'pallet' || kind === 'box' || kind === 'cargo_place') return kind
    return null
  }

  async function openInventory(row: MapRow) {
    const type = countObjectType(row.kind)
    if (!type) {
      setOperationError(
        'Раздел «Без ячеек» пересчитывается с экрана инвентаризации: там документ заводится по складу целиком.',
      )
      return
    }
    setOperationError(null)
    const target: MapInventoryTarget = {
      kind: row.kind,
      id: row.id,
      title: targetTitle(row.kind, row.title),
    }
    try {
      // У строки товара собственный id — это ключ остатка «товар на месте».
      // Сервер ждёт сам товар, иначе отвечает «объект уже переместили».
      const objectId = row.kind === 'product' ? (row.productId ?? row.id) : row.id
      const created = await createObjectCount(token, { type, id: objectId })
      setCountTarget(target)
      setCount(created)
    } catch (err) {
      setOperationError(humanError(err, 'Не удалось открыть пересчёт'))
    }
  }

  async function saveCount(edited: InventoryCount) {
    try {
      setCount(await saveCountActuals(token, edited))
    } catch (err) {
      setOperationError(humanError(err, 'Не удалось сохранить пересчёт'))
    }
  }

  async function postAndClose(edited: InventoryCount) {
    try {
      const result = await postCount(token, edited)
      setCount(null)
      setCountTarget(null)
      // Проведение меняет остаток, поэтому карту читаем заново: старая картинка
      // после проводки больше не правда.
      setOperationError(postResultNote(result))
      await load({ preserveOperationError: true })
    } catch (err) {
      setOperationError(humanError(err, 'Не удалось провести пересчёт'))
    }
  }

  return (
    <Box>
      {operationError ? (
        <ErrorNotice testId="warehouse-map-operation-error">{operationError}</ErrorNotice>
      ) : null}
      <FfWarehouseMapScreen
        data={data}
        loading={loading}
        error={loadError}
        warehouseId={warehouseId}
        onWarehouseChange={selectWarehouse}
        onMove={move}
        onCreateCell={(code: string) => void createCell(code)}
        onCreateWarehouse={(name: string, code: string) => void createWarehouse(name, code)}
        onPrintCell={printCell}
        onInventory={(row: MapRow) => void openInventory(row)}
        historyFor={(row: MapRow) =>
          // История строки — это не только то, что двигали саму строку, но и
          // то, что клали в неё и забирали из неё. Иначе у короба, в который
          // только что положили товар, история пустая: переезжал товар, а не
          // короб, и по одному названию строки запись не находится.
          data?.journal.filter(
            (entry) =>
              entry.subject === row.title ||
              entry.from_label === row.title ||
              entry.to_label === row.title,
          ) ?? []
        }
      />
      <InventoryCountDialog
        open={count !== null}
        title={countTarget?.title ?? ''}
        place={data && countTarget ? placeOf(data, countTarget) : null}
        initialCount={count}
        onClose={() => {
          setCount(null)
          setCountTarget(null)
        }}
        onSave={(edited: InventoryCount) => void saveCount(edited)}
        onPost={(edited: InventoryCount) => void postAndClose(edited)}
      />
    </Box>
  )
}
