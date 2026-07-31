import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
  Drawer,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Step,
  StepLabel,
  Stepper,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import {
  createFbsTrbx,
  deliverFbsSupply,
  fetchFbsTrbxStickers,
  generateFbsSupplyStickers,
  getFbsOrderMarkings,
  getFbsSupply,
  MARKING_KIND_LABEL,
  putFbsOrderMarking,
  type FbsMarkingKind,
  type FbsOrderMarking,
  type FbsSupply,
  type FbsSupplyOrder,
  type FbsTrbx,
} from './fbsApi'
import { FbsStatusChip, MarkingCheckStatusChip } from '../../components/fbs/FbsChips'
import { FfFbsPickList } from './FfFbsPickList'

const MARKING_KINDS: FbsMarkingKind[] = ['sgtin', 'uin', 'imei', 'gtin']

// Диалог «Идентификаторы заказа» — маркировка WB привязана к заказу, а не к артикулу,
// поэтому вызывается прямо из строки заказа в таблице отгрузки.
type OrderMarkingsDialogProps = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  order: FbsSupplyOrder | null
  open: boolean
  onClose: () => void
}

function OrderMarkingsDialog({ token, authHeaders, order, open, onClose }: OrderMarkingsDialogProps) {
  const [markings, setMarkings] = useState<FbsOrderMarking[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [kind, setKind] = useState<FbsMarkingKind>('sgtin')
  const [value, setValue] = useState('')

  const orderId = order?.id ?? null

  const load = useCallback(async () => {
    if (!orderId) return
    setError(null)
    setBusy(true)
    try {
      setMarkings(await getFbsOrderMarkings(token, authHeaders, orderId))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить идентификаторы')
    } finally {
      setBusy(false)
    }
  }, [token, authHeaders, orderId])

  useEffect(() => {
    if (open && orderId) void load()
    if (!open) {
      setValue('')
      setError(null)
    }
  }, [open, orderId, load])

  const addMarking = useCallback(async () => {
    if (!orderId) return
    const trimmed = value.trim()
    if (!trimmed) {
      setError('Введите значение идентификатора.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await putFbsOrderMarking(token, authHeaders, orderId, kind, trimmed)
      setValue('')
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить идентификатор')
    } finally {
      setBusy(false)
    }
  }, [token, authHeaders, orderId, kind, value, load])

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm" data-testid="fbs-markings-dialog">
      <DialogTitle>
        Идентификаторы заказа
        {order ? (
          <Typography variant="body2" color="text.secondary">
            № {order.wb_order_id}
          </Typography>
        ) : null}
      </DialogTitle>
      <DialogContent dividers>
        {error ? (
          <Alert severity="error" sx={{ mb: 2 }} data-testid="fbs-markings-error">
            {error}
          </Alert>
        ) : null}

        <Table size="small" sx={{ mb: 2 }}>
          <TableHead>
            <TableRow>
              <TableCell>Тип</TableCell>
              <TableCell>Значение</TableCell>
              <TableCell align="right">Проверка</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {markings.map((m) => (
              <TableRow key={m.id} data-testid="fbs-marking-row">
                <TableCell>{MARKING_KIND_LABEL[m.kind as FbsMarkingKind] ?? m.kind}</TableCell>
                <TableCell sx={{ wordBreak: 'break-all' }}>{m.value}</TableCell>
                <TableCell align="right">
                  <MarkingCheckStatusChip status={m.check_status} />
                </TableCell>
              </TableRow>
            ))}
            {markings.length === 0 ? (
              <TableRow>
                <TableCell colSpan={3}>
                  <Typography variant="body2" color="text.secondary">
                    Идентификаторы ещё не добавлены.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ alignItems: { sm: 'center' } }}>
          <FormControl size="small" sx={{ minWidth: 160 }}>
            <InputLabel id="fbs-marking-kind-label">Тип</InputLabel>
            <Select
              labelId="fbs-marking-kind-label"
              label="Тип"
              value={kind}
              onChange={(e) => setKind(e.target.value as FbsMarkingKind)}
              data-testid="fbs-marking-kind"
            >
              {MARKING_KINDS.map((k) => (
                <MenuItem key={k} value={k}>
                  {MARKING_KIND_LABEL[k]}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            size="small"
            label="Значение"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            sx={{ flexGrow: 1 }}
            slotProps={{ htmlInput: { 'data-testid': 'fbs-marking-value' } }}
          />
          <Button
            variant="outlined"
            onClick={() => void addMarking()}
            disabled={busy}
            data-testid="fbs-marking-add"
          >
            Добавить
          </Button>
          {busy ? <CircularProgress size={18} /> : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button variant="contained" onClick={onClose}>
          Закрыть
        </Button>
      </DialogActions>
    </Dialog>
  )
}

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  supplyId: string | null
  open: boolean
  onClose: () => void
  onChanged?: () => void
}

// Открыть картинки (base64 PNG) в окне печати — стикеры заказов и QR поставки.
function printImages(title: string, dataUrls: string[]): void {
  const w = window.open('', '_blank')
  if (!w) return
  const imgs = dataUrls.map((src) => `<img src="${src}" style="display:block;margin:0 auto 8px" />`).join('')
  w.document.write(`<title>${title}</title><body onload="window.print()">${imgs}</body>`)
  w.document.close()
}

function pngDataUrl(base64: string): string {
  return base64.startsWith('data:') ? base64 : `data:image/png;base64,${base64}`
}

function stepsFor(deliveryType: string): string[] {
  return deliveryType === 'pvz'
    ? ['Сборка', 'Грузоместа', 'В доставке', 'Готово']
    : ['Сборка', 'В доставке', 'Готово']
}

function activeStep(supply: FbsSupply): number {
  const steps = stepsFor(supply.delivery_type)
  if (supply.status === 'done') return steps.length - 1
  if (supply.status === 'in_delivery') return steps.indexOf('В доставке')
  return 0 // draft | assembling
}

export function FfFbsSupplyDrawer({ token, authHeaders, supplyId, open, onClose, onChanged }: Props) {
  const [supply, setSupply] = useState<FbsSupply | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmDeliver, setConfirmDeliver] = useState(false)
  const [pickOpen, setPickOpen] = useState(false)
  const [trbxList, setTrbxList] = useState<FbsTrbx[]>([])
  const [trbxCount, setTrbxCount] = useState('1')
  const [trbxBusy, setTrbxBusy] = useState(false)
  const [markingsOrder, setMarkingsOrder] = useState<FbsSupplyOrder | null>(null)

  const load = useCallback(async () => {
    if (!supplyId) return
    setError(null)
    setBusy(true)
    try {
      setSupply(await getFbsSupply(token, authHeaders, supplyId))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить отгрузку')
      setSupply(null)
    } finally {
      setBusy(false)
    }
  }, [token, authHeaders, supplyId])

  useEffect(() => {
    if (open && supplyId) void load()
  }, [open, supplyId, load])

  // Грузоместа — только для отгрузок в ПВЗ. Отдельной ручки «список» на backend нет,
  // поэтому список подтягиваем через ту же ручку стикеров при открытии карточки.
  const loadTrbx = useCallback(async () => {
    if (!supplyId) return
    try {
      setTrbxList(await fetchFbsTrbxStickers(token, authHeaders, supplyId))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить грузоместа')
    }
  }, [token, authHeaders, supplyId])

  useEffect(() => {
    if (open && supplyId && supply?.delivery_type === 'pvz') void loadTrbx()
    if (!open) setTrbxList([])
  }, [open, supplyId, supply?.delivery_type, loadTrbx])

  const createTrbx = useCallback(async () => {
    if (!supplyId) return
    const count = Number(trbxCount)
    if (!Number.isInteger(count) || count < 1) {
      setError('Укажите количество коробов — целое число не меньше 1.')
      return
    }
    setTrbxBusy(true)
    setError(null)
    try {
      const created = await createFbsTrbx(token, authHeaders, supplyId, count)
      setTrbxList((prev) => [...prev, ...created])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось создать грузоместа')
    } finally {
      setTrbxBusy(false)
    }
  }, [token, authHeaders, supplyId, trbxCount])

  const printTrbxQr = useCallback(
    async (trbx: FbsTrbx) => {
      if (!supplyId) return
      if (trbx.sticker_file) {
        printImages('QR грузоместа FBS', [pngDataUrl(trbx.sticker_file)])
        return
      }
      setTrbxBusy(true)
      setError(null)
      try {
        const refreshed = await fetchFbsTrbxStickers(token, authHeaders, supplyId)
        setTrbxList(refreshed)
        const match = refreshed.find((t) => t.id === trbx.id)
        if (match?.sticker_file) {
          printImages('QR грузоместа FBS', [pngDataUrl(match.sticker_file)])
        } else {
          setError('QR грузоместа ещё не готов — попробуйте позже.')
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось получить QR грузоместа')
      } finally {
        setTrbxBusy(false)
      }
    },
    [token, authHeaders, supplyId],
  )

  const printStickers = useCallback(async () => {
    if (!supplyId) return
    setBusy(true)
    setError(null)
    try {
      const stickers = await generateFbsSupplyStickers(token, authHeaders, supplyId)
      const urls = stickers
        .map((s) => s.sticker_file)
        .filter((f): f is string => !!f)
        .map(pngDataUrl)
      if (urls.length === 0) {
        setError('Стикеры ещё не готовы — попробуйте позже.')
      } else {
        printImages('Стикеры заказов FBS', urls)
      }
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось получить стикеры')
    } finally {
      setBusy(false)
    }
  }, [token, authHeaders, supplyId, load])

  const doDeliver = useCallback(async () => {
    if (!supplyId) return
    setBusy(true)
    setError(null)
    try {
      setSupply(await deliverFbsSupply(token, authHeaders, supplyId))
      setConfirmDeliver(false)
      onChanged?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось передать в доставку')
    } finally {
      setBusy(false)
    }
  }, [token, authHeaders, supplyId, onChanged])

  const canDeliver = supply && (supply.status === 'assembling' || supply.status === 'draft')

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      slotProps={{ paper: { sx: { width: { xs: '100%', sm: 640 }, p: 2 } } }}
      data-testid="fbs-supply-drawer"
    >
      {!supply && busy ? (
        <Stack sx={{ alignItems: 'center', py: 6 }}>
          <CircularProgress data-testid="fbs-supply-loading" />
        </Stack>
      ) : null}

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="fbs-supply-error" action={
          <Button color="inherit" size="small" onClick={() => void load()}>Повтор</Button>
        }>
          {error}
        </Alert>
      ) : null}

      {supply ? (
        <Box>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1 }}>
            <Typography variant="h6" sx={{ flexGrow: 1 }}>
              {supply.name}
            </Typography>
            <FbsStatusChip status={supply.status} />
            <IconButton size="small" onClick={onClose} aria-label="Закрыть">
              ✕
            </IconButton>
          </Stack>
          <Typography variant="caption" color="text.secondary">
            {supply.delivery_type === 'pvz' ? 'Отгрузка в ПВЗ' : 'Отгрузка на склад/СЦ'}
            {supply.wb_supply_id ? ` · ${supply.wb_supply_id}` : ''}
          </Typography>

          <Stepper activeStep={activeStep(supply)} sx={{ my: 2 }} data-testid="fbs-supply-stepper">
            {stepsFor(supply.delivery_type).map((label) => (
              <Step key={label}>
                <StepLabel>{label}</StepLabel>
              </Step>
            ))}
          </Stepper>

          <Divider sx={{ mb: 1 }} />
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            Заказы в отгрузке ({supply.orders?.length ?? 0})
          </Typography>
          <Table size="small" data-testid="fbs-supply-orders">
            <TableHead>
              <TableRow>
                <TableCell>Заказ</TableCell>
                <TableCell>Статус</TableCell>
                <TableCell align="right">Стикер</TableCell>
                <TableCell align="right">Идентификаторы</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(supply.orders ?? []).map((o) => (
                <TableRow key={o.id} data-testid="fbs-supply-order-row">
                  <TableCell>№ {o.wb_order_id}</TableCell>
                  <TableCell>
                    <FbsStatusChip status={o.status} />
                  </TableCell>
                  <TableCell align="right">
                    {o.sticker_file ? (
                      <Chip size="small" color="success" variant="outlined" label="есть" />
                    ) : (
                      <Chip size="small" variant="outlined" label="нет" />
                    )}
                  </TableCell>
                  <TableCell align="right">
                    <Button
                      size="small"
                      onClick={() => setMarkingsOrder(o)}
                      data-testid="fbs-order-markings-open"
                    >
                      Идентификаторы
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {(supply.orders ?? []).length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4}>
                    <Typography variant="body2" color="text.secondary">
                      В отгрузке пока нет заказов.
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>

          {supply.delivery_type === 'pvz' ? (
            <Box data-testid="fbs-trbx-section" sx={{ mt: 2 }}>
              <Divider sx={{ mb: 1 }} />
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Грузоместа ({trbxList.length})
              </Typography>
              <Stack direction="row" spacing={1} sx={{ mb: 1, alignItems: 'center', flexWrap: 'wrap' }}>
                <TextField
                  size="small"
                  label="Сколько коробов"
                  type="number"
                  value={trbxCount}
                  onChange={(e) => setTrbxCount(e.target.value)}
                  sx={{ width: 160 }}
                  slotProps={{ htmlInput: { min: 1, 'data-testid': 'fbs-trbx-count' } }}
                />
                <Button
                  variant="outlined"
                  onClick={() => void createTrbx()}
                  disabled={trbxBusy}
                  data-testid="fbs-trbx-create"
                >
                  Создать грузоместа
                </Button>
                {trbxBusy ? <CircularProgress size={18} data-testid="fbs-trbx-loading" /> : null}
              </Stack>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Грузоместо</TableCell>
                    <TableCell align="right">QR</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {trbxList.map((t) => (
                    <TableRow key={t.id} data-testid="fbs-trbx-row">
                      <TableCell>{t.wb_trbx_id}</TableCell>
                      <TableCell align="right">
                        <Button
                          size="small"
                          onClick={() => void printTrbxQr(t)}
                          disabled={trbxBusy}
                          data-testid="fbs-trbx-print"
                        >
                          Печать QR
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                  {trbxList.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={2}>
                        <Typography variant="body2" color="text.secondary">
                          Грузоместа ещё не созданы.
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </Box>
          ) : null}

          <Stack direction="row" spacing={1} sx={{ mt: 2, flexWrap: 'wrap' }}>
            <Button
              variant="outlined"
              onClick={() => setPickOpen(true)}
              data-testid="fbs-supply-open-pick-list"
            >
              Лист подбора
            </Button>
            <Button
              variant="outlined"
              onClick={() => void printStickers()}
              disabled={busy}
              data-testid="fbs-supply-print-stickers"
            >
              Печать стикеров
            </Button>
            {supply.barcode_file ? (
              <Button
                variant="outlined"
                onClick={() => printImages('QR отгрузки FBS', [pngDataUrl(supply.barcode_file!)])}
                data-testid="fbs-supply-print-qr"
              >
                Печать QR отгрузки
              </Button>
            ) : null}
            <Button
              variant="contained"
              onClick={() => setConfirmDeliver(true)}
              disabled={busy || !canDeliver}
              data-testid="fbs-supply-deliver"
              sx={{ ml: { sm: 'auto' } }}
            >
              Передать в доставку
            </Button>
          </Stack>
        </Box>
      ) : null}

      <Dialog open={confirmDeliver} onClose={() => setConfirmDeliver(false)} data-testid="fbs-supply-confirm-dialog">
        <DialogTitle>Передать отгрузку в доставку?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            После передачи изменить состав отгрузки будет нельзя. Убедитесь, что все заказы собраны,
            промаркированы и упакованы.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDeliver(false)} data-testid="fbs-supply-deliver-cancel">
            Отмена
          </Button>
          <Button
            variant="contained"
            onClick={() => void doDeliver()}
            disabled={busy}
            data-testid="fbs-supply-deliver-confirm"
          >
            Передать
          </Button>
        </DialogActions>
      </Dialog>

      <FfFbsPickList
        token={token}
        authHeaders={authHeaders}
        supplyId={supplyId}
        open={pickOpen}
        onClose={() => setPickOpen(false)}
      />

      <OrderMarkingsDialog
        token={token}
        authHeaders={authHeaders}
        order={markingsOrder}
        open={markingsOrder !== null}
        onClose={() => setMarkingsOrder(null)}
      />
    </Drawer>
  )
}
