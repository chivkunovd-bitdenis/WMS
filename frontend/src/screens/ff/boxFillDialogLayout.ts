import type { SxProps, Theme } from '@mui/material'

/** ~2× former `sm` dialog: wide, tall product table with internal scroll. */
export const boxFillDialogPaperSx: SxProps<Theme> = {
  width: '100%',
  maxWidth: { xs: '100%', sm: 720, md: 960 },
  height: { xs: 'calc(100vh - 32px)', sm: 'min(88vh, 820px)' },
  maxHeight: 'calc(100vh - 32px)',
  display: 'flex',
  flexDirection: 'column',
}

export const boxFillDialogContentSx: SxProps<Theme> = {
  display: 'flex',
  flexDirection: 'column',
  flex: 1,
  minHeight: 0,
  overflow: 'hidden',
  p: 2,
}

export const boxFillTableScrollSx: SxProps<Theme> = {
  flex: 1,
  minHeight: { xs: 280, sm: 420 },
  overflow: 'auto',
  border: 1,
  borderColor: 'divider',
  borderRadius: 1,
}

export const boxFillProductCellSx: SxProps<Theme> = {
  minWidth: 0,
  verticalAlign: 'top',
  '& .MuiTypography-root': {
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    display: 'block',
  },
}

// Колонка ввода количества прижата к правому краю: строка товара рисуется общим
// FfProductLineCells на шесть колонок, и таблица шире диалога (maxWidth 960 на десктопе,
// 720 на планшете) — без прилипания поле ввода уезжает за край горизонтальной прокрутки,
// а это единственное, ради чего диалог открывают.
export const boxFillQtyCellSx: SxProps<Theme> = {
  width: 88,
  minWidth: 88,
  whiteSpace: 'nowrap',
  px: 1,
  verticalAlign: 'top',
  position: 'sticky',
  right: 0,
  zIndex: 1,
  bgcolor: 'background.paper',
  borderLeft: '1px solid',
  borderLeftColor: 'divider',
}

// У шапки таблицы уже включён stickyHeader (прилипание сверху). Угловая ячейка прилипает
// в обе стороны сразу, поэтому ей нужен z-index выше и тела строк, и обычной шапки.
export const boxFillQtyHeadCellSx: SxProps<Theme> = {
  ...(boxFillQtyCellSx as Record<string, unknown>),
  zIndex: 3,
}
