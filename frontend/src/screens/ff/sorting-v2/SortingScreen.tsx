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
import { SortingCellPicker } from './SortingCellPicker'
import { SortingPlacePanel } from './SortingPlacePanel'
import {
  CELLS,
  INITIAL_CONTAINERS,
  PRODUCTS,
  canDropInto,
  findByBarcode,
  remainingFor,
  totalAccepted,
  totalRemaining,
  type Carried,
  type Container,
  type ContainerKind,
  type PlaceRef,
  type Placement,
  type SortProduct,
} from './sortingStub'

// Раскладка по ячейкам, собранная от места, а не от товара.
//
// Сегодня экран устроен наоборот: стопка карточек по одной на товар, и в каждой
// выпадающий список из всех ячеек склада. На приёмке в тридцать позиций это
// тридцать карточек и тридцать раз пролистать двести ячеек. Кладовщик работает
// не так: он подходит к полке и кладёт туда то, что принёс. Единица работы —
// место: ячейка, палета на ней или короб внутри.


export function SortingScreen({ onNote }: { onNote: (note: string) => void }) {
  const [placements, setPlacements] = useState<Placement[]>([])
  const [containers, setContainers] = useState<Container[]>(INITIAL_CONTAINERS)
  const [path, setPath] = useState<PlaceRef[]>([])
  const [scanValue, setScanValue] = useState('')
  const [scanError, setScanError] = useState<string | null>(null)
  const [scanNotice, setScanNotice] = useState<string | null>(null)
  const [carried, setCarried] = useState<Carried | null>(null)
  const [asking, setAsking] = useState<SortProduct | null>(null)
  const [askQty, setAskQty] = useState<number | null>(null)
  // Счётчик номеров живёт в состоянии: переменная вне компонента менялась бы
  // во время отрисовки, а это побочный эффект и непредсказуемый порядок.
  const [created, setCreated] = useState(0)
  // Куда положим то, о чём спрашиваем: перетащили на одно место, а активно другое.
  const [askPlace, setAskPlace] = useState<PlaceRef | null>(null)
  const [recent, setRecent] = useState<string[]>([])

  const place = path.length > 0 ? path[path.length - 1]! : null
  const cell = path.length > 0 ? (CELLS.find((one) => one.id === path[0]!.id) ?? null) : null
  const left = totalRemaining(PRODUCTS, placements)
  const accepted = totalAccepted(PRODUCTS)

  function put(product: SortProduct, qty: number, placeId: string) {
    const capped = Math.min(qty, remainingFor(product, placements))
    if (capped <= 0) return
    setPlacements((current) => {
      const twin = current.find((one) => one.productId === product.id && one.cellId === placeId)
      if (twin) return current.map((one) => (one === twin ? { ...one, qty: one.qty + capped } : one))
      return [...current, { productId: product.id, cellId: placeId, qty: capped }]
    })
    setRecent((current) => (current.includes(placeId) ? current : [placeId, ...current].slice(0, 8)))
  }

  function pickCell(cellId: string) {
    const target = CELLS.find((one) => one.id === cellId)
    if (!target) return
    const ref: PlaceRef = { id: target.id, code: target.code, kind: 'cell' }
    setPath([ref])
    if (carried) dropOnto(ref)
  }

  function dropOnto(target: PlaceRef) {
    if (!carried) return
    if (!canDropInto(carried, target, containers)) {
      setCarried(null)
      return
    }
    if (carried.kind === 'product') {
      // Количество спрашиваем всегда: перетащить — не значит «высыпать всё».
      // Столько же раз, сколько кладут коробку целиком, кладут и её половину.
      setAsking(carried.product)
      setAskQty(remainingFor(carried.product, placements))
      setAskPlace(target)
    } else {
      const moving = carried.container
      setContainers((current) =>
        current.map((one) => (one.id === moving.id ? { ...one, parentId: target.id } : one)),
      )
      onNote(`${moving.kind === 'pallet' ? 'Палета' : 'Короб'} ${moving.code} → ${target.code}`)
    }
    setCarried(null)
  }

  function nextNumber() {
    const value = created + 1
    setCreated(value)
    return value
  }

  function createContainer(kind: ContainerKind) {
    if (!place) return
    const created = nextNumber()
    const container: Container = {
      id: `new-${kind}-${created}`,
      kind,
      code: kind === 'pallet' ? `П-${String(200 + created).padStart(6, '0')}` : `КР-${String(500 + created).padStart(6, '0')}`,
      parentId: place.id,
    }
    setContainers((current) => [...current, container])
    onNote(`Заглушка: создан ${kind === 'pallet' ? 'палета' : 'короб'} ${container.code} в ${place.code}`)
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
      const target = CELLS.find((one) => one.id === hit.id)!
      setPath([{ id: target.id, code: target.code, kind: 'cell' }])
      setScanError(null)
      setScanNotice(`Ячейка ${target.code} — кладите товар`)
      return
    }
    if (!place) {
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
    put(product, 1, place.id)
    setScanError(null)
    setScanNotice(`${product.name} → ${place.code}, +1`)
  }

  function changeQty(productId: string, qty: number) {
    if (!place) return
    setPlacements((current) =>
      qty <= 0
        ? current.filter((one) => !(one.productId === productId && one.cellId === place.id))
        : current.map((one) =>
            one.productId === productId && one.cellId === place.id ? { ...one, qty } : one,
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
            expects={place ? 'товар или другую ячейку' : 'ячейку с полки'}
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
          </Stack>
        </Stack>
      </Paper>

      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} sx={{ alignItems: 'flex-start' }}>
        <Box sx={{ flexGrow: 1, minWidth: 0, width: '100%' }}>
          <SortingRemaining
            products={PRODUCTS}
            placements={placements}
            activeCell={place ? { id: place.id, code: place.code, barcode: '', occupied: [] } : null}
            onPlaceAll={(product) => {
              setAsking(product)
              setAskQty(remainingFor(product, placements))
              setAskPlace(place)
            }}
            onPickCell={pickCell}
            onDragProduct={(product) => setCarried({ kind: 'product', product })}
            onDragEnd={() => setCarried(null)}
          />
        </Box>
        <Stack spacing={2} sx={{ width: { lg: 460 }, flexShrink: 0, minWidth: 0 }}>
          <SortingCellPicker
            cells={CELLS}
            activeCellId={path[0]?.id ?? null}
            suggestedIds={[]}
            recentIds={recent}
            carried={carried !== null}
            onPick={pickCell}
            onCreateCell={() => onNote('Заглушка: та же модалка создания ячейки, что на карте склада')}
          />
          <SortingPlacePanel
            cell={cell}
            path={path}
            place={place}
            containers={containers}
            placements={placements}
            products={PRODUCTS}
            carried={carried}
            onEnter={(next) => setPath((current) => [...current, next])}
            onLeaveTo={(index) => setPath((current) => current.slice(0, index + 1))}
            onCreate={createContainer}
            onChangeQty={changeQty}
            onRemove={(productId) => changeQty(productId, 0)}
            onDropHere={dropOnto}
            onDragContainer={(container) => setCarried({ kind: 'container', container })}
            onDragEnd={() => setCarried(null)}
            onCommit={() => onNote(`Заглушка: ячейка ${path[0]?.code ?? ''} записана`)}
            onPrint={() => onNote(`Заглушка: печать ШК ячейки ${path[0]?.code ?? ''}`)}
          />
        </Stack>
      </Stack>

      <AppDialog
        open={asking !== null}
        onClose={() => {
          setAsking(null)
          setAskPlace(null)
        }}
        title="Сколько положить"
        testId="sorting-qty-dialog"
        actions={
          <ActionGroup>
            <SecondaryAction
              onClick={() => {
                setAsking(null)
                setAskPlace(null)
              }}
              data-testid="sorting-qty-cancel"
            >
              Отмена
            </SecondaryAction>
            <PrimaryAction
              onClick={() => {
                const target = askPlace ?? place
                if (asking && target && askQty) put(asking, askQty, target.id)
                setAsking(null)
                setAskPlace(null)
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
              Куда: {(askPlace ?? place)?.code ?? '—'}
            </Typography>
          </Stack>
          <NumberInput
            label="Сколько штук"
            value={askQty}
            onChange={setAskQty}
            min={1}
            max={asking ? remainingFor(asking, placements) : undefined}
            helperText={asking ? `Осталось разложить ${remainingFor(asking, placements)} шт` : undefined}
            testId="sorting-qty-input"
          />
        </Stack>
      </AppDialog>
    </Box>
  )
}
