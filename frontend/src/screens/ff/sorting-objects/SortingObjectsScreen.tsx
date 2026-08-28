import { Box, Paper, Stack, Typography } from '@mui/material'
import { alpha, useTheme } from '@mui/material/styles'
import { useState } from 'react'
import {
  ActionGroup,
  AppDialog,
  NumberInput,
  PrimaryAction,
  PrintAction,
  ScannerField,
  ScreenHeader,
  SecondaryAction,
  SelectInput,
} from '../../../ui-kit'
import { CreateCellDialog } from '../warehouse-map/WarehouseMapToolbar'
import { BoxLabelPrintDialog } from '../../../components/BoxLabelPrintDialog'
import { LinearProgress } from '@mui/material'
import { ObjectsTree } from './ObjectsTree'
import {
  CELLS,
  INITIAL_LINES,
  INITIAL_OBJECTS,
  KIND_TITLE,
  cellQty,
  cellRef,
  productById,
  type GoodsLine,
  type Holder,
  whereIs,
  type ObjKind,
  type WarehouseObject,
} from './objectsStub'
import {
  canPut,
  cellRows,
  destinationsFor,
  objectTitle,
  unplacedRows,
  type Carried,
  type ObjectRow,
} from './objectsRows'

// Раскладка объектами.
//
// Порядок работы обратный привычному: сначала собираем объект — товар в короб,
// короб на палету, — и только готовый объект ставим на полку. Где лежит товар,
// отдельно не хранится: это вычисляется по цепочке держателей, поэтому «что в
// коробе» и «где короб» не могут разъехаться. Это одно знание.
//
// Список один. Короба, палеты и грузоместа стоят в нём как агрегаты со своим
// содержимым внутри, товар россыпью — такими же строками верхнего уровня, а
// разница между «ещё не поставлено» и «стоит на полке» видна колонкой «Где».

