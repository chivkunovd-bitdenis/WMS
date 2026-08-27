import { Stack, Typography } from '@mui/material'
import { useMemo, useState } from 'react'
import {
  ActionGroup,
  AppDialog,
  CheckboxInput,
  DataTable,
  PrimaryAction,
  QtyCell,
  SecondaryAction,
  StatusChip,
  TextCell,
} from '../../../ui-kit'
import type { Column } from '../../../ui-kit'
import type { Proposal } from './sortingProposals'

// Массовая раскладка по подсказке.
//
// Двести строк по одной — это не работа, а наказание, и именно на этом экран
// ломается при настоящем объёме. Система знает, где каждый товар уже лежит, и
// умеет предложить раскладку целиком. Но предложить — не значит сделать: список
// показывается целиком, с причиной по каждой строке, и любую можно исключить.
// Молча разложить двести позиций «как система решила» нельзя: это остаток, а
// остаток потом кто-то идёт искать руками.

export function SortingBulkDialog({
  open,
  proposals,
  onClose,
  onApply,
}: {
  open: boolean
  proposals: Proposal[]
  onClose: () => void
  onApply: (accepted: Proposal[]) => void
}) {
  const [excluded, setExcluded] = useState<Set<string>>(new Set())

  const rows = useMemo(
    () => proposals.map((one) => ({ ...one, included: one.included && !excluded.has(one.product.id) })),
    [excluded, proposals],
  )
  const accepted = rows.filter((one) => one.included && one.cell)
  const qty = accepted.reduce((sum, one) => sum + one.qty, 0)

  const columns: Column<Proposal>[] = [
    {
      key: 'take',
      header: '',
      width: 56,
      render: (row) =>
        row.cell ? (
          <CheckboxInput
            label={`Разложить ${row.product.name}`}
            hideLabel
            checked={row.included}
            onChange={(checked) =>
              setExcluded((current) => {
                const next = new Set(current)
                if (checked) next.delete(row.product.id)
                else next.add(row.product.id)
                return next
              })
            }
            testId={`bulk-take-${row.product.id}`}
          />
        ) : null,
    },
    {
      key: 'product',
      header: 'Товар',
      render: (row) => <TextCell value={row.product.name} width={280} />,
    },
    {
      key: 'qty',
      header: 'Штук',
      width: 88,
      align: 'right',
      render: (row) => <QtyCell value={row.qty} />,
    },
    {
      key: 'cell',
      header: 'Куда',
      width: 120,
      render: (row) =>
        row.cell ? (
          <Typography variant="body2" sx={{ fontWeight: 700 }}>
            {row.cell.code}
          </Typography>
        ) : (
          <Typography variant="body2" color="text.secondary">
            выберите руками
          </Typography>
        ),
    },
    {
      key: 'reason',
      header: 'Почему',
      width: 190,
      render: (row) => (
        <StatusChip
          label={row.reason}
          tone={row.cell ? 'ok' : row.reason === 'новый на складе' ? 'neutral' : 'warn'}
        />
      ),
    },
  ]

  return (
    <AppDialog
      open={open}
      onClose={onClose}
      maxWidth="lg"
      title="Разложить по подсказке"
      testId="sorting-bulk-dialog"
      actions={
        <ActionGroup>
          <SecondaryAction onClick={onClose} data-testid="sorting-bulk-cancel">
            Отмена
          </SecondaryAction>
          <PrimaryAction
            onClick={() => onApply(accepted)}
            disabledReason={accepted.length === 0 ? 'Ни одной строки не выбрано' : undefined}
            data-testid="sorting-bulk-apply"
          >
            {`Разложить ${accepted.length}`}
          </PrimaryAction>
        </ActionGroup>
      }
    >
      <Stack spacing={1.5}>
        <Typography variant="body2" color="text.secondary">
          Отмечено {accepted.length} строк из {rows.length}, это {qty.toLocaleString('ru-RU')} шт.
          Строки без подсказки не отмечены — для них система не знает, куда класть.
        </Typography>
        <DataTable
          testId="sorting-bulk-table"
          columns={columns}
          rows={rows}
          getRowKey={(row) => row.product.id}
          empty={{ title: 'Раскладывать нечего', hint: 'Всё уже разложено по ячейкам.' }}
        />
      </Stack>
    </AppDialog>
  )
}
