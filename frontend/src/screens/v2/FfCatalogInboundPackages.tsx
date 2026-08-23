import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  CircularProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import { forwardRef, useCallback, useImperativeHandle, useMemo, useRef, useState } from 'react'
import { apiUrl } from '../../api'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'

type InboundPackageLine = {
  product_id: string
  remaining_qty: number
}

type InboundPackage = {
  id: string
  kind: 'box' | 'cargo_place'
  number: number
  internal_barcode: string
  request_id: string
  request_display_number: string | null
  warehouse_name: string | null
  intake_status: string
  composition_tracked: boolean
  fully_distributed: boolean
  remaining_qty: number | null
  lines: InboundPackageLine[]
}

export type CatalogInboundPackageProduct = {
  id: string
  sku_code: string
  name: string
  wb_primary_image_url: string | null
  wb_primary_barcode: string | null
  wb_barcodes: string[]
}

export type CatalogInboundPackagesHandle = {
  lookup: (barcode: string) => Promise<boolean | null>
}

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  products: CatalogInboundPackageProduct[]
}

type PackageCompositionRow = InboundPackageLine & CatalogInboundPackageProduct

function EmptyPanel({ title, hint }: { title: string; hint?: string }) {
  return (
    <Box sx={{ py: 2, color: 'text.secondary' }}>
      <Typography variant="body2">{title}</Typography>
      {hint ? (
        <Typography variant="caption" color="text.secondary">
          {hint}
        </Typography>
      ) : null}
    </Box>
  )
}

function packageTitle(item: InboundPackage): string {
  return `${item.kind === 'box' ? 'Короб' : 'Грузоместо'} № ${item.number}`
}

function intakeLabel(item: InboundPackage): string {
  const number = item.request_display_number ?? item.request_id
  return `Приёмка ${number.includes('№') ? number : `№ ${number}`}`
}

