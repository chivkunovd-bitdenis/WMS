import { memo } from 'react'
import Typography from '@mui/material/Typography'
import { productBarcodeColumnSubLines } from '../utils/productLabelText'
import { normalizeProductBarcodes } from '../utils/productBarcodes'

type Props = {
  barcode: string | null
  barcodes?: string[]
  wb_size?: string | null
  wb_composition?: string | null
  testId?: string
  /** Состав ткани нужен только на печатной этикетке; в рабочей таблице скрыт по умолчанию. */
  showComposition?: boolean
}

/** ШК column: barcode digits + compact size sub-line (fixed width, no layout shift). */
function ProductBarcodeCellBase({
  barcode,
  barcodes = [],
  wb_size,
  wb_composition,
  testId,
  showComposition = false,
}: Props) {
  const subLines = productBarcodeColumnSubLines(
    { wb_size, wb_composition },
    { includeComposition: showComposition },
  )
  const normalizedBarcodes = normalizeProductBarcodes(barcode, barcodes)
  const title = normalizedBarcodes.length > 0 ? normalizedBarcodes.join('\n') : undefined

  return (
    <Typography
      component="div"
      variant="body2"
      sx={{ maxWidth: 220 }}
      data-testid={testId}
    >
      {normalizedBarcodes.length > 0 ? normalizedBarcodes.map((digits) => (
        <Typography
          key={digits}
          variant="body2"
          component="span"
          sx={{ display: 'block', wordBreak: 'break-word' }}
          title={title}
          data-barcode-line="true"
        >
          {digits}
        </Typography>
      )) : (
        <Typography variant="body2" component="span" sx={{ display: 'block' }} data-barcode-line="true">
          —
        </Typography>
      )}
      {subLines.map((line) => {
        const isComposition = line.startsWith('Состав:')
        return (
          <Typography
            key={line}
            variant="caption"
            color={isComposition ? 'text.secondary' : 'text.primary'}
            component="span"
            sx={{
              display: '-webkit-box',
              WebkitLineClamp: isComposition ? 2 : 1,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
              wordBreak: 'break-word',
            }}
            title={isComposition ? wb_composition?.trim() || undefined : undefined}
          >
            {line}
          </Typography>
        )
      })}
    </Typography>
  )
}

/**
 * memo: компонент повторяется в каждой строке операционных таблиц.
 * Без него любое обновление состояния экрана перерисовывало его во всех строках сразу.
 */
export const ProductBarcodeCell = memo(ProductBarcodeCellBase)
