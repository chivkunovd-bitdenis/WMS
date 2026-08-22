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
import { fbsTapeOrderErrorText, resolveFbsAssetUrl, type FbsOrderPrintTape, type FbsPrintAsset, type FbsPrintBatch } from './fbsApi'
import { ActionGroup, ErrorNotice, PrintAction, SecondaryAction } from '../../ui-kit'
import { loadLabelSizeId, resolveLabelSize, type LabelSize } from '../../utils/labelSize'
import { LabelSizeSelect } from '../../components/LabelSizeSelect'
import { fetchLabelArtifactDataUrl, renderDataMatrixDataUrl } from '../../utils/printMarkingCodeLabel'

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  batch: FbsPrintBatch | null
  tape?: FbsOrderPrintTape | null
  open: boolean
  onClose: () => void
  onApplied: (asset: FbsPrintAsset) => Promise<void>
}

type Preview = { asset: FbsPrintAsset; objectUrl: string }

type TapeOrderError = {
  order_id: string
  wb_order_id: number
  order_number?: number | null
  code: string
}

export type FbsPrintPreviewEntry =
  | { kind: 'ready'; preview: Preview }
  | { kind: 'error'; item: TapeOrderError }

export function buildFbsPrintPreviewSequence(
  previews: Preview[],
  orderErrors: TapeOrderError[],
): FbsPrintPreviewEntry[] {
  return [
    ...previews.map((preview, responseIndex) => ({
      kind: 'ready' as const,
      preview,
      orderNumber: preview.asset.order_number ?? Number.MAX_SAFE_INTEGER,
      responseIndex,
    })),
    ...orderErrors.map((item, responseIndex) => ({
      kind: 'error' as const,
      item,
      orderNumber: item.order_number ?? Number.MAX_SAFE_INTEGER,
      responseIndex: previews.length + responseIndex,
    })),
  ]
    .sort((left, right) => left.orderNumber - right.orderNumber || left.responseIndex - right.responseIndex)
    .map((entry): FbsPrintPreviewEntry => entry.kind === 'ready'
      ? { kind: 'ready', preview: entry.preview }
      : { kind: 'error', item: entry.item })
}

export function getFbsMarkingPrintSource(code: {
  id: string
  cis_code: string
  has_label_artifact: boolean
}): { kind: 'artifact'; codeId: string } | { kind: 'matrix'; cis: string } {
  return code.has_label_artifact
    ? { kind: 'artifact', codeId: code.id }
    : { kind: 'matrix', cis: code.cis_code }
}

function assetLabel(asset: FbsPrintAsset): string {
  if (asset.kind === 'box_qr') return 'Печать QR короба WMS'
  if (asset.kind === 'cargo_place_qr') return 'Печать QR грузоместа WB'
  if (asset.kind === 'supply_qr') return 'Печать QR поставки WB'
  return 'Печать стикера заказа WB'
}

export function buildFbsTapePairHtml(
  asset: FbsPrintAsset,
  objectUrl: string,
  markingImageUrls: string[] = [],
): string {
  const wbPage = `<section class="label"><img src="${objectUrl}" alt="${assetLabel(asset)}"></section>`
  if (asset.kind !== 'order_sticker' || asset.order_number == null) return wbPage
  const markingPages = markingImageUrls
    .map((imageUrl) => `<section class="label"><img src="${imageUrl}" alt="Этикетка Честного знака"></section>`)
    .join('')
  return `${wbPage}<section class="label service-label"><div>Служебная этикетка WMS<br><strong>№ ${asset.order_number}</strong></div></section>${markingPages}`
}

