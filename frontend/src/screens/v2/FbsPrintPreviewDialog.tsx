import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import PrintOutlinedIcon from '@mui/icons-material/PrintOutlined'
import { resolveFbsAssetUrl, type FbsPrintAsset, type FbsPrintBatch } from './fbsApi'
import { loadLabelSizeId, resolveLabelSize, type LabelSize } from '../../utils/labelSize'
import { LabelSizeSelect } from '../../components/LabelSizeSelect'

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  batch: FbsPrintBatch | null
  open: boolean
  onClose: () => void
  onApplied: (asset: FbsPrintAsset) => Promise<void>
}

type Preview = { asset: FbsPrintAsset; objectUrl: string }

function assetLabel(asset: FbsPrintAsset): string {
  if (asset.kind === 'box_qr') return 'Печать QR короба WMS'
  if (asset.kind === 'cargo_place_qr') return 'Печать QR грузоместа WB'
  if (asset.kind === 'supply_qr') return 'Печать QR поставки WB'
  return 'Печать стикера заказа WB'
}

export function FbsPrintPreviewDialog({
  token,
  authHeaders,
  batch,
  open,
  onClose,
  onApplied,
}: Props) {
  const [previews, setPreviews] = useState<Preview[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [applyingId, setApplyingId] = useState<string | null>(null)
  const [copies, setCopies] = useState(1)
  const [labelSize, setLabelSize] = useState<LabelSize>(() => resolveLabelSize(loadLabelSizeId()))

  const readyAssets = useMemo(
    () => batch?.assets.filter((asset) => asset.status === 'ready' && asset.preview_url) ?? [],
    [batch],
  )

  useEffect(() => {
    if (!open || readyAssets.length === 0) {
      setPreviews([])
      return
    }
    let active = true
    const objectUrls: string[] = []
    setLoading(true)
    setError(null)
    void Promise.all(
      readyAssets.map(async (asset) => {
        const response = await fetch(resolveFbsAssetUrl(asset.preview_url!), {
          headers: { ...authHeaders(token) },
        })
        if (!response.ok) throw new Error(`Предпросмотр ${asset.id} недоступен (${response.status}).`)
        const objectUrl = URL.createObjectURL(await response.blob())
        objectUrls.push(objectUrl)
        return { asset, objectUrl }
      }),
    )
      .then((next) => {
        if (active) setPreviews(next)
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : 'Предпросмотр не загружен.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
      objectUrls.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [open, readyAssets, token, authHeaders])

  useEffect(() => {
    if (open) {
      setCopies(1)
      setLabelSize(resolveLabelSize(loadLabelSizeId()))
    }
  }, [open, batch])

  const print = (items: Preview[]) => {
    if (items.length === 0) {
      setError('Нет готовых изображений — окно печати не открыто.')
      return
    }
    const safeCopies = Math.max(1, Math.min(99, copies))
    const popup = window.open('', '_blank')
    if (!popup) {
      setError('Браузер заблокировал окно печати. Разрешите всплывающие окна для WMS.')
      return
    }
    popup.opener = null
    const pages = items
      .flatMap(({ objectUrl, asset }) =>
        Array.from(
          { length: safeCopies },
          () => `<section class="label"><img src="${objectUrl}" alt="${assetLabel(asset)}"></section>`,
        ),
      )
      .join('')
    const pageWidthMm = `${labelSize.widthMm}mm`
    const pageHeightMm = `${labelSize.heightMm}mm`
    popup.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>Печать WB</title><style>@page{size:${pageWidthMm} ${pageHeightMm};margin:0}html,body{margin:0;padding:0}.label{width:${pageWidthMm};height:${pageHeightMm};display:flex;align-items:center;justify-content:center;break-after:page;page-break-after:always;overflow:hidden}.label:last-child{break-after:auto;page-break-after:auto}.label img{width:${pageWidthMm};height:${pageHeightMm};object-fit:contain;image-rendering:auto}</style></head><body>${pages}<script>Promise.all(Array.from(document.images).map(function(img){return img.complete?Promise.resolve():new Promise(function(resolve){img.onload=resolve;img.onerror=resolve})})).then(function(){window.focus();window.print()})</script></body></html>`)
    popup.document.close()
  }

  const apply = async (asset: FbsPrintAsset) => {
    setApplyingId(asset.id)
    setError(null)
    try {
      await onApplied(asset)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Нанесение не подтверждено.')
    } finally {
      setApplyingId(null)
    }
  }

  return (
    <Dialog open={open} onClose={loading || applyingId ? undefined : onClose} fullWidth maxWidth="lg">
      <DialogTitle>Проверка перед печатью</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }} useFlexGap>
            <Chip label={`Готово ${batch?.ready ?? 0}`} color="success" />
            {batch?.missing ? <Chip label={`Не получено ${batch.missing}`} color="warning" /> : null}
            {batch?.failed ? <Chip label={`Ошибок ${batch.failed}`} color="error" /> : null}
          </Stack>
          <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap' }} useFlexGap data-task-id="FBS-10">
            <TextField
              size="small"
              type="number"
              label="Копий каждого макета"
              value={copies}
              onChange={(event) => setCopies(Math.max(1, Math.min(99, Number(event.target.value) || 1)))}
              slotProps={{ htmlInput: { min: 1, max: 99 } }}
              sx={{ width: 220 }}
              data-testid="fbs-print-preview-copies"
              data-task-id="FBS-10"
            />
            <LabelSizeSelect
              value={labelSize.id}
              onChange={setLabelSize}
              testId="fbs-print-preview-label-size"
            />
          </Stack>
          {error ? <Alert severity="error">{error}</Alert> : null}
          {batch?.order_errors.map((item) => (
            <Alert key={item.order_id} severity="error">
              Заказ WB №{item.wb_order_id}: {item.message}
            </Alert>
          ))}
          {loading ? (
            <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', py: 4 }}>
              <CircularProgress size={22} />
              <Typography>Загружаем защищённые PNG для preview…</Typography>
            </Stack>
          ) : null}
          {!loading && previews.length === 0 ? (
            <Alert severity="warning">Готовых изображений нет. Печать не будет открыта.</Alert>
          ) : null}
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(260px,1fr))', gap: 2 }}>
            {previews.map(({ asset, objectUrl }) => (
              <Paper key={asset.id} variant="outlined" sx={{ p: 2 }}>
                <Typography variant="subtitle2">{assetLabel(asset)}</Typography>
                <Box component="img" src={objectUrl} alt={assetLabel(asset)} sx={{ width: '100%', aspectRatio: `${labelSize.widthMm} / ${labelSize.heightMm}`, objectFit: 'contain', bgcolor: '#fff', my: 1.5 }} />
                <Stack direction="row" spacing={1}>
                  {previews.length > 1 ? <Button startIcon={<PrintOutlinedIcon />} onClick={() => print([{ asset, objectUrl }])} data-task-id="FBS-10">Печать только этого</Button> : null}
                  {asset.kind !== 'box_qr' ? (
                    <Button disabled={Boolean(asset.applied_at) || applyingId === asset.id} onClick={() => void apply(asset)} data-task-id="FBS-09">
                      {asset.applied_at ? 'Уже нанесён' : 'Подтвердить нанесение'}
                    </Button>
                  ) : null}
                </Stack>
              </Paper>
            ))}
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={loading || Boolean(applyingId)}>Закрыть</Button>
        <Button variant="contained" startIcon={<PrintOutlinedIcon />} disabled={previews.length === 0 || loading} onClick={() => print(previews)} data-task-id="FBS-10">
          {previews.length === 1 ? 'Печать' : 'Печать всех готовых'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
