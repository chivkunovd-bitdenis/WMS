import { Alert, Box, Button, CircularProgress, Skeleton, Stack, TableBody, TableCell, TableRow, Typography } from '@mui/material'
import type { ReactNode } from 'react'

// Канон R-21: пустой раздел говорит, что пусто, почему и что нажать.
// Молча пустой блок оператор читает как поломку и идёт спрашивать.
export function EmptyState({
  title,
  hint,
  action,
  testId,
}: {
  title: string
  hint?: string
  action?: ReactNode
  testId?: string
}) {
  return (
    <Stack spacing={1.25} sx={{ alignItems: 'flex-start', px: 2, py: 3 }} data-testid={testId}>
      <Typography variant="subtitle2">{title}</Typography>
      {hint ? (
        <Typography variant="body2" color="text.secondary">
          {hint}
        </Typography>
      ) : null}
      {action}
    </Stack>
  )
}

// Канон R-22: таблица грузится скелетом строк, а не спиннером поверх пустоты.
// Скелет сразу показывает форму будущей таблицы — глаз уже стоит на нужной колонке.
export function TableSkeletonBody({ columns, rows = 5 }: { columns: number; rows?: number }) {
  return (
    <TableBody>
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <TableRow key={rowIndex}>
          {Array.from({ length: columns }).map((__, cellIndex) => (
            <TableCell key={cellIndex}>
              <Skeleton variant="rounded" height={12} />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </TableBody>
  )
}

// Канон R-23: ошибка — плашка в теле экрана, на языке склада, без кода ответа и стектрейса.
export function ErrorNotice({ children, testId }: { children: ReactNode; testId?: string }) {
  return (
    <Alert severity="error" sx={{ mb: 2 }} data-testid={testId}>
      {children}
    </Alert>
  )
}

// Канон R-01/R-02: шапка экрана — название и одна строка о назначении. Больше в ней ничего.
export function ScreenHeader({ title, purpose }: { title: string; purpose?: string }) {
  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="h5" gutterBottom>
        {title}
      </Typography>
      {purpose ? (
        <Typography variant="body2" color="text.secondary">
          {purpose}
        </Typography>
      ) : null}
    </Box>
  )
}

// Канон R-37: «Показать ещё» под таблицей — текстовая кнопка в строке TableRow с colSpan
// во всю ширину. Скрывается если hasNext=false. Во время загрузки — «Загружаем…» со спиннером.
// Не SecondaryAction (R-31 запрещает solo-outlined), не PrimaryAction (главное в шапке).
export function TableLoadMore({
  hasNext,
  loading,
  onLoadMore,
  columns,
  testId,
}: {
  hasNext: boolean
  loading: boolean
  onLoadMore: () => void
  columns: number
  testId?: string
}) {
  if (!hasNext) return null
  return (
    <TableRow>
      <TableCell colSpan={columns} sx={{ textAlign: 'center', py: 1 }}>
        <Button
          variant="text"
          size="small"
          disabled={loading}
          onClick={onLoadMore}
          data-testid={testId}
        >
          {loading ? (
            <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center' }}>
              <CircularProgress size={12} />
              <span>Загружаем…</span>
            </Stack>
          ) : (
            'Показать ещё'
          )}
        </Button>
      </TableCell>
    </TableRow>
  )
}
