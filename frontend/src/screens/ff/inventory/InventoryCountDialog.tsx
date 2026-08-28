import { Box, Stack, Typography } from '@mui/material'
import { useMemo, useState } from 'react'
import { AppDialog, PrimaryAction, SecondaryAction, WarningNotice } from '../../../ui-kit'
import { InventoryTree } from './InventoryTree'
import {
  EMPTY_FILTERS,
  buildRows,
  setActual,
  totals,
  type InvRow,
} from './InventoryRows'
import type { InventoryCount } from './InventoryTypes'

// Пересчёт прямо с карты склада.
//
// Это тот же документ инвентаризации, что и на экране S-11, только суженный до
// одной ячейки или одной тары. Человек стоит у полки: уводить его на другой
// экран, чтобы пересчитать один короб, — лишний шаг и потерянное место в списке.
//
// Фильтров здесь нет намеренно: отбирать не из чего, в документе десяток строк.

function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod100 >= 11 && mod100 <= 14) return `${n} ${many}`
  if (mod10 === 1) return `${n} ${one}`
  if (mod10 >= 2 && mod10 <= 4) return `${n} ${few}`
  return `${n} ${many}`
}

type Props = {
  open: boolean
  /** Что пересчитываем: «Короб КР-000471», «Ячейка А-01-02». */
  title: string
  /** Где это лежит. Пусто, когда пересчитываем саму ячейку. */
  place?: string | null
  count: InventoryCount | null
  onChange: (next: InventoryCount) => void
  onClose: () => void
  onSave: () => void
  onPost: () => void
}

export function InventoryCountDialog({
  open,
  title,
  place,
  count,
  onChange,
  onClose,
  onSave,
  onPost,
}: Props) {
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set())

  const rows = useMemo(
    () => (count ? buildRows(count, EMPTY_FILTERS, collapsed) : []),
    [count, collapsed],
  )
  const t = useMemo(
    () => (count ? totals(count) : { lines: 0, counted: 0, discrepancies: 0, surplus: 0, shortage: 0, stale: 0 }),
    [count],
  )

  function toggle(row: InvRow) {
    setCollapsed((current) => {
      const next = new Set(current)
      if (next.has(row.key)) next.delete(row.key)
      else next.add(row.key)
      return next
    })
  }

  function handleActual(row: InvRow, value: number | null) {
    if (count) onChange(setActual(count, row.id, value))
  }

  const postReason =
    t.counted === 0 ? 'Не введено ни одной цифры' : undefined

  return (
    <AppDialog
      open={open}
      title={`Пересчёт: ${title}`}
      onClose={onClose}
      maxWidth="lg"
      testId="inventory-count-dialog"
      actions={
        <>
          <SecondaryAction onClick={onClose} data-testid="inv-dialog-close">
            Закрыть
          </SecondaryAction>
          <SecondaryAction
            onClick={onSave}
            disabledReason={t.counted === 0 ? 'Нечего сохранять' : undefined}
            data-testid="inv-dialog-save"
          >
            Сохранить
          </SecondaryAction>
          <PrimaryAction onClick={onPost} disabledReason={postReason} data-testid="inv-dialog-post">
            Провести
          </PrimaryAction>
        </>
      }
    >
      <Stack spacing={1.5}>
        {place ? (
          <Typography variant="body2" color="text.secondary">
            Лежит в ячейке <strong>{place}</strong>
          </Typography>
        ) : null}
        <Typography variant="body2" color="text.secondary">
          Введите фактическое количество у товара. Строка сходится — зелёная, расходится —
          красная. Сохранение оставит документ черновиком, проведение изменит остаток и
          запишет движения.
        </Typography>

        {t.stale > 0 ? (
          <WarningNotice testId="inv-dialog-stale">
            {`По ${plural(t.stale, 'строке', 'строкам', 'строкам')} остаток изменился с момента открытия: там прошло движение. При проведении посчитаем от нового остатка.`}
          </WarningNotice>
        ) : null}

        <Stack direction="row" spacing={3} sx={{ flexWrap: 'wrap' }}>
          <Typography variant="body2">
            Строк: <strong>{t.lines}</strong>
          </Typography>
          <Typography variant="body2">
            Посчитано: <strong>{t.counted}</strong>
          </Typography>
          <Typography variant="body2" color={t.discrepancies ? 'error.main' : 'text.secondary'}>
            С расхождением: <strong>{t.discrepancies}</strong>
          </Typography>
          {t.surplus > 0 ? (
            <Typography variant="body2" sx={{ color: 'success.main' }}>
              Излишек: <strong>+{t.surplus}</strong>
            </Typography>
          ) : null}
          {t.shortage > 0 ? (
            <Typography variant="body2" sx={{ color: 'error.main' }}>
              Недостача: <strong>−{t.shortage}</strong>
            </Typography>
          ) : null}
        </Stack>

        {/* Высоту держим: у короба три строки, у ячейки может быть сорок, и диалог
            не должен прыгать от одного нажатия к другому. */}
        <Box sx={{ maxHeight: 460, overflowY: 'auto' }}>
          <InventoryTree
            rows={rows}
            loading={false}
            readOnly={false}
            empty={{
              title: 'Здесь пусто',
              hint: 'Внутри этого места сейчас нет товара — пересчитывать нечего.',
            }}
            onToggle={toggle}
            onActual={handleActual}
          />
        </Box>
      </Stack>
    </AppDialog>
  )
}
