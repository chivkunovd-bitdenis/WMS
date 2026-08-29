import { Box, LinearProgress, Paper, Stack, Typography } from '@mui/material'
import { useEffect, useRef, useState } from 'react'
import CloseOutlined from '@mui/icons-material/CloseOutlined'
import UndoOutlined from '@mui/icons-material/UndoOutlined'
import {
  ActionGroup,
  DataTable,
  IconAction,
  PrimaryAction,
  ProductCell,
  QtyCell,
  ScannerField,
  ScreenHeader,
  SecondaryAction,
  TextCell,
} from '../../../ui-kit'
import type { Column } from '../../../ui-kit'
import { ProductPhotoThumb } from '../../../components/ProductPhotoThumb'
import { PickPlacesTree } from './PickPlacesTree'
import {
  DOCUMENT,
  OBJECTS,
  PICK_CELLS,
  PLAN,
  PRODUCTS,
  SELLER,
  cellRef,
  objRef,
} from './pickStub'
import {
  ALL_STOCK,
  pickKey,
  placeLabel,
  placesUnder,
  rowsOf,
  rowsWithin,
  type PickPlace,
  type PickRow,
  type PickedMap,
} from './pickRows'
import type {
  Cell,
  GoodsLine,
  PickProduct,
  PlanLine,
  WarehouseObject,
} from './pickStub'

// Подбор на отгрузку.
//
// Товар снимается не «с ячейки», а с того объекта, где он реально лежит: с
// палеты, из короба, из грузоместа или прямо с ячейки, если он лежит там
// россыпью. Ячейка при этом никуда не девается — она просто верхнее слово в
// адресе места. Если у палеты или короба ячейки нет, снимается точно так же:
// объект стоит без ячейки, и это нормальное состояние склада, а не ошибка.
//
// Раскрывашка товара отвечает на вопрос «откуда снимаем» сама — постоянно и
// на месте (§6 контракта 20260828). Диалога «Откуда снимаем» на этом экране
// больше нет: то же самое поле количества, что и раньше открывалось окном,
// теперь стоит прямо в строке места.

type PickOp = { productId: string; placeKey: string; qty: number }

export type UnloadPickScanResult =
  | {
      kind: 'location'
      storageLocationId: string
      locationCode: string
    }
  | {
      kind: 'product'
      storageLocationId: string | null
      productId: string
      sku: string
      productName: string
      pickedQty: number
      allocationQuantity: number
    }

type UnloadPickScreenProps = {
  onNote: (note: string) => void
  document?: string
  seller?: string
  products?: PickProduct[]
  plan?: PlanLine[]
  stock?: GoodsLine[]
  objects?: WarehouseObject[]
  cells?: Cell[]
  initialPicked?: PickedMap
  busy?: boolean
  onSetPicked?: (payload: {
    productId: string
    place: PickPlace
    quantity: number
  }) => void | Promise<void>
  onScan?: (payload: {
    barcode: string
    sourceKey: string | null
  }) => Promise<UnloadPickScanResult>
  onPause?: () => void
  onComplete?: () => void
}

/** «В 3 местах», «В 1 месте», «Нет на складе» — колонка «Где лежит» (§2). */
function placesCountLabel(count: number): string {
  if (count === 0) return 'Нет на складе'
  return count === 1 ? 'В 1 месте' : `В ${count} местах`
}

