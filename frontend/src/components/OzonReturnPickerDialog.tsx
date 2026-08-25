import { useMemo, useState } from 'react'
import {
  Alert,
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  Checkbox,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import ExpandMoreOutlined from '@mui/icons-material/ExpandMoreOutlined'
import { ProductPhotoThumb } from './ProductPhotoThumb'
import { StatusChip } from '../ui-kit'
import {
  filterOzonReturnGroups,
  formatOzonUtilizationDate,
  isOzonReturnUrgent,
  ozonGiveoutStatus,
} from './ozonReturnPickerHelpers'

export type OzonReturnPreviewItem = {
  inbound_line_id?: string | null
  return_id: number | null
  product_id: string | null
  return_barcode: string | null
  offer_id: string | null
  ozon_sku: number | null
  product_name: string
  quantity: number
  approved?: boolean
  return_reason_name: string | null
  wms_sku: string | null
  wms_barcode: string | null
  image_url?: string | null
  matched: boolean
  warning: string | null
}

export type OzonReturnPreviewGroup = {
  giveout_id: number
  giveout_status: string
  warehouse_name: string
  warehouse_address: string
  approved_articles_count: number
  total_articles_count: number
  storage_days: number | null
  utilization_forecast_date: string | null
  already_imported: boolean
  items: OzonReturnPreviewItem[]
}

type Props = {
  open: boolean
  busy: boolean
  loading: boolean
  groups: OzonReturnPreviewGroup[]
  error?: string | null
  message?: string | null
  onClose: () => void
  onApply: (giveoutIds: number[]) => void | Promise<void>
}

function selectedItemsCount(groups: OzonReturnPreviewGroup[], selectedIds: Set<number>): number {
  return groups.reduce(
    (total, group) =>
      selectedIds.has(group.giveout_id)
        ? total + group.items.reduce((sum, item) => sum + item.quantity, 0)
        : total,
    0,
  )
}

export function OzonReturnPickerDialog({
  open,
  busy,
  loading,
  groups,
  error = null,
  message = null,
  onClose,
  onApply,
}: Props) {
  const [search, setSearch] = useState('')
  const [selectedGiveoutIds, setSelectedGiveoutIds] = useState<Set<number>>(
    () =>
      new Set(groups.filter((group) => group.already_imported).map((group) => group.giveout_id)),
  )

  const filteredGroups = useMemo(() => filterOzonReturnGroups(groups, search), [groups, search])
  const newSelectedGiveoutIds = useMemo(
    () =>
      groups
        .filter((group) => selectedGiveoutIds.has(group.giveout_id) && !group.already_imported)
        .map((group) => group.giveout_id),
    [groups, selectedGiveoutIds],
  )
  const selectedPointsCount = selectedGiveoutIds.size
  const selectedArticlesCount = selectedItemsCount(groups, selectedGiveoutIds)
  const canApply = newSelectedGiveoutIds.length > 0

  const toggleGiveout = (group: OzonReturnPreviewGroup, checked: boolean) => {
    if (group.already_imported) return
    setSelectedGiveoutIds((current) => {
      const next = new Set(current)
      if (checked) next.add(group.giveout_id)
      else next.delete(group.giveout_id)
      return next
    })
  }

  const selectAll = () => {
    setSelectedGiveoutIds(new Set(groups.map((group) => group.giveout_id)))
  }

  const close = () => {
    if (!busy) onClose()
  }

  return (
    <Dialog
      open={open}
      onClose={close}
      maxWidth={false}
      fullWidth
      slotProps={{
        paper: { sx: { width: 'min(1200px, 96vw)', maxHeight: '92vh' } },
      }}
      data-testid="ozon-return-picker"
    >
      <DialogTitle>Возвраты Ozon</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2} sx={{ mb: 2 }}>
          {error ? (
            <Alert severity="error" data-testid="ozon-return-picker-error">
              {error}
            </Alert>
          ) : null}
          {message ? (
            <Alert severity="info" data-testid="ozon-return-picker-message">
              {message}
            </Alert>
          ) : null}
          <Stack
            direction={{ xs: 'column', md: 'row' }}
            spacing={1}
            sx={{ alignItems: { md: 'center' } }}
          >
            <TextField
              label="Поиск по названию, артикулу или ШК возврата"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              size="small"
              fullWidth
              disabled={loading || busy}
              slotProps={{
                htmlInput: { 'data-testid': 'ozon-return-picker-search' },
              }}
            />
            <Button
              variant="outlined"
              disabled={loading || busy || groups.length === 0}
              onClick={selectAll}
              data-testid="ozon-return-picker-select-all"
            >
              Выбрать все пункты
            </Button>
            <Typography
              variant="body2"
              sx={{ whiteSpace: 'nowrap', fontWeight: 700 }}
              data-testid="ozon-return-picker-selected-count"
            >
              Выбрано пунктов: {selectedPointsCount} · товаров: {selectedArticlesCount}
            </Typography>
          </Stack>
        </Stack>

        {loading ? (
          <Stack
            direction="row"
            spacing={1.5}
            sx={{ alignItems: 'center', py: 3 }}
            data-testid="ozon-return-picker-loading"
          >
            <CircularProgress size={22} />
            <Typography variant="body2">Получаем возвраты Ozon…</Typography>
          </Stack>
        ) : null}

        {!loading && filteredGroups.length === 0 && !error ? (
          <Alert severity="info" data-testid="ozon-return-picker-empty">
            {groups.length === 0
              ? 'Нет возвратов Ozon, доступных к получению.'
              : 'По этому поиску возвратов нет.'}
          </Alert>
        ) : null}

        <Stack spacing={1}>
          {filteredGroups.map((group) => {
            const imported = group.already_imported
            const selected = selectedGiveoutIds.has(group.giveout_id)
            const status = ozonGiveoutStatus(group.giveout_status)
            const utilizationDate = formatOzonUtilizationDate(group.utilization_forecast_date)
            const urgent = isOzonReturnUrgent(group.utilization_forecast_date)
            return (
              <Accordion
                key={group.giveout_id}
                disableGutters
                variant="outlined"
                data-testid="ozon-return-picker-group"
              >
                <AccordionSummary
                  expandIcon={<ExpandMoreOutlined />}
                  sx={{ '& .MuiAccordionSummary-content': { my: 1 } }}
                >
                  <Stack
                    direction={{ xs: 'column', md: 'row' }}
                    spacing={1}
                    useFlexGap
                    sx={{ width: '100%', alignItems: { md: 'center' }, pr: 1 }}
                  >
                    <Checkbox
                      size="small"
                      checked={selected}
                      disabled={busy || imported}
                      onClick={(event) => event.stopPropagation()}
                      onChange={(_, checked) => toggleGiveout(group, checked)}
                      slotProps={{
                        input: {
                          'aria-label': `Выбрать пункт ${group.warehouse_name}`,
                        },
                      }}
                      data-testid="ozon-return-picker-group-select"
                    />
                    <Box sx={{ minWidth: 220, flex: 1 }}>
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>
                        {group.warehouse_name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {group.warehouse_address}
                      </Typography>
                    </Box>
                    <Typography variant="body2" sx={{ whiteSpace: 'nowrap' }}>
                      Товаров: {group.approved_articles_count} / {group.total_articles_count}
                    </Typography>
                    <StatusChip
                      label={status.label}
                      tone={status.tone}
                      testId="ozon-return-picker-status"
                    />
                    {group.storage_days != null ? (
                      <Typography
                        variant="caption"
                        color={urgent ? 'warning.dark' : 'text.secondary'}
                        sx={{ whiteSpace: 'nowrap' }}
                      >
                        ждёт {group.storage_days} дн.
                      </Typography>
                    ) : null}
                    {utilizationDate ? (
                      <Typography
                        variant="caption"
                        color={urgent ? 'warning.dark' : 'text.secondary'}
                        sx={{
                          whiteSpace: 'nowrap',
                          fontWeight: urgent ? 700 : undefined,
                        }}
                      >
                        утилизация {utilizationDate}
                      </Typography>
                    ) : null}
                    {imported ? (
                      <Typography variant="caption" color="text.secondary">
                        Уже добавлен
                      </Typography>
                    ) : null}
                  </Stack>
                </AccordionSummary>
                <AccordionDetails sx={{ pt: 0 }}>
                  <TableContainer>
                    <Table size="small" data-testid="ozon-return-picker-items-table">
                      <TableHead>
                        <TableRow>
                          <TableCell sx={{ width: 56 }}>Фото</TableCell>
                          <TableCell>Артикул</TableCell>
                          <TableCell>ШК</TableCell>
                          <TableCell>Артикул продавца</TableCell>
                          <TableCell>Артикул Ozon</TableCell>
                          <TableCell>Наименование</TableCell>
                          <TableCell>Причина возврата</TableCell>
                          <TableCell align="right">Количество</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {group.items.map((item, index) => (
                          <TableRow
                            key={`${item.return_id ?? item.product_name}-${index}`}
                            hover
                            data-testid="ozon-return-picker-item"
                          >
                            <TableCell>
                              <ProductPhotoThumb
                                src={item.image_url ?? null}
                                alt={item.product_name}
                              />
                            </TableCell>
                            <TableCell>{item.wms_sku ?? '—'}</TableCell>
                            <TableCell>{item.wms_barcode ?? '—'}</TableCell>
                            <TableCell>{item.offer_id ?? '—'}</TableCell>
                            <TableCell>{item.ozon_sku ?? '—'}</TableCell>
                            <TableCell sx={{ minWidth: 220 }}>
                              <Typography variant="body2">{item.product_name}</Typography>
                              {!item.matched ? (
                                <Typography
                                  variant="caption"
                                  color="warning.dark"
                                  data-testid="ozon-return-picker-unmatched"
                                >
                                  {item.warning ?? 'Товар не сопоставлен с каталогом'}
                                </Typography>
                              ) : null}
                            </TableCell>
                            <TableCell>{item.return_reason_name ?? '—'}</TableCell>
                            <TableCell align="right">{item.quantity}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </AccordionDetails>
              </Accordion>
            )
          })}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={close} disabled={busy} data-testid="ozon-return-picker-cancel">
          Отмена
        </Button>
        <Tooltip title={canApply ? '' : 'Выберите хотя бы один новый пункт выдачи'}>
          <span>
            <Button
              variant="contained"
              disabled={busy || !canApply}
              onClick={() => void onApply(newSelectedGiveoutIds)}
              data-testid="ozon-return-picker-apply"
            >
              Добавить в возврат
            </Button>
          </span>
        </Tooltip>
      </DialogActions>
    </Dialog>
  )
}
