import { confirmDiscardChanges } from '../../utils/confirmDiscardChanges'
import { PrintQuantityField } from '../../components/PrintQuantityField'
import { useEffect, useMemo, useRef, useState } from 'react'
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
  LinearProgress,
} from '@mui/material'
import PrintOutlinedIcon from '@mui/icons-material/PrintOutlined'
import { resolveFbsAssetUrl, type FbsPrintAsset, type FbsPrintBatch } from './fbsApi'
import { loadLabelSizeId, resolveLabelSize, type LabelSize } from '../../utils/labelSize'
import { LabelSizeSelect } from '../../components/LabelSizeSelect'
import { buildFbsImagePrintDocument } from './fbsImagePrintDocument'
import { buildFbsPdfPrintTape } from './fbsPdfPrintTape'

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  batch: FbsPrintBatch | null
  warning?: string | null
  open: boolean
  onClose: () => void
  onApplied: (asset: FbsPrintAsset) => Promise<void>
}

type Preview = { asset: FbsPrintAsset; objectUrl: string }

const PDF_CONTENT_TYPE = 'application/pdf'

// Wildberries отдаёт стикер картинкой, Ozon — документом PDF. Картинку мы
// раскладываем на рулон 58x40 сами, у документа страница своя, и подменять её
// нашей вёрсткой нельзя: этикетка уедет за срез.
function isDocument(asset: FbsPrintAsset): boolean {
  return asset.content_type === PDF_CONTENT_TYPE
}

function assetLabel(asset: FbsPrintAsset): string {
  if (asset.kind === 'box_qr') return 'Печать QR короба WMS'
  if (asset.kind === 'cargo_place_qr') return 'Печать QR грузоместа WB'
  if (asset.kind === 'supply_qr') return 'Печать QR поставки WB'
  if (isDocument(asset)) return 'Печать этикетки отправления Ozon'
  return 'Печать стикера заказа WB'
}

