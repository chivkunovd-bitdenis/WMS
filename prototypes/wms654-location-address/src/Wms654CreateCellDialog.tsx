import { Stack, Typography } from '@mui/material'
import { useMemo, useState } from 'react'
import {
  ActionGroup,
  AppDialog,
  CheckboxInput,
  NumberInput,
  PrimaryAction,
  SecondaryAction,
  SelectInput,
  TextInput,
} from '../../../frontend/src/ui-kit'

type DraftNumber = { signature: string; value: number | null }

function normalized(value: string) {
  return value.trim().replace(/\s+/g, ' ').toLocaleUpperCase('ru-RU')
}

function composeLocationName({
  rack,
  useSides,
  side,
  useTiers,
  tier,
  position,
}: {
  rack: string
  useSides: boolean
  side: string
  useTiers: boolean
  tier: number | null
  position: number | null
}) {
  const addressParts = [
    useSides ? side : null,
    useTiers ? tier : null,
    position,
  ].filter((part): part is string | number => part !== null)
  const row = normalized(rack)
  return row && position !== null ? `${row} ${addressParts.join('.')}` : ''
}

function suggestedPosition(signature: string) {
  let hash = 0
  for (const symbol of signature) hash = (hash * 31 + symbol.charCodeAt(0)) % 4
  return hash + 1
}

export function Wms654CreateCellDialog({
  open,
  warehouseName,
  onClose,
}: {
  open: boolean
  warehouseName: string
  onClose: () => void
}) {
  if (!open) return null
  return <DialogBody warehouseName={warehouseName} onClose={onClose} />
}

function DialogBody({ warehouseName, onClose }: { warehouseName: string; onClose: () => void }) {
  const [rack, setRack] = useState('А')
  const [useSides, setUseSides] = useState(true)
  const [side, setSide] = useState('1')
  const [useTiers, setUseTiers] = useState(false)
  const [tier, setTier] = useState<number | null>(1)
  const [manual, setManual] = useState<DraftNumber | null>(null)

  const signature = `${normalized(rack)}|${useSides ? side : '-'}|${useTiers ? tier ?? '-' : '-'}`
  const suggested = useMemo(
    () => (normalized(rack) && (!useTiers || tier !== null) ? suggestedPosition(signature) : null),
    [rack, signature, tier, useTiers],
  )
  const position = manual?.signature === signature ? manual.value : suggested
  const name = composeLocationName({ rack, useSides, side, useTiers, tier, position })
  const context = [
    `ряд ${normalized(rack) || '—'}`,
    useSides ? `сторона ${side}` : 'без сторон',
    useTiers ? `ярус ${tier ?? '—'}` : 'без ярусов',
  ].join(' · ')

  return (
    <AppDialog
      open
      onClose={onClose}
      title="Создать ячейку"
      testId="wms654-cell-dialog"
      actions={
        <ActionGroup>
          <SecondaryAction onClick={onClose} data-testid="wms654-cell-cancel">
            Отмена
          </SecondaryAction>
          <PrimaryAction
            onClick={() => undefined}
            disabledReason={name ? undefined : 'Заполните адрес ячейки'}
            data-testid="wms654-cell-submit"
          >
            Создать
          </PrimaryAction>
        </ActionGroup>
      }
    >
      <Stack spacing={2}>
        <Typography variant="body2" color="text.secondary">
          Склад: {warehouseName}
        </Typography>
        <TextInput
          label="Стеллаж"
          value={rack}
          onChange={setRack}
          required
          helperText="Как написано на стеллаже: А, Б, В1"
          testId="wms654-cell-rack"
        />

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={{ xs: 0, sm: 3 }}>
          <CheckboxInput
            label="Учитывать стороны"
            checked={useSides}
            onChange={setUseSides}
            testId="wms654-use-sides"
          />
          <CheckboxInput
            label="Учитывать ярусы"
            checked={useTiers}
            onChange={setUseTiers}
            testId="wms654-use-tiers"
          />
        </Stack>

        {useSides ? (
          <SelectInput
            label="Сторона"
            value={side}
            onChange={setSide}
            options={[
              { value: '1', label: 'Сторона 1' },
              { value: '2', label: 'Сторона 2' },
            ]}
            testId="wms654-cell-side"
          />
        ) : null}

        {useTiers ? (
          <NumberInput
            label="Ярус"
            value={tier}
            onChange={setTier}
            min={1}
            testId="wms654-cell-tier"
          />
        ) : null}

        <NumberInput
          label="Позиция"
          value={position}
          onChange={(value) => setManual({ signature, value })}
          min={1}
          helperText={`Следующая свободная для: ${context}`}
          testId="wms654-cell-position"
        />
        <Typography variant="subtitle2" data-testid="wms654-cell-preview">
          Код ячейки: {name || 'появится после заполнения адреса'}
        </Typography>
      </Stack>
    </AppDialog>
  )
}
