import type { FormEventHandler } from 'react'
import { useEffect, useMemo, useState } from 'react'
import { suggestNextLocationForRack } from '../utils/formatLocationCode'
import { storageLocationLabel } from '../utils/inboundQueues'
import { suggestNextLocationCode } from '../utils/suggestNextLocationCode'
import { DeleteOutlined, EditOutlined, PrintOutlined } from '@mui/icons-material'
import JsBarcode from 'jsbarcode'
import {
  Alert,
  Autocomplete,
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
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material'

type WarehouseRow = { id: string; name: string; code: string }
type LocationRow = { id: string; code: string; warehouse_id: string; barcode: string }
type SellerRow = { id: string; name: string }
type LocationBalanceRow = {
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
  reserved: number
  available: number
}
type ProductRow = {
  id: string
  name: string
  sku_code: string
  volume_liters: number | null
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
  onCreateLocation: (body: {
    code?: string
    rack_name?: string
    side?: 1 | 2
    position?: number
  }) => Promise<boolean> // code — превью/совместимость со старым API
  onRenameWarehouse: (warehouseId: string, name: string) => Promise<boolean>
  onDeleteWarehouse: (warehouseId: string) => Promise<boolean>
  onRenameLocation: (warehouseId: string, locationId: string, code: string) => Promise<boolean>
  onDeleteLocation: (
    warehouseId: string,
    locationId: string,
    moveStockTo?: 'sorting' | 'unallocated',
  ) => Promise<boolean>
  onLoadLocationBalances: (locationId: string) => Promise<LocationBalanceRow[]>
  onListWarehouseRacks: (warehouseId: string) => Promise<string[]>
  onSuggestLocation: (
    warehouseId: string,
    rackName: string,
    side: 1 | 2,
  ) => Promise<{ position: number; code: string } | null>
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
    onRenameWarehouse,
    onDeleteWarehouse,
    onRenameLocation,
    onDeleteLocation,
    onLoadLocationBalances,
    onListWarehouseRacks,
    onSuggestLocation,
  } = props

  const [warehouseDialogOpen, setWarehouseDialogOpen] = useState(false)
  const [locationDialogOpen, setLocationDialogOpen] = useState(false)
  const [rackNameDraft, setRackNameDraft] = useState('')
  const [sideDraft, setSideDraft] = useState<1 | 2>(1)
  const [positionDraft, setPositionDraft] = useState<number | null>(null)
  const [generatedCode, setGeneratedCode] = useState('')
  const [rackOptions, setRackOptions] = useState<string[]>([])
  const [printDialogOpen, setPrintDialogOpen] = useState(false)
  const [printLocation, setPrintLocation] = useState<LocationRow | null>(null)
  const [barcodeRenderError, setBarcodeRenderError] = useState<string | null>(null)
  const [barcodeDataUrl, setBarcodeDataUrl] = useState<string | null>(null)
  const [warehouseEdit, setWarehouseEdit] = useState<WarehouseRow | null>(null)
  const [warehouseNameDraft, setWarehouseNameDraft] = useState('')
  const [warehouseDelete, setWarehouseDelete] = useState<WarehouseRow | null>(null)
  const [locationEdit, setLocationEdit] = useState<LocationRow | null>(null)
  const [locationCodeDraft, setLocationCodeDraft] = useState('')
  const [locationDelete, setLocationDelete] = useState<LocationRow | null>(null)
  const [locationDeleteBalances, setLocationDeleteBalances] = useState<LocationBalanceRow[]>([])
  const [locationDeleteLoading, setLocationDeleteLoading] = useState(false)

  const selectedWarehouse = useMemo(
    () => warehouses.find((w) => w.id === selectedWarehouseId) ?? null,
    [selectedWarehouseId, warehouses],
  )

  const visibleLocations = useMemo(() => {
    if (!selectedWarehouseId) return []
    return locations.filter((l) => l.warehouse_id === selectedWarehouseId)
  }, [locations, selectedWarehouseId])

  const locationDeleteQty = useMemo(
    () => locationDeleteBalances.reduce((sum, row) => sum + row.quantity, 0),
    [locationDeleteBalances],
  )

  const openLocationDelete = (loc: LocationRow) => {
    setLocationDelete(loc)
    setLocationDeleteBalances([])
    setLocationDeleteLoading(true)
    void (async () => {
      const rows = await onLoadLocationBalances(loc.id)
      setLocationDeleteBalances(rows)
      setLocationDeleteLoading(false)
    })()
  }

  const closeLocationDelete = () => {
    setLocationDelete(null)
    setLocationDeleteBalances([])
    setLocationDeleteLoading(false)
  }

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

  useEffect(() => {
    if (!locationDialogOpen || !selectedWarehouseId) {
      return
    }
    void (async () => {
      const racks = await onListWarehouseRacks(selectedWarehouseId)
      setRackOptions(racks)
    })()
  }, [locationDialogOpen, onListWarehouseRacks, selectedWarehouseId])

  useEffect(() => {
    if (!locationDialogOpen || !selectedWarehouseId) {
      return
    }
    const trimmed = rackNameDraft.trim()
    if (!trimmed) {
      setGeneratedCode('')
      setPositionDraft(null)
      return
    }
    const local = suggestNextLocationForRack(
      trimmed,
      sideDraft,
      visibleLocations.map((l) => l.code),
    )
    setGeneratedCode(local.code)
    setPositionDraft(local.position)

    void (async () => {
      const s = await onSuggestLocation(selectedWarehouseId, trimmed, sideDraft)
      if (s) {
        setGeneratedCode(s.code)
        setPositionDraft(s.position)
      }
    })()
  }, [
    locationDialogOpen,
    onSuggestLocation,
    rackNameDraft,
    selectedWarehouseId,
    sideDraft,
    visibleLocations,
  ])

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
                    <TableCell align="right" width={96} />
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
                      <TableCell align="right">
                        <Stack direction="row" spacing={0.5} sx={{ justifyContent: 'flex-end' }}>
                          <Tooltip title="Переименовать склад">
                            <IconButton
                              size="small"
                              aria-label="Переименовать склад"
                              data-testid="warehouse-rename"
                              onClick={(event) => {
                                event.stopPropagation()
                                setWarehouseEdit(w)
                                setWarehouseNameDraft(w.name)
                              }}
                            >
                              <EditOutlined fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="Удалить склад">
                            <IconButton
                              size="small"
                              aria-label="Удалить склад"
                              data-testid="warehouse-delete"
                              onClick={(event) => {
                                event.stopPropagation()
                                setWarehouseDelete(w)
                              }}
                            >
                              <DeleteOutlined fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        </Stack>
                      </TableCell>
                    </TableRow>
                  ))}
                  {warehouses.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={3}>
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
                onClick={() => {
                  setRackNameDraft('')
                  setSideDraft(1)
                  setPositionDraft(null)
                  setGeneratedCode(
                    // Fallback for the very first cell (legacy numeric pattern).
                    suggestNextLocationCode(visibleLocations.map((l) => l.code)),
                  )
                  setLocationDialogOpen(true)
                }}
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
                      <TableCell data-testid={loc.code === '__SORTING__' ? 'location-sorting-zone' : undefined}>
                        {storageLocationLabel(loc.code)}
                      </TableCell>
                      <TableCell sx={{ fontFamily: 'monospace', fontSize: 13 }}>
                        {loc.code === '__SORTING__' ? '—' : loc.barcode}
                      </TableCell>
                      <TableCell align="right">
                        {loc.code === '__SORTING__' ? null : (
                          <Stack direction="row" spacing={0.5} sx={{ justifyContent: 'flex-end' }}>
                            <Tooltip title="Печать ШК">
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
                            </Tooltip>
                            <Tooltip title="Переименовать ячейку">
                              <IconButton
                                size="small"
                                aria-label="Переименовать ячейку"
                                data-testid="location-rename"
                                onClick={() => {
                                  setLocationEdit(loc)
                                  setLocationCodeDraft(loc.code)
                                }}
                              >
                                <EditOutlined fontSize="small" />
                              </IconButton>
                            </Tooltip>
                            <Tooltip title="Удалить ячейку">
                              <IconButton
                                size="small"
                                aria-label="Удалить ячейку"
                                data-testid="location-delete"
                                onClick={() => openLocationDelete(loc)}
                              >
                                <DeleteOutlined fontSize="small" />
                              </IconButton>
                            </Tooltip>
                          </Stack>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                  {selectedWarehouseId && visibleLocations.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={3}>
                        <Typography variant="body2" color="text.secondary">
                          Для этого склада пока нет ячеек. Создайте первую.
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ) : null}
                  {!selectedWarehouseId ? (
                    <TableRow>
                      <TableCell colSpan={3}>
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
        open={warehouseEdit != null}
        onClose={() => setWarehouseEdit(null)}
        fullWidth
        maxWidth="sm"
        aria-labelledby="rename-warehouse-title"
      >
        <DialogTitle id="rename-warehouse-title">Переименовать склад</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            sx={{ mt: 1 }}
            label="Название"
            value={warehouseNameDraft}
            onChange={(event) => setWarehouseNameDraft(event.target.value)}
            data-testid="warehouse-rename-name"
          />
        </DialogContent>
        <DialogActions>
          <MuiButton type="button" onClick={() => setWarehouseEdit(null)}>
            Отмена
          </MuiButton>
          <MuiButton
            type="button"
            variant="contained"
            disabled={catalogBusy || !warehouseEdit || !warehouseNameDraft.trim()}
            data-testid="warehouse-rename-submit"
            onClick={() => {
              if (!warehouseEdit) return
              void (async () => {
                const ok = await onRenameWarehouse(warehouseEdit.id, warehouseNameDraft)
                if (ok) {
                  setWarehouseEdit(null)
                }
              })()
            }}
          >
            Сохранить
          </MuiButton>
        </DialogActions>
      </Dialog>

      <Dialog
        open={warehouseDelete != null}
        onClose={() => setWarehouseDelete(null)}
        fullWidth
        maxWidth="sm"
        aria-labelledby="delete-warehouse-title"
      >
        <DialogTitle id="delete-warehouse-title">Удалить склад</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mt: 1 }}>
            {warehouseDelete
              ? `Склад «${warehouseDelete.name}» будет удалён только если к нему не привязаны документы, ячейки и остатки.`
              : ''}
          </Typography>
        </DialogContent>
        <DialogActions>
          <MuiButton type="button" onClick={() => setWarehouseDelete(null)}>
            Отмена
          </MuiButton>
          <MuiButton
            type="button"
            color="error"
            variant="contained"
            disabled={catalogBusy || !warehouseDelete}
            data-testid="warehouse-delete-submit"
            onClick={() => {
              if (!warehouseDelete) return
              void (async () => {
                const ok = await onDeleteWarehouse(warehouseDelete.id)
                if (ok) {
                  setWarehouseDelete(null)
                }
              })()
            }}
          >
            Удалить
          </MuiButton>
        </DialogActions>
      </Dialog>

      <Dialog
        open={locationEdit != null}
        onClose={() => setLocationEdit(null)}
        fullWidth
        maxWidth="sm"
        aria-labelledby="rename-location-title"
      >
        <DialogTitle id="rename-location-title">Переименовать ячейку</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            sx={{ mt: 1 }}
            label="Код ячейки"
            value={locationCodeDraft}
            onChange={(event) => setLocationCodeDraft(event.target.value)}
            data-testid="location-rename-code"
          />
        </DialogContent>
        <DialogActions>
          <MuiButton type="button" onClick={() => setLocationEdit(null)}>
            Отмена
          </MuiButton>
          <MuiButton
            type="button"
            variant="contained"
            disabled={catalogBusy || !locationEdit || !locationCodeDraft.trim()}
            data-testid="location-rename-submit"
            onClick={() => {
              if (!locationEdit) return
              void (async () => {
                const ok = await onRenameLocation(
                  locationEdit.warehouse_id,
                  locationEdit.id,
                  locationCodeDraft,
                )
                if (ok) {
                  setLocationEdit(null)
                }
              })()
            }}
          >
            Сохранить
          </MuiButton>
        </DialogActions>
      </Dialog>

      <Dialog
        open={locationDelete != null}
        onClose={closeLocationDelete}
        fullWidth
        maxWidth="sm"
        aria-labelledby="delete-location-title"
      >
        <DialogTitle id="delete-location-title">Удалить ячейку</DialogTitle>
        <DialogContent>
          {locationDelete ? (
            <Stack spacing={1.25} sx={{ mt: 1 }}>
              <Typography variant="body2">
                Ячейка {locationDelete.code}. Перед удалением остаток не будет потерян.
              </Typography>
              {locationDeleteLoading ? (
                <Typography variant="body2" color="text.secondary">
                  Проверяем остатки…
                </Typography>
              ) : locationDeleteQty > 0 ? (
                <>
                  <Alert severity="warning" data-testid="location-delete-stock-warning">
                    В ячейке лежит {locationDeleteQty} шт. Выберите, куда перенести товар перед удалением адреса.
                  </Alert>
                  <TableContainer>
                    <Table size="small" data-testid="location-delete-balances">
                      <TableHead>
                        <TableRow>
                          <TableCell>Товар</TableCell>
                          <TableCell align="right">Шт</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {locationDeleteBalances.map((row) => (
                          <TableRow key={row.product_id}>
                            <TableCell>
                              {row.sku_code} · {row.product_name}
                            </TableCell>
                            <TableCell align="right">{row.quantity}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  В ячейке нет товара, её можно удалить.
                </Typography>
              )}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions sx={{ flexWrap: 'wrap', gap: 1 }}>
          <MuiButton type="button" onClick={closeLocationDelete}>
            Отмена
          </MuiButton>
          {locationDeleteQty > 0 ? (
            <>
              <MuiButton
                type="button"
                variant="outlined"
                disabled={catalogBusy || locationDeleteLoading || !locationDelete}
                data-testid="location-delete-move-sorting"
                onClick={() => {
                  if (!locationDelete) return
                  void (async () => {
                    const ok = await onDeleteLocation(
                      locationDelete.warehouse_id,
                      locationDelete.id,
                      'sorting',
                    )
                    if (ok) {
                      closeLocationDelete()
                    }
                  })()
                }}
              >
                В сортировку и удалить
              </MuiButton>
              <MuiButton
                type="button"
                variant="contained"
                color="warning"
                disabled={catalogBusy || locationDeleteLoading || !locationDelete}
                data-testid="location-delete-move-unallocated"
                onClick={() => {
                  if (!locationDelete) return
                  void (async () => {
                    const ok = await onDeleteLocation(
                      locationDelete.warehouse_id,
                      locationDelete.id,
                      'unallocated',
                    )
                    if (ok) {
                      closeLocationDelete()
                    }
                  })()
                }}
              >
                Без ячейки и удалить
              </MuiButton>
            </>
          ) : (
            <MuiButton
              type="button"
              color="error"
              variant="contained"
              disabled={catalogBusy || locationDeleteLoading || !locationDelete}
              data-testid="location-delete-submit"
              onClick={() => {
                if (!locationDelete) return
                void (async () => {
                  const ok = await onDeleteLocation(locationDelete.warehouse_id, locationDelete.id)
                  if (ok) {
                    closeLocationDelete()
                  }
                })()
              }}
            >
              Удалить
            </MuiButton>
          )}
        </DialogActions>
      </Dialog>

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
              e.preventDefault()
              void (async () => {
                const trimmedRack = rackNameDraft.trim()
                const ok = await onCreateLocation(
                  trimmedRack
                    ? {
                        rack_name: trimmedRack,
                        side: sideDraft,
                        position: positionDraft ?? undefined,
                        code: generatedCode,
                      }
                    : { code: generatedCode },
                )
                if (ok) {
                  setLocationDialogOpen(false)
                  setRackNameDraft('')
                  setPositionDraft(null)
                  setGeneratedCode('')
                }
              })()
            }}
            sx={{ pt: 2 }}
          >
            <Stack spacing={2}>
              <Autocomplete
                freeSolo
                options={rackOptions}
                value={rackNameDraft}
                onChange={(_, v) => {
                  setRackNameDraft(typeof v === 'string' ? v : (v ?? ''))
                }}
                onInputChange={(_, v) => setRackNameDraft(v)}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    name="rack_name"
                    data-testid="location-rack"
                    label="Стеллаж"
                    required
                    autoComplete="off"
                    disabled={!selectedWarehouseId}
                    helperText={
                      rackOptions.length > 0
                        ? 'Можно выбрать существующий или ввести новый.'
                        : 'Введите название стеллажа (текст или цифры).'
                    }
                  />
                )}
              />

              <Box>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                  Сторона
                </Typography>
                <ToggleButtonGroup
                  exclusive
                  size="small"
                  value={sideDraft}
                  onChange={(_, v) => {
                    if (v === 1 || v === 2) setSideDraft(v)
                  }}
                  aria-label="side"
                >
                  <ToggleButton value={1} data-testid="location-side-1">
                    1
                  </ToggleButton>
                  <ToggleButton value={2} data-testid="location-side-2">
                    2
                  </ToggleButton>
                </ToggleButtonGroup>
              </Box>

              <TextField
                name="location_generated_code"
                data-testid="location-code"
                label="Название ячейки"
                fullWidth
                value={generatedCode}
                helperText={
                  rackNameDraft.trim()
                    ? 'Название формируется автоматически: стеллаж + сторона + номер.'
                    : 'Сначала укажите стеллаж.'
                }
                slotProps={{ input: { readOnly: true } }}
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
                disabled={catalogBusy || !selectedWarehouseId || !rackNameDraft.trim()}
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
