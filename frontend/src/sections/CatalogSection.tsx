import type { FormEventHandler } from 'react'
import { useEffect, useMemo, useState } from 'react'
import { PrintOutlined } from '@mui/icons-material'
import JsBarcode from 'jsbarcode'
import {
  Alert,
  Box,
  Button as MuiButton,
  Card as MuiCard,
  CardContent,
  CardHeader,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
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

type WarehouseRow = { id: string; name: string; code: string }
type LocationRow = { id: string; code: string; warehouse_id: string; barcode: string }
type SellerRow = { id: string; name: string }
type ProductRow = {
  id: string
  name: string
  sku_code: string
  volume_liters: number
  seller_id: string | null
  seller_name: string | null
  wb_nm_id?: number | null
  wb_vendor_code?: string | null
}

type WbImportedCardRow = {
  nm_id: number
  vendor_code: string | null
  title: string | null
  updated_at: string
}

type WbImportedSupplyRow = {
  external_key: string
  wb_supply_id: number | null
  wb_preorder_id: number | null
  status_id: number | null
  updated_at: string
}

type Props = {
  isFulfillmentAdmin: boolean
  catalogBusy: boolean
  catalogError: string | null
  sellers: SellerRow[]
  warehouses: WarehouseRow[]
  locations: LocationRow[]
  selectedWarehouseId: string | null
  setSelectedWarehouseId: (id: string) => void
  products: ProductRow[]

  onCreateWarehouse: FormEventHandler<HTMLFormElement>
  onCreateLocation: FormEventHandler<HTMLFormElement>
  onCreateSeller: FormEventHandler<HTMLFormElement>
  onCreateProduct: FormEventHandler<HTMLFormElement>

  // Wildberries
  wbSellerId: string | null
  setWbSellerId: (id: string) => void
  wbHasContentToken: boolean
  wbHasSuppliesToken: boolean
  wbTokensBusy: boolean
  wbSyncBusy: boolean
  wbSuppliesSyncBusy: boolean
  wbLinkBusy: boolean
  wbJobStatus: string | null
  wbJobResult: string | null
  wbSuppliesJobStatus: string | null
  wbSuppliesJobResult: string | null
  wbImportedCards: WbImportedCardRow[]
  wbImportedSupplies: WbImportedSupplyRow[]

  onSaveWbTokens: FormEventHandler<HTMLFormElement>
  onStartWbCardsSyncJob: () => void
  onStartWbSuppliesSyncJob: () => void
  onLinkProductToWb: FormEventHandler<HTMLFormElement>
}

export function CatalogSection(props: Props) {
  const {
    isFulfillmentAdmin,
    catalogBusy,
    catalogError,
    warehouses,
    locations,
    selectedWarehouseId,
    setSelectedWarehouseId,
    onCreateWarehouse,
    onCreateLocation,
  } = props

  const [warehouseDialogOpen, setWarehouseDialogOpen] = useState(false)
  const [locationDialogOpen, setLocationDialogOpen] = useState(false)
  const [printDialogOpen, setPrintDialogOpen] = useState(false)
  const [printLocation, setPrintLocation] = useState<LocationRow | null>(null)
  const [barcodeRenderError, setBarcodeRenderError] = useState<string | null>(null)
  const [barcodeDataUrl, setBarcodeDataUrl] = useState<string | null>(null)

  const selectedWarehouse = useMemo(
    () => warehouses.find((w) => w.id === selectedWarehouseId) ?? null,
    [selectedWarehouseId, warehouses],
  )

  const visibleLocations = useMemo(() => {
    if (!selectedWarehouseId) return []
    return locations.filter((l) => l.warehouse_id === selectedWarehouseId)
  }, [locations, selectedWarehouseId])

  useEffect(() => {
    if (!printDialogOpen || !printLocation) {
      return
    }
    setBarcodeRenderError(null)
    setBarcodeDataUrl(null)
    const draw =
      (JsBarcode as unknown as { default?: typeof JsBarcode }).default ?? JsBarcode

    // Render into an offscreen canvas and show as image.
    // This avoids browser quirks with drawing into a canvas that is being mounted via a Dialog portal.
    const t = window.setTimeout(() => {
      try {
        const c = document.createElement('canvas')
        c.width = 320
        c.height = 80
        const ctx = c.getContext('2d')
        if (!ctx) {
          setBarcodeRenderError('Canvas context недоступен.')
          return
        }
        ctx.fillStyle = '#fff'
        ctx.fillRect(0, 0, c.width, c.height)
        draw(c, printLocation.barcode, {
          format: 'CODE128',
          displayValue: false,
          height: 64,
          margin: 8,
          lineColor: '#111',
          background: '#fff',
        })
        setBarcodeDataUrl(c.toDataURL('image/png'))
      } catch (e) {
        setBarcodeRenderError(e instanceof Error ? e.message : 'Не удалось отрисовать штрихкод.')
      }
    }, 0)

    return () => window.clearTimeout(t)
  }, [printDialogOpen, printLocation])

  return (
    <Box id="catalog-section" data-testid="catalog-section" sx={{ display: 'grid', gap: 2 }}>
      {catalogError ? (
        <Alert severity="error" data-testid="catalog-error">
          {catalogError}
        </Alert>
      ) : null}

      {!isFulfillmentAdmin ? (
        <Alert severity="info" data-testid="catalog-not-available">
          Управление складами и ячейками доступно только фулфилменту.
        </Alert>
      ) : (
        <MuiCard
          variant="outlined"
          data-testid="warehouses-panel"
          sx={{
            height: '33vh',
            minHeight: 260,
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <CardHeader
            title="Склады"
            subheader="Выберите склад — ниже отобразятся ячейки. Код склада: латиница, цифры, _ и -."
            action={
              <MuiButton
                type="button"
                variant="contained"
                size="small"
                data-testid="create-warehouse"
                onClick={() => setWarehouseDialogOpen(true)}
              >
                Создать склад
              </MuiButton>
            }
            sx={{ pb: 1 }}
          />
          <Divider />
          <CardContent sx={{ pt: 0, flex: 1, minHeight: 0 }}>
            <TableContainer sx={{ height: '100%' }}>
              <Table size="small" stickyHeader aria-label="Склады" data-testid="warehouse-table">
                <TableHead>
                  <TableRow>
                    <TableCell>Название</TableCell>
                    <TableCell width={180}>Код</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {warehouses.map((w) => (
                    <TableRow
                      key={w.id}
                      hover
                      selected={w.id === selectedWarehouseId}
                      onClick={() => setSelectedWarehouseId(w.id)}
                      sx={{ cursor: 'pointer' }}
                      data-testid="warehouse-row"
                      data-warehouse-id={w.id}
                    >
                      <TableCell>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {w.name}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" color="text.secondary">
                          {w.code}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                  {warehouses.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={2}>
                        <Typography variant="body2" color="text.secondary">
                          Пока нет складов. Создайте первый.
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </MuiCard>
      )}

      {isFulfillmentAdmin ? (
        <MuiCard variant="outlined" data-testid="locations-panel">
          <CardHeader
            title="Ячейки"
            subheader={
              selectedWarehouse ? (
                <span>
                  Склад: <strong>{selectedWarehouse.name}</strong> ({selectedWarehouse.code})
                </span>
              ) : (
                'Ячейку нельзя создать без склада. Сначала выберите склад сверху.'
              )
            }
            action={
              <MuiButton
                type="button"
                variant="contained"
                size="small"
                data-testid="create-location"
                disabled={!selectedWarehouseId}
                onClick={() => setLocationDialogOpen(true)}
              >
                Создать ячейку
              </MuiButton>
            }
            sx={{ pb: 1 }}
          />
          <Divider />
          <CardContent sx={{ pt: 0 }}>
            <TableContainer>
              <Table size="small" aria-label="Ячейки" data-testid="location-table">
                <TableHead>
                  <TableRow>
                    <TableCell width={240}>Код ячейки</TableCell>
                    <TableCell>Штрихкод</TableCell>
                    <TableCell align="right" width={80} />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {visibleLocations.map((loc) => (
                    <TableRow key={loc.id} data-testid="location-row" data-location-id={loc.id}>
                      <TableCell>{loc.code}</TableCell>
                      <TableCell sx={{ fontFamily: 'monospace', fontSize: 13 }}>
                        {loc.barcode}
                      </TableCell>
                      <TableCell align="right">
                        <Tooltip title="Печать ШК">
                          <span>
                            <IconButton
                              size="small"
                              aria-label="Печать ШК"
                              data-testid="location-print"
                              onClick={() => {
                                setPrintLocation(loc)
                                setPrintDialogOpen(true)
                              }}
                            >
                              <PrintOutlined fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  ))}
                  {selectedWarehouseId && visibleLocations.length === 0 ? (
                    <TableRow>
                      <TableCell>
                        <Typography variant="body2" color="text.secondary">
                          Для этого склада пока нет ячеек. Создайте первую.
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ) : null}
                  {!selectedWarehouseId ? (
                    <TableRow>
                      <TableCell>
                        <Typography variant="body2" color="text.secondary">
                          Выберите склад сверху — ячейки отфильтруются по нему.
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </MuiCard>
      ) : null}

      <Dialog
        open={warehouseDialogOpen}
        onClose={() => setWarehouseDialogOpen(false)}
        fullWidth
        maxWidth="sm"
        aria-labelledby="create-warehouse-title"
      >
        <DialogTitle id="create-warehouse-title">Создать склад</DialogTitle>
        <DialogContent>
          <Box
            component="form"
            data-testid="warehouse-form"
            noValidate
            onSubmit={(e) => {
              onCreateWarehouse(e)
              setWarehouseDialogOpen(false)
            }}
            sx={{ pt: 1 }}
          >
            <Stack spacing={2}>
              <TextField
                name="warehouse_name"
                data-testid="warehouse-name"
                label="Название"
                required
                autoComplete="off"
                fullWidth
              />
              <TextField
                name="warehouse_code"
                data-testid="warehouse-code"
                label="Код"
                required
                autoComplete="off"
                fullWidth
                helperText="Латиница, цифры, символы _ и -"
              />
            </Stack>
            <DialogActions sx={{ px: 0, pt: 2 }}>
              <MuiButton type="button" onClick={() => setWarehouseDialogOpen(false)}>
                Отмена
              </MuiButton>
              <MuiButton
                type="submit"
                variant="contained"
                data-testid="warehouse-submit"
                disabled={catalogBusy}
              >
                {catalogBusy ? '…' : 'Создать'}
              </MuiButton>
            </DialogActions>
          </Box>
        </DialogContent>
      </Dialog>

      <Dialog
        open={printDialogOpen}
        onClose={() => {
          setPrintDialogOpen(false)
          setPrintLocation(null)
        }}
        fullWidth
        maxWidth="sm"
        aria-labelledby="print-location-title"
      >
        <DialogTitle id="print-location-title">Печать штрихкода</DialogTitle>
        <DialogContent>
          {printLocation ? (
            <Box
              data-testid="location-print-preview"
              sx={{
                border: '1px solid',
                borderColor: 'divider',
                borderRadius: 2,
                p: 2,
                mt: 1,
                display: 'grid',
                gap: 1,
                justifyItems: 'center',
              }}
            >
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                Ячейка № {printLocation.code}
              </Typography>
              {barcodeDataUrl ? (
                <img
                  src={barcodeDataUrl}
                  alt="barcode"
                  data-testid="barcode-image"
                  style={{
                    width: 320,
                    maxWidth: '100%',
                    height: 'auto',
                    border: '1px dashed rgba(0,0,0,0.2)',
                    borderRadius: 12,
                    background: '#fff',
                  }}
                />
              ) : (
                <Box
                  sx={{
                    width: 320,
                    height: 80,
                    maxWidth: '100%',
                    border: '1px dashed',
                    borderColor: 'divider',
                    borderRadius: 2,
                    bgcolor: '#fff',
                  }}
                />
              )}
              <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                {printLocation.barcode}
              </Typography>
              <Typography
                variant="caption"
                color="text.secondary"
                data-testid="barcode-render-status"
              >
                {barcodeRenderError
                  ? 'ошибка рендера'
                  : barcodeDataUrl
                    ? `готово (len=${barcodeDataUrl.length})`
                    : 'генерация…'}
              </Typography>
              {barcodeRenderError ? (
                <Typography variant="caption" color="error" data-testid="barcode-render-error">
                  {barcodeRenderError}
                </Typography>
              ) : null}
            </Box>
          ) : (
            <Typography variant="body2" color="text.secondary">
              Ячейка не выбрана.
            </Typography>
          )}
        </DialogContent>
        <DialogActions>
          <MuiButton
            type="button"
            onClick={() => {
              if (!printLocation || !barcodeDataUrl) {
                return
              }
              // Safari can open a blank window when using window.open + document.write.
              // Use an offscreen iframe to print reliably.
              const html = `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Print barcode</title>
    <style>
      @page { margin: 10mm; }
      body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; padding: 0; margin: 0; }
      .wrap { display: grid; gap: 8px; justify-items: center; }
      .title { font-size: 14px; font-weight: 700; }
      .code { font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
      img { width: 320px; height: auto; }
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="title">Ячейка № ${printLocation.code}</div>
      <img id="barcode" src="${barcodeDataUrl}" alt="barcode" />
      <div class="code">${printLocation.barcode}</div>
    </div>
  </body>
</html>`

              const iframe = document.createElement('iframe')
              iframe.setAttribute('aria-hidden', 'true')
              iframe.style.position = 'fixed'
              iframe.style.right = '0'
              iframe.style.bottom = '0'
              iframe.style.width = '0'
              iframe.style.height = '0'
              iframe.style.border = '0'
              document.body.appendChild(iframe)

              const cleanup = () => {
                try {
                  document.body.removeChild(iframe)
                } catch {
                  // ignore
                }
              }

              const printNow = () => {
                const w = iframe.contentWindow
                if (!w) {
                  cleanup()
                  return
                }
                try {
                  w.focus()
                } catch {
                  // ignore
                }
                // Delay to ensure image decode/paint.
                setTimeout(() => {
                  try {
                    w.print()
                  } finally {
                    setTimeout(cleanup, 500)
                  }
                }, 100)
              }

              iframe.srcdoc = html
              iframe.onload = () => {
                const doc = iframe.contentDocument
                const img = doc?.getElementById('barcode') as HTMLImageElement | null
                if (!img) {
                  printNow()
                  return
                }
                if (img.complete) {
                  printNow()
                  return
                }
                img.addEventListener('load', printNow, { once: true })
                img.addEventListener('error', printNow, { once: true })
              }
            }}
            variant="contained"
            disabled={!printLocation || !barcodeDataUrl}
            data-testid="location-print-action"
          >
            Печать
          </MuiButton>
          <MuiButton
            type="button"
            onClick={() => {
              setPrintDialogOpen(false)
              setPrintLocation(null)
            }}
          >
            Закрыть
          </MuiButton>
        </DialogActions>
      </Dialog>

      <Dialog
        open={locationDialogOpen}
        onClose={() => setLocationDialogOpen(false)}
        fullWidth
        maxWidth="sm"
        aria-labelledby="create-location-title"
      >
        <DialogTitle id="create-location-title">Создать ячейку</DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ pt: 1 }}>
            <Typography variant="body2" color="text.secondary" data-testid="location-dialog-hint">
              {selectedWarehouse
                ? `Склад: ${selectedWarehouse.name} (${selectedWarehouse.code})`
                : 'Склад не выбран.'}
            </Typography>
          </Stack>
          <Box
            component="form"
            data-testid="location-form"
            noValidate
            onSubmit={(e) => {
              onCreateLocation(e)
              setLocationDialogOpen(false)
            }}
            sx={{ pt: 2 }}
          >
            <Stack spacing={2}>
              <TextField
                name="location_code"
                data-testid="location-code"
                label="Код ячейки"
                required
                autoComplete="off"
                fullWidth
                disabled={!selectedWarehouseId}
              />
            </Stack>
            <DialogActions sx={{ px: 0, pt: 2 }}>
              <MuiButton type="button" onClick={() => setLocationDialogOpen(false)}>
                Отмена
              </MuiButton>
              <MuiButton
                type="submit"
                variant="contained"
                data-testid="location-submit"
                disabled={catalogBusy || !selectedWarehouseId}
              >
                {catalogBusy ? '…' : 'Создать'}
              </MuiButton>
            </DialogActions>
          </Box>
        </DialogContent>
      </Dialog>

    </Box>
  )
}

