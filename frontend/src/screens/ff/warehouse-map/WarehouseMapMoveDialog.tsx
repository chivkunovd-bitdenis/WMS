import { Stack, Typography } from '@mui/material'
import { useState } from 'react'
import {
  ActionGroup,
  AppDialog,
  DangerAction,
  NumberInput,
  PrimaryAction,
  SecondaryAction,
} from '../../../ui-kit'
import type { MapRow } from './WarehouseMapRows'

// Что оператор собирается сделать руками. Три повода — один диалог: во всех
// трёх случаях вопрос один и тот же — что, откуда, куда и сколько.
export type MoveIntent = {
  reason: 'move' | 'takeOff' | 'disband'
  row: MapRow
  /** Откуда берём — подпись места, где строка лежит сейчас. */
  fromLabel: string
  /** Ключ строки-места, куда кладём. У расформирования это всегда «Без ячеек». */
  toKey: string
  /** Куда кладём — подпись того же места для человека. */
  toLabel: string
}

const TITLE: Record<MoveIntent['reason'], string> = {
  move: 'Переместить',
  takeOff: 'Снять с ячейки',
  disband: 'Расформировать палету',
}

function qtyText(value: number) {
  return value.toLocaleString('ru-RU')
}

export function WarehouseMapMoveDialog({
  intent,
  onClose,
  onConfirm,
}: {
  intent: MoveIntent | null
  onClose: () => void
  onConfirm: (intent: MoveIntent, qty: number) => void
}) {
  if (!intent) {
    return null
  }
  // Тело монтируется под конкретное намерение: количество по умолчанию — «всё»,
  // и при следующем перетаскивании оно берётся заново само, без синхронизации.
  return (
    <MoveDialogBody
      key={`${intent.reason}:${intent.row.key}:${intent.toKey}`}
      intent={intent}
      onClose={onClose}
      onConfirm={onConfirm}
    />
  )
}

function MoveDialogBody({
  intent,
  onClose,
  onConfirm,
}: {
  intent: MoveIntent
  onClose: () => void
  onConfirm: (intent: MoveIntent, qty: number) => void
}) {
  const { reason, row, fromLabel, toLabel } = intent
  const [qty, setQty] = useState<number | null>(row.qty)
  const partial = reason !== 'disband' && row.kind === 'product'
  const tooMuch = partial && (qty === null || qty < 1 || qty > row.qty)

  return (
    <AppDialog
      open
      onClose={onClose}
      testId="warehouse-map-move-dialog"
      title={TITLE[reason]}
      actions={
        <ActionGroup>
          <SecondaryAction onClick={onClose} data-testid="warehouse-map-move-cancel">
            Отмена
          </SecondaryAction>
          {reason === 'disband' ? (
            <DangerAction
              onClick={() => onConfirm(intent, row.qty)}
              data-testid="warehouse-map-move-confirm"
            >
              Расформировать
            </DangerAction>
          ) : (
            <PrimaryAction
              onClick={() => onConfirm(intent, partial ? (qty ?? 0) : row.qty)}
              disabledReason={tooMuch ? `Можно от 1 до ${qtyText(row.qty)} штук` : undefined}
              data-testid="warehouse-map-move-confirm"
            >
              {reason === 'takeOff' ? 'Снять' : 'Переместить'}
            </PrimaryAction>
          )}
        </ActionGroup>
      }
    >
      <Stack spacing={2}>
        <Stack spacing={0.5}>
          <Typography variant="subtitle2" data-testid="warehouse-map-move-subject">
            {row.title}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Откуда: {fromLabel}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Куда: {toLabel}
          </Typography>
        </Stack>

        {reason === 'disband' ? (
          <Typography variant="body2">
            Короба и товар с палеты уедут в «Без ячеек» — они останутся на складе и никуда не
            пропадут. Сама палета перестанет существовать, собрать её заново нельзя.
          </Typography>
        ) : partial ? (
          <NumberInput
            label="Сколько штук"
            value={qty}
            onChange={setQty}
            min={1}
            max={row.qty}
            required
            helperText={`Всего ${qtyText(row.qty)} — можно перенести часть`}
            error={tooMuch ? `Можно от 1 до ${qtyText(row.qty)} штук` : undefined}
            testId="warehouse-map-move-qty"
          />
        ) : (
          <Typography variant="body2">
            Переедет целиком, вместе с содержимым — {qtyText(row.qty)} шт.
          </Typography>
        )}
      </Stack>
    </AppDialog>
  )
}
