import { useEffect, useRef, useState } from 'react'
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
import { cellPickRowsOf, isPlanDone, type CellPickRow, type PickPlace, type PickRow } from './pickRows'
import type { Cell, WarehouseObject } from './pickStub'

const ICONS = {
  cell: <GridViewOutlined fontSize="small" color="action" />,
  pallet: <LayersOutlined fontSize="small" color="action" />,
  box: <Inventory2Outlined fontSize="small" color="action" />,
  cargo_place: <WidgetsOutlined fontSize="small" color="action" />,
}

export function FbsCellPickTable({
  rows,
  objects,
  cells,
  source,
  scrollTo,
  onQtyChange,
  canUndo,
  onUndo,
}: {
  rows: PickRow[]
  objects: WarehouseObject[]
  cells: Cell[]
  source: string | null
  /**
   * WMS-709 R10: строка, к которой надо прокрутить экран один раз. Новый объект
   * означает новый запрос: при скане ячейки или тары экран прокручивается к её
   * строке, а при скане товара и правке «Собрано» — нет.
   */
  scrollTo?: { key: string } | null
  onQtyChange: (row: PickRow, place: PickPlace, next: number | null) => void
  canUndo: (row: PickRow, place: PickPlace | null) => boolean
  onUndo: (row: PickRow) => void
}) {
  // WMS-709: раздел «Уже подобрано» свёрнут, пока его не раскроют.
  const [pickedOpen, setPickedOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)
  const displayRows = cellPickRowsOf(rows, objects, cells, { hideUntouchedOfDone: true })
    .filter((item) => pickedOpen || !(item.kind === 'goods' && item.alreadyPicked))
  useEffect(() => {
    if (!scrollTo) return
    const target = Array.from(wrapRef.current?.querySelectorAll<HTMLElement>('tr[data-row-key]') ?? [])
      .find((row) => row.dataset.rowKey === scrollTo.key)
    target?.scrollIntoView({ block: 'center' })
  }, [scrollTo])
  // Столбцы называет владелец задачи WMS-610: «Остаток в коробе», «Собрать»,
  // «Собрано». Отмена последней правки живёт в той же ячейке справа от поля,
  // чтобы не заводить отдельную пустую колонку правее «Собрано».
  const columns: Column<CellPickRow>[] = [
    {
      key: 'what',
      header: 'Ячейка / тара / товар',
      render: (item) => (
        <Stack
          direction="row"
          spacing={1}
          sx={{
            alignItems: 'center',
            minHeight: 36,
            pl: `${item.depth * 22}px`,
            borderLeft: item.depth ? '1px solid' : 'none',
            borderColor: 'divider',
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
        const barcode = item.kind === 'goods' ? item.row.product.barcode : item.barcode
        return barcode ? <Typography variant="body2" sx={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', whiteSpace: 'nowrap' }}>{barcode}</Typography> : null
      },
    },
    {
      key: 'size', header: 'Размер', width: 84,
      render: (item) => item.kind === 'goods' ? item.row.product.size : null,
    },
    {
      // WMS-709: «План» — сколько товара нужно в поставку всего; одинаков во
      // всех строках товара.
      key: 'plan', header: 'План', align: 'right', width: 72,
      render: (item) => item.kind === 'goods' ? <QtyCell value={item.row.plan} muted /> : null,
    },
    {
      // WMS-709: «Осталось подобрать» — план минус снятое со всех мест товара.
      // Меняется сразу, как только в любой строке этого товара меняют «Собрано».
      // Шапка таблицы не переносит строки сама, поэтому перенос задан здесь.
      key: 'left',
      header: <Box sx={{ whiteSpace: 'normal', lineHeight: 1.15 }}>Осталось подобрать</Box>,
      align: 'right', width: 96,
      render: (item) => item.kind === 'goods' ? <QtyCell value={item.row.left} /> : null,
    },
    {
      // «Остаток в коробе» — физический остаток именно того места, откуда
      // снимаем (короб, палета или сама ячейка при россыпи). Значение уже
      // приходит без вычетов текущей смены, повторно отнимать «Собрано» нельзя.
      key: 'inBox',
      header: <Box sx={{ whiteSpace: 'normal', lineHeight: 1.15 }}>Остаток<br />в коробе</Box>,
      align: 'right', width: 112,
      render: (item) => item.kind === 'goods' && item.place ? <QtyCell value={item.place.qty} /> : null,
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
          <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', justifyContent: 'flex-end' }}>
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
  return <Box ref={wrapRef}>
    <DataTable
      columns={columns}
      rows={displayRows}
      getRowKey={(item) => item.key}
      // WMS-709 R3: зелёным подсвечиваются только места собранного товара, с
      // которых в этом подборе снимали. Заголовки ячеек и тары и строки раздела
      // «Уже подобрано» не подсвечиваются.
      isComplete={(item) => item.kind === 'goods' && !item.alreadyPicked
        && Boolean(item.place) && (item.place?.picked ?? 0) > 0 && isPlanDone(item.row)}
      fixedLayout
      pageStickyHeader
      selectedKey={source}
      testId="fbs-cell-pick-table"
      empty={{ title: 'В отгрузке нет товаров', hint: 'Добавьте товары в план отгрузки — снимать пока нечего.' }}
    />
  </Box>
}
