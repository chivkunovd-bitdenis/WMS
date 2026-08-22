import { CircularProgress, Stack } from '@mui/material'
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

  return (
    <Stack spacing={1} sx={{ alignItems: 'center', py: 1.5 }} data-testid={testId}>
      {error ? <ErrorNotice>{error}</ErrorNotice> : null}
      <PrimaryAction
        onClick={onLoadMore}
        disabled={loading}
        data-testid={testId ? `${testId}-action` : undefined}
        startIcon={loading ? <CircularProgress size={14} color="inherit" /> : undefined}
      >
        {loading ? 'Загружаем…' : 'Показать ещё'}
      </PrimaryAction>
    </Stack>
  )
}
