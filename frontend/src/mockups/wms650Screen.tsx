import { Box, IconButton, LinearProgress, Paper, Stack, Tooltip, Typography } from '@mui/material'
import UndoOutlinedIcon from '@mui/icons-material/UndoOutlined'
import { useEffect, useRef, useState } from 'react'
import {
  createSortingScanner,
  emptyScanContext,
  type ScanContext,
} from '../screens/ff/sorting-objects/sortingScan'
import {
  ActionGroup,
  AppDialog,
  NumberInput,
  PrimaryAction,
  ScannerField,
  ScreenHeader,
  SecondaryAction,
  SelectInput,
} from '../ui-kit'
import { CreateCellDialog } from '../screens/ff/warehouse-map/WarehouseMapToolbar'
import { BoxLabelPrintDialog } from '../components/BoxLabelPrintDialog'
import { Wms650Tree } from './wms650Tree'
import {
  CELLS,
  INITIAL_LINES,
  INITIAL_OBJECTS,
  PRODUCTS,
  KIND_TITLE,
  cellRef,
  objRef,
  productById,
  whereIs,
  type GoodsLine,
  type Holder,
  type ObjKind,
  type WarehouseObject,
} from '../screens/ff/sorting-objects/objectsStub'
import {
  canPut,
  destinationsFor,
  objectTitle,
  unplacedRows,
  type Carried,
  type ObjectRow,
} from '../screens/ff/sorting-objects/objectsRows'
import { PlacedByCells } from './wms650Placed'

// WMS-650. Вариант экрана «Раскладка по ячейкам» для макета.
//
// От продуктового SortingObjectsScreen отличается тремя вещами и только ими:
//  1. в основном списке остаётся одно неразложенное (unplacedRows), а
//     поставленное показано рядом, под ячейкой, на которой стоит;
//  2. рядом с полем сканера стоит стрелка «назад», отменяющая последнее действие;
//  3. строки, которых коснулось действие, подсвечены: открытая ячейка, открытая
//     тара, только что положенное.
// Всё остальное — тот же экран, те же компоненты и тема. Сервера нет: состояние
// живёт в памяти макета.

/** Снимок до действия: «назад» просто возвращает его. */
type Snapshot = {
  label: string
  objects: WarehouseObject[]
  lines: GoodsLine[]
  ctx: ScanContext
  /** Какую строку подсветить после отмены — ту, что вернулась. */
  undoFocus: string | null
}

export type Wms650Api = { scan: (code: string) => void }

/** Цепочка тар от ячейки вниз к этому держателю — чтобы раскрыть путь к строке. */
function chainTo(holder: Holder, objects: WarehouseObject[]): string[] {
  const ids: string[] = []
  let cursor = holder
  while (cursor && cursor.startsWith('obj:')) {
    const id = cursor.slice(4)
    ids.push(id)
    cursor = objects.find((one) => one.id === id)?.holder ?? null
  }
  return ids
}

