import type { ReactNode } from 'react'
import PrintOutlined from '@mui/icons-material/PrintOutlined'
import { IconButton, TableCell, Tooltip, Typography } from '@mui/material'
import { ProductPhotoThumb } from './ProductPhotoThumb'
import {
  formatProductBarcodeDisplay,
  resolveProductPrimaryBarcode,
  type ProductLineDisplayMeta,
} from '../types/wbProductCatalog'
import { printProductBarcodeFromMeta } from '../utils/productBarcodePrint'

type HeadProps = {
  showPrint?: boolean
  nameLabel?: string
}

export function FfProductTableHeadCells({ showPrint = true, nameLabel = 'Наименование' }: HeadProps) {
  return (
    <>
      <TableCell sx={{ width: 56 }}>Фото</TableCell>
      <TableCell sx={{ width: 190, pl: 2 }}>Артикул</TableCell>
      <TableCell sx={{ width: 220 }}>ШК</TableCell>
      <TableCell sx={{ width: 140 }}>Артикул продавца</TableCell>
      <TableCell sx={{ width: 120, pr: 2 }}>Артикул WB</TableCell>
      <TableCell sx={{ pl: 2 }}>{nameLabel}</TableCell>
      {showPrint ? (
        <TableCell align="center" sx={{ width: 56, pr: 1 }} />
      ) : null}
    </>
  )
}

type CellsProps = {
  meta: ProductLineDisplayMeta
  showPrint?: boolean
  printTestId?: string
  nameExtra?: ReactNode
}

export function FfProductLineCells({
  meta,
  showPrint = true,
  printTestId = 'ff-product-barcode-print',
  nameExtra,
}: CellsProps) {
  const barcodeDisplay = formatProductBarcodeDisplay(meta)
  const printable = Boolean(resolveProductPrimaryBarcode(meta))

  return (
    <>
      <TableCell>
        <ProductPhotoThumb src={meta.wb_primary_image_url} />
      </TableCell>
      <TableCell sx={{ whiteSpace: 'nowrap', pl: 2 }} title={meta.sku_code}>
        {meta.sku_code}
      </TableCell>
      <TableCell sx={{ whiteSpace: 'nowrap' }} title={barcodeDisplay}>
        {barcodeDisplay}
      </TableCell>
      <TableCell
        sx={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
        title={meta.wb_vendor_code ?? '—'}
      >
        {meta.wb_vendor_code ?? '—'}
      </TableCell>
      <TableCell sx={{ pr: 2 }}>{meta.wb_nm_id ?? '—'}</TableCell>
      <TableCell sx={{ pl: 2, whiteSpace: 'normal', wordBreak: 'break-word' }}>
        <Typography variant="body2" sx={{ lineHeight: 1.25 }}>
          {meta.product_name}
        </Typography>
        {nameExtra}
      </TableCell>
      {showPrint ? (
        <TableCell align="center" sx={{ pr: 1 }}>
          <Tooltip title={printable ? 'Печать ШК товара' : 'Нет баркода WB'}>
            <span>
              <IconButton
                size="small"
                aria-label="Печать ШК товара"
                disabled={!printable}
                data-testid={printTestId}
                onClick={() => {
                  try {
                    printProductBarcodeFromMeta(meta)
                  } catch (e) {
                    window.alert(e instanceof Error ? e.message : 'Не удалось напечатать ШК.')
                  }
                }}
              >
                <PrintOutlined fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        </TableCell>
      ) : null}
    </>
  )
}
