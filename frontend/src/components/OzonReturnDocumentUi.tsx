import PrintOutlined from '@mui/icons-material/PrintOutlined'
import { Box, Stack, TableCell, TableRow, TextField, Typography } from '@mui/material'

import { PrimaryAction, SecondaryAction, StatusChip } from '../ui-kit'
import {
  OzonReturnPickerDialog,
  type OzonReturnPreviewGroup,
} from './OzonReturnPickerDialog'
import { ozonGiveoutStatus } from './ozonReturnPickerHelpers'

type ActionsProps = {
  busy: boolean
  showPickerAction: boolean
  workflow: {
    groups: OzonReturnPreviewGroup[]
    pickerOpen: boolean
    preview: { groups: OzonReturnPreviewGroup[]; message: string | null }
    previewError: string | null
    previewLoading: boolean
    closePicker: () => void
    downloadPass: () => void | Promise<void>
    importGiveouts: (giveoutIds: number[]) => void | Promise<void>
    openPicker: () => void | Promise<void>
    printReconciliation: () => void | Promise<void>
  }
}

export function OzonReturnActions({
  busy,
  showPickerAction,
  workflow,
}: ActionsProps) {
  const { groups, pickerOpen, preview, previewError, previewLoading } = workflow
  return (
    <>
      {showPickerAction ? (
        <PrimaryAction
          disabledReason={busy ? 'Дождитесь завершения операции' : undefined}
          onClick={() => void workflow.openPicker()}
          data-testid="ff-inbound-ozon-return-picker-open"
        >
          Получить возврат
        </PrimaryAction>
      ) : null}
      <SecondaryAction
        startIcon={<PrintOutlined />}
        disabledReason={busy ? 'Дождитесь завершения операции' : undefined}
        onClick={() => void workflow.downloadPass()}
        data-testid="ff-inbound-ozon-return-pass"
      >
        Печать пропуска
      </SecondaryAction>
      <SecondaryAction
        startIcon={<PrintOutlined />}
        disabledReason={
          busy
            ? 'Дождитесь завершения операции'
            : groups.length === 0
              ? 'Сначала добавьте пункт выдачи'
              : undefined
        }
        onClick={() => void workflow.printReconciliation()}
        data-testid="ff-inbound-ozon-return-reconciliation"
      >
        Печать листа сверки
      </SecondaryAction>
      {pickerOpen ? (
        <OzonReturnPickerDialog
          key={preview.groups
            .map((group) => `${group.giveout_id}:${group.already_imported}`)
            .join('|')}
          open
          busy={busy}
          loading={previewLoading}
          groups={preview.groups}
          error={previewError}
          message={preview.message}
          onClose={workflow.closePicker}
          onApply={workflow.importGiveouts}
        />
      ) : null}
    </>
  )
}

type GroupRowProps = {
  group: OzonReturnPreviewGroup
  documentDone: boolean
  colSpan: number
}

export function OzonReturnGroupRow({ group, documentDone, colSpan }: GroupRowProps) {
  const status = ozonGiveoutStatus(group.giveout_status)
  const unmatchedItems = group.items.filter((item) => !item.matched)
  const statusMismatch =
    documentDone &&
    group.giveout_status !== 'GIVEOUT_STATUS_COMPLETED' &&
    group.giveout_status !== 'completed'
  return (
    <TableRow data-testid="ff-inbound-ozon-return-group">
      <TableCell colSpan={colSpan} sx={{ bgcolor: 'action.hover', py: 1 }}>
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={1}
          useFlexGap
          sx={{ alignItems: { sm: 'center' } }}
        >
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="body2" sx={{ fontWeight: 700 }}>
              {group.warehouse_name}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {group.warehouse_address}
            </Typography>
          </Box>
          {unmatchedItems.length > 0 ? (
            <Typography variant="caption" color="warning.dark">
              Не сопоставлено с каталогом:{' '}
              {unmatchedItems
                .map((item) => `${item.product_name} × ${item.quantity}`)
                .join(' · ')}
            </Typography>
          ) : null}
          <Typography variant="caption" color="text.secondary">
            {group.items.map((item) => `${item.product_name} × ${item.quantity}`).join(' · ')}
          </Typography>
          {statusMismatch ? (
            <Typography
              variant="caption"
              color="warning.dark"
              data-testid="ff-inbound-ozon-status-mismatch"
            >
              Товар принят, но выдача в Ozon ещё не завершена.
            </Typography>
          ) : null}
          <StatusChip label={status.label} tone={status.tone} />
        </Stack>
      </TableCell>
    </TableRow>
  )
}

export function OzonReturnOrphanGroupRows({
  groups,
  documentDone,
  colSpan,
}: {
  groups: OzonReturnPreviewGroup[]
  documentDone: boolean
  colSpan: number
}) {
  return groups.map((group) => (
      <OzonReturnGroupRow
        key={group.giveout_id}
        group={group}
        documentDone={documentDone}
        colSpan={colSpan}
      />
    ))
}

export function ReturnDefectiveQtyCell({
  lineId,
  defectiveQty,
  acceptedQty,
  disabled,
  onSave,
}: {
  lineId: string
  defectiveQty: number
  acceptedQty: number
  disabled: boolean
  onSave: (lineId: string, raw: string, acceptedQty: number) => void | Promise<void>
}) {
  return (
    <TableCell align="right" sx={{ width: 120, minWidth: 0 }}>
      <TextField
        key={`defective-${lineId}-${defectiveQty}`}
        type="number"
        size="small"
        defaultValue={defectiveQty || ''}
        disabled={disabled}
        onBlur={(event) => void onSave(lineId, event.currentTarget.value, acceptedQty)}
        slotProps={{
          htmlInput: {
            min: 0,
            max: acceptedQty,
            inputMode: 'numeric',
            'data-testid': 'ff-inbound-line-defective',
          },
        }}
        sx={{ width: 96 }}
      />
    </TableCell>
  )
}
