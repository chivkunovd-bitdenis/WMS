import { Box, Stack, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material'
import ChevronLeft from '@mui/icons-material/ChevronLeft'
import ChevronRight from '@mui/icons-material/ChevronRight'
import { useMemo, useState } from 'react'
import {
  ActionGroup,
  AppDialog,
  CheckboxInput,
  FilterBar,
  NumberInput,
  IconAction,
  PrimaryAction,
  ScannerField,
  ScreenHeader,
  SecondaryAction,
  SelectInput,
  StatusChip,
} from '../../../ui-kit'
import { SortingRemaining } from './SortingRemaining'
import { SortingPlacePanel } from './SortingPlacePanel'
import { SortingCellPicker } from './SortingCellPicker'
import { SortingBulkDialog } from './SortingBulkDialog'
import { buildProposals } from './sortingProposals'
import { WAREHOUSES, bigCells, bigProducts } from './sortingBigStub'
import {
  INITIAL_CONTAINERS,
  canDropInto,
  remainingFor,
  type Carried,
  type Container,
  type ContainerKind,
  type PlaceRef,
  type Placement,
  type SortProduct,
} from './sortingStub'

// Тот же экран, но на настоящем объёме: три склада, сотни ячеек, две сотни строк.
// Всё, что здесь добавлено сверх маленького макета, добавлено не для красоты —
// каждый элемент отвечает на вопрос «а если их много».

const PAGE_SIZE = 25
const HOME = WAREHOUSES[0]!

export function SortingScaleScreen({ onNote }: { onNote: (note: string) => void }) {
  const homeCells = useMemo(() => bigCells(HOME.id), [])
  const products = useMemo(() => bigProducts(homeCells), [homeCells])

  const [warehouseId, setWarehouseId] = useState(HOME.id)
  const [placements, setPlacements] = useState<Placement[]>([])
  const [activeCellId, setActiveCellId] = useState<string | null>(null)
  const [scanValue, setScanValue] = useState('')
  const [scanError, setScanError] = useState<string | null>(null)
  const [scanNotice, setScanNotice] = useState<string | null>(null)
  const [carried, setCarried] = useState<Carried | null>(null)
  const [containers, setContainers] = useState<Container[]>(INITIAL_CONTAINERS)
  const [path, setPath] = useState<PlaceRef[]>([])
  const [recent, setRecent] = useState<string[]>([])
  const [bulkOpen, setBulkOpen] = useState(false)
  const [asking, setAsking] = useState<{ product: SortProduct; place: PlaceRef } | null>(null)
  const [askQty, setAskQty] = useState<number | null>(null)
  const [page, setPage] = useState(0)
  const [query, setQuery] = useState('')
  const [seller, setSeller] = useState('')
  const [source, setSource] = useState('')
  const [onlyLeft, setOnlyLeft] = useState(true)

  const cells = useMemo(
    () => (warehouseId === HOME.id ? homeCells : bigCells(warehouseId)),
    [homeCells, warehouseId],
  )
  const activeCell = cells.find((cell) => cell.id === activeCellId) ?? null
  const place = path.length > 0 ? path[path.length - 1]! : null
  const sellers = useMemo(() => [...new Set(products.map((one) => one.seller))].sort(), [products])
  const sources = useMemo(
    () => [...new Set(products.map((one) => one.source.label))].sort(),
    [products],
  )

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return products.filter((product) => {
      if (onlyLeft && remainingFor(product, placements) <= 0) return false
      if (seller && product.seller !== seller) return false
      if (source && product.source.label !== source) return false
      if (!needle) return true
      return [product.name, product.sku, product.barcode, product.seller].some((value) =>
        value.toLowerCase().includes(needle),
      )
    })
  }, [onlyLeft, placements, products, query, seller, source])

  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const current = Math.min(page, pages - 1)
  const shown = filtered.slice(current * PAGE_SIZE, current * PAGE_SIZE + PAGE_SIZE)

  const left = products.reduce((sum, product) => sum + remainingFor(product, placements), 0)
  const total = products.reduce((sum, product) => sum + product.accepted, 0)
  const linesLeft = products.filter((product) => remainingFor(product, placements) > 0).length

  const suggestedIds = useMemo(() => {
    const ids = new Set<string>()
    products.forEach((product) => {
      if (remainingFor(product, placements) <= 0) return
      product.alreadyAt.forEach((place) => {
        if (!place.warehouseId || place.warehouseId === warehouseId) ids.add(place.cellId)
      })
    })
    return [...ids].slice(0, 12)
  }, [placements, products, warehouseId])

  function put(product: SortProduct, qty: number, cellId: string) {
    const capped = Math.min(qty, remainingFor(product, placements))
    if (capped <= 0) return
    setPlacements((currentList) => {
      const twin = currentList.find((one) => one.productId === product.id && one.cellId === cellId)
      if (twin) return currentList.map((one) => (one === twin ? { ...one, qty: one.qty + capped } : one))
      return [...currentList, { productId: product.id, cellId, qty: capped }]
    })
    setRecent((currentList) =>
      currentList.includes(cellId) ? currentList : [cellId, ...currentList].slice(0, 8),
    )
  }

  function pickCell(cellId: string) {
    const target = cells.find((one) => one.id === cellId)
    if (!target) return
    setActiveCellId(cellId)
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
      setAsking({ product: carried.product, place: target })
    } else {
      const moving = carried.container
      setContainers((currentList) =>
        currentList.map((one) => (one.id === moving.id ? { ...one, parentId: target.id } : one)),
      )
    }
    setCarried(null)
  }

  function createContainer(kind: ContainerKind) {
    if (!place) return
    const id = `new-${kind}-${containers.length + 1}`
    setContainers((currentList) => [
      ...currentList,
      {
        id,
        kind,
        code: kind === 'pallet' ? `П-${300 + currentList.length}` : `КР-${600 + currentList.length}`,
        parentId: place.id,
      },
    ])
    onNote(`Заглушка: создан ${kind === 'pallet' ? 'палета' : 'короб'} в ${place.code}`)
  }

  function handleScan(code: string) {
    setScanValue('')
    const cell = cells.find((one) => one.barcode === code || one.code.toLowerCase() === code.toLowerCase())
    if (cell) {
      setActiveCellId(cell.id)
      setScanError(null)
      setScanNotice(`Ячейка ${cell.code} — кладите товар`)
      return
    }
    const product = products.find((one) => one.barcode === code || one.sku.toLowerCase() === code.toLowerCase())
    if (!product) {
      setScanNotice(null)
      setScanError(`Штрихкод ${code} — ни ячейка этого склада, ни товар из приёмки`)
      return
    }
    if (!activeCell) {
      setScanNotice(null)
      setScanError('Сначала пикните ячейку — иначе непонятно, куда кладём')
      return
    }
    if (remainingFor(product, placements) <= 0) {
      setScanNotice(null)
      setScanError(`${product.name} уже разложен весь`)
      return
    }
    const target = place ?? { id: activeCell.id, code: activeCell.code, kind: 'cell' as const }
    put(product, 1, target.id)
    setScanError(null)
    setScanNotice(`${product.name} → ${target.code}, +1`)
  }

  return (
    <Box data-testid="sorting-scale-screen">
      <ScreenHeader
        title="Раскладка по ячейкам"
        purpose={`Приёмка №1284 от 27.08.2026 · ${products.length} строк товара, ${total.toLocaleString('ru-RU')} шт`}
      />

      <FilterBar
        search={query}
        onSearchChange={(value) => {
          setQuery(value)
          setPage(0)
        }}
        searchPlaceholder="Товар, артикул или ШК"
        searchHelperText={`Показано ${shown.length} из ${filtered.length} подходящих строк`}
        testId="sorting-scale-filters"
        scanner={
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
            testId="sorting-scale-scan"
          />
        }
        actions={
          <PrimaryAction onClick={() => setBulkOpen(true)} data-testid="sorting-bulk-open">
            Разложить по подсказке
          </PrimaryAction>
        }
      >
        <Box sx={{ minWidth: 210 }}>
          <SelectInput
            label="Селлер"
            value={seller}
            onChange={(value) => {
              setSeller(value)
              setPage(0)
            }}
            options={sellers.map((one) => ({ value: one, label: one }))}
            emptyLabel="Все селлеры"
            testId="sorting-filter-seller"
          />
        </Box>
        <Box sx={{ minWidth: 190 }}>
          <SelectInput
            label="Откуда приехало"
            value={source}
            onChange={(value) => {
              setSource(value)
              setPage(0)
            }}
            options={sources.map((one) => ({ value: one, label: one }))}
            emptyLabel="Россыпь и короба"
            testId="sorting-filter-source"
          />
        </Box>
        <Box sx={{ pt: 0.5 }}>
          <CheckboxInput
            label="Только неразложенные"
            checked={onlyLeft}
            onChange={(value) => {
              setOnlyLeft(value)
              setPage(0)
            }}
            testId="sorting-filter-left"
          />
        </Box>
      </FilterBar>

      <Stack direction="row" spacing={1.5} sx={{ mb: 2, alignItems: 'center', flexWrap: 'wrap' }}>
        <Typography variant="body2" color="text.secondary">
          Склад:
        </Typography>
        <ToggleButtonGroup
          exclusive
          size="small"
          value={warehouseId}
          onChange={(_event, value: string | null) => {
            if (!value) return
            setWarehouseId(value)
            setActiveCellId(null)
            setRecent([])
          }}
          data-testid="sorting-warehouses"
        >
          {WAREHOUSES.map((warehouse) => (
            <ToggleButton
              key={warehouse.id}
              value={warehouse.id}
              sx={{ textTransform: 'none', fontWeight: 600 }}
              data-testid={`sorting-warehouse-${warehouse.id}`}
            >
              {warehouse.name}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
        <StatusChip
          label={left === 0 ? 'всё разложено' : `осталось ${linesLeft} строк · ${left.toLocaleString('ru-RU')} шт`}
          tone={left === 0 ? 'ok' : 'warn'}
          testId="sorting-scale-total"
        />
      </Stack>

      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} sx={{ alignItems: 'flex-start' }}>
        <Box sx={{ flexGrow: 1, minWidth: 0, width: '100%' }}>
          <SortingRemaining
            products={shown}
            placements={placements}
            activeCell={activeCell}
            activeWarehouseId={warehouseId}
            summary={{ left, total }}
            onPlaceAll={(product) => {
              const target = place ?? (activeCell ? { id: activeCell.id, code: activeCell.code, kind: 'cell' as const } : null)
              if (!target) return
              setAsking({ product, place: target })
              setAskQty(remainingFor(product, placements))
            }}
            onPickCell={pickCell}
            onDragProduct={(product) => setCarried({ kind: 'product', product })}
            onDragEnd={() => setCarried(null)}
            footer={
              <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', justifyContent: 'flex-end' }}>
                <IconAction
                  title="Предыдущая страница"
                  onClick={() => setPage(current - 1)}
                  disabledReason={current === 0 ? 'Это первая страница' : undefined}
                  testId="sorting-page-prev"
                >
                  <ChevronLeft fontSize="small" />
                </IconAction>
                <Typography variant="body2" sx={{ whiteSpace: 'nowrap' }}>
                  страница {current + 1} из {pages}
                </Typography>
                <IconAction
                  title="Следующая страница"
                  onClick={() => setPage(current + 1)}
                  disabledReason={current >= pages - 1 ? 'Это последняя страница' : undefined}
                  testId="sorting-page-next"
                >
                  <ChevronRight fontSize="small" />
                </IconAction>
              </Stack>
            }
          />
        </Box>
        <Stack spacing={2} sx={{ width: { lg: 440 }, flexShrink: 0, minWidth: 0 }}>
          <SortingCellPicker
            cells={cells}
            activeCellId={activeCellId}
            suggestedIds={suggestedIds}
            recentIds={recent}
            carried={carried !== null}
            onPick={pickCell}
            onCreateCell={() => onNote('Заглушка: та же модалка создания ячейки, что на карте склада')}
          />
          <SortingPlacePanel
            cell={activeCell}
            path={path}
            place={place}
            containers={containers}
            placements={placements}
            products={products}
            carried={carried}
            onEnter={(next) => setPath((currentPath) => [...currentPath, next])}
            onLeaveTo={(index) => setPath((currentPath) => currentPath.slice(0, index + 1))}
            onCreate={createContainer}
            onChangeQty={(productId, qty) => {
              if (!place) return
              setPlacements((currentList) =>
                qty <= 0
                  ? currentList.filter(
                      (one) => !(one.productId === productId && one.cellId === place.id),
                    )
                  : currentList.map((one) =>
                      one.productId === productId && one.cellId === place.id ? { ...one, qty } : one,
                    ),
              )
            }}
            onRemove={(productId) => {
              if (!place) return
              setPlacements((currentList) =>
                currentList.filter((one) => !(one.productId === productId && one.cellId === place.id)),
              )
            }}
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
                if (asking && askQty) put(asking.product, askQty, asking.place.id)
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
            <Typography variant="subtitle2">{asking?.product.name}</Typography>
            <Typography variant="body2" color="text.secondary">
              Куда: {asking?.place.code ?? '—'}
            </Typography>
          </Stack>
          <NumberInput
            label="Сколько штук"
            value={askQty}
            onChange={setAskQty}
            min={1}
            max={asking ? remainingFor(asking.product, placements) : undefined}
            helperText={
              asking ? `Осталось разложить ${remainingFor(asking.product, placements)} шт` : undefined
            }
            testId="sorting-qty-input"
          />
        </Stack>
      </AppDialog>

      <SortingBulkDialog
        open={bulkOpen}
        proposals={buildProposals(products, placements, cells, warehouseId)}
        onClose={() => setBulkOpen(false)}
        onApply={(accepted) => {
          accepted.forEach((one) => {
            if (one.cell) put(one.product, one.qty, one.cell.id)
          })
          setBulkOpen(false)
          onNote(`Заглушка: разложено ${accepted.length} строк по подсказке`)
        }}
      />
    </Box>
  )
}
