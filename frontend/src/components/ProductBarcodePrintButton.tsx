import { useState } from 'react'
import PrintOutlined from '@mui/icons-material/PrintOutlined'
import { IconButton, Tooltip } from '@mui/material'
import { ProductBarcodePrintDialog } from './ProductBarcodePrintDialog'
import { resolveProductPrimaryBarcode, type ProductLineDisplayMeta } from '../types/wbProductCatalog'

type Props = {
  meta: ProductLineDisplayMeta
  testId?: string
}

export function ProductBarcodePrintButton({
  meta,
  testId = 'ff-product-barcode-print',
}: Props) {
  const [printOpen, setPrintOpen] = useState(false)
  const printable = Boolean(resolveProductPrimaryBarcode(meta))

  return (
    <>
      <Tooltip
        title={
          printable
            ? 'Печать этикетки 58×40'
            : 'Нет баркода WB — откройте диалог и синхронизируйте карточки'
        }
      >
        <span>
          <IconButton
            size="small"
            aria-label="Печать ШК товара"
            data-testid={testId}
            onClick={() => setPrintOpen(true)}
          >
            <PrintOutlined fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>
      <ProductBarcodePrintDialog
        open={printOpen}
        meta={meta}
        onClose={() => setPrintOpen(false)}
      />
    </>
  )
}
