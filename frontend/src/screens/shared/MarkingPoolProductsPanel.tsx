import { useEffect, useState } from 'react'
import { Alert, Box, Button, Chip, Paper, Stack, Typography } from '@mui/material'
import LinkOutlined from '@mui/icons-material/LinkOutlined'
import { MarkingPoolProductsDialog } from './MarkingPoolProductsDialog'

type LinkedProduct = {
  id: string
  sku_code: string
  name: string
}

type Props = {
  token: string
  poolId: string
  poolTitle: string
  sellerId: string
  testIdPrefix: string
}

export function MarkingPoolProductsPanel({
  token,
  poolId,
  poolTitle,
  sellerId,
  testIdPrefix,
}: Props) {
  const [products, setProducts] = useState<LinkedProduct[]>([])
  const [dialogOpen, setDialogOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setProducts([])
    setError(null)
  }, [poolId])

  return (
    <Paper variant="outlined" sx={{ p: 2 }} data-testid={`${testIdPrefix}-pool-panel`}>
      <Stack spacing={1.5}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
          <Typography variant="subtitle2">Пул: {poolTitle}</Typography>
          <Box sx={{ flex: 1 }} />
          <Button
            size="small"
            variant="outlined"
            startIcon={<LinkOutlined />}
            onClick={() => setDialogOpen(true)}
            data-testid={`${testIdPrefix}-pool-link-products`}
          >
            Привязать товары
          </Button>
        </Stack>
        {error ? (
          <Alert severity="error" data-testid={`${testIdPrefix}-pool-panel-error`}>
            {error}
          </Alert>
        ) : null}
        <Stack
          direction="row"
          spacing={0.75}
          sx={{ flexWrap: 'wrap' }}
          data-testid={`${testIdPrefix}-pool-product-chips`}
        >
          {products.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              Товары не привязаны.
            </Typography>
          ) : (
            products.map((p) => (
              <Chip
                key={p.id}
                label={p.sku_code}
                size="small"
                data-testid={`${testIdPrefix}-pool-linked-chip-${p.id}`}
              />
            ))
          )}
        </Stack>
      </Stack>
      <MarkingPoolProductsDialog
        open={dialogOpen}
        token={token}
        poolId={poolId}
        poolTitle={poolTitle}
        sellerId={sellerId}
        linkedProducts={products}
        testIdPrefix={testIdPrefix}
        onClose={() => setDialogOpen(false)}
        onSaved={setProducts}
        onError={setError}
      />
    </Paper>
  )
}