export function SortingObjectsScreen({ onNote }: { onNote: (note: string) => void }) {
  const theme = useTheme()
  const [objects, setObjects] = useState<WarehouseObject[]>(INITIAL_OBJECTS)
  const [lines, setLines] = useState<GoodsLine[]>(INITIAL_LINES)
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [carried, setCarried] = useState<Carried | null>(null)
  const [activeCellId, setActiveCellId] = useState<string | null>(null)
  const [scanValue, setScanValue] = useState('')
  const [scanError, setScanError] = useState<string | null>(null)
  const [scanNotice, setScanNotice] = useState<string | null>(null)
  const [asking, setAsking] = useState<Carried | null>(null)
  const [askTarget, setAskTarget] = useState('')
  const [askQty, setAskQty] = useState<number | null>(null)
  const [created, setCreated] = useState(0)
  const [printing, setPrinting] = useState<string | null>(null)
  const [cellDialogOpen, setCellDialogOpen] = useState(false)
  const [extraCells, setExtraCells] = useState<typeof CELLS>([])

  const cells = [...CELLS, ...extraCells]
  const activeCell = cells.find((one) => one.id === activeCellId) ?? null
  const loose = lines.filter((line) => line.holder === null)
  const unplaced = objects.filter((one) => one.holder === null)
  const totalQty = lines.reduce((sum, line) => sum + line.qty, 0)
  const leftQty = lines
    .filter((line) => !whereIs(line.holder, objects, cells).cell)
    .reduce((sum, line) => sum + line.qty, 0)

  function toggle(objectId: string) {
    setCollapsed((current) => {
      const next = new Set(current)
      if (next.has(objectId)) next.delete(objectId)
      else next.add(objectId)
      return next
    })
  }

  function moveGoods(line: GoodsLine, qty: number, target: Holder) {
    setLines((current) => {
      const rest = current.filter((one) => one.id !== line.id)
      const left = line.qty - qty
      const twin = rest.find((one) => one.productId === line.productId && one.holder === target)
      const withTarget = twin
        ? rest.map((one) => (one === twin ? { ...one, qty: one.qty + qty } : one))
        : [...rest, { id: `l-${Date.now()}-${line.id}`, productId: line.productId, qty, holder: target }]
      return left > 0 ? [...withTarget, { ...line, qty: left }] : withTarget
    })
  }

  function moveObject(object: WarehouseObject, target: Holder, label: string) {
    setObjects((current) => current.map((one) => (one.id === object.id ? { ...one, holder: target } : one)))
    onNote(`${KIND_TITLE[object.kind]} ${object.code} → ${label}`)
  }

  function labelOf(target: Holder): string {
    if (!target) return 'россыпь'
    if (target.startsWith('cell:')) {
      const cell = cells.find((one) => cellRef(one.id) === target)
      return cell ? `ячейку ${cell.code}` : 'ячейку'
    }
    const object = objects.find((one) => `obj:${one.id}` === target)
    return object ? objectTitle(object) : 'объект'
  }

  /** Перетащили: контейнер едет целиком, у товара спрашиваем количество. */
  function drop(target: Holder) {
    if (!carried) return
    if (!canPut(carried, target, objects)) {
      setCarried(null)
      return
    }
    if (carried.kind === 'object') {
      moveObject(carried.object, target, labelOf(target))
    } else {
      openDialog(carried, target)
    }
    setCarried(null)
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
    setObjects((current) => [
      ...current,
      { id: `new-${number}`, kind, code, barcode: `29${String(number).padStart(11, '0')}`, holder: null },
    ])
    onNote(`Заглушка: создан ${KIND_TITLE[kind].toLowerCase()} ${code}`)
  }

  function handleScan(code: string) {
    setScanValue('')
    const cell = cells.find((one) => one.barcode === code || one.code.toLowerCase() === code.toLowerCase())
    if (cell) {
      setActiveCellId(cell.id)
      setScanError(null)
      setScanNotice(`Ячейка ${cell.code} — плюс у строки поставит сюда`)
      return
    }
    const object = objects.find((one) => one.barcode === code)
    if (object) {
      if (!activeCell) {
        setScanNotice(null)
        setScanError('Сначала пикните ячейку — иначе непонятно, куда ставим')
        return
      }
      moveObject(object, cellRef(activeCell.id), `ячейку ${activeCell.code}`)
      setScanError(null)
      setScanNotice(`${KIND_TITLE[object.kind]} ${object.code} → ячейка ${activeCell.code}`)
      return
    }
    setScanNotice(null)
    setScanError(`Штрихкод ${code} — ни ячейка, ни объект этой приёмки`)
  }

  const destinations = asking ? destinationsFor(asking, objects, cells) : []

  return (
    <Box data-testid="sorting-objects-screen">
      <ScreenHeader
        title="Раскладка по ячейкам"
        purpose="Приёмка №1284 от 27.08.2026. Собираем объект и ставим готовый объект на полку."
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
            expects={activeCell ? 'объект, который ставим' : 'ячейку с полки'}
            error={scanError}
            notice={scanNotice}
            testId="objects-scan"
          />
        </Stack>
      </Paper>

      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} sx={{ alignItems: 'flex-start' }}>
        <Box sx={{ flexGrow: 1, minWidth: 0, width: '100%' }}>
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
          <ObjectsTree
            rows={unplacedRows(objects, lines, collapsed)}
            objects={objects}
            carried={carried}
            testId="objects-tree"
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
            onPrint={(row) => setPrinting(row.kind === 'object' ? objectTitle(row.object) : row.name)}
            onPickCell={setActiveCellId}
          />
        </Box>

        <Stack spacing={2} sx={{ width: { lg: 628 }, flexShrink: 0, minWidth: 0 }}>
          <Paper variant="outlined" sx={{ p: 2 }} data-testid="objects-cells">
            <Typography variant="subtitle1" sx={{ mb: 1.5 }}>
              Ячейки склада
            </Typography>
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 1 }}>
              {cells.map((cell) => {
                const active = activeCellId === cell.id
                const qty = cellQty(cell.id, objects, lines)
                const target = Boolean(carried && canPut(carried, cellRef(cell.id), objects))
                return (
                  <Box
                    key={cell.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => setActiveCellId(cell.id)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') setActiveCellId(cell.id)
                    }}
                    onDragOver={(event) => {
                      if (target) event.preventDefault()
                    }}
                    onDrop={() => {
                      setActiveCellId(cell.id)
                      drop(cellRef(cell.id))
                    }}
                    data-testid={`objects-cell-${cell.id}`}
                    sx={{
                      px: 1.25,
                      py: 0.6,
                      borderRadius: 1.5,
                      cursor: 'pointer',
                      border: '1px solid',
                      borderColor: active ? 'primary.main' : 'divider',
                      backgroundColor: active ? alpha(theme.palette.primary.main, 0.08) : 'transparent',
                      outline: target && !active ? `1px dashed ${alpha(theme.palette.primary.main, 0.45)}` : 'none',
                      outlineOffset: '-3px',
                    }}
                  >
                    <Typography variant="body2" sx={{ fontWeight: 600, whiteSpace: 'nowrap' }}>
                      {cell.code}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {qty === 0 ? 'пусто' : `${qty} шт`}
                    </Typography>
                  </Box>
                )
              })}
            </Stack>
          </Paper>

          {activeCell ? (
            <Paper
              variant="outlined"
              sx={{
                p: 2,
                outline:
                  carried && canPut(carried, cellRef(activeCell.id), objects)
                    ? `2px dashed ${alpha(theme.palette.primary.main, 0.5)}`
                    : 'none',
                outlineOffset: '-4px',
              }}
              onDragOver={(event) => {
                if (carried && canPut(carried, cellRef(activeCell.id), objects)) event.preventDefault()
              }}
              onDrop={() => drop(cellRef(activeCell.id))}
              data-testid="objects-active-cell"
            >
              <Stack direction="row" spacing={1} sx={{ mb: 1, alignItems: 'center' }}>
                {/* Код ячейки не переносится на вторую строку (канон R-36):
                    заголовок, разорванный пополам, перестаёт читаться как код. */}
                <Typography variant="h6" sx={{ whiteSpace: 'nowrap' }}>
                  {activeCell.code}
                </Typography>
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                >
                  {cellQty(activeCell.id, objects, lines)} шт — по составу того, что стоит
                </Typography>
                <Box sx={{ flexGrow: 1 }} />
                <PrintAction
                  what="ШК ячейки"
                  placement="row"
                  onClick={() => setPrinting(`ячейка ${activeCell.code}`)}
                  testId="objects-print-cell"
                />
              </Stack>
              <ObjectsTree
                rows={cellRows(activeCell, objects, lines, collapsed)}
                objects={objects}
                carried={carried}
                testId="objects-cell-tree"
                compact
                empty={{ title: 'На ячейке пусто', hint: 'Перетащите сюда объект или нажмите плюс в списке.' }}
                onToggle={toggle}
                onPlace={(row: ObjectRow) =>
                  openDialog(
                    row.kind === 'goods'
                      ? { kind: 'goods', line: row.line }
                      : { kind: 'object', object: row.object },
                  )
                }
                onDragStart={(row: ObjectRow) =>
                  setCarried(
                    row.kind === 'goods'
                      ? { kind: 'goods', line: row.line }
                      : { kind: 'object', object: row.object },
                  )
                }
                onDragEnd={() => setCarried(null)}
                onDropOn={drop}
                onTakeOut={takeOut}
                onPrint={(row) => setPrinting(row.kind === 'object' ? objectTitle(row.object) : row.name)}
                onPickCell={setActiveCellId}
              />
              <Stack direction="row" sx={{ mt: 1.5, justifyContent: 'flex-end' }}>
                <PrimaryAction
                  onClick={() => onNote(`Заглушка: ячейка ${activeCell.code} записана`)}
                  disabledReason={
                    cellQty(activeCell.id, objects, lines) === 0
                      ? 'На ячейку ничего не поставлено'
                      : undefined
                  }
                  data-testid="objects-commit"
                >
                  Записать ячейку
                </PrimaryAction>
              </Stack>
            </Paper>
          ) : null}
        </Stack>
      </Stack>

      <BoxLabelPrintDialog
        open={printing !== null}
        title={printing ? `Печать стикера: ${printing}` : ''}
        description="Выберите размер этикетки. Напечатанное не отменить."
        scope="label"
        onClose={() => setPrinting(null)}
        onConfirm={(size) => {
          onNote(`Заглушка: ${printing}, этикетка ${size.label} — принтера в макете нет`)
          setPrinting(null)
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
          onNote(`Заглушка: ячейка ${code} создана только в макете`)
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
                ? productById(asking.line.productId).name
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