export const FfCatalogInboundPackages = forwardRef<CatalogInboundPackagesHandle, Props>(
  function FfCatalogInboundPackages({ token, authHeaders, products }, ref) {
    const [sectionOpen, setSectionOpen] = useState(false)
    const [listLoading, setListLoading] = useState(false)
    const [listLoaded, setListLoaded] = useState(false)
    const [listError, setListError] = useState(false)
    const [listedPackages, setListedPackages] = useState<InboundPackage[]>([])
    const [addressedPackage, setAddressedPackage] = useState<InboundPackage | null>(null)
    const [openPackageId, setOpenPackageId] = useState<string | null>(null)
    const requestSequence = useRef(0)

    const productsById = useMemo(() => new Map(products.map((product) => [product.id, product])), [products])

    const packages = useMemo(() => {
      if (!addressedPackage) return listedPackages
      const matchingListedPackage = listedPackages.find((item) => item.id === addressedPackage.id)
      if (!matchingListedPackage) return [addressedPackage, ...listedPackages]
      return listedPackages.map((item) => (item.id === addressedPackage.id ? addressedPackage : item))
    }, [addressedPackage, listedPackages])

    const visiblePackages = listLoading
      ? addressedPackage
        ? [addressedPackage]
        : []
      : packages

    const loadList = useCallback(async () => {
      setListLoading(true)
      setListError(false)
      try {
        const response = await fetch(apiUrl('/operations/inbound-packages'), {
          headers: { ...authHeaders(token) },
        })
        if (!response.ok) throw new Error('inbound_packages_load_failed')
        setListedPackages((await response.json()) as InboundPackage[])
        setListLoaded(true)
      } catch {
        setListError(true)
      } finally {
        setListLoading(false)
      }
    }, [authHeaders, token])

    const lookup = useCallback(async (barcode: string): Promise<boolean | null> => {
      const sequence = requestSequence.current + 1
      requestSequence.current = sequence
      setAddressedPackage(null)
      try {
        const response = await fetch(
          apiUrl(`/operations/inbound-packages/lookup?barcode=${encodeURIComponent(barcode)}`),
          { headers: { ...authHeaders(token) } },
        )
        if (requestSequence.current !== sequence) return null
        if (!response.ok) return false
        const item = (await response.json()) as InboundPackage
        if (requestSequence.current !== sequence) return null
        setAddressedPackage(item)
        setOpenPackageId(item.id)
        setSectionOpen(true)
        window.setTimeout(() => {
          document.getElementById(`ff-catalog-inbound-package-${item.id}`)?.scrollIntoView({
            behavior: 'smooth',
            block: 'nearest',
          })
        }, 0)
        return true
      } catch {
        return requestSequence.current === sequence ? false : null
      }
    }, [authHeaders, token])

    useImperativeHandle(ref, () => ({ lookup }), [lookup])

    const handleSectionChange = useCallback(
      (_: React.SyntheticEvent, expanded: boolean) => {
        setSectionOpen(expanded)
        if (expanded && !listLoaded && !listLoading) {
          void loadList()
        }
      },
      [listLoaded, listLoading, loadList],
    )

    return (
      <Accordion
        expanded={sectionOpen}
        onChange={handleSectionChange}
        disableGutters
        elevation={0}
        variant="outlined"
        data-testid="ff-catalog-inbound-packages"
        sx={{ mt: 2, overflow: 'hidden', '&::before': { display: 'none' } }}
      >
        <AccordionSummary
          expandIcon={<ExpandMoreIcon />}
          aria-controls="ff-catalog-inbound-packages-content"
          id="ff-catalog-inbound-packages-header"
          data-testid="ff-catalog-inbound-packages-toggle"
          sx={{ minHeight: 48, '& .MuiAccordionSummary-content': { my: 1.25 } }}
        >
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            Короба и грузоместа
          </Typography>
        </AccordionSummary>
        <AccordionDetails id="ff-catalog-inbound-packages-content" sx={{ p: 0 }}>
          {listLoading ? (
            <Stack
              direction="row"
              spacing={1}
              sx={{ p: 2, alignItems: 'center' }}
              data-testid="ff-catalog-inbound-packages-skeleton"
            >
              <CircularProgress size={18} />
              <Typography variant="body2" color="text.secondary">
                Загружаем короба и грузоместа…
              </Typography>
            </Stack>
          ) : null}

          {listError ? (
            <Stack spacing={1.5} sx={{ p: 2, alignItems: 'flex-start' }}>
              <Alert severity="error" data-testid="ff-catalog-inbound-packages-error">
                Не удалось загрузить короба и грузоместа
              </Alert>
              <Button variant="contained" onClick={() => void loadList()} data-testid="ff-catalog-inbound-packages-retry">
                Повторить
              </Button>
            </Stack>
          ) : null}

          {listLoaded && !listLoading && !listError && packages.length === 0 ? (
            <EmptyPanel
              title="Коробов и грузомест пока нет"
              hint="Создайте короб или грузоместо в разделе «Приёмка»."
            />
          ) : null}

          {visiblePackages.map((item) => {
            const compositionRows: PackageCompositionRow[] = item.lines.flatMap((line) => {
              const product = productsById.get(line.product_id)
              return product ? [{ ...line, ...product }] : []
            })
            const completed = item.intake_status === 'done'
            const fullyDistributed = item.kind === 'box' && item.fully_distributed
            return (
              <Accordion
                    key={item.id}
                    id={`ff-catalog-inbound-package-${item.id}`}
                    expanded={openPackageId === item.id}
                    onChange={(_, expanded) => setOpenPackageId(expanded ? item.id : null)}
                    disableGutters
                    elevation={0}
                    square
                    data-testid={`ff-catalog-inbound-package-${item.id}`}
                    sx={{ '&::before': { display: 'none' }, borderTop: '1px solid', borderColor: 'divider' }}
                  >
                    <AccordionSummary
                      expandIcon={<ExpandMoreIcon />}
                      aria-controls={`ff-catalog-inbound-package-content-${item.id}`}
                      id={`ff-catalog-inbound-package-header-${item.id}`}
                      sx={{ px: 2, minHeight: 48, '& .MuiAccordionSummary-content': { my: 1, minWidth: 0 } }}
                    >
                      <Stack
                        direction={{ xs: 'column', sm: 'row' }}
                        spacing={{ xs: 0.25, sm: 2 }}
                        sx={{ minWidth: 0, width: '100%', pr: 1, alignItems: { sm: 'center' } }}
                      >
                        <Typography variant="body2" sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}>
                          {packageTitle(item)}
                        </Typography>
                        <Typography variant="body2" color="text.secondary" sx={{ fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                          {item.internal_barcode}
                        </Typography>
                        <Stack direction="row" spacing={2} sx={{ minWidth: 0, ml: { sm: 'auto' }, flexWrap: 'wrap' }}>
                          <Typography variant="body2" color="text.secondary" noWrap>
                            {intakeLabel(item)}
                          </Typography>
                          {item.warehouse_name ? (
                            <Typography variant="body2" color="text.secondary" noWrap>
                              Склад: {item.warehouse_name}
                            </Typography>
                          ) : null}
                        </Stack>
                      </Stack>
                    </AccordionSummary>
                    <AccordionDetails id={`ff-catalog-inbound-package-content-${item.id}`} sx={{ px: 2, pb: 2, pt: 0 }}>
                      {item.kind === 'cargo_place' ? (
                        <EmptyPanel
                          title={completed ? 'Приёмка завершена' : 'Состав по грузоместу не ведётся'}
                          hint={completed ? 'Состав по грузоместу не ведётся' : undefined}
                        />
                      ) : fullyDistributed || completed ? (
                        <EmptyPanel
                          title="Товар из короба уже разложен"
                          hint="Исторический состав здесь не показывается."
                        />
                      ) : compositionRows.length === 0 ? (
                        <EmptyPanel
                          title="В коробе пока нет товаров"
                          hint="Наполните короб в разделе «Приёмка»."
                        />
                      ) : (
                        <TableContainer
                          sx={{ maxWidth: '100%', overflowX: 'auto' }}
                          data-testid={`ff-catalog-inbound-composition-${item.id}`}
                        >
                          <Table size="small" sx={{ minWidth: 760, tableLayout: 'fixed' }}>
                            <TableHead>
                              <TableRow>
                                <TableCell sx={{ width: 72 }}>Фото</TableCell>
                                <TableCell sx={{ width: 320 }}>Название</TableCell>
                                <TableCell sx={{ width: 140 }}>SKU</TableCell>
                                <TableCell sx={{ width: 180 }}>ШК</TableCell>
                                <TableCell align="right" sx={{ width: 96 }}>Остаток</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {compositionRows.map((row) => (
                                <TableRow key={row.product_id}>
                                  <TableCell>
                                    <ProductPhotoThumb src={row.wb_primary_image_url} alt={row.name} />
                                  </TableCell>
                                  <TableCell>
                                    <Typography variant="body2" noWrap title={row.name}>{row.name}</Typography>
                                  </TableCell>
                                  <TableCell>
                                    <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>{row.sku_code}</Typography>
                                  </TableCell>
                                  <TableCell>
                                    <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                                      {row.wb_primary_barcode ?? row.wb_barcodes[0] ?? '—'}
                                    </Typography>
                                  </TableCell>
                                  <TableCell align="right">{row.remaining_qty}</TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </TableContainer>
                      )}
                    </AccordionDetails>
              </Accordion>
            )
          })}
        </AccordionDetails>
      </Accordion>
    )
  },
)
