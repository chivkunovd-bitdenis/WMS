import { Box, CircularProgress, Stack } from '@mui/material'
import type { ReactNode } from 'react'
import { ErrorNotice } from './States'
import { PrimaryAction } from './Actions'

export type TableLoadMoreProps = {
  hasNext: boolean
  loading?: boolean
  error?: ReactNode
  onLoadMore: () => void
  testId?: string
}

/** The single continuation action rendered below a paginated table. */
export function TableLoadMore({ hasNext, loading = false, error, onLoadMore, testId }: TableLoadMoreProps) {
  if (!hasNext) return null

  const handleLoadMore = () => {
    if (!loading) onLoadMore()
  }

  return (
    <Stack spacing={1} sx={{ py: 1.5 }} data-testid={testId}>
      {error ? <ErrorNotice>{error}</ErrorNotice> : null}
      <Box sx={{ alignSelf: 'center' }}>
        <PrimaryAction
          onClick={handleLoadMore}
          disabled={loading}
          data-testid={testId ? `${testId}-action` : undefined}
          startIcon={loading ? <CircularProgress size={14} color="inherit" /> : undefined}
        >
          {loading ? 'Загружаем…' : 'Показать ещё'}
        </PrimaryAction>
      </Box>
    </Stack>
  )
}
