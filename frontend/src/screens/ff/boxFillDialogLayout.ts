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

export const boxFillQtyCellSx: SxProps<Theme> = {
  width: 88,
  minWidth: 88,
  whiteSpace: 'nowrap',
  px: 1,
  verticalAlign: 'top',
}