export function FbsPrintPreviewDialog({
  token,
  authHeaders,
  batch,
  tape = null,
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

  const orderErrors = useMemo<TapeOrderError[]>(
    () => (tape?.order_errors ?? batch?.order_errors ?? []).map(({ order_id, wb_order_id, order_number, code }) => ({ order_id, wb_order_id, order_number, code })),
    [batch, tape],
  )

  const readyAssets = useMemo(
    () => tape
      ? tape.orders.flatMap((order) => order.qr_asset?.status === 'ready' && order.qr_asset.preview_url
        ? [{ ...order.qr_asset, order_number: order.order_number, wb_order_id: order.wb_order_id }]
        : [])
      : batch?.assets.filter((asset) => asset.status === 'ready' && asset.preview_url) ?? [],
    [batch, tape],
  )
  const orderedReadyAssets = useMemo(
    () => [...readyAssets].sort((a, b) => (a.order_number ?? Number.MAX_SAFE_INTEGER) - (b.order_number ?? Number.MAX_SAFE_INTEGER)),
    [readyAssets],
  )
  const previewSequence = useMemo(
    () => buildFbsPrintPreviewSequence(previews, orderErrors),
    [previews, orderErrors],
  )

  useEffect(() => {
    if (!open || orderedReadyAssets.length === 0) {
      setPreviews([])
      return
    }
    let active = true
    const objectUrls: string[] = []
    setLoading(true)
    setError(null)
    void Promise.all(
      orderedReadyAssets.map(async (asset) => {
        const response = await fetch(resolveFbsAssetUrl(asset.preview_url!), {
          headers: { ...authHeaders(token) },
        })
        if (!response.ok) throw new Error('Не удалось загрузить предпросмотр стикеров.')
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
  }, [open, orderedReadyAssets, token, authHeaders])

  useEffect(() => {
    if (open) {
      setCopies(1)
      setLabelSize(resolveLabelSize(loadLabelSizeId()))
    }
  }, [open, batch, tape])

  const print = async (items: Preview[]) => {
    if (items.length === 0) {
      setError('Нет готовых изображений — окно печати не открыто.')
      return
    }
    const safeCopies = tape ? 1 : Math.max(1, Math.min(99, copies))
    const popup = window.open('', '_blank')
    if (!popup) {
      setError('Браузер заблокировал окно печати. Разрешите всплывающие окна для WMS.')
      return
    }
    popup.opener = null
    try {
      const pages = (await Promise.all(items.map(async ({ objectUrl, asset }) => {
        const tapeOrder = tape?.orders.find((order) => order.order_id === asset.id || order.qr_asset?.id === asset.id)
        const markingImageUrls = await Promise.all((tapeOrder?.printed_codes ?? []).map(async (code) => {
          const source = getFbsMarkingPrintSource(code)
          return source.kind === 'artifact'
            ? await fetchLabelArtifactDataUrl(source.codeId, token)
            : await renderDataMatrixDataUrl(source.cis)
        }))
        return Array.from(
          { length: safeCopies },
          () => buildFbsTapePairHtml(asset, objectUrl, markingImageUrls),
        ).join('')
      }))).join('')
    const pageWidthMm = `${labelSize.widthMm}mm`
    const pageHeightMm = `${labelSize.heightMm}mm`
    // Размер страницы объявляем, но вёрстку привязываем к реальному листу принтера:
    // рулон 60x40 при объявленных 58x40 обрезал QR по краю. Проценты плюс max-* дают
    // картинке вписаться в любую бумагу, а поле в 1 мм не даёт ей упереться в срез.
    const printCss = [
      `@page{size:${pageWidthMm} ${pageHeightMm};margin:0}`,
      'html,body{margin:0;padding:0}',
      '.label{box-sizing:border-box;width:100%;height:100vh;padding:1mm;display:flex;',
      'align-items:center;justify-content:center;break-after:page;page-break-after:always;overflow:hidden}',
      '.label:last-child{break-after:auto;page-break-after:auto}',
      '.label img{max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain;image-rendering:auto}',
      '.service-label{font-family:Arial,sans-serif;text-align:center;font-size:18pt;font-weight:700}',
    ].join('')
      popup.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>Печать WB</title><style>${printCss}</style></head><body>${pages}<script>Promise.all(Array.from(document.images).map(function(img){return img.complete?Promise.resolve():new Promise(function(resolve){img.onload=resolve;img.onerror=resolve})})).then(function(){window.focus();window.print()})</script></body></html>`)
      popup.document.close()
    } catch {
      popup.close()
      setError('Не удалось подготовить этикетки к печати.')
    }
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
            {!tape ? <TextField
              size="small"
              type="number"
              label="Копий каждого макета"
              value={copies}
              onChange={(event) => setCopies(Math.max(1, Math.min(99, Number(event.target.value) || 1)))}
              slotProps={{ htmlInput: { min: 1, max: 99 } }}
              sx={{ width: 220 }}
              data-testid="fbs-print-preview-copies"
              data-task-id="FBS-10"
            /> : null}
            <LabelSizeSelect
              value={labelSize.id}
              onChange={setLabelSize}
              testId="fbs-print-preview-label-size"
            />
          </Stack>
          {error ? <Alert severity="error">{error}</Alert> : null}
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
            {previewSequence.map((entry) => entry.kind === 'error' ? (
              <Box key={`${entry.item.order_id}-${entry.item.code}`} sx={{ gridColumn: '1 / -1' }}>
                <ErrorNotice>{fbsTapeOrderErrorText(entry.item)}</ErrorNotice>
              </Box>
            ) : (
              <Paper key={entry.preview.asset.id} variant="outlined" sx={{ p: 2 }}>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ alignItems: 'stretch' }}><Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography variant="subtitle2">Стикер WB №{entry.preview.asset.wb_order_id ?? '—'}</Typography><Box component="img" src={entry.preview.objectUrl} alt={assetLabel(entry.preview.asset)} sx={{ width: '100%', aspectRatio: `${labelSize.widthMm} / ${labelSize.heightMm}`, objectFit: 'contain', bgcolor: '#fff', my: 1.5 }} />
                  </Box>
                  {entry.preview.asset.kind === 'order_sticker' ? <Paper variant="outlined" sx={{ width: { xs: '100%', md: 180 }, minHeight: 120, p: 2, display: 'flex', alignItems: 'center', justifyContent: 'center', bgcolor: 'grey.50' }}><Typography variant="h6" sx={{ textAlign: 'center' }}>Служебная этикетка WMS<br />№ {entry.preview.asset.order_number ?? '—'}</Typography></Paper> : null}
                </Stack>
                <Stack direction="row" spacing={1}>
                  {!tape && previews.length > 1 ? <Button startIcon={<PrintOutlinedIcon />} onClick={() => void print([entry.preview])} data-task-id="FBS-10">Печать только этого</Button> : null}
                  {entry.preview.asset.kind !== 'box_qr' ? (
                    <Button disabled={Boolean(entry.preview.asset.applied_at) || applyingId === entry.preview.asset.id} onClick={() => void apply(entry.preview.asset)} data-task-id="FBS-09">
                      {entry.preview.asset.applied_at ? 'Уже нанесён' : 'Подтвердить нанесение'}
                    </Button>
                  ) : null}
                </Stack>
              </Paper>
            ))}
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions>
        <ActionGroup>
          <SecondaryAction onClick={onClose} disabled={loading || Boolean(applyingId)}>Закрыть</SecondaryAction>
          <PrintAction
            what="стикеры заказов"
            placement="panel"
            onClick={() => void print(previews)}
            disabledReason={loading ? 'Предпросмотр ещё загружается' : previews.length === 0 ? 'Нет готовых стикеров для печати' : undefined}
            testId="fbs-print-preview-print-stickers"
          />
        </ActionGroup>
      </DialogActions>
    </Dialog>
  )
}
