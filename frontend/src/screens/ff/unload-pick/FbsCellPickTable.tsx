import { useState, type ReactNode } from 'react'
import { Box, ListItemButton, Stack, Typography } from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import GridViewOutlined from '@mui/icons-material/GridViewOutlined'
import Inventory2Outlined from '@mui/icons-material/Inventory2Outlined'
import LayersOutlined from '@mui/icons-material/LayersOutlined'
import WidgetsOutlined from '@mui/icons-material/WidgetsOutlined'
import UndoOutlined from '@mui/icons-material/UndoOutlined'
import { DataTable, IconAction, NumberInput, QtyCell } from '../../../ui-kit'
import type { Column } from '../../../ui-kit'
import { ProductPhotoThumb } from '../../../components/ProductPhotoThumb'
import { cellPickRowsOf, type CellPickRow, type PickPlace, type PickRow } from './pickRows'
import type { Cell, WarehouseObject } from './pickStub'
import { FboKizCount, FboKizList } from './fboPickKiz'
import { kizCodesOfProduct, kizCountsByProduct, type FboKizCode } from './fboKizData'
import { FboPrintCheckbox } from './FboPrintCheckbox'
import { printBranchKeys, type FboPrintSelection } from './fboPickPrint'

const ICONS = {
  cell: <GridViewOutlined fontSize="small" color="action" />,
  pallet: <LayersOutlined fontSize="small" color="action" />,
  box: <Inventory2Outlined fontSize="small" color="action" />,
  cargo_place: <WidgetsOutlined fontSize="small" color="action" />,
}

/**
 * WMS-686: то, что отгрузка FBO добавляет к таблице подбора по ячейкам. Без этого
 * параметра таблица такая же, как в подборе поставки FBS (WMS-637, WMS-709).
 */
export type FbsCellPickFbo = {
  printSelection?: FboPrintSelection
  /** Свёрнутые ячейки и короба; по умолчанию всё раскрыто. */
  collapsed: Set<string>
  onToggleCollapsed: (key: string) => void
  /** КИЗ, привязанные к товарам отгрузки. */
  kizCodes: FboKizCode[]
  /** Товары с включённым Честным знаком: у них число КИЗ видно и при нуле. */
  markingProducts: Set<string>
  /** Товары, под которыми открыт список КИЗ: один список на товар, под его первой строкой. */
  kizOpen: Set<string>
  onToggleKiz: (productId: string) => void
  onKizReprint: (code: FboKizCode) => Promise<void>
  onKizRemove: (code: FboKizCode) => Promise<void>
}

/** Строка со списком КИЗ под строкой товара (только FBO). */
type KizListItem = { kind: 'kiz'; key: string; depth: number; productId: string }
type TableItem = CellPickRow | KizListItem

/**
 * FBO: свернуть ячейки/короба и вставить список КИЗ под открытыми товарами.
 * Ячейка (глубина 0) и короб (глубина больше) прячут всё, что глубже них.
 */
function applyFbo(items: CellPickRow[], fbo: FbsCellPickFbo): TableItem[] {
  const result: TableItem[] = []
  let hiddenBelow: number | null = null
  const listed = new Set<string>()
  for (const item of items) {
    if (hiddenBelow !== null) {
      if (item.depth > hiddenBelow) continue
      hiddenBelow = null
    }
    result.push(item)
    if ((item.kind === 'cell' || item.kind === 'object') && fbo.collapsed.has(item.key)) hiddenBelow = item.depth
    if (item.kind === 'goods' && fbo.kizOpen.has(item.row.product.id) && !listed.has(item.row.product.id)) {
      listed.add(item.row.product.id)
      result.push({ kind: 'kiz', key: `kiz|${item.key}`, depth: item.depth, productId: item.row.product.id })
    }
  }
  return result
}

/** FBO: товар подобран полностью, а у короба/ячейки с него нечего больше брать — строка серая. */
function isMutedItem(item: TableItem): boolean {
  if (item.kind !== 'goods') return false
  if (item.row.plan > 0 && item.row.left === 0) return true
  return Boolean(item.place && item.place.picked > 0 && item.place.left === 0)
}

