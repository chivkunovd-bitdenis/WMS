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
  Typography,
} from '@mui/material'
import PrintOutlinedIcon from '@mui/icons-material/PrintOutlined'
import { fetchFbsPrintPreviewBlobs, type FbsPrintAsset, type FbsPrintBatch } from './fbsApi'

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
  const [previewErrors, setPreviewErrors] = useState<Array<{ asset: FbsPrintAsset; message: string }>>([])
  const [applyingId, setApplyingId] = useState<string | null>(null)

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
    setPreviewErrors([])
    void fetchFbsPrintPreviewBlobs(token, authHeaders, readyAssets)
      .then((result) => {
        const next = result.ready.map(({ asset, blob }) => {
          const objectUrl = URL.createObjectURL(blob)
          objectUrls.push(objectUrl)
          return { asset, objectUrl }
        })
        if (active) {
          setPreviews(next)
          setPreviewErrors(result.errors)
        }
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

  const print = (items: Preview[]) => {
    if (items.length === 0) {
      setError('Нет готовых изображений — окно печати не открыто.')
      return
    }
    const popup = window.open('', '_blank')
    if (!popup) {
      setError('Браузер заблокировал окно печати. Разрешите всплывающие окна для WMS.')
      return
    }
    popup.opener = null
    const pages = items
      .map(
        ({ objectUrl, asset }) =>
          `<section class="label"><img src="${objectUrl}" alt="${assetLabel(asset)}"></section>`,
      )
      .join('')
    popup.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>Печать WB</title><style>@page{size:58mm 40mm;margin:0}html,body{margin:0;padding:0}.label{width:58mm;height:40mm;display:flex;align-items:center;justify-content:center;break-after:page;page-break-after:always;overflow:hidden}.label:last-child{break-after:auto;page-break-after:auto}.label img{width:58mm;height:40mm;object-fit:contain;image-rendering:auto}</style></head><body>${pages}<script>Promise.all(Array.from(document.images).map(function(img){return img.complete?Promise.resolve():new Promise(function(resolve){img.onload=resolve;img.onerror=resolve})})).then(function(){window.focus();window.print()})</script></body></html>`)
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
          {error ? <Alert severity="error">{error}</Alert> : null}
          {previewErrors.map((item) => (
            <Alert key={item.asset.id} severity="error">
              {assetLabel(item.asset)}: {item.message}
            </Alert>
          ))}
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
                <Box component="img" src={objectUrl} alt={assetLabel(asset)} sx={{ width: '100%', aspectRatio: '58 / 40', objectFit: 'contain', bgcolor: '#fff', my: 1.5 }} />
                <Stack direction="row" spacing={1}>
                  {previews.length > 1 ? <Button startIcon={<PrintOutlinedIcon />} onClick={() => print([{ asset, objectUrl }])} data-testid={`fbs-preview-print-${asset.id}`}>Печать только этого</Button> : null}
                  <Button disabled={Boolean(asset.applied_at) || applyingId === asset.id} onClick={() => void apply(asset)} data-testid={`fbs-preview-apply-${asset.id}`}>
                    {asset.applied_at ? 'Уже нанесён' : 'Подтвердить нанесение'}
                  </Button>
                </Stack>
              </Paper>
            ))}
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={loading || Boolean(applyingId)}>Закрыть</Button>
        <Button variant="contained" startIcon={<PrintOutlinedIcon />} disabled={previews.length === 0 || loading} onClick={() => print(previews)} data-testid="fbs-preview-print-all">
          {previews.length === 1 ? 'Печать' : 'Печать всех готовых'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
