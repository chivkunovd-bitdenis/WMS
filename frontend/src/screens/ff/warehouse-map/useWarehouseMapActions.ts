import { useCallback, useEffect, useRef, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import { changedActualIds } from '../inventory/InventoryRows'
import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { renderBarcodeDataUrl } from '../../../utils/renderBarcodeDataUrl'
import { printBarcodeLabel } from '../../../utils/printBarcodeLabel'
import type { LabelSize } from '../../../utils/labelSize'
import { placeOf as inventoryPlaceOf, targetTitle, type MapInventoryTarget } from '../inventory/fromWarehouseMap'
import {
  createObjectCount,
  postCount,
  postResultNote,
  saveCountActuals,
  markCountPlaceEmpty,
  type CountObjectType,
} from '../inventory/inventoryCountApi'
import type { InventoryCount } from '../inventory/InventoryTypes'
import type { MoveIntent } from './WarehouseMapMoveDialog'
import type { MapRow } from './WarehouseMapRows'
import type { WarehouseMapData } from './WarehouseMapTypes'
import { applyWarehouseMapIntent } from './warehouseMapState'

// WMS-490 D5: работа с сервером у «Карты склада» — перемещение, расформирование,
// печать ШК ячейки, пересчёт (создание/сохранение/«пусто»/проведение) и тексты
// ошибок — вынесена сюда из `FfWarehouseMapPage.tsx` без изменения поведения,
// чтобы вкладка «Расположение» карточки товара (`ProductCardLocationTab.tsx`)
// пользовалась теми же самыми действиями над теми же строками дерева, не
// переписывая их второй раз. Страница «Карта склада» продолжает владеть
// собственным списком складов, фильтрами, созданием ячеек и складов — это не
// «работа с сервером» в смысле этого куска, а собственно экран.

export { inventoryPlaceOf as placeOf }

export const MAP_ERROR_MESSAGES: Record<string, string> = {
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
export function humanError(err: unknown, fallback: string): string {
  const raw = err instanceof Error ? err.message : ''
  if (raw === 'comment_changed') return 'Другой сотрудник изменил комментарий. Откройте документ заново и сверьте текст.'
  return MAP_ERROR_MESSAGES[raw] ?? (raw || fallback)
}

export async function mapErrorMessage(res: Response): Promise<string> {
  const message = await readApiErrorMessage(res)
  return MAP_ERROR_MESSAGES[message] ?? message
}

function headers(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` }
}

export type LoadOptions = { preserveOperationError?: boolean }

type Params = {
  token: string
  /** Склад, к которому относятся текущие `data` — для отсечения устаревшего ответа при смене склада. */
  warehouseId: string | null
  data: WarehouseMapData | null
  setData: Dispatch<SetStateAction<WarehouseMapData | null>>
  /** Перечитать карту (страница сама решает, для какого склада и с каким фильтром). */
  load: (options?: LoadOptions) => Promise<boolean>
  /** Ошибка действия — вызывающий экран сам решает, где и как её показать. */
  onError: (message: string | null) => void
  /** Пересчёт провели: вызывающий экран может перечитать то, что зависит от остатка (WMS-490: шапку и «Движения»). */
  onCountPosted?: () => void
}

export type UseWarehouseMapActionsResult = {
  move: (intent: MoveIntent, qty: number) => void
  printCell: (row: MapRow, size: LabelSize) => void
  count: InventoryCount | null
  countTarget: MapInventoryTarget | null
  countBusy: boolean
  openInventory: (row: MapRow) => Promise<void>
  saveCount: (edited: InventoryCount) => Promise<void>
  markEmpty: (
    edited: InventoryCount,
    target: { kind: 'cell' | 'pallet' | 'box' | 'cargo_place'; id: string },
  ) => Promise<void>
  postAndClose: (edited: InventoryCount) => Promise<void>
  closeCount: () => void
}

/** Виду строки карты соответствует вид объекта пересчёта на сервере. */
function countObjectType(kind: MapRow['kind']): CountObjectType | null {
  if (kind === 'cell' || kind === 'product') return kind
  if (kind === 'pallet' || kind === 'box' || kind === 'cargo_place') return kind
  return null
}

export function useWarehouseMapActions({
  token,
  warehouseId,
  setData,
  load,
  onError,
  onCountPosted,
}: Params): UseWarehouseMapActionsResult {
  const [countBusy, setCountBusy] = useState(false)
  const [count, setCount] = useState<InventoryCount | null>(null)
  const [countTarget, setCountTarget] = useState<MapInventoryTarget | null>(null)
  // Пока запрос идёт, оператор мог переключить склад — ответ старого склада не
  // должен заменить уже выбранную карту (перенесено из FfWarehouseMapPage).
  const selectedWarehouseRef = useRef(warehouseId)
  useEffect(() => {
    selectedWarehouseRef.current = warehouseId
  }, [warehouseId])

  const persistMove = useCallback(
    async (requestWarehouseId: string, intent: MoveIntent, qty: number) => {
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
                    // Количество имеет смысл только у товара. Тара переезжает
                    // целиком вместе с содержимым — контракт карты склада, 3.1.
                    qty: intent.row.kind === 'product' ? qty : null,
                  },
            ),
          },
        )
        if (!res.ok) throw new Error(await mapErrorMessage(res))
        if (selectedWarehouseRef.current !== requestWarehouseId) return
        const refreshed = await load({ preserveOperationError: true })
        if (!refreshed && selectedWarehouseRef.current === requestWarehouseId) {
          onError(
            'Перемещение сохранено, но перечитать карту не удалось. Обновите страницу перед следующей операцией.',
          )
        }
      } catch (err) {
        if (selectedWarehouseRef.current !== requestWarehouseId) return
        onError(err instanceof Error ? err.message : 'Не удалось сохранить перемещение')
        // Оптимистическая картинка больше не является доказанной правдой.
        setData(null)
        await load({ preserveOperationError: true })
      }
    },
    [token, load, onError, setData],
  )

  const move = useCallback(
    (intent: MoveIntent, qty: number) => {
      const requestWarehouseId = selectedWarehouseRef.current
      if (!requestWarehouseId) return
      if (intent.row.kind === 'cell' || intent.row.kind === 'unassigned') return

      onError(null)
      // Сначала меняется управляемое состояние экрана, затем начинается запрос:
      // перетаскивание не ждёт сеть.
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
    },
    [persistMove, setData, onError],
  )

  const printCell = useCallback(
    (row: MapRow, size: LabelSize) => {
      if (!row.barcode) {
        onError('У этой ячейки нет штрихкода — печатать нечего.')
        return
      }
      onError(null)
      printBarcodeLabel({
        title: `Ячейка № ${row.title}`,
        barcode: row.barcode,
        barcodeDataUrl: renderBarcodeDataUrl(row.barcode, { variant: 'storageCell' }),
        labelSize: size,
        layout: 'storageCell',
      })
    },
    [onError],
  )

  const openInventory = useCallback(
    async (row: MapRow) => {
      const type = countObjectType(row.kind)
      if (!type) {
        onError(
          'Раздел «Без ячеек» пересчитывается с экрана инвентаризации: там документ заводится по складу целиком.',
        )
        return
      }
      onError(null)
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
        onError(humanError(err, 'Не удалось открыть пересчёт'))
      }
    },
    [token, onError],
  )

  const saveCount = useCallback(
    async (edited: InventoryCount) => {
      if (!count || countBusy || count.id !== edited.id) return
      setCountBusy(true)
      try {
        const saved = await saveCountActuals(token, edited, changedActualIds(edited, count), {
          updateComment: edited.comment !== count.comment,
          comment: edited.comment,
          expectedComment: count.comment,
        })
        setCount((current) => (current?.id === saved.id ? saved : current))
      } catch (err) {
        onError(humanError(err, 'Не удалось сохранить пересчёт'))
      } finally {
        setCountBusy(false)
      }
    },
    [token, count, countBusy, onError],
  )

  const markEmpty = useCallback(
    async (edited: InventoryCount, target: { kind: 'cell' | 'pallet' | 'box' | 'cargo_place'; id: string }) => {
      if (!count || countBusy || count.id !== edited.id) return
      setCountBusy(true)
      try {
        await saveCountActuals(token, edited, changedActualIds(edited, count), {
          updateComment: edited.comment !== count.comment,
          comment: edited.comment,
          expectedComment: count.comment,
        })
        const saved = await markCountPlaceEmpty(token, edited.id, target)
        setCount((current) => (current?.id === saved.id ? saved : current))
      } catch (err) {
        onError(humanError(err, 'Не удалось подтвердить пустое место'))
      } finally {
        setCountBusy(false)
      }
    },
    [token, count, countBusy, onError],
  )

  const postAndClose = useCallback(
    async (edited: InventoryCount) => {
      if (!count || countBusy || count.id !== edited.id) return
      setCountBusy(true)
      try {
        const result = await postCount(token, edited, changedActualIds(edited, count), {
          expectedComment: count.comment,
          updateComment: edited.comment !== count.comment,
          comment: edited.comment,
        })
        setCount(null)
        setCountTarget(null)
        // Проведение меняет остаток, поэтому карту читаем заново: старая
        // картинка после проводки больше не правда.
        onError(postResultNote(result))
        await load({ preserveOperationError: true })
        onCountPosted?.()
      } catch (err) {
        onError(humanError(err, 'Не удалось провести пересчёт'))
      } finally {
        setCountBusy(false)
      }
    },
    [token, count, countBusy, load, onError, onCountPosted],
  )

  const closeCount = useCallback(() => {
    setCount(null)
    setCountTarget(null)
  }, [])

  return {
    move,
    printCell,
    count,
    countTarget,
    countBusy,
    openInventory,
    saveCount,
    markEmpty,
    postAndClose,
    closeCount,
  }
}
