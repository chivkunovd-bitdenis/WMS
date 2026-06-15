import Typography from '@mui/material/Typography'
import { productBarcodeColumnSubLines } from '../utils/productLabelText'

type Props = {
  barcode: string | null
  wb_size?: string | null
  wb_composition?: string | null
  testId?: string
}

/** ШК column: barcode digits + compact size/composition sub-lines (fixed width, no layout shift). */
export function ProductBarcodeCell({ barcode, wb_size, wb_composition, testId }: Props) {
  const subLines = productBarcodeColumnSubLines({ wb_size, wb_composition })
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
      {subLines.map((line) => (
        <Typography
          key={line}
          variant="caption"
          color="text.secondary"
          component="span"
          sx={{
            display: '-webkit-box',
            WebkitLineClamp: line.startsWith('Состав:') ? 2 : 1,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            wordBreak: 'break-word',
          }}
          title={line.startsWith('Состав:') ? wb_composition?.trim() || undefined : undefined}
        >
          {line}
        </Typography>
      ))}
    </Typography>
  )
}
