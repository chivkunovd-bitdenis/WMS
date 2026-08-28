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
import { PickSourceDialog } from './PickSourceDialog'
import {
  DOCUMENT,
  OBJECTS,
  PICK_CELLS,
  PLAN,
  PRODUCTS,
  SELLER,
  STOCK,
  cellRef,
  objRef,
} from './pickStub'
import {
  isInside,
  pickKey,
  placeLabel,
  placesUnder,
  rowsOf,
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
// Переключателя «списать с ячейки / с короба / с палеты» здесь намеренно нет.
// Кладовщик подошёл, увидел штрихкод и пикнул его — что это было, разбирает
// экран (канон R-26: сканер тупой, решает экран). Выбор руками появляется
// только там, где выбор действительно есть: когда один и тот же товар лежит в
// нескольких местах внутри того, что пикнули.

type PickOp = { productId: string; placeKey: string; qty: number }

export function UnloadPickScreen({ onNote }: { onNote: (note: string) => void }) {
  const [picked, setPicked] = useState<PickedMap>({})
  const [history, setHistory] = useState<PickOp[]>([])
  const [source, setSource] = useState<string | null>(null)
  const [scanValue, setScanValue] = useState('')
  const [scanError, setScanError] = useState<string | null>(null)
  const [scanNotice, setScanNotice] = useState<string | null>(null)
  const [asking, setAsking] = useState<{ row: PickRow; places: PickPlace[] } | null>(null)

  const rows = rowsOf(PLAN, STOCK, OBJECTS, PICK_CELLS, picked)
  const planQty = rows.reduce((sum, row) => sum + row.plan, 0)
  const pickedQty = rows.reduce((sum, row) => sum + Math.min(row.picked, row.plan), 0)
  const leftQty = planQty - pickedQty
  const sourceText = source ? placeLabel(source, OBJECTS, PICK_CELLS) : null

  function take(row: PickRow, place: PickPlace, qty: number) {
    const key = pickKey(row.product.id, place.key)
    setPicked((current) => ({ ...current, [key]: (current[key] ?? 0) + qty }))
    setHistory((current) => [...current, { productId: row.product.id, placeKey: place.key, qty }])
    setScanError(null)
    setScanNotice(`${row.product.sku}: снято ${qty} шт — ${place.label}`)
    onNote(`Заглушка: ${row.product.sku}, снято ${qty} шт — ${place.label}`)
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

  /** Кнопка в строке: место выбирается руками и количество вводится числом. */
  function askFor(row: PickRow) {
    setAsking({ row, places: row.places.filter((place) => place.left > 0) })
  }

  function handleScan(code: string) {
    setScanValue('')
    const cell = PICK_CELLS.find(
      (one) => one.barcode === code || one.code.toLowerCase() === code.toLowerCase(),
    )
    if (cell) {
      setSource(cellRef(cell.id))
      setScanError(null)
      setScanNotice(`Ячейка ${cell.code} — пикните товар, который снимаете`)
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
      take(row, found[0], 1)
      return
    }
    setScanNotice(null)
    setAsking({ row, places: found })
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
      render: (row) => <TextCell value={row.product.name} />,
    },
    {
      // Ключевая колонка экрана. Не список ячеек, а список мест сверху вниз:
      // адрес читается целиком одной строкой, и «палета без ячейки» стоит в том
      // же списке, что и полка, — снимают с неё точно так же.
      key: 'places',
      header: 'Где лежит',
      render: (row) => {
        if (row.places.length === 0) {
          return (
            <Typography variant="body2" color="text.secondary">
              Нет на складе — снимать нечего
            </Typography>
          )
        }
        return (
          <Stack spacing={0.25} data-testid={`pick-places-${row.product.id}`}>
            {row.places.map((place) => {
              const inSource = Boolean(source && isInside(place.holder, source, OBJECTS))
              return (
                <Stack
                  key={place.key}
                  direction="row"
                  spacing={0.75}
                  sx={{ alignItems: 'baseline', whiteSpace: 'nowrap' }}
                >
                  <Typography variant="body2" sx={{ fontWeight: inSource ? 700 : 400 }}>
                    {place.label}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    — {place.left} шт
                    {place.picked > 0 ? ` · снято ${place.picked}` : ''}
                  </Typography>
                </Stack>
              )
            })}
          </Stack>
        )
      },
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
      render: (row) => (
        <Stack direction="row" spacing={0.5} sx={{ justifyContent: 'flex-end', alignItems: 'center' }}>
          {row.picked > 0 ? (
            <IconAction
              title={`Отменить последнее снятие: ${row.product.sku}`}
              onClick={() => undoLast(row)}
              testId={`pick-undo-${row.product.id}`}
            >
              <UndoOutlined fontSize="small" />
            </IconAction>
          ) : null}
          <PrimaryAction
            onClick={() => askFor(row)}
            disabledReason={
              row.left === 0
                ? 'По плану уже всё снято'
                : row.places.every((place) => place.left === 0)
                  ? 'Этого товара нет на складе'
                  : undefined
            }
            data-testid={`pick-take-${row.product.id}`}
          >
            Снять
          </PrimaryAction>
        </Stack>
      ),
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

      <PickSourceDialog
        open={asking !== null}
        productName={asking ? asking.row.product.name : ''}
        planLeft={asking ? asking.row.left : 0}
        places={asking ? asking.places : []}
        onClose={() => setAsking(null)}
        onConfirm={(placeKey, qty) => {
          if (!asking) return
          const place = asking.places.find((one) => one.key === placeKey)
          if (place) take(asking.row, place, qty)
          setAsking(null)
        }}
      />
    </Box>
  )
}
