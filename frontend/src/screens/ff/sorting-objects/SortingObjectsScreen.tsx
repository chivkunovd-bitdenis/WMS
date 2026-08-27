import { Box, Paper, Stack, Typography } from '@mui/material'
import { alpha, useTheme } from '@mui/material/styles'
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
import { ObjectsTree } from './ObjectsTree'
import {
  CELLS,
  INITIAL_LINES,
  INITIAL_OBJECTS,
  KIND_TITLE,
  cellQty,
  cellRef,
  productById,
  type Cell,
  type GoodsLine,
  type Holder,
  type ObjKind,
  type WarehouseObject,
} from './objectsStub'
import { assembledRows, canPut, cellRows, creatableIn, looseRows, type Carried } from './objectsRows'

// Раскладка объектами.
//
// Порядок работы обратный привычному: сначала собираем объект — кладём товар в
// короб, короб на палету, — и только готовый объект ставим на полку. Где лежит
// товар, отдельно не хранится: это вычисляется по цепочке держателей, поэтому
// «что в коробе» и «где короб» не могут разъехаться. Это одно знание.


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
  const [asking, setAsking] = useState<{ line: GoodsLine; target: Holder; label: string } | null>(null)
  const [askQty, setAskQty] = useState<number | null>(null)
  // Счётчик номеров живёт в состоянии: переменная вне компонента менялась бы
  // во время отрисовки, а это побочный эффект и непредсказуемый порядок.
  const [created, setCreated] = useState(0)

  const activeCell = CELLS.find((one) => one.id === activeCellId) ?? null
  const loose = lines.filter((line) => line.holder === null)
  const looseQty = loose.reduce((sum, line) => sum + line.qty, 0)
  const unplaced = objects.filter((one) => one.holder === null)

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

  function put(target: Holder, label: string) {
    if (!carried) return
    if (!canPut(carried, target, objects)) {
      setCarried(null)
      return
    }
    if (carried.kind === 'goods') {
      // Количество спрашиваем всегда: перетащить — не значит «высыпать всё».
      setAsking({ line: carried.line, target, label })
      setAskQty(carried.line.qty)
    } else {
      const moving = carried.object
      setObjects((current) => current.map((one) => (one.id === moving.id ? { ...one, holder: target } : one)))
      onNote(`${KIND_TITLE[moving.kind]} ${moving.code} → ${label}`)
    }
    setCarried(null)
  }

  function nextNumber() {
    const value = created + 1
    setCreated(value)
    return value
  }

  function createObject(kind: ObjKind) {
    const created = nextNumber()
    const code =
      kind === 'pallet'
        ? `П-${String(200 + created).padStart(6, '0')}`
        : kind === 'box'
          ? `КР-${String(500 + created).padStart(6, '0')}`
          : `ГМ-${String(400 + created).padStart(6, '0')}`
    setObjects((current) => [
      ...current,
      { id: `new-${created}`, kind, code, barcode: `29${String(created).padStart(11, '0')}`, holder: null },
    ])
    onNote(`Заглушка: создан ${KIND_TITLE[kind].toLowerCase()} ${code}`)
  }

  function handleScan(code: string) {
    setScanValue('')
    const cell = CELLS.find((one) => one.barcode === code || one.code.toLowerCase() === code.toLowerCase())
    if (cell) {
      setActiveCellId(cell.id)
      setScanError(null)
      setScanNotice(`Ячейка ${cell.code} — ставьте объект`)
      return
    }
    const object = objects.find((one) => one.barcode === code)
    if (object) {
      if (!activeCell) {
        setScanNotice(null)
        setScanError('Сначала пикните ячейку — иначе непонятно, куда ставим')
        return
      }
      setObjects((current) =>
        current.map((one) => (one.id === object.id ? { ...one, holder: cellRef(activeCell.id) } : one)),
      )
      setScanError(null)
      setScanNotice(`${KIND_TITLE[object.kind]} ${object.code} → ячейка ${activeCell.code}`)
      return
    }
    setScanNotice(null)
    setScanError(`Штрихкод ${code} — ни ячейка, ни объект этой приёмки`)
  }

  const cellDropReady = Boolean(carried && activeCell)

  return (
    <Box data-testid="sorting-objects-screen">
      <ScreenHeader
        title="Раскладка по ячейкам"
        purpose="Собираем объект — товар в короб, короб на палету — и ставим готовый объект на полку."
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
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
            <StatusChip
              label={
                unplaced.length + loose.length === 0
                  ? 'всё расставлено'
                  : `осталось поставить: ${unplaced.length} объектов и ${loose.length} позиций россыпью`
              }
              tone={unplaced.length + loose.length === 0 ? 'ok' : 'warn'}
              testId="objects-total"
            />
            <Typography variant="body2" color="text.secondary">
              россыпью {looseQty} шт
            </Typography>
          </Stack>
        </Stack>
      </Paper>

      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} sx={{ alignItems: 'flex-start' }}>
        <Stack spacing={2} sx={{ flexGrow: 1, minWidth: 0, width: '100%' }}>
          <Paper
            variant="outlined"
            sx={{ p: 2 }}
            onDragOver={(event) => {
              if (carried) event.preventDefault()
            }}
            onDrop={() => put(null, 'россыпь')}
            data-testid="objects-loose"
          >
            <Typography variant="subtitle1" sx={{ mb: 1 }}>
              Товары россыпью
            </Typography>
            <ObjectsTree
              rows={looseRows(lines)}
              carried={carried}
              objects={objects}
              placeLabel={activeCell ? `ячейку ${activeCell.code}` : null}
              testId="objects-loose-tree"
              empty={{ title: 'Россыпью ничего не осталось', hint: 'Всё убрано в короба или на полки.' }}
              onToggle={toggle}
              onDragStart={(row) => setCarried(row.kind === 'goods' ? { kind: 'goods', line: row.line } : { kind: 'object', object: row.object })}
              onDragEnd={() => setCarried(null)}
              onDropOn={(target) => put(target, 'объект')}
              onPlace={(row) => {
                if (!activeCell || row.kind !== 'goods') return
                setAsking({ line: row.line, target: cellRef(activeCell.id), label: `ячейку ${activeCell.code}` })
                setAskQty(row.line.qty)
              }}
              onTakeOut={(row) => {
                if (row.kind === 'goods') moveGoods(row.line, row.line.qty, null)
              }}
            />
          </Paper>

          <Paper variant="outlined" sx={{ p: 2 }} data-testid="objects-assembled">
            <Stack direction="row" spacing={1} sx={{ mb: 1, alignItems: 'center', flexWrap: 'wrap' }}>
              <Typography variant="subtitle1">Короба, палеты и грузоместа</Typography>
              <Box sx={{ flexGrow: 1 }} />
              {creatableIn(null, objects).map((kind) => (
                <SecondaryAction
                  key={kind}
                  onClick={() => createObject(kind)}
                  data-testid={`objects-create-${kind}`}
                >
                  {kind === 'pallet' ? 'Новая палета' : kind === 'box' ? 'Новый короб' : 'Новое грузоместо'}
                </SecondaryAction>
              ))}
            </Stack>
            <ObjectsTree
              rows={assembledRows(objects, lines, collapsed)}
              carried={carried}
              objects={objects}
              placeLabel={activeCell ? `ячейку ${activeCell.code}` : null}
              testId="objects-tree"
              empty={{
                title: 'Собранных объектов нет',
                hint: 'Создайте палету или короб и перетащите в них товар.',
              }}
              onToggle={toggle}
              onDragStart={(row) => setCarried(row.kind === 'goods' ? { kind: 'goods', line: row.line } : { kind: 'object', object: row.object })}
              onDragEnd={() => setCarried(null)}
              onDropOn={(target) => put(target, 'объект')}
              onPlace={(row) => {
                if (!activeCell) return
                if (row.kind === 'object') {
                  setObjects((current) =>
                    current.map((one) =>
                      one.id === row.object.id ? { ...one, holder: cellRef(activeCell.id) } : one,
                    ),
                  )
                  onNote(`${KIND_TITLE[row.object.kind]} ${row.object.code} → ячейка ${activeCell.code}`)
                } else {
                  setAsking({ line: row.line, target: cellRef(activeCell.id), label: `ячейку ${activeCell.code}` })
                  setAskQty(row.line.qty)
                }
              }}
              onTakeOut={(row) => {
                if (row.kind === 'goods') moveGoods(row.line, row.line.qty, null)
                else setObjects((current) => current.map((one) => (one.id === row.object.id ? { ...one, holder: null } : one)))
              }}
            />
          </Paper>
        </Stack>

        <Stack spacing={2} sx={{ width: { lg: 340 }, flexShrink: 0, minWidth: 0 }}>
          <Paper variant="outlined" sx={{ p: 2 }} data-testid="objects-cells">
            <Typography variant="subtitle1" sx={{ mb: 1 }}>
              Ячейки склада
            </Typography>
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 1 }}>
              {CELLS.map((cell) => {
                const active = activeCellId === cell.id
                const qty = cellQty(cell.id, objects, lines)
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
                      if (carried) event.preventDefault()
                    }}
                    onDrop={() => {
                      setActiveCellId(cell.id)
                      put(cellRef(cell.id), `ячейку ${cell.code}`)
                    }}
                    data-testid={`objects-cell-${cell.id}`}
                    sx={{
                      px: 1.25,
                      py: 0.6,
                      borderRadius: 2,
                      cursor: 'pointer',
                      border: '1px solid',
                      borderColor: active ? 'primary.main' : 'divider',
                      backgroundColor: active ? alpha(theme.palette.primary.main, 0.12) : 'background.paper',
                      outline: carried && !active ? `1px dashed ${alpha(theme.palette.primary.main, 0.45)}` : 'none',
                      outlineOffset: '-3px',
                    }}
                  >
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>
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
                outline: cellDropReady ? `2px dashed ${alpha(theme.palette.primary.main, 0.5)}` : 'none',
                outlineOffset: '-4px',
              }}
              onDragOver={(event) => {
                if (carried) event.preventDefault()
              }}
              onDrop={() => put(cellRef(activeCell.id), `ячейку ${activeCell.code}`)}
              data-testid="objects-active-cell"
            >
              <Stack direction="row" spacing={1} sx={{ mb: 1, alignItems: 'center' }}>
                <Typography variant="h6">{activeCell.code}</Typography>
                <StatusChip
                  label={`${cellQty(activeCell.id, objects, lines)} шт`}
                  tone={cellQty(activeCell.id, objects, lines) > 0 ? 'ok' : 'neutral'}
                />
              </Stack>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Количество на ячейке считается по составу объектов, которые на ней стоят.
              </Typography>
              <ObjectsTree
                rows={cellRows(activeCell as Cell, objects, lines, collapsed)}
                carried={carried}
                objects={objects}
                placeLabel={null}
                testId="objects-cell-tree"
                empty={{ title: 'На ячейке пусто', hint: 'Перетащите сюда объект или товар россыпью.' }}
                onToggle={toggle}
                onDragStart={(row) => setCarried(row.kind === 'goods' ? { kind: 'goods', line: row.line } : { kind: 'object', object: row.object })}
                onDragEnd={() => setCarried(null)}
                onDropOn={(target) => put(target, 'объект')}
                onPlace={() => undefined}
                onTakeOut={(row) => {
                  if (row.kind === 'goods') moveGoods(row.line, row.line.qty, null)
                  else setObjects((current) => current.map((one) => (one.id === row.object.id ? { ...one, holder: null } : one)))
                }}
              />
            </Paper>
          ) : null}
        </Stack>
      </Stack>

      <AppDialog
        open={asking !== null}
        onClose={() => setAsking(null)}
        title="Сколько переложить"
        testId="objects-qty-dialog"
        actions={
          <ActionGroup>
            <SecondaryAction onClick={() => setAsking(null)} data-testid="objects-qty-cancel">
              Отмена
            </SecondaryAction>
            <PrimaryAction
              onClick={() => {
                if (asking && askQty) moveGoods(asking.line, Math.min(askQty, asking.line.qty), asking.target)
                setAsking(null)
              }}
              data-testid="objects-qty-confirm"
            >
              Переложить
            </PrimaryAction>
          </ActionGroup>
        }
      >
        <Stack spacing={2}>
          <Stack spacing={0.5}>
            <Typography variant="subtitle2">
              {asking ? productById(asking.line.productId).name : ''}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Куда: {asking?.label ?? '—'}
            </Typography>
          </Stack>
          <NumberInput
            label="Сколько штук"
            value={askQty}
            onChange={setAskQty}
            min={1}
            max={asking?.line.qty}
            helperText={asking ? `Всего ${asking.line.qty} — можно переложить часть` : undefined}
            testId="objects-qty-input"
          />
        </Stack>
      </AppDialog>
    </Box>
  )
}
