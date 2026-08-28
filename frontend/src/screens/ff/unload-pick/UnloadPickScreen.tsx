import { Box, LinearProgress, Paper, Stack, Typography } from '@mui/material'
import { useState } from 'react'
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

/** «В 3 местах», «В 1 месте», «Нет на складе» — колонка «Где лежит» (§2). */
function placesCountLabel(count: number): string {
  if (count === 0) return 'Нет на складе'
  return count === 1 ? 'В 1 месте' : `В ${count} местах`
}

export function UnloadPickScreen({ onNote }: { onNote: (note: string) => void }) {
  const [picked, setPicked] = useState<PickedMap>({})
  const [history, setHistory] = useState<PickOp[]>([])
  const [source, setSource] = useState<string | null>(null)
  const [scanValue, setScanValue] = useState('')
  const [scanError, setScanError] = useState<string | null>(null)
  const [scanNotice, setScanNotice] = useState<string | null>(null)
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())

  const rows = rowsOf(PLAN, ALL_STOCK, OBJECTS, PICK_CELLS, picked)
  const planQty = rows.reduce((sum, row) => sum + row.plan, 0)
  const pickedQty = rows.reduce((sum, row) => sum + Math.min(row.picked, row.plan), 0)
  const leftQty = planQty - pickedQty
  const sourceText = source ? placeLabel(source, OBJECTS, PICK_CELLS) : null

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
    setPicked((current) => ({ ...current, [key]: Math.max(0, (current[key] ?? 0) + delta) }))
    setScanError(null)
    if (delta > 0) {
      // Только снятие ложится в историю отмены: ручное уменьшение — это уже
      // сама по себе поправка оператора, отменять поправку поправкой незачем.
      setHistory((current) => [...current, { productId: row.product.id, placeKey: place.key, qty: delta }])
      if (fromScan) setScanNotice(`${row.product.sku}: снято ${delta} шт — ${place.label}`)
      onNote(`Заглушка: ${row.product.sku}, снято ${delta} шт — ${place.label}`)
    } else {
      if (fromScan) setScanNotice(`${row.product.sku}: возврат ${Math.abs(delta)} шт — ${place.label}`)
      onNote(`Заглушка: возврат ${Math.abs(delta)} шт — ${place.label}`)
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
    setPicked((current) => ({ ...current, [key]: Math.max(0, (current[key] ?? 0) - operation.qty) }))
    setHistory((current) => current.filter((_, position) => position !== index))
    const place = row.places.find((one) => one.key === operation.placeKey)
    setScanNotice(`${row.product.sku}: снятие ${operation.qty} шт отменено`)
    onNote(`Заглушка: возврат ${operation.qty} шт — ${place?.label ?? 'место не найдено'}`)
  }

  function handleScan(code: string) {
    setScanValue('')
    const cell = PICK_CELLS.find(
      (one) => one.barcode === code || one.code.toLowerCase() === code.toLowerCase(),
    )
    if (cell) {
      const reference = cellRef(cell.id)
      setSource(reference)
      setScanError(null)
      setScanNotice(`Ячейка ${cell.code} — пикните товар, который снимаете`)
      expandRows(rowsWithin(rows, reference, OBJECTS).map((one) => one.key))
      return
    }
    const object = OBJECTS.find(
      (one) => one.barcode === code || one.code.toLowerCase() === code.toLowerCase(),
    )
    if (object) {
      const reference = objRef(object.id)
      setSource(reference)
      setScanError(null)
      setScanNotice(`${placeLabel(reference, OBJECTS, PICK_CELLS)} — пикните товар`)
      expandRows(rowsWithin(rows, reference, OBJECTS).map((one) => one.key))
      return
    }
    const product = PRODUCTS.find(
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
    const found = placesUnder(row.places, source, OBJECTS)
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
        purpose={`${DOCUMENT}. Продавец ${SELLER}. Снимаем товар с ячеек, палет, коробов и грузомест.`}
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
            />
          ),
        }}
      />

      <Stack direction="row" sx={{ mt: 2, justifyContent: 'flex-end' }}>
        <ActionGroup>
          <SecondaryAction onClick={() => onNote('Заглушка: подбор отложен')} data-testid="pick-pause">
            Отложить
          </SecondaryAction>
          <PrimaryAction
            onClick={() => onNote('Заглушка: подбор завершён')}
            disabledReason={leftQty > 0 ? 'Собран не весь план отгрузки' : undefined}
            data-testid="pick-complete"
          >
            Завершить подбор
          </PrimaryAction>
        </ActionGroup>
      </Stack>
    </Box>
  )
}
