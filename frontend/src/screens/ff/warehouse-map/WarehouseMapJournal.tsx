import { Box, Paper, Stack, Typography } from '@mui/material'
import ChevronLeft from '@mui/icons-material/ChevronLeft'
import ChevronRight from '@mui/icons-material/ChevronRight'
import ExpandMore from '@mui/icons-material/ExpandMore'
import { useState } from 'react'
import {
  ActionGroup,
  AppDialog,
  DataTable,
  IconAction,
  QtyCell,
  SecondaryAction,
  TextCell,
} from '../../../ui-kit'
import type { Column } from '../../../ui-kit'
import type { MovementEntry } from './WarehouseMapTypes'

// Журнал отвечает на единственный вопрос, который возникает у склада наутро:
// «кто это переложил и когда». Поэтому сотрудник и время — обычные колонки,
// а не подсказка под строкой.

function formatMoment(iso: string): string {
  const moment = new Date(iso)
  if (!Number.isFinite(moment.getTime())) {
    return iso
  }
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Europe/Moscow',
  })
    .format(moment)
    .replace(', ', ' ')
}

const COLUMNS: Column<MovementEntry>[] = [
  {
    key: 'subject',
    header: 'Что переместили',
    render: (entry) => <TextCell value={entry.subject} width={380} />,
  },
  {
    key: 'qty',
    header: 'Штук',
    width: 90,
    align: 'right',
    render: (entry) => <QtyCell value={entry.qty} />,
  },
  {
    key: 'from',
    header: 'Откуда',
    width: 180,
    render: (entry) => <TextCell value={entry.from_label} width={168} />,
  },
  {
    key: 'to',
    header: 'Куда',
    width: 180,
    render: (entry) => <TextCell value={entry.to_label} width={168} />,
  },
  {
    key: 'actor',
    header: 'Сотрудник',
    width: 170,
    render: (entry) => <TextCell value={entry.actor_name} width={158} />,
  },
  {
    key: 'at',
    header: 'Когда',
    width: 130,
    render: (entry) => (
      <Typography variant="body2" sx={{ whiteSpace: 'nowrap' }}>
        {formatMoment(entry.at)}
      </Typography>
    ),
  },
]

// Восемь строк на страницу: столько влезает под таблицу, не отжимая карту вниз.
// Журнал — справка, а не второй экран, и занимать половину высоты он не должен.
const PAGE_SIZE = 8

export function WarehouseMapJournal({
  entries,
  loading,
  open,
  onToggle,
}: {
  entries: MovementEntry[]
  loading: boolean
  open: boolean
  onToggle: () => void
}) {
  const [page, setPage] = useState(0)
  const pages = Math.max(1, Math.ceil(entries.length / PAGE_SIZE))
  const current = Math.min(page, pages - 1)
  const from = current * PAGE_SIZE
  const shown = entries.slice(from, from + PAGE_SIZE)

  return (
    <Paper variant="outlined" sx={{ mt: 2, p: 2 }} data-testid="warehouse-map-journal">
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        <IconAction
          title={open ? 'Свернуть журнал' : 'Раскрыть журнал'}
          onClick={onToggle}
          testId="warehouse-map-journal-toggle"
        >
          <ExpandMore
            fontSize="small"
            sx={{ transition: 'transform 120ms', transform: open ? 'rotate(180deg)' : 'none' }}
          />
        </IconAction>
        <Typography variant="subtitle1">Журнал перемещений</Typography>
        <Typography variant="body2" color="text.secondary">
          {loading
            ? 'загружается'
            : entries.length > 0
              ? `записей: ${entries.length}`
              : 'записей пока нет'}
        </Typography>
        <Box sx={{ flexGrow: 1 }} />
        {open && !loading && entries.length > PAGE_SIZE ? (
          <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
            <IconAction
              title="Предыдущая страница"
              onClick={() => setPage(current - 1)}
              disabledReason={current === 0 ? 'Это первая страница' : undefined}
              testId="warehouse-map-journal-prev"
            >
              <ChevronLeft fontSize="small" />
            </IconAction>
            <Typography variant="body2" sx={{ whiteSpace: 'nowrap' }}>
              {from + 1}–{Math.min(from + PAGE_SIZE, entries.length)} из {entries.length}
            </Typography>
            <IconAction
              title="Следующая страница"
              onClick={() => setPage(current + 1)}
              disabledReason={current >= pages - 1 ? 'Это последняя страница' : undefined}
              testId="warehouse-map-journal-next"
            >
              <ChevronRight fontSize="small" />
            </IconAction>
          </Stack>
        ) : null}
      </Stack>
      {open ? (
        <Box sx={{ mt: 1.5 }}>
          <DataTable
            testId="warehouse-map-journal-table"
            columns={COLUMNS}
            rows={shown}
            getRowKey={(entry) => entry.id}
            loading={loading}
            empty={{
              title: 'Перемещений пока не было',
              hint: 'Перетащите строку на другую ячейку — запись появится здесь.',
            }}
          />
        </Box>
      ) : null}
    </Paper>
  )
}

export function WarehouseMapHistoryDialog({
  title,
  entries,
  onClose,
}: {
  title: string | null
  entries: MovementEntry[]
  onClose: () => void
}) {
  if (!title) {
    return null
  }
  return (
    <AppDialog
      open
      onClose={onClose}
      maxWidth="lg"
      testId="warehouse-map-history-dialog"
      title={`История · ${title}`}
      actions={
        <ActionGroup>
          <SecondaryAction onClick={onClose} data-testid="warehouse-map-history-close">
            Закрыть
          </SecondaryAction>
        </ActionGroup>
      }
    >
      <DataTable
        testId="warehouse-map-history-table"
        columns={COLUMNS}
        rows={entries}
        getRowKey={(entry) => entry.id}
        empty={{
          title: 'Ничего не перекладывали',
          hint: 'С этой строкой пока не делали перемещений.',
        }}
      />
    </AppDialog>
  )
}