export function Wms650Screen({
  onNote,
  onReady,
}: {
  onNote: (note: string) => void
  /** Макет отдаёт ленте способ «пикнуть» код кнопкой — как будто сканером. */
  onReady?: (api: Wms650Api) => void
}) {
  const products = PRODUCTS
  const [objects, setObjects] = useState<WarehouseObject[]>(INITIAL_OBJECTS)
  const [lines, setLines] = useState<GoodsLine[]>(INITIAL_LINES)
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [placedOpen, setPlacedOpen] = useState<Set<string>>(new Set())
  const [carried, setCarried] = useState<Carried | null>(null)
  const [scanContext, setScanContext] = useState<ScanContext>(emptyScanContext)
  const [history, setHistory] = useState<Snapshot[]>([])
  const [focusKey, setFocusKey] = useState<string | null>(null)
  const [scanError, setScanError] = useState<string | null>(null)
  const [scanNotice, setScanNotice] = useState<string | null>(null)
  const [asking, setAsking] = useState<Carried | null>(null)
  const [askTarget, setAskTarget] = useState('')
  const [askQty, setAskQty] = useState<number | null>(null)
  const [created, setCreated] = useState(0)
  const [printing, setPrinting] = useState<{ title: string; barcode: string } | null>(null)
  const [cellDialogOpen, setCellDialogOpen] = useState(false)
  const [extraCells, setExtraCells] = useState<typeof CELLS>([])
  const root = useRef<HTMLDivElement>(null)

  const cells = [...CELLS, ...extraCells]
  const activeCellId = scanContext.cellId
  const activeCell = cells.find((one) => one.id === activeCellId) ?? null
  const activeObject = objects.find((one) => one.id === scanContext.objectId) ?? null

  // Сканер и действия экрана читают одни и те же свежие данные: следующий скан
  // из очереди может прийти раньше, чем React перерисует подтверждённую постановку.
  const live = useRef({ objects, lines, cells })
  live.current = { objects, lines, cells }
  const ctxRef = useRef<ScanContext>(emptyScanContext)
  /** Контекст на момент начала текущего скана: к нему вернёт «назад». */
  const scanBefore = useRef<ScanContext>(emptyScanContext)
  const placedNote = useRef<string | null>(null)
  const lineSeq = useRef(0)

  /** Каждое изменение склада идёт через одну точку: запоминаем снимок «до». */
  function commit(
    label: string,
    next: { objects?: WarehouseObject[]; lines?: GoodsLine[] },
    focus: string | null,
    undoFocus: string | null,
    ctxBefore: ScanContext = ctxRef.current,
  ) {
    const current = live.current
    const nextObjects = next.objects ?? current.objects
    const nextLines = next.lines ?? current.lines
    setHistory((past) => [
      ...past,
      { label, objects: current.objects, lines: current.lines, ctx: ctxBefore, undoFocus },
    ])
    live.current = { ...current, objects: nextObjects, lines: nextLines }
    setObjects(nextObjects)
    setLines(nextLines)
    setFocusKey(focus)
    // Действие не из сканера тоже оставляет след в строке под полем; скан перепишет его своим.
    setScanError(null)
    setScanNotice(label)
  }

  /** Перенести qty штук строки в target: одинаковый товар в одном месте складывается. */
  function splitLines(from: GoodsLine, qty: number, target: Holder) {
    const rest = live.current.lines.filter((one) => one.id !== from.id)
    const left = from.qty - qty
    const twin = rest.find((one) => one.productId === from.productId && one.holder === target)
    const movedId = twin ? twin.id : `l-m${++lineSeq.current}`
    const withTarget = twin
      ? rest.map((one) => (one === twin ? { ...one, qty: one.qty + qty } : one))
      : [...rest, { id: movedId, productId: from.productId, qty, holder: target }]
    return { lines: left > 0 ? [...withTarget, { ...from, qty: left }] : withTarget, movedId }
  }

  function placeLabel(target: Holder): string {
    if (!target) return 'россыпь'
    if (target.startsWith('cell:')) {
      const cell = live.current.cells.find((one) => cellRef(one.id) === target)
      return cell ? `ячейку ${cell.code}` : 'ячейку'
    }
    const object = live.current.objects.find((one) => objRef(one.id) === target)
    return object ? objectTitle(object) : 'объект'
  }

  function moveGoods(line: GoodsLine, qty: number, target: Holder) {
    const { lines: next, movedId } = splitLines(line, qty, target)
    const name = productById(products, line.productId).name
    commit(
      `${name}, ${qty} шт → ${placeLabel(target)}`,
      { lines: next },
      `l-${movedId}`,
      `l-${line.id}`,
    )
  }

  function moveObject(object: WarehouseObject, target: Holder, label: string) {
    const next = live.current.objects.map((one) => (one.id === object.id ? { ...one, holder: target } : one))
    commit(`${objectTitle(object)} → ${label}`, { objects: next }, `o-${object.id}`, `o-${object.id}`)
    onNote(`${KIND_TITLE[object.kind]} ${object.code} → ${label}`)
  }

  /** Товар по штрихкоду: одна штука россыпью уходит в открытую тару, а без неё — в ячейку. */
  async function scanProduct(barcode: string): Promise<string> {
    const ctx = ctxRef.current
    const product = products.find((one) => one.barcode === barcode)
    if (!product) throw new Error('Такого кода нет среди ячеек, тары и товаров этой приёмки')
    const line = live.current.lines.find(
      (one) => one.productId === product.id && one.holder === null && one.qty > 0,
    )
    if (!line) throw new Error(`«${product.name}» — россыпью не осталось`)
    const target: Holder = ctx.objectId ? objRef(ctx.objectId) : cellRef(ctx.cellId ?? '')
    const { lines: next, movedId } = splitLines(line, 1, target)
    const where = ctx.objectId
      ? `${objectTitle(live.current.objects.find((one) => one.id === ctx.objectId)!)}`
      : `ячейку ${live.current.cells.find((one) => one.id === ctx.cellId)?.code ?? ''}`
    commit(`${product.name}, 1 шт → ${where}`, { lines: next }, `l-${movedId}`, `l-${line.id}`, scanBefore.current)
    const looseLeft = next
      .filter((one) => one.productId === product.id && one.holder === null)
      .reduce((sum, one) => sum + one.qty, 0)
    return `${product.name}: +1 шт → ${where}. Россыпью осталось ${looseLeft}`
  }

  const makeScanner = (initial: ScanContext) =>
    createSortingScanner(initial, {
      data: () => live.current,
      place: async (object, cellId) => {
        const cell = live.current.cells.find((one) => one.id === cellId)
        const next = live.current.objects.map((one) =>
          one.id === object.id ? { ...one, holder: cellRef(cellId) } : one,
        )
        commit(
          `${objectTitle(object)} → ячейку ${cell?.code ?? ''}`,
          { objects: next },
          `o-${object.id}`,
          `o-${object.id}`,
          scanBefore.current,
        )
        placedNote.current = `${objectTitle(object)} положен на ячейку ${cell?.code ?? ''}`
      },
      product: (barcode) => scanProduct(barcode),
      changed: (next) => {
        ctxRef.current = next
        setScanContext(next)
      },
      notice: (message) => {
        const prefix = placedNote.current
        placedNote.current = null
        setScanError(null)
        setScanNotice(prefix ? `${prefix}. ${message}` : message)
      },
      error: (error) => {
        placedNote.current = null
        setScanNotice(null)
        setScanError(error instanceof Error ? error.message : 'Не удалось выполнить скан')
      },
    })
  const scannerRef = useRef<ReturnType<typeof makeScanner> | null>(null)
  if (!scannerRef.current) scannerRef.current = makeScanner(emptyScanContext)

  function handleScan(code: string) {
    scanBefore.current = ctxRef.current
    void scannerRef.current?.scan(code)
  }
  const handleScanRef = useRef(handleScan)
  handleScanRef.current = handleScan
  useEffect(() => {
    onReady?.({ scan: (code) => handleScanRef.current(code) })
  }, [onReady])

  /** «Назад»: последнее действие снимается целиком, включая то, что стало открытым. */
  function undo() {
    const last = history[history.length - 1]
    if (!last) return
    setHistory((past) => past.slice(0, -1))
    live.current = { ...live.current, objects: last.objects, lines: last.lines }
    setObjects(last.objects)
    setLines(last.lines)
    scannerRef.current = makeScanner(last.ctx)
    ctxRef.current = last.ctx
    setScanContext(last.ctx)
    setFocusKey(last.undoFocus)
    setScanError(null)
    setScanNotice(`Отменено: ${last.label}`)
  }

  const loose = lines.filter((line) => line.holder === null)
  const unplaced = objects.filter((one) => one.holder === null)
  const totalQty = lines.reduce((sum, line) => sum + line.qty, 0)
  const leftQty = lines
    .filter((line) => !whereIs(line.holder, objects, cells).cell)
    .reduce((sum, line) => sum + line.qty, 0)
  const quantitiesByCell = new Map<string, number>()
  for (const line of lines) {
    const id = whereIs(line.holder, objects, cells).cell?.id
    if (id) quantitiesByCell.set(id, (quantitiesByCell.get(id) ?? 0) + line.qty)
  }
  // Поставленное по умолчанию свёрнуто: короб на ячейке — одна строка, а не десять.
  // Раскрыто то, что открыл сам оператор, плюс открытая сканом тара и путь к строке,
  // которой коснулось последнее действие: в неё летят товары, и видеть это надо сразу.
  const focusLine = focusKey ? lines.find((one) => `l-${one.id}` === focusKey) : undefined
  const focusObject = focusKey ? objects.find((one) => `o-${one.id}` === focusKey) : undefined
  const forcedOpen = new Set<string>([
    ...(activeObject ? [activeObject.id, ...chainTo(activeObject.holder, objects)] : []),
    ...(focusLine ? chainTo(focusLine.holder, objects) : []),
    ...(focusObject ? chainTo(focusObject.holder, objects) : []),
  ])
  const placedCollapsed = new Set(
    objects.filter((one) => !placedOpen.has(one.id) && !forcedOpen.has(one.id)).map((one) => one.id),
  )
  const mainRows = unplacedRows(objects, lines, products, collapsed)
  const mainKeys = new Set(mainRows.map((row) => row.key))
  const openKey = scanContext.objectId ? `o-${scanContext.objectId}` : null
  const mainHighlight = openKey && mainKeys.has(openKey) ? openKey : focusKey && mainKeys.has(focusKey) ? focusKey : null

  useEffect(() => {
    const key = scanContext.objectId ? `o-${scanContext.objectId}` : focusKey
    const row = key ? root.current?.querySelector(`[data-row-key="${key}"]`) : null
    row?.scrollIntoView({ block: 'nearest', behavior: 'instant' })
  }, [scanContext.objectId, focusKey, objects, lines])

  function toggle(objectId: string) {
    setCollapsed((current) => {
      const next = new Set(current)
      if (next.has(objectId)) next.delete(objectId)
      else next.add(objectId)
      return next
    })
  }

  function togglePlaced(objectId: string) {
    setPlacedOpen((current) => {
      const next = new Set(current)
      if (next.has(objectId)) next.delete(objectId)
      else next.add(objectId)
      return next
    })
  }

  function labelOf(target: Holder): string {
    return placeLabel(target)
  }

  /** Перетащили: контейнер едет целиком, у товара спрашиваем количество. */
  function drop(target: Holder) {
    if (!carried) return
    if (!canPut(carried, target, objects)) {
      setCarried(null)
      return
    }
    if (carried.kind === 'object') moveObject(carried.object, target, labelOf(target))
    else openDialog(carried, target)
    setCarried(null)
  }

  /** Снять с ячейки: уезжает целиком и вместе с содержимым, без вопросов. */
  function takeOffCell(row: ObjectRow) {
    if (row.kind === 'goods') {
      moveGoods(row.line, row.line.qty, null)
      return
    }
    moveObject(row.object, null, 'россыпь')
  }

  /** Вынуть наружу: то же окно, но место уже выбрано — россыпь. */
  function takeOut(row: ObjectRow) {
    openDialog(
      row.kind === 'goods' ? { kind: 'goods', line: row.line } : { kind: 'object', object: row.object },
      null,
    )
  }

  /** Нажали плюс: то же самое, только место выбирается в диалоге. */
  function openDialog(what: Carried, target?: Holder) {
    setAsking(what)
    setAskTarget(target === undefined ? (activeCell ? cellRef(activeCell.id) : '') : (target ?? 'none'))
    setAskQty(what.kind === 'goods' ? what.line.qty : null)
  }

  function confirmDialog() {
    if (!asking) return
    const target: Holder = askTarget === 'none' || askTarget === '' ? null : askTarget
    if (asking.kind === 'object') {
      moveObject(asking.object, target, labelOf(target))
    } else if (askQty && askQty > 0) {
      moveGoods(asking.line, Math.min(askQty, asking.line.qty), target)
    }
    setAsking(null)
  }

  function createObject(kind: ObjKind) {
    const number = created + 1
    setCreated(number)
    const code =
      kind === 'pallet'
        ? `П-${String(200 + number).padStart(6, '0')}`
        : kind === 'box'
          ? `КР-${String(500 + number).padStart(6, '0')}`
          : `ГМ-${String(400 + number).padStart(6, '0')}`
    setObjects((current) => {
      const next = [
        ...current,
        { id: `new-${number}`, kind, code, barcode: `29${String(number).padStart(11, '0')}`, holder: null },
      ]
      live.current = { ...live.current, objects: next }
      return next
    })
    onNote(`Макет: создан ${KIND_TITLE[kind].toLowerCase()} ${code}`)
  }

  const destinations = asking ? destinationsFor(asking, objects, cells) : []

  return (
    <Box ref={root} data-testid="sorting-objects-screen">
      <ScreenHeader
        title="Раскладка по ячейкам"
        purpose="Приёмка №1284 от 27.08.2026. Собираем объект и ставим готовый объект на полку."
      />

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        {/* Стрелка «назад» — как у упаковки FBS (FbsScanPrintToggles): значок с
            подсказкой рядом с полем сканирования, недоступен, пока отменять нечего. */}
        <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-start' }}>
          <Box sx={{ flexGrow: 1, minWidth: 0 }}>
            <ScannerField
              onScan={handleScan}
              expects={
                activeCell
                  ? activeObject
                    ? `товар в ${activeObject.code} · ячейка ${activeCell.code}`
                    : `тару или товар · ячейка ${activeCell.code}`
                  : 'ячейку с полки'
              }
              error={scanError}
              notice={scanNotice}
              testId="objects-scan"
            />
          </Box>
          <Tooltip title={history.length ? `Отменить: ${history[history.length - 1].label}` : 'Отменять нечего'}>
            <span style={{ marginTop: 50 }}>
              <IconButton
                size="small"
                aria-label="Отменить последнее действие"
                disabled={history.length === 0}
                // Не уводим фокус из поля сканера: следующий пик должен попасть в него.
                onMouseDown={(event) => event.preventDefault()}
                onClick={undo}
                data-testid="objects-undo"
              >
                <UndoOutlinedIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        </Stack>
      </Paper>

      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} sx={{ alignItems: 'flex-start' }}>
        <Box
          sx={{
            flexGrow: 1,
            flexShrink: 1,
            minWidth: 0,
            width: { xs: '100%', lg: 'auto' },
          }}
        >
          <Stack spacing={1} sx={{ mb: 1.5 }}>
            <Stack direction="row" spacing={2} sx={{ alignItems: 'baseline' }}>
              <Typography variant="h5" data-testid="objects-left-qty">
                {leftQty.toLocaleString('ru-RU')}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                штук осталось поставить из {totalQty.toLocaleString('ru-RU')} принятых —
                это {unplaced.length} объектов и {loose.length} позиций россыпью
              </Typography>
            </Stack>
            <LinearProgress
              variant="determinate"
              value={totalQty === 0 ? 0 : ((totalQty - leftQty) / totalQty) * 100}
              sx={{ height: 8, borderRadius: 4 }}
            />
          </Stack>
          <Stack
            direction="row"
            spacing={1}
            sx={{ mb: 1.5, alignItems: 'center', flexWrap: 'wrap', gap: 1, justifyContent: 'flex-end' }}
          >
            <SecondaryAction onClick={() => setCellDialogOpen(true)} data-testid="objects-create-cell">
              Создать ячейку
            </SecondaryAction>
            <SecondaryAction onClick={() => createObject('pallet')} data-testid="objects-create-pallet">
              Новая палета
            </SecondaryAction>
            <SecondaryAction onClick={() => createObject('box')} data-testid="objects-create-box">
              Новый короб
            </SecondaryAction>
            <SecondaryAction
              onClick={() => createObject('cargo_place')}
              data-testid="objects-create-cargo_place"
            >
              Новое грузоместо
            </SecondaryAction>
          </Stack>
          <Wms650Tree
            rows={mainRows}
            objects={objects}
            carried={carried}
            testId="objects-tree"
            highlightedKey={mainHighlight}
            empty={{
              title: 'Всё расставлено по ячейкам',
              hint: 'Ни товара россыпью, ни собранных объектов не осталось.',
            }}
            onToggle={toggle}
            onPlace={(row: ObjectRow) =>
              openDialog(
                row.kind === 'goods' ? { kind: 'goods', line: row.line } : { kind: 'object', object: row.object },
              )
            }
            onDragStart={(row: ObjectRow) =>
              setCarried(
                row.kind === 'goods' ? { kind: 'goods', line: row.line } : { kind: 'object', object: row.object },
              )
            }
            onDragEnd={() => setCarried(null)}
            onDropOn={drop}
            onTakeOut={takeOut}
            onMinus={takeOffCell}
            onPrint={(row) =>
              setPrinting(
                row.kind === 'object'
                  ? { title: objectTitle(row.object), barcode: row.object.barcode }
                  : { title: row.name, barcode: row.barcode },
              )
            }
            onPickCell={(cellId) => void scannerRef.current?.selectCell(cellId)}
          />
        </Box>

        <Stack
          spacing={2}
          sx={{
            flexGrow: 0,
            flexShrink: 0,
            minWidth: 0,
            width: { xs: '100%', lg: 320 },
            position: { lg: 'sticky' },
            top: { lg: 16 },
          }}
        >
          <Paper variant="outlined" data-testid="objects-cells">
            <Stack
              direction="row"
              sx={{ alignItems: 'baseline', justifyContent: 'space-between', px: 2, pt: 2, pb: 1 }}
            >
              <Typography variant="subtitle1">Ячейки склада</Typography>
              <Typography variant="caption" color="text.secondary" data-testid="objects-placed-qty">
                размещено {(totalQty - leftQty).toLocaleString('ru-RU')} шт
              </Typography>
            </Stack>
            <Box sx={{ maxHeight: 'calc(100vh - 140px)', overflowY: 'auto', borderTop: '1px solid', borderColor: 'divider' }}>
              <PlacedByCells
                cells={cells}
                objects={objects}
                lines={lines}
                products={products}
                collapsed={placedCollapsed}
                quantities={quantitiesByCell}
                activeCellId={activeCellId}
                openObjectId={scanContext.objectId}
                focusKey={focusKey}
                carried={carried}
                onPickCell={(cellId) => void scannerRef.current?.selectCell(cellId)}
                onDropOnCell={(cellId) => drop(cellRef(cellId))}
                onToggle={togglePlaced}
                onTakeOff={takeOffCell}
                onTakeOut={takeOut}
              />
            </Box>
          </Paper>
        </Stack>
      </Stack>

      <Stack direction="row" sx={{ mt: 2, justifyContent: 'flex-end' }}>
        <ActionGroup>
          <SecondaryAction onClick={() => onNote('Макет: документ закрыт')} data-testid="objects-close">
            Закрыть
          </SecondaryAction>
          <SecondaryAction onClick={() => onNote('Макет: раскладка сохранена')} data-testid="objects-save">
            Сохранить
          </SecondaryAction>
          <PrimaryAction
            onClick={() => onNote('Макет: распределение завершено')}
            disabledReason={unplaced.length + loose.length > 0 ? 'Ещё не всё поставлено на полки' : undefined}
            data-testid="objects-complete"
          >
            Завершить
          </PrimaryAction>
        </ActionGroup>
      </Stack>

      <BoxLabelPrintDialog
        open={printing !== null}
        title={printing ? `Печать стикера: ${printing.title}` : ''}
        description="Выберите размер этикетки. Напечатанное не отменить."
        scope="label"
        onClose={() => setPrinting(null)}
        onConfirm={(size) => {
          const target = printing
          setPrinting(null)
          if (target) onNote(`Макет: ${target.title}, этикетка ${size.label} — принтера в макете нет`)
        }}
        testId="objects-print-dialog"
      />
      <CreateCellDialog
        open={cellDialogOpen}
        warehouseName="Ярцево"
        existingCodes={cells.map((one) => one.code)}
        onClose={() => setCellDialogOpen(false)}
        onCreate={(code) => {
          setExtraCells((current) => [
            ...current,
            { id: `new-cell-${current.length + 1}`, code, barcode: `29${String(current.length + 1).padStart(11, '0')}` },
          ])
          setCellDialogOpen(false)
          onNote(`Макет: ячейка ${code} создана только в макете`)
        }}
      />
      <AppDialog
        open={asking !== null}
        onClose={() => setAsking(null)}
        title="Куда положить"
        testId="objects-qty-dialog"
        actions={
          <ActionGroup>
            <SecondaryAction onClick={() => setAsking(null)} data-testid="objects-qty-cancel">
              Отмена
            </SecondaryAction>
            <PrimaryAction
              onClick={confirmDialog}
              disabledReason={askTarget === '' ? 'Выберите место' : undefined}
              data-testid="objects-qty-confirm"
            >
              Положить
            </PrimaryAction>
          </ActionGroup>
        }
      >
        <Stack spacing={2}>
          <Typography variant="subtitle2">
            {asking
              ? asking.kind === 'goods'
                ? productById(products, asking.line.productId).name
                : objectTitle(asking.object)
              : ''}
          </Typography>
          <SelectInput
            label="Место"
            value={askTarget}
            onChange={setAskTarget}
            options={destinations}
            emptyLabel="Выберите место"
            testId="objects-target"
          />
          {asking?.kind === 'goods' ? (
            <NumberInput
              label="Сколько штук"
              value={askQty}
              onChange={setAskQty}
              min={1}
              max={asking.line.qty}
              helperText={`Всего ${asking.line.qty} — можно переложить часть`}
              testId="objects-qty-input"
            />
          ) : (
            <Typography variant="body2" color="text.secondary">
              Переедет целиком, вместе со всем содержимым.
            </Typography>
          )}
        </Stack>
      </AppDialog>
    </Box>
  )
}
