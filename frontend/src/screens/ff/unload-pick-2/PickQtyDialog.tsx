import { Stack, Typography } from '@mui/material'
import { useEffect, useState } from 'react'
import { ActionGroup, AppDialog, NumberInput, PrimaryAction, SecondaryAction } from '../../../ui-kit'
import type { RouteItem } from './routeRows'

// Здесь спрашивают только «сколько».
//
// В варианте А окно спрашивало «откуда», потому что экран не знал, у какого
// стеллажа стоит человек. Здесь место человек уже назвал сам — пикнул палету
// или взял её в работу, — и вопрос «откуда» просто исчезает. Остаётся один
// вопрос, на который экран ответить не может: сколько штук легло в руку.

export function PickQtyDialog({
  open,
  item,
  placeLabel,
  onClose,
  onConfirm,
}: {
  open: boolean
  item: RouteItem | null
  /** Адрес места одной строкой — чтобы человек видел, с чего списывает. */
  placeLabel: string
  onClose: () => void
  onConfirm: (qty: number) => void
}) {
  const [qty, setQty] = useState<number | null>(null)
  const left = item ? Math.max(0, item.qty - item.picked) : 0
  const max = item ? Math.min(item.need, left) : 0

  // Окно открывается под другой товар — старое число надо забыть. Подставляем
  // сразу нужное количество: чаще всего человек берёт ровно столько, сколько
  // просит документ, и лишнее подтверждение здесь стоит движения руки.
  useEffect(() => {
    if (!open) return
    setQty(max > 0 ? max : null)
  }, [open, max])

  return (
    <AppDialog
      open={open}
      onClose={onClose}
      title="Сколько снимаем"
      testId="route-qty-dialog"
      actions={
        <ActionGroup>
          <SecondaryAction onClick={onClose} data-testid="route-qty-cancel">
            Отмена
          </SecondaryAction>
          <PrimaryAction
            onClick={() => {
              if (!qty) return
              onConfirm(Math.min(qty, max))
            }}
            disabledReason={!qty || qty > max ? 'Укажите количество' : undefined}
            data-testid="route-qty-confirm"
          >
            Снять
          </PrimaryAction>
        </ActionGroup>
      }
    >
      <Stack spacing={2}>
        <Stack spacing={0.5}>
          <Typography variant="subtitle2">{item ? item.product.name : ''}</Typography>
          <Typography variant="body2" color="text.secondary">
            {placeLabel}
            {item ? ` · ${item.inside.toLowerCase()}` : ''}
          </Typography>
        </Stack>
        <NumberInput
          label="Сколько штук"
          value={qty}
          onChange={setQty}
          min={1}
          max={max || 1}
          helperText={
            item
              ? `Здесь лежит ${left} шт, по документу отсюда нужно ${item.need} шт`
              : 'Выберите строку'
          }
          testId="route-qty-value"
        />
      </Stack>
    </AppDialog>
  )
}
