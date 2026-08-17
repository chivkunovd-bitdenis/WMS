import { useEffect, useState } from 'react'
import { Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, Typography } from '@mui/material'
import PrintOutlinedIcon from '@mui/icons-material/PrintOutlined'
import {
  loadLabelSizeId,
  resolveLabelSize,
  type LabelSize,
  type LabelSizeScope,
} from '../utils/labelSize'
import { LabelSizeSelect } from './LabelSizeSelect'

type Props = {
  open: boolean
  title: string
  description?: string
  busy?: boolean
  /** Раздельное запоминание последнего выбранного размера, см. utils/labelSize.ts. */
  scope?: LabelSizeScope
  onClose: () => void
  onConfirm: (size: LabelSize) => void
  testId?: string
}

/**
 * Единый диалог печати штрихкода/QR короба или грузоместа: выбор физического
 * размера этикетки (дефолт 58×40) перед печатью — вместо мгновенной печати
 * листом A4. Используется в отгрузке на МП и в приёмке.
 */
export function BoxLabelPrintDialog({
  open,
  title,
  description,
  busy = false,
  scope = 'default',
  onClose,
  onConfirm,
  testId = 'box-label-print-dialog',
}: Props) {
  const [labelSize, setLabelSize] = useState<LabelSize>(() => resolveLabelSize(loadLabelSizeId(scope)))

  useEffect(() => {
    if (open) {
      setLabelSize(resolveLabelSize(loadLabelSizeId(scope)))
    }
  }, [open, scope])

  return (
    <Dialog open={open} onClose={busy ? undefined : onClose} maxWidth="xs" fullWidth data-testid={testId}>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 0.5 }}>
          {description ? (
            <Typography variant="body2" color="text.secondary">
              {description}
            </Typography>
          ) : null}
          <LabelSizeSelect
            value={labelSize.id}
            onChange={setLabelSize}
            scope={scope}
            disabled={busy}
            testId={`${testId}-size`}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          Отмена
        </Button>
        <Button
          variant="contained"
          startIcon={<PrintOutlinedIcon />}
          disabled={busy}
          onClick={() => onConfirm(labelSize)}
          data-testid={`${testId}-confirm`}
        >
          Печать
        </Button>
      </DialogActions>
    </Dialog>
  )
}