export function UnloadPickScreen({
  onNote,
  document: documentProp,
  seller: sellerProp,
  products: productsProp,
  plan: planProp,
  stock: stockProp,
  objects: objectsProp,
  cells: cellsProp,
  initialPicked,
  busy = false,
  onSetPicked,
  onScan,
  onPause,
  onComplete,
}: UnloadPickScreenProps) {
  const document = documentProp ?? DOCUMENT
  const seller = sellerProp ?? SELLER
  const products = productsProp ?? PRODUCTS
  const plan = planProp ?? PLAN
  const stock = stockProp ?? ALL_STOCK
  const objects = objectsProp ?? OBJECTS
  const cells = cellsProp ?? PICK_CELLS
  const [picked, setPicked] = useState<PickedMap>(() => ({ ...(initialPicked ?? {}) }))
  const [history, setHistory] = useState<PickOp[]>([])
  const [source, setSource] = useState<string | null>(null)
  const [sourceLabel, setSourceLabel] = useState<string | null>(null)
  const [scanValue, setScanValue] = useState('')
  const [scanError, setScanError] = useState<string | null>(null)
  const [scanNotice, setScanNotice] = useState<string | null>(null)
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())
  // Ручной ввод в поле места копится здесь, ключ — товар+место (§Ж-01, §Е-06).
  // Списывается всё равно сразу и без «Провести»: значение видно в поле и в
  // счётчике мгновенно, а на сервер уходит после паузы в наборе, а не на
  // каждую цифру — иначе сканер, стреляющий «12» одним залпом, довозил бы
  // только первую цифру.
  const pendingSetPicked = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  useEffect(() => {
    const timers = pendingSetPicked.current
    return () => {
      timers.forEach((timer) => clearTimeout(timer))
      timers.clear()
    }
  }, [])

  const rows = rowsOf(plan, stock, objects, cells, picked, products)
  const planQty = rows.reduce((sum, row) => sum + row.plan, 0)
  const pickedQty = rows.reduce((sum, row) => sum + Math.min(row.picked, row.plan), 0)
  const leftQty = planQty - pickedQty
  const sourceText = source ? (sourceLabel ?? placeLabel(source, objects, cells)) : null

  function expandRow(rowKey: string) {
    setExpandedIds((current) => (current.has(rowKey) ? current : new Set(current).add(rowKey)))
  }

  function expandRows(rowKeys: string[]) {
    setExpandedIds((current) => {
      const next = new Set(current)
      rowKeys.forEach((key) => next.add(key))
      return next
    })
  }

  function toggleRow(rowKey: string) {
    setExpandedIds((current) => {
      const next = new Set(current)
      if (next.has(rowKey)) next.delete(rowKey)
      else next.add(rowKey)
      return next
    })
  }

  /**
   * Единственный способ поменять «снято»: и сканер (+1), и рука в поле места
   * зовут эту же функцию — экран не решает разными путями одно и то же
   * (контракт §4, §5).
   */
  function applyDelta(
    row: PickRow,
    place: PickPlace,
    delta: number,
    // Подсказку сканера меняет только сам сканер. Поле сканера возвращает себе
    // фокус на каждое изменение подсказки — это правильно, когда пикают, и
    // невыносимо, когда вписывают число рукой: курсор выбрасывало из поля на
    // первой же цифре.
    { fromScan = true }: { fromScan?: boolean } = {},
  ) {
    if (delta === 0) return
    const key = pickKey(row.product.id, place.key)
    const nextQuantity = Math.max(0, place.picked + delta)
    setPicked((current) => ({ ...current, [key]: nextQuantity }))
    if (fromScan) {
      // Скан — одно движение, один запрос: отправляем сразу же, как и раньше.
      void onSetPicked?.({ productId: row.product.id, place, quantity: nextQuantity })
    } else {
      // Рука в поле места печатает цифру за цифрой: запрос ждёт паузы в
      // наборе, чтобы поле не дёргалось disabled↔enabled на каждый символ —
      // именно это снятие фокуса и съедало вторую цифру.
      const timers = pendingSetPicked.current
      const existing = timers.get(key)
      if (existing) clearTimeout(existing)
      const timer = setTimeout(() => {
        timers.delete(key)
        void onSetPicked?.({ productId: row.product.id, place, quantity: nextQuantity })
      }, 400)
      timers.set(key, timer)
    }
    setScanError(null)
    if (delta > 0) {
      // Только снятие ложится в историю отмены: ручное уменьшение — это уже
      // сама по себе поправка оператора, отменять поправку поправкой незачем.
      setHistory((current) => [...current, { productId: row.product.id, placeKey: place.key, qty: delta }])
      if (fromScan) setScanNotice(`${row.product.sku}: снято ${delta} шт — ${place.label}`)
      onNote(`${row.product.sku}: снято ${delta} шт — ${place.label}`)
    } else {
      if (fromScan) setScanNotice(`${row.product.sku}: возврат ${Math.abs(delta)} шт — ${place.label}`)
      onNote(`${row.product.sku}: возврат ${Math.abs(delta)} шт — ${place.label}`)
    }
  }

  /** Поле места — сразу факт: новое значение и есть снятое количество. */
  function handlePlaceQtyChange(row: PickRow, place: PickPlace, next: number | null) {
    applyDelta(row, place, (next ?? 0) - place.picked, { fromScan: false })
  }

  /**
   * Отмена последнего снятия по этому товару.
   *
   * Списание физическое: товар уехал с полки в отгрузку, и ошибиться числом
   * здесь стоит дороже, чем в любом справочнике. Поэтому обратный ход есть, но
   * он именно обратный ход, а не «поправить цифру»: снятое возвращается ровно
   * в то место, откуда его сняли.
   */
  function undoLast(row: PickRow) {
    const index = history.map((one) => one.productId).lastIndexOf(row.product.id)
    if (index < 0) return
    const operation = history[index]
    const key = pickKey(operation.productId, operation.placeKey)
    const place = row.places.find((one) => one.key === operation.placeKey)
    if (!place) return
    const nextQuantity = Math.max(0, place.picked - operation.qty)
    setPicked((current) => ({ ...current, [key]: nextQuantity }))
    void onSetPicked?.({ productId: row.product.id, place, quantity: nextQuantity })
    setHistory((current) => current.filter((_, position) => position !== index))
    setScanNotice(`${row.product.sku}: снятие ${operation.qty} шт отменено`)
    onNote(`Возврат ${operation.qty} шт — ${place.label}`)
  }

  async function handleServerScan(code: string) {
    if (!onScan) return false
    try {
      const result = await onScan({ barcode: code, sourceKey: source })
      if (result.kind === 'location') {
        const reference = cellRef(result.storageLocationId)
        setSource(reference)
        setSourceLabel(result.locationCode)
        setScanError(null)
        setScanNotice(`Ячейка ${result.locationCode} — пикните товар, который снимаете`)
        expandRows(rowsWithin(rows, reference, objects).map((one) => one.key))
        return true
      }

      const row = rows.find((one) => one.product.id === result.productId)
      if (!row) {
        setScanNotice(null)
        setScanError(`${result.sku} нет в плане этой отгрузки`)
        return true
      }
      // Сужение по свойству не доживает до колбэка: держим ячейку отдельной
      // переменной, иначе TypeScript видит внутри find снова «строка или пусто».
      const scannedLocationId = result.storageLocationId
      const place = scannedLocationId
        ? row.places.find((one) => one.key === cellRef(scannedLocationId))
        : row.places[0]
      if (!place) {
        setScanNotice(null)
        setScanError(`${result.sku} — сервер не вернул место снятия`)
        return true
      }
      const previous = place.picked
      const key = pickKey(result.productId, place.key)
      setPicked((current) => ({ ...current, [key]: result.allocationQuantity }))
      const added = Math.max(0, result.allocationQuantity - previous)
      if (added > 0) {
        setHistory((current) => [
          ...current,
          { productId: result.productId, placeKey: place.key, qty: added },
        ])
      }
      expandRow(row.key)
      setScanError(null)
      setScanNotice(`${result.sku}: снято ${added || 1} шт — ${place.label}`)
      onNote(`${result.sku}: снято ${added || 1} шт — ${place.label}`)
      return true
    } catch (err) {
      setScanNotice(null)
      setScanError(err instanceof Error ? err.message : 'Не удалось выполнить скан')
      return true
    }
  }

  async function handleScan(code: string) {
    setScanValue('')
    if (await handleServerScan(code)) return

    const cell = cells.find(
      (one) => one.barcode === code || one.code.toLowerCase() === code.toLowerCase(),
    )
    if (cell) {
      const reference = cellRef(cell.id)
      setSource(reference)
      setSourceLabel(cell.code)
      setScanError(null)
      setScanNotice(`Ячейка ${cell.code} — пикните товар, который снимаете`)
      expandRows(rowsWithin(rows, reference, objects).map((one) => one.key))
      return
    }
    const object = objects.find(
      (one) => one.barcode === code || one.code.toLowerCase() === code.toLowerCase(),
    )
    if (object) {
      const reference = objRef(object.id)
      setSource(reference)
      setSourceLabel(placeLabel(reference, objects, cells))
      setScanError(null)
      setScanNotice(`${placeLabel(reference, objects, cells)} — пикните товар`)
      expandRows(rowsWithin(rows, reference, objects).map((one) => one.key))
      return
    }
    const product = products.find(
      (one) => one.barcode === code || one.sku.toLowerCase() === code.toLowerCase(),
    )
    if (!product) {
      setScanNotice(null)
      setScanError(`Штрихкод ${code} — ни место, ни товар этой отгрузки`)
      return
    }
    const row = rows.find((one) => one.product.id === product.id)
    if (!row) {
      setScanNotice(null)
      setScanError(`${product.sku} нет в плане этой отгрузки`)
      return
    }
    if (row.left === 0) {
      setScanNotice(null)
      setScanError(`${product.sku} — по плану уже всё снято`)
      return
    }
    const found = placesUnder(row.places, source, objects)
    if (found.length === 0) {
      setScanNotice(null)
      setScanError(
        sourceText
          ? `${product.sku} не лежит в ${sourceText}`
          : `${product.sku} — этого товара нет на складе`,
      )
      return
    }
    // Одно место — вопрос не задаём: спрашивать «откуда», когда ответ один,
    // значит тратить движение кладовщика на подтверждение очевидного.
    if (found.length === 1) {
      expandRow(row.key)
      applyDelta(row, found[0], 1)
      return
    }
    // Мест-кандидатов несколько — экран не выбирает за оператора (ДЫРА → R-38):
    // ничего не списывается, раскрывашка открыта, чтобы было видно кандидатов.
    expandRow(row.key)
    setScanNotice(null)
    setScanError(
      `${product.sku} лежит в ${found.length} местах внутри ${sourceText ?? 'склада'} — уточните место или укажите число руками`,
    )
  }

  const columns: Column<PickRow>[] = [
    {
      key: 'product',
      header: 'Товар',
      render: (row) => (
        <ProductCell
          photo={<ProductPhotoThumb src={row.product.photo} alt={row.product.name} size={32} />}
          sku={row.product.sku}
        />
      ),
    },
    {
      key: 'name',
      header: 'Наименование',
      render: (row) => (
        <Stack sx={{ minWidth: 0 }}>
          <TextCell value={row.product.name} />
          {/* Штрихкод товара подписью, а не колонкой: своей колонкой он на 1280
              выдавливал «Осталось» за край экрана. */}
          <Typography
            variant="caption"
            sx={{
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
              color: 'text.secondary',
            }}
          >
            {row.product.barcode}
          </Typography>
        </Stack>
      ),
    },
    {
      key: 'size',
      header: 'Размер',
      width: 72,
      render: (row) =>
        row.product.size ? (
          <Typography variant="body2" sx={{ whiteSpace: 'nowrap' }}>
            {row.product.size}
          </Typography>
        ) : null,
    },
    {
      key: 'places',
      header: 'Где лежит',
      render: (row) => <TextCell value={placesCountLabel(row.places.length)} />,
    },
    {
      key: 'plan',
      header: 'План',
      align: 'right',
      width: 72,
      render: (row) => <QtyCell value={row.plan} muted />,
    },
    {
      key: 'picked',
      header: 'Снято',
      align: 'right',
      width: 72,
      render: (row) => <QtyCell value={row.picked} />,
    },
    {
      key: 'left',
      header: 'Осталось',
      align: 'right',
      width: 88,
      render: (row) => <QtyCell value={row.left} muted={row.left === 0} />,
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      render: (row) =>
        row.picked > 0 ? (
          <Stack direction="row" sx={{ justifyContent: 'flex-end' }}>
            <IconAction
              title={`Отменить последнее снятие: ${row.product.sku}`}
              onClick={() => undoLast(row)}
              testId={`pick-undo-${row.product.id}`}
            >
              <UndoOutlined fontSize="small" />
            </IconAction>
          </Stack>
        ) : null,
    },
  ]

  return (
    <Box data-testid="unload-pick-screen">
      <ScreenHeader
        title="Подбор на отгрузку"
        purpose={`${document}. Продавец ${seller}. Снимаем товар с ячеек, палет, коробов и грузомест.`}
      />

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack spacing={1.5}>
          <ScannerField
            value={scanValue}
            onChange={(value) => {
              setScanValue(value)
              setScanError(null)
            }}
            onScan={handleScan}
            expects={source ? 'товар, который снимаете' : 'место или товар'}
            busy={busy}
            error={scanError}
            notice={scanNotice}
            testId="pick-scan"
          />
          {sourceText ? (
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
              <Typography variant="body2" color="text.secondary">
                Снимаем с:
              </Typography>
              <Typography variant="body2" sx={{ fontWeight: 700 }} data-testid="pick-source">
                {sourceText}
              </Typography>
              <IconAction
                title="Забыть место — искать товар по всему складу"
                onClick={() => {
                  setSource(null)
                  setSourceLabel(null)
                  setScanNotice(null)
                }}
                testId="pick-source-clear"
              >
                <CloseOutlined fontSize="small" />
              </IconAction>
            </Stack>
          ) : (
            <Typography variant="body2" color="text.secondary">
              Место не выбрано. Можно сразу пикнуть товар — экран сам найдёт, где он лежит, и
              спросит только если мест несколько.
            </Typography>
          )}
        </Stack>
      </Paper>

      <Stack spacing={1} sx={{ mb: 1.5 }}>
        <Stack direction="row" spacing={2} sx={{ alignItems: 'baseline' }}>
          <Typography variant="h5" data-testid="pick-left-qty">
            {leftQty.toLocaleString('ru-RU')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            штук осталось снять из {planQty.toLocaleString('ru-RU')} по плану отгрузки
          </Typography>
        </Stack>
        <LinearProgress
          variant="determinate"
          value={planQty === 0 ? 0 : (pickedQty / planQty) * 100}
          sx={{ height: 8, borderRadius: 4 }}
        />
      </Stack>

      <DataTable
        columns={columns}
        rows={rows}
        getRowKey={(row) => row.key}
        // Собранная строка гаснет зелёным: оператор ведёт глазом по столбцу и
        // видит, где ещё работа. Скорректировал вниз — подсветка уходит сама.
        isComplete={(row) => row.plan > 0 && row.left === 0}
        testId="pick-table"
        empty={{
          title: 'В отгрузке нет товаров',
          hint: 'Добавьте товары в план отгрузки — снимать пока нечего.',
        }}
        expand={{
          isExpanded: (row) => expandedIds.has(row.key),
          onToggle: (row) => toggleRow(row.key),
          label: (row) => `Показать места товара ${row.product.sku}`,
          render: (row) => (
            <PickPlacesTree
              row={row}
              highlightedKey={source}
              onQtyChange={(place, next) => handlePlaceQtyChange(row, place, next)}
              objects={objects}
              cells={cells}
            />
          ),
        }}
      />

      <Stack direction="row" sx={{ mt: 2, justifyContent: 'flex-end' }}>
        <ActionGroup>
          <SecondaryAction
            onClick={() => {
              onNote('Подбор отложен')
              onPause?.()
            }}
            disabled={busy}
            data-testid="pick-pause"
          >
            Отложить
          </SecondaryAction>
          <PrimaryAction
            onClick={() => {
              onNote('Подбор завершён')
              onComplete?.()
            }}
            disabledReason={
              busy
                ? 'Сохраняем последнее снятие'
                : leftQty > 0
                  ? 'Собран не весь план отгрузки'
                  : undefined
            }
            data-testid="pick-complete"
          >
            Завершить подбор
          </PrimaryAction>
        </ActionGroup>
      </Stack>
    </Box>
  )
}
