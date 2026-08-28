import { memo } from 'react'
import { Box, Stack, TableCell, Typography } from '@mui/material'
import { ProductBarcodePrintButton } from '../../components/ProductBarcodePrintButton'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { formatProductBarcodeDisplay, type ProductLineDisplayMeta } from '../../types/wbProductCatalog'

type InboundProductLineCellProps = {
  meta: ProductLineDisplayMeta
  productId: string
  printTestId: string
}

// memo обязателен: в заявке бывает под триста строк, и без него каждый скан
// перерисовывал фото, штрихкоды и названия во всей таблице разом.
export const InboundProductLineCell = memo(function InboundProductLineCell({
  meta,
  productId,
  printTestId,
}: InboundProductLineCellProps) {
  const barcode = formatProductBarcodeDisplay(meta)

  return (
    <TableCell sx={{ minWidth: 0, overflow: 'hidden' }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', minWidth: 0 }}>
        <Box sx={{ flex: '0 0 44px', display: 'flex' }}>
          <ProductPhotoThumb
            src={meta.wb_primary_image_url}
            alt={meta.product_name}
            testId="ff-inbound-line-photo"
          />
        </Box>
        <Box sx={{ flex: '1 1 auto', minWidth: 0 }}>
          <Typography
            variant="body2"
            sx={{
              fontWeight: 700,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={meta.product_name}
            data-testid="ff-inbound-line-product-name"
          >
            {meta.product_name}
          </Typography>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={{ xs: 0, sm: 1 }}
            sx={{ minWidth: 0 }}
          >
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{
                flex: '1 1 0',
                minWidth: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
              title={meta.sku_code}
              data-testid="ff-inbound-line-sku"
            >
              SKU {meta.sku_code}
            </Typography>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{
                flex: '1 1 0',
                minWidth: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
              title={barcode !== '—' ? barcode : undefined}
              data-testid="ff-inbound-line-barcode"
            >
              ШК {barcode}
            </Typography>
          </Stack>
        </Box>
        <Box sx={{ flex: '0 0 40px', display: 'flex', justifyContent: 'center' }}>
          <ProductBarcodePrintButton
            meta={meta}
            testId={printTestId}
            productId={productId}
            printSource="catalog"
          />
        </Box>
      </Stack>
    </TableCell>
  )
})

type InboundBoxContentLineProps = {
  meta: ProductLineDisplayMeta
  quantity: number
}

/** Компактная строка товара в содержимом короба (фото, название, артикул+ШК, кол-во). */
export const InboundBoxContentLine = memo(function InboundBoxContentLine({ meta, quantity }: InboundBoxContentLineProps) {
  const barcode = formatProductBarcodeDisplay(meta)

  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center', minWidth: 0 }}>
      <Box sx={{ flex: '0 0 32px', display: 'flex' }}>
        <ProductPhotoThumb
          src={meta.wb_primary_image_url}
          alt={meta.product_name}
          size={32}
          testId="ff-inbound-box-line-photo"
        />
      </Box>
      <Box sx={{ flex: '1 1 auto', minWidth: 0 }}>
        <Typography
          variant="body2"
          sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
          title={meta.product_name}
          data-testid="ff-inbound-box-line-name"
        >
          {meta.product_name}
        </Typography>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
          title={`${meta.sku_code} · ШК ${barcode}`}
          data-testid="ff-inbound-box-line-sku"
        >
          {meta.sku_code} · ШК {barcode}
        </Typography>
      </Box>
      <Typography
        variant="body2"
        sx={{ fontWeight: 700, flexShrink: 0, pl: 1 }}
        data-testid="ff-inbound-box-line-qty"
      >
        {quantity}
      </Typography>
    </Stack>
  )
})