export function FbsCellPickTable({
  rows,
  objects,
  cells,
  source,
  onQtyChange,
  canUndo,
  onUndo,
  fbo,
}: {
  rows: PickRow[]
  objects: WarehouseObject[]
  cells: Cell[]
  source: string | null
  onQtyChange: (row: PickRow, place: PickPlace, next: number | null) => void
  canUndo: (row: PickRow, place: PickPlace | null) => boolean
  onUndo: (row: PickRow) => void
  /** Только отгрузка FBO; для поставки FBS не передаётся. */
  fbo?: FbsCellPickFbo
}) {
  // WMS-709: раздел «Уже подобрано» свёрнут, пока его не раскроют.
  const [pickedOpen, setPickedOpen] = useState(false)
  const visibleRows = cellPickRowsOf(rows, objects, cells)
    .filter((item) => pickedOpen || !(item.kind === 'goods' && item.alreadyPicked))
  const displayRows: TableItem[] = fbo ? applyFbo(visibleRows, fbo) : visibleRows
  const kizCounts = fbo ? kizCountsByProduct(fbo.kizCodes) : null
  // FBO: подобранная строка — приглушённый серый текст, но читаемый.
  const dim = (item: TableItem, node: ReactNode): ReactNode =>
    fbo && isMutedItem(item) ? <Box sx={{ opacity: 0.55 }}>{node}</Box> : node
  // Столбцы называет владелец задачи WMS-610: «Остаток в коробе», «Собрать»,
  // «Собрано». Отмена последней правки живёт в той же ячейке справа от поля,
  // чтобы не заводить отдельную пустую колонку правее «Собрано».
  const columns: Column<TableItem>[] = [
    {
      key: 'what',
      header: 'Ячейка / тара / товар',
      render: (item) => item.kind === 'kiz' && fbo ? (
        // FBO: список КИЗ товара — под его строкой, обычными отступами темы.
        <Box
          sx={{ pl: `${item.depth * 22}px`, borderLeft: '1px solid', borderColor: 'divider', minWidth: 0 }}
        >
          <FboKizList
            codes={kizCodesOfProduct(fbo.kizCodes, item.productId)}
            onReprint={fbo.onKizReprint}
            onRemove={fbo.onKizRemove}
            testId={`pick-kiz-list-${item.productId}`}
          />
        </Box>
      ) : item.kind === 'kiz' ? null : (
        <Stack
          direction="row"
          spacing={1}
          sx={{
            alignItems: 'center',
            minHeight: 36,
            pl: `${item.depth * 22}px`,
            borderLeft: item.depth ? '1px solid' : 'none',
            borderColor: 'divider',
            ...(item.kind === 'goods' && fbo && isMutedItem(item) ? { opacity: 0.55 } : null),
          }}
          data-testid={`fbs-pick-item-${item.key}`}
        >
          {item.kind === 'goods' ? (
            <>
              <ProductPhotoThumb src={item.row.product.photo} alt={item.row.product.name} size={32} />
              <Stack sx={{ minWidth: 0 }}>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>{item.row.product.name}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {item.row.product.sellerArticle ? `${item.row.product.sellerArticle} · ` : ''}
                  {item.row.product.sku}
                  {!item.place ? ' · Нет на складе' : ''}
                </Typography>
              </Stack>
            </>
          ) : item.kind === 'picked' ? (
            <ListItemButton
              dense
              onClick={() => setPickedOpen((open) => !open)}
              aria-expanded={pickedOpen}
              sx={{ px: 0, py: 0.5, gap: 1, flexGrow: 0 }}
              data-testid="fbs-pick-already-picked-toggle"
            >
              <ExpandMoreIcon fontSize="small" color="action" sx={{ transform: pickedOpen ? 'rotate(180deg)' : 'none' }} />
              <Typography variant="body2" sx={{ fontWeight: 700 }}>
                {item.title}
                <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                  {item.qty} шт
                </Typography>
              </Typography>
            </ListItemButton>
          ) : (
            <>
              {fbo?.printSelection ? <FboPrintCheckbox
                selection={fbo.printSelection}
                keys={printBranchKeys(rows, item.key, objects, cells)}
                label={item.title}
              /> : null}
              {fbo ? (
                <IconAction
                  title={`${fbo.collapsed.has(item.key) ? 'Развернуть' : 'Свернуть'} ${item.title}`}
                  onClick={() => fbo.onToggleCollapsed(item.key)}
                  testId={`fbs-pick-collapse-${item.key}`}
                >
                  <ExpandMoreIcon
                    fontSize="small"
                    sx={{
                      transition: 'transform 120ms',
                      transform: fbo.collapsed.has(item.key) ? 'none' : 'rotate(180deg)',
                    }}
                  />
                </IconAction>
              ) : null}
              {item.kind === 'cell'
                ? ICONS.cell
                : item.objectKind ? ICONS[item.objectKind] : null}
              <Typography variant="body2" sx={{ fontWeight: item.kind === 'cell' ? 700 : 600 }}>
                {item.title}
                <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                  {item.qty} шт
                </Typography>
              </Typography>
            </>
          )}
        </Stack>
      ),
    },
    {
      key: 'barcode', header: 'ШК', width: 140,
      render: (item) => {
        if (item.kind === 'kiz') return null
        const barcode = item.kind === 'goods' ? item.row.product.barcode : item.barcode
        return barcode ? dim(item, <Typography variant="body2" sx={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', whiteSpace: 'nowrap' }}>{barcode}</Typography>) : null
      },
    },
    {
      key: 'size', header: 'Размер', width: 84,
      render: (item) => item.kind === 'goods' ? dim(item, item.row.product.size) : null,
    },
    {
      // WMS-709: «План» — сколько товара нужно в поставку всего; одинаков во
      // всех строках товара.
      key: 'plan', header: 'План', align: 'right', width: 72,
      render: (item) => item.kind === 'goods' ? dim(item, <QtyCell value={item.row.plan} muted />) : null,
    },
    {
      // WMS-709: «Осталось» — план минус снятое со всех мест товара. Меняется
      // сразу, как только в любой строке этого товара меняют «Собрано».
      key: 'left', header: 'Осталось', align: 'right', width: 96,
      render: (item) => item.kind === 'goods' ? dim(item, <QtyCell value={item.row.left} />) : null,
    },
    ...(fbo && kizCounts ? [{
      // WMS-686: сколько КИЗ привязано к товару в этой отгрузке (счёт кодов, не отдельный
      // счётчик). Клик раскрывает под товаром список кодов, повторный клик скрывает.
      key: 'kiz', header: 'КИЗ', align: 'right' as const, width: 88,
      render: (item: TableItem) => {
        if (item.kind !== 'goods') return null
        const count = kizCounts.get(item.row.product.id) ?? 0
        // Число видно, если у товара включён ЧЗ или КИЗ уже есть; иначе ячейка пуста (R3).
        if (count === 0 && !fbo.markingProducts.has(item.row.product.id)) return null
        return (
          <FboKizCount
            count={count}
            open={fbo.kizOpen.has(item.row.product.id)}
            onToggle={() => fbo.onToggleKiz(item.row.product.id)}
            productName={item.row.product.name}
            testId={`pick-kiz-count-${item.row.product.id}-${item.place?.key ?? 'none'}`}
          />
        )
      },
    }] : []),
    {
      // «Остаток в коробе» — физический остаток именно того места, откуда
      // снимаем (короб, палета или сама ячейка при россыпи). Значение уже
      // приходит без вычетов текущей смены, повторно отнимать «Собрано» нельзя.
      key: 'inBox',
      header: <Box sx={{ whiteSpace: 'normal', lineHeight: 1.15 }}>Остаток<br />в коробе</Box>,
      align: 'right', width: 112,
      render: (item) => item.kind === 'goods' && item.place ? dim(item, <QtyCell value={item.place.qty} />) : null,
    },
    {
      // «Собрано» — редактируемое поле по конкретному месту: сколько уже снято
      // с этого короба/палеты/россыпи. Верхняя граница — сколько ещё можно снять
      // отсюда с учётом плана товара (та же логика, что была у столбца «Снять»).
      // Отмена последней правки живёт здесь же, справа от поля: без отдельной
      // колонки правее и без «пустой» ячейки в шапке.
      key: 'picked', header: 'Собрано', align: 'right', width: 132,
      render: (item) => {
        if (item.kind !== 'goods' || !item.place || item.alreadyPicked) return null
        const ceiling = item.place.picked + Math.min(item.place.left, item.row.left)
        return (
          <Stack
            direction="row"
            spacing={0.5}
            sx={{ alignItems: 'center', justifyContent: 'flex-end', ...(fbo && isMutedItem(item) ? { opacity: 0.55 } : null) }}
          >
            <Box sx={{ width: 84 }}>
              <NumberInput
                label="Собрано"
                hideLabel
                value={item.place.picked}
                onChange={(next) => onQtyChange(item.row, item.place!, next)}
                min={0}
                max={ceiling}
                testId={`pick-place-qty-${item.row.product.id}-${item.place.key}`}
              />
            </Box>
            {canUndo(item.row, item.place) ? (
              <IconAction
                title={`Отменить последнее снятие: ${item.row.product.sku}`}
                onClick={() => onUndo(item.row)}
                testId={`pick-undo-${item.row.product.id}-${item.place.key}`}
              >
                <UndoOutlined fontSize="small" />
              </IconAction>
            ) : null}
          </Stack>
        )
      },
    },
  ]
  return <DataTable
    columns={columns}
    rows={displayRows}
    getRowKey={(item) => item.key}
    fixedLayout
    pageStickyHeader
    selectedKey={source}
    testId="fbs-cell-pick-table"
    empty={{ title: 'В отгрузке нет товаров', hint: 'Добавьте товары в план отгрузки — снимать пока нечего.' }}
  />
}
