import Typography from '@mui/material/Typography'
import { productBarcodeColumnSubLines } from '../utils/productLabelText'

type Props = {
  barcode: string | null
  wb_size?: string | null
  wb_composition?: string | null
  testId?: string
  /** Состав ткани нужен только на печатной этикетке; в рабочей таблице скрыт по умолчанию. */
  showComposition?: boolean
}

/** ШК column: barcode digits + compact size sub-line (fixed width, no layout shift). */
export function ProductBarcodeCell({
  barcode,
  wb_size,
  wb_composition,
  testId,
  showComposition = false,
}: Props) {
  const subLines = productBarcodeColumnSubLines(
    { wb_size, wb_composition },
    { includeComposition: showComposition },
  )
  const digits = barcode?.trim() || '—'

  return (
    <Typography
      component="div"
      variant="body2"
      sx={{ maxWidth: 220 }}
      data-testid={testId}
    >
      <Typography variant="body2" component="span" sx={{ display: 'block' }} title={digits !== '—' ? digits : undefined}>
        {digits}
      </Typography>
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