export function FbsPrintPreviewDialog({
  token,
  authHeaders,
  batch,
  warning = null,
  open,
  onClose,
  onApplied,
}: Props) {
  const [previews, setPreviews] = useState<Preview[]>([])
  const [loading, setLoading] = useState(false)
  const [loadedCount, setLoadedCount] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [applyingId, setApplyingId] = useState<string | null>(null)
  const [copies, setCopies] = useState(1)
  const appliedCopies = useRef(1)
  const requestClose = () => {
    if (confirmDiscardChanges(copies !== appliedCopies.current)) onClose()
  }

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
    setPreviews([])
    setLoadedCount(0)
    setError(null)

    // Поставка на двести заказов — это триста этикеток. Раньше все запросы
    // уходили разом и окно показывало один кружок до последней картинки:
    // браузер держит около шести соединений, остальные стоят в очереди, а
    // оператор видит намертво замерший экран (бой 31.08.2026). Теперь качаем
    // порциями и показываем каждую этикетку сразу, как она пришла.
    const CONCURRENCY = 6
    const orderIndex = new Map(readyAssets.map((asset, index) => [asset.id, index]))
    let failedCount = 0
    let cursor = 0

    const loadOne = async (asset: (typeof readyAssets)[number]) => {
      const response = await fetch(resolveFbsAssetUrl(asset.preview_url!), {
        headers: { ...authHeaders(token) },
      })
      if (!response.ok) throw new Error(`Предпросмотр ${asset.id} недоступен (${response.status}).`)
      const objectUrl = URL.createObjectURL(await response.blob())
      objectUrls.push(objectUrl)
      return { asset, objectUrl }
    }

    const worker = async () => {
      while (active) {
        const index = cursor
        cursor += 1
        const asset = readyAssets[index]
        if (!asset) return
        try {
          const loaded = await loadOne(asset)
          if (!active) {
            URL.revokeObjectURL(loaded.objectUrl)
            return
          }
          // Порядок этикеток обязан совпадать с порядком заказов: печатают
          // пачкой и раскладывают по коробам подряд. Сеть возвращает картинки
          // вразнобой, поэтому вставляем на своё место, а не в конец.
          setPreviews((current) => {
            const next = [...current, loaded]
            next.sort((a, b) => orderIndex.get(a.asset.id)! - orderIndex.get(b.asset.id)!)
            return next
          })
        } catch {
          failedCount += 1
        }
        if (active) {
          setLoadedCount((current) => current + 1)
        }
      }
    }

    void Promise.all(Array.from({ length: Math.min(CONCURRENCY, readyAssets.length) }, worker))
      .then(() => {
        if (!active) return
        setError(failedCount > 0
          ? `Не загрузилось изображений: ${failedCount}. Остальные QR можно напечатать.`
          : null)
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
      appliedCopies.current = 1
      setCopies(1)
      setLabelSize(resolveLabelSize(loadLabelSizeId()))
    }
  }, [open, batch])

  const print = (items: Preview[]) => {
    if (items.length === 0) {
      setError('Нет готовых изображений — окно печати не открыто.')
      return
    }
    // Ozon присылает PDF со своим размером страниц. Соединяем страницы без
    // перерисовки, чтобы все короба ушли в одно задание печати и одну вкладку.
    const documents = items.filter(({ asset }) => isDocument(asset))
    const images = items.filter(({ asset }) => !isDocument(asset))
    // Окно нужно открыть прямо по нажатию кнопки: после асинхронной сборки
    // браузер сочтёт его всплывающим и заблокирует.
    const pdfPopup = documents.length > 0 ? window.open('', '_blank') : null
    const imagePopup = images.length > 0 ? window.open('', '_blank') : null
    if ((documents.length > 0 && !pdfPopup) || (images.length > 0 && !imagePopup)) {
      pdfPopup?.close()
      imagePopup?.close()
      setError('Браузер заблокировал окно печати. Разрешите всплывающие окна для WMS.')
      return
    }
    if (pdfPopup) {
      pdfPopup.opener = null
      pdfPopup.document.write('<!doctype html><html lang="ru"><meta charset="utf-8"><title>Лента этикеток Ozon</title><body>Собираем ленту этикеток Ozon…</body></html>')
      pdfPopup.document.close()
      void buildFbsPdfPrintTape(documents.map(({ objectUrl }) => objectUrl), copies)
        .then((blob) => {
          if (pdfPopup.closed) return
          const tapeUrl = URL.createObjectURL(blob)
          pdfPopup.location.replace(tapeUrl)
          appliedCopies.current = copies
          const cleanup = window.setInterval(() => {
            if (pdfPopup.closed) {
              URL.revokeObjectURL(tapeUrl)
              window.clearInterval(cleanup)
            }
          }, 2000)
        })
        .catch((cause) => {
          pdfPopup.close()
          setError(cause instanceof Error ? cause.message : 'Не удалось собрать общую ленту Ozon.')
        })
    }
    if (imagePopup) {
      imagePopup.opener = null
      imagePopup.document.write(buildFbsImagePrintDocument(
        images.map(({ objectUrl, asset }) => ({ objectUrl, label: assetLabel(asset) })),
        copies,
        labelSize,
      ))
      imagePopup.document.close()
      appliedCopies.current = copies
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
    <Dialog open={open} onClose={loading || applyingId ? undefined : requestClose} fullWidth maxWidth="lg">
      <DialogTitle>Проверка перед печатью</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }} useFlexGap>
            {/* Считаем то, что реально скачалось: сервер может считать актив готовым,
                а файла на диске не быть — тогда «Готово N» рядом с «готовых нет»
                сбивало оператора с толку (бой 27.08.2026). */}
            <Chip
              label={loading
                ? `Загружено ${previews.length} из ${readyAssets.length}`
                : `Готово ${previews.length}`}
              color={!loading && previews.length === 0 ? 'default' : 'success'}
            />
            {batch?.missing ? <Chip label={`Не получено ${batch.missing}`} color="warning" /> : null}
            {batch?.failed ? <Chip label={`Ошибок ${batch.failed}`} color="error" /> : null}
          </Stack>
          <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap' }} useFlexGap data-task-id="FBS-10">
            <PrintQuantityField
              size="small"
              label="Копий каждого макета"
              value={copies}
              onChange={setCopies}
              min={1} max={99}
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
          {warning ? <Alert severity="warning">{warning}</Alert> : null}
          {previews.some(({ asset }) => isDocument(asset)) ? (
            <Alert severity="info">
              Этикетки Ozon откроются одной PDF-лентой с исходным размером страниц.
              Печать — в окне браузера.
            </Alert>
          ) : null}
          {batch?.order_errors.map((item) => (
            <Alert key={item.order_id} severity="error">
              Заказ WB №{item.wb_order_id}: {item.message}
            </Alert>
          ))}
          {loading ? (
            <Stack spacing={1} sx={{ py: 2 }}>
              <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
                <CircularProgress size={22} />
                <Typography>
                  Загружаем этикетки: {loadedCount} из {readyAssets.length}. Готовые
                  можно печатать, не дожидаясь остальных.
                </Typography>
              </Stack>
              <LinearProgress
                variant="determinate"
                value={readyAssets.length > 0 ? (loadedCount / readyAssets.length) * 100 : 0}
                data-testid="fbs-print-preview-progress"
              />
            </Stack>
          ) : null}
          {!loading && previews.length === 0 ? (
            <Alert severity="warning">
              Готовых изображений нет: файлы не пришли от WB или пропали из хранилища.
              Запросите стикеры заново — кнопка запроса на вкладке упаковки.
            </Alert>
          ) : null}
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(260px,1fr))', gap: 2 }}>
            {previews.map(({ asset, objectUrl }) => (
              <Paper key={asset.id} variant="outlined" sx={{ p: 2 }}>
                <Typography variant="subtitle2">{assetLabel(asset)}</Typography>
                {isDocument(asset) ? (
                  <Box component="iframe" src={objectUrl} title={assetLabel(asset)} sx={{ width: '100%', height: 320, border: 0, bgcolor: '#fff', my: 1.5 }} />
                ) : (
                  <Box component="img" src={objectUrl} alt={assetLabel(asset)} sx={{ width: '100%', aspectRatio: `${labelSize.widthMm} / ${labelSize.heightMm}`, objectFit: 'contain', bgcolor: '#fff', my: 1.5 }} />
                )}
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
        <Button onClick={requestClose} disabled={Boolean(applyingId)}>Закрыть</Button>
        <Button variant="contained" startIcon={<PrintOutlinedIcon />} disabled={previews.length === 0} onClick={() => print(previews)} data-task-id="FBS-10">
          {previews.length === 1 ? 'Печать' : `Печать готовых (${previews.length})`}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
