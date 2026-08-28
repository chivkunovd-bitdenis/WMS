import { Stack, Typography } from '@mui/material'
import { useEffect, useState } from 'react'
import {
  ActionGroup,
  AppDialog,
  NumberInput,
  PrimaryAction,
  SecondaryAction,
  SelectInput,
} from '../../../ui-kit'
import type { PickPlace } from './pickRows'

// Окно выбора места открывается только тогда, когда мест действительно
// несколько. Если товар лежит в одном месте, спрашивать не о чем: пик по
// товару сразу снимает штуку оттуда, где она лежит.
//
// Это зеркало окна раскладки «Куда положить»: там место и количество, и здесь
// место и количество. Один и тот же вопрос не должен выглядеть на двух экранах
// по-разному, иначе оператор каждый раз перечитывает.

export function PickSourceDialog({
  open,
  productName,
  planLeft,
  places,
  onClose,
  onConfirm,
}: {
  open: boolean
  productName: string
  /** Сколько ещё нужно по плану отгрузки — больше этого снимать незачем. */
  planLeft: number
  places: PickPlace[]
  onClose: () => void
  onConfirm: (placeKey: string, qty: number) => void
}) {
  const [placeKey, setPlaceKey] = useState('')
  const [qty, setQty] = useState<number | null>(null)

  const place = places.find((one) => one.key === placeKey) ?? null
  const max = place ? Math.min(place.left, planLeft) : 0

  // Окно открывается заново под другой товар, поэтому старый выбор надо забыть.
  // Место не подставляем: экран не знает, к какому стеллажу подошёл человек, а
  // угаданное за него место — это списание не с того короба.
  useEffect(() => {
    if (!open) return
    const single = places.length === 1 ? places[0] : null
    setPlaceKey(single ? single.key : '')
    setQty(single ? Math.min(single.left, planLeft) : null)
  }, [open, places, planLeft])

  function choose(value: string) {
    setPlaceKey(value)
    const next = places.find((one) => one.key === value)
    setQty(next ? Math.min(next.left, planLeft) : null)
  }

  return (
    <AppDialog
      open={open}
      onClose={onClose}
      title="Откуда снимаем"
      testId="pick-source-dialog"
      actions={
        <ActionGroup>
          <SecondaryAction onClick={onClose} data-testid="pick-source-cancel">
            Отмена
          </SecondaryAction>
          <PrimaryAction
            onClick={() => {
              if (!place || !qty) return
              onConfirm(place.key, Math.min(qty, max))
            }}
            disabledReason={
              !place ? 'Выберите место' : !qty || qty > max ? 'Укажите количество' : undefined
            }
            data-testid="pick-source-confirm"
          >
            Снять
          </PrimaryAction>
        </ActionGroup>
      }
    >
      <Stack spacing={2}>
        <Stack spacing={0.5}>
          <Typography variant="subtitle2">{productName}</Typography>
          <Typography variant="body2" color="text.secondary">
            По плану осталось снять {planLeft} шт. Этот товар лежит в {places.length} местах —
            выберите, откуда взяли.
          </Typography>
        </Stack>
        <SelectInput
          label="Место"
          value={placeKey}
          onChange={choose}
          options={places.map((one) => ({
            value: one.key,
            label: `${one.label} — ${one.left} шт`,
          }))}
          emptyLabel="Выберите место"
          testId="pick-source-place"
        />
        <NumberInput
          label="Сколько штук"
          value={qty}
          onChange={setQty}
          min={1}
          max={max || 1}
          disabled={!place}
          helperText={
            place
              ? `В этом месте лежит ${place.left} шт, по плану осталось ${planLeft} шт`
              : 'Сначала выберите место'
          }
          testId="pick-source-qty"
        />
      </Stack>
    </AppDialog>
  )
}
