import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import { Accordion, AccordionDetails, AccordionSummary, Box, Stack, Typography } from '@mui/material'
import { forwardRef, useCallback, useImperativeHandle, useMemo, useRef, useState } from 'react'
import { apiUrl } from '../../api'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import {
  DataTable,
  EmptyState,
  ErrorNotice,
  PrimaryAction,
  ProductCell,
  QtyCell,
  TextCell,
} from '../../ui-kit'
import type { Column } from '../../ui-kit'

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

function packageTitle(item: InboundPackage): string {
  return `${item.kind === 'box' ? 'Короб' : 'Грузоместо'} № ${item.number}`
}

function intakeLabel(item: InboundPackage): string {
  return `Приёмка № ${item.request_display_number ?? item.request_id}`
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

    const visiblePackages = listError
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
        setAddressedPackage(null)
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
        return false
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

    const compositionColumns: Column<PackageCompositionRow>[] = [
      {
        key: 'product',
        header: 'Товар',
        width: 168,
        render: (row) => (
          <ProductCell
            photo={<ProductPhotoThumb src={row.wb_primary_image_url} alt={row.name} />}
            sku={row.sku_code}
          />
        ),
      },
      { key: 'name', header: 'Название', width: 320, render: (row) => <TextCell value={row.name} width={320} /> },
      {
        key: 'barcode',
        header: 'ШК',
        width: 220,
        render: (row) => <TextCell value={row.wb_primary_barcode ?? row.wb_barcodes[0]} width={220} />,
      },
      {
        key: 'remaining',
        header: 'Остаток',
        width: 120,
        align: 'right',
        render: (row) => <QtyCell value={row.remaining_qty} />,
      },
    ]

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
            <DataTable<InboundPackage>
              columns={[
                { key: 'object', header: 'Объект', render: () => null },
                { key: 'barcode', header: 'Внутренний ШК', render: () => null },
                { key: 'intake', header: 'Приёмка', render: () => null },
                { key: 'warehouse', header: 'Склад', render: () => null },
              ]}
              rows={[]}
              getRowKey={(item) => item.id}
              loading
              testId="ff-catalog-inbound-packages-skeleton"
            />
          ) : null}

          {listError ? (
            <Stack spacing={1.5} sx={{ p: 2, alignItems: 'flex-start' }}>
              <ErrorNotice testId="ff-catalog-inbound-packages-error">
                Не удалось загрузить короба и грузоместа
              </ErrorNotice>
              <PrimaryAction onClick={() => void loadList()} data-testid="ff-catalog-inbound-packages-retry">
                Повторить
              </PrimaryAction>
            </Stack>
          ) : null}

          {listLoaded && !listLoading && !listError && packages.length === 0 ? (
            <EmptyState
              title="Коробов и грузомест пока нет"
              hint="Создайте короб или грузоместо в разделе «Приёмка»."
              testId="ff-catalog-inbound-packages-empty"
            />
          ) : null}

          {!listLoading
            ? visiblePackages.map((item) => {
                const compositionRows: PackageCompositionRow[] = item.lines.flatMap((line) => {
                  const product = productsById.get(line.product_id)
                  return product ? [{ ...line, ...product }] : []
                })
                const completed = item.intake_status === 'done'
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
                        <EmptyState
                          title={completed ? 'Приёмка завершена' : 'Состав по грузоместу не ведётся'}
                          hint={completed ? 'Состав по грузоместу не ведётся' : undefined}
                        />
                      ) : completed ? (
                        <EmptyState
                          title="Товар из короба уже разложен"
                          hint="Исторический состав здесь не показывается."
                        />
                      ) : compositionRows.length === 0 ? (
                        <EmptyState
                          title="В коробе пока нет товаров"
                          hint="Наполните короб в разделе «Приёмка»."
                        />
                      ) : (
                        <Box sx={{ maxWidth: '100%', overflowX: 'auto' }}>
                          <Box sx={{ minWidth: 828 }}>
                            <DataTable
                              columns={compositionColumns}
                              rows={compositionRows}
                              getRowKey={(row) => row.product_id}
                              testId={`ff-catalog-inbound-composition-${item.id}`}
                            />
                          </Box>
                        </Box>
                      )}
                    </AccordionDetails>
                  </Accordion>
                )
              })
            : null}
        </AccordionDetails>
      </Accordion>
    )
  },
)
