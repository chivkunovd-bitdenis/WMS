import { Box, Paper, Stack, Typography } from '@mui/material'
import { useState } from 'react'
import {
  ActionGroup,
  AppDialog,
  NumberInput,
  PrimaryAction,
  ScannerField,
  ScreenHeader,
  SecondaryAction,
  StatusChip,
} from '../../../ui-kit'
import { SortingRemaining } from './SortingRemaining'
import { SortingCellPanel } from './SortingCellPanel'
import {
  CELLS,
  PRODUCTS,
  findByBarcode,
  remainingFor,
  totalAccepted,
  totalRemaining,
  type Placement,
  type SortProduct,
} from './sortingStub'

// Раскладка по ячейкам, собранная от ячейки, а не от товара.
//
// Сегодня экран устроен наоборот: стопка карточек по одной на товар, и в каждой
// выпадающий список из всех ячеек склада. На приёмке в тридцать позиций это
// тридцать карточек и тридцать раз пролистать двести ячеек. А кладовщик работает
// не так: он подходит к полке и кладёт туда то, что принёс. Здесь единица работы
// — ячейка: выбрал её один раз, сложил в неё всё, что к ней относится, записал.

export function SortingScreen({ onNote }: { onNote: (note: string) => void }) {
  const [placements, setPlacements] = useState<Placement[]>([])
  const [activeCellId, setActiveCellId] = useState<string | null>(null)
  const [scanValue, setScanValue] = useState('')
  const [scanError, setScanError] = useState<string | null>(null)
  const [scanNotice, setScanNotice] = useState<string | null>(null)
  const [carried, setCarried] = useState<SortProduct | null>(null)
  const [asking, setAsking] = useState<SortProduct | null>(null)
  const [askQty, setAskQty] = useState<number | null>(null)
  const [committed, setCommitted] = useState<string[]>([])

  const activeCell = CELLS.find((cell) => cell.id === activeCellId) ?? null
  const left = totalRemaining(PRODUCTS, placements)
  const accepted = totalAccepted(PRODUCTS)

  function put(product: SortProduct, qty: number, cellId: string) {
    const capped = Math.min(qty, remainingFor(product, placements))
    if (capped <= 0) return
    setPlacements((current) => {
      const twin = current.find((one) => one.productId === product.id && one.cellId === cellId)
      if (twin) {
        return current.map((one) =>
          one === twin ? { ...one, qty: one.qty + capped } : one,
        )
      }
      return [...current, { productId: product.id, cellId, qty: capped }]
    })
  }

  function handleScan(code: string) {
    setScanValue('')
    const hit = findByBarcode(code)
    if (!hit) {
      setScanNotice(null)
      setScanError(`Штрихкод ${code} — ни ячейка, ни товар из этой приёмки`)
      return
    }
    if (hit.kind === 'cell') {
      const cell = CELLS.find((one) => one.id === hit.id)!
      setActiveCellId(cell.id)
      setScanError(null)
      setScanNotice(`Ячейка ${cell.code} — кладите товар`)
      return
    }
    // Товар без выбранной ячейки класть некуда, и молчать об этом нельзя:
    // оператор будет пикать дальше и решит, что всё уходит куда надо.
    if (!activeCell) {
      setScanNotice(null)
      setScanError('Сначала пикните ячейку — иначе непонятно, куда кладём')
      return
    }
    const product = PRODUCTS.find((one) => one.id === hit.id)!
    if (remainingFor(product, placements) <= 0) {
      setScanNotice(null)
      setScanError(`${product.name} уже разложен весь`)
      return
    }
    put(product, 1, activeCell.id)
    setScanError(null)
    setScanNotice(`${product.name} → ${activeCell.code}, +1`)
  }

  function changeQty(productId: string, qty: number) {
    if (!activeCell) return
    if (qty <= 0) {
      setPlacements((current) =>
        current.filter((one) => !(one.productId === productId && one.cellId === activeCell.id)),
      )
      return
    }
    setPlacements((current) =>
      current.map((one) =>
        one.productId === productId && one.cellId === activeCell.id ? { ...one, qty } : one,
      ),
    )
  }

  return (
    <Box data-testid="sorting-screen">
      <ScreenHeader
        title="Раскладка по ячейкам"
        purpose="Приёмка №1284 от 27.08.2026 · ИП Горячкина, ООО Ситипак, ИП Ларин"
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
            expects={activeCell ? 'товар или другую ячейку' : 'ячейку с полки'}
            error={scanError}
            notice={scanNotice}
            testId="sorting-scan"
          />
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
            <StatusChip
              label={left === 0 ? 'всё разложено' : `осталось ${left} шт`}
              tone={left === 0 ? 'ok' : 'warn'}
              testId="sorting-total-chip"
            />
            <Typography variant="body2" color="text.secondary">
              принято {accepted} шт
            </Typography>
            {committed.length > 0 ? (
              <Typography variant="body2" color="text.secondary">
                · записано ячеек: {committed.length}
              </Typography>
            ) : null}
          </Stack>
        </Stack>
      </Paper>

      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} sx={{ alignItems: 'flex-start' }}>
        <Box sx={{ flexGrow: 1, minWidth: 0, width: '100%' }}>
          <SortingRemaining
            products={PRODUCTS}
            placements={placements}
            activeCell={activeCell}
            onPlaceAll={(product) => {
              setAsking(product)
              setAskQty(remainingFor(product, placements))
            }}
            onPickCell={setActiveCellId}
            onDragProduct={setCarried}
            onDragEnd={() => setCarried(null)}
          />
        </Box>
        <Box sx={{ width: { lg: 440 }, flexShrink: 0, minWidth: 0 }}>
          <SortingCellPanel
            cells={CELLS}
            activeCell={activeCell}
            placements={placements}
            products={PRODUCTS}
            carried={carried}
            onPickCell={(cellId) => {
              setActiveCellId(cellId)
              if (carried) {
                put(carried, remainingFor(carried, placements), cellId)
                setCarried(null)
              }
            }}
            onChangeQty={changeQty}
            onRemove={(productId) => changeQty(productId, 0)}
            onCommit={() => {
              if (!activeCell) return
              setCommitted((current) =>
                current.includes(activeCell.id) ? current : [...current, activeCell.id],
              )
              onNote(`Заглушка: ячейка ${activeCell.code} записана — на сервер ничего не ушло`)
            }}
            onPrint={() =>
              onNote(`Заглушка: печать ШК ячейки ${activeCell?.code ?? ''} — принтера в макете нет`)
            }
            onCreateCell={() => onNote('Заглушка: тут откроется та же модалка создания ячейки, что на карте склада')}
          />
        </Box>
      </Stack>

      <AppDialog
        open={asking !== null}
        onClose={() => setAsking(null)}
        title="Сколько положить"
        testId="sorting-qty-dialog"
        actions={
          <ActionGroup>
            <SecondaryAction onClick={() => setAsking(null)} data-testid="sorting-qty-cancel">
              Отмена
            </SecondaryAction>
            <PrimaryAction
              onClick={() => {
                if (asking && activeCell && askQty) put(asking, askQty, activeCell.id)
                setAsking(null)
              }}
              data-testid="sorting-qty-confirm"
            >
              Положить
            </PrimaryAction>
          </ActionGroup>
        }
      >
        <Stack spacing={2}>
          <Stack spacing={0.5}>
            <Typography variant="subtitle2">{asking?.name}</Typography>
            <Typography variant="body2" color="text.secondary">
              Куда: {activeCell?.code ?? '—'}
            </Typography>
          </Stack>
          <NumberInput
            label="Сколько штук"
            value={askQty}
            onChange={setAskQty}
            min={1}
            max={asking ? remainingFor(asking, placements) : undefined}
            helperText={
              asking ? `Осталось разложить ${remainingFor(asking, placements)} шт` : undefined
            }
            testId="sorting-qty-input"
          />
        </Stack>
      </AppDialog>
    </Box>
  )
}
