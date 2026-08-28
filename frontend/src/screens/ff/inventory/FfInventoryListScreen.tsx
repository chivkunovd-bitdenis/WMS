import { Box, Link, Stack, Typography } from '@mui/material'
import { useState } from 'react'
import {
  DataTable,
  FilterBar,
  PrimaryAction,
  QtyCell,
  ScreenHeader,
  SelectInput,
  StatusChip,
  TextCell,
} from '../../../ui-kit'
import type { Column, StatusTone } from '../../../ui-kit'
import type { CountListItem, CountStatus } from './InventoryTypes'

const STATUS_LABEL: Record<CountStatus, string> = {
  draft: 'Черновик',
  posted: 'Проведён',
  cancelled: 'Отменён',
}

const STATUS_TONE: Record<CountStatus, StatusTone> = {
  draft: 'neutral',
  posted: 'ok',
  cancelled: 'stop',
}

type Props = {
  items: CountListItem[]
  loading: boolean
  onOpen: (id: string) => void
  onCreate: () => void
}

export function FfInventoryListScreen({ items, loading, onOpen, onCreate }: Props) {
  const [status, setStatus] = useState('')
  const [query, setQuery] = useState('')

  const rows = items.filter((item) => {
    if (status && item.status !== status) return false
    const needle = query.trim().toLowerCase()
    if (!needle) return true
    return `${item.number} ${item.createdBy} ${item.fillLabel}`.toLowerCase().includes(needle)
  })

  const columns: Column<CountListItem>[] = [
    {
      key: 'number',
      header: 'Документ',
      width: 190,
      // Номер — настоящая кнопка, а не покрашенный текст: иначе с клавиатуры
      // в документ не попасть, а программа чтения экрана назовёт его просто текстом.
      render: (row) => (
        <Stack spacing={0.25}>
          <Link
            component="button"
            type="button"
            underline="hover"
            align="left"
            variant="body2"
            sx={{ fontWeight: 700, textAlign: 'left' }}
            onClick={() => onOpen(row.id)}
            data-testid={`inv-open-${row.id}`}
          >
            {row.number}
          </Link>
          <Typography variant="caption" color="text.secondary">
            {row.createdAt}
          </Typography>
        </Stack>
      ),
    },
    {
      key: 'status',
      header: 'Статус',
      width: 130,
      render: (row) => <StatusChip label={STATUS_LABEL[row.status]} tone={STATUS_TONE[row.status]} />,
    },
    {
      key: 'fill',
      header: 'Чем наполнен',
      width: 220,
      render: (row) => <TextCell value={row.fillLabel} width={206} />,
    },
    {
      key: 'author',
      header: 'Кто создал',
      width: 170,
      render: (row) => <TextCell value={row.createdBy} width={158} />,
    },
    {
      key: 'progress',
      header: 'Посчитано',
      width: 120,
      align: 'right',
      render: (row) => (
        <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
          {row.counted} из {row.lines}
        </Typography>
      ),
    },
    {
      key: 'diff',
      header: 'Расхождений',
      width: 120,
      align: 'right',
      render: (row) => <QtyCell value={row.discrepancies} muted={row.discrepancies === 0} />,
    },
    {
      key: 'delta',
      header: 'Излишек / недостача',
      width: 170,
      align: 'right',
      render: (row) =>
        row.surplus === 0 && row.shortage === 0 ? (
          <Typography variant="body2" color="text.disabled">
            —
          </Typography>
        ) : (
          // Нулевую половину не показываем: «+0 −3» читается как две цифры там,
          // где новость ровно одна.
          <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
            {row.surplus > 0 ? (
              <Typography variant="body2" sx={{ color: 'success.main', fontWeight: 700 }}>
                +{row.surplus}
              </Typography>
            ) : null}
            {row.shortage > 0 ? (
              <Typography variant="body2" sx={{ color: 'error.main', fontWeight: 700 }}>
                −{row.shortage}
              </Typography>
            ) : null}
          </Stack>
        ),
    },
  ]

  return (
    <Box sx={{ p: 3 }}>
      <ScreenHeader
        title="Инвентаризация"
        purpose="Документы пересчёта: что числится и что реально лежит. Проведение выравнивает остаток по факту и записывает движения."
      />
      <FilterBar
        search={query}
        onSearchChange={setQuery}
        searchPlaceholder="Номер, автор или отбор"
        testId="inv-list-filters"
        actions={
          <PrimaryAction onClick={onCreate} data-testid="inv-create">
            Создать
          </PrimaryAction>
        }
      >
        <SelectInput
          label="Статус"
          value={status}
          onChange={setStatus}
          options={[
            { value: 'draft', label: 'Черновик' },
            { value: 'posted', label: 'Проведён' },
            { value: 'cancelled', label: 'Отменён' },
          ]}
          emptyLabel="Любой"
          testId="inv-list-status"
        />
      </FilterBar>
      <DataTable
        testId="inventory-list"
        columns={columns}
        rows={rows}
        getRowKey={(row) => row.id}
        loading={loading}
        fixedLayout
        empty={{
          title: 'Инвентаризаций пока нет',
          hint: 'Создайте документ или нажмите значок пересчёта на карте склада.',
        }}
      />
    </Box>
  )
}
