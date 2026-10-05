import { Box, Stack, Typography } from '@mui/material'
import { useMemo, useState } from 'react'
import {
  ActionGroup,
  AppDialog,
  NumberInput,
  PreferenceSwitch,
  PrimaryAction,
  SecondaryAction,
  SelectInput,
  TextInput,
} from '../../../ui-kit'

type Props = {
  open: boolean
  warehouseName: string
  onClose: () => void
}

function previewPosition(useSides: boolean, useTiers: boolean, side: string, tier: number | null) {
  const sideOffset = useSides && side === '2' ? 20 : useSides ? 10 : 0
  const tierOffset = useTiers ? (tier ?? 1) : 0
  return 1 + sideOffset + tierOffset
}

function previewCode(
  rack: string,
  useSides: boolean,
  side: string,
  useTiers: boolean,
  tier: number | null,
  position: number | null,
) {
  const normalizedRack = rack.trim().toLocaleUpperCase('ru-RU')
  if (!normalizedRack || position === null || (useTiers && tier === null)) return ''

  const addressParts = [
    useSides ? side : null,
    useTiers && tier !== null ? String(tier) : null,
    String(position),
  ].filter((part): part is string => part !== null)
  return `${normalizedRack} ${addressParts.join('.')}`
}

/**
 * Автономная форма WMS-654 живёт только в макете. Она намеренно не получает
 * callback создания ячейки и поэтому не может обратиться к рабочему API или
 * изменить демонстрационные строки карты.
 */
export function Wms654CreateCellPreviewDialog({ open, warehouseName, onClose }: Props) {
  if (!open) return null
  return <Wms654CreateCellPreviewDialogBody warehouseName={warehouseName} onClose={onClose} />
}

function Wms654CreateCellPreviewDialogBody({
  warehouseName,
  onClose,
}: Omit<Props, 'open'>) {
  const [rack, setRack] = useState('')
  const [useSides, setUseSides] = useState(true)
  const [useTiers, setUseTiers] = useState(true)
  const [side, setSide] = useState('1')
  const [tier, setTier] = useState<number | null>(1)
  const [manualPosition, setManualPosition] = useState<number | null>(null)

  const suggestedPosition = useMemo(
    () => previewPosition(useSides, useTiers, side, tier),
    [side, tier, useSides, useTiers],
  )
  const position = manualPosition ?? suggestedPosition
  const code = previewCode(rack, useSides, side, useTiers, tier, position)
  const context = [
    `ряд ${rack.trim().toLocaleUpperCase('ru-RU') || 'не выбран'}`,
    useSides ? `сторона ${side}` : 'без стороны',
    useTiers ? `ярус ${tier ?? 'не выбран'}` : 'без яруса',
  ].join(', ')
  const disabledReason = !rack.trim()
    ? 'Укажите стеллаж'
    : useTiers && tier === null
      ? 'Укажите ярус'
      : undefined

  return (
    <AppDialog
      open
      onClose={onClose}
      title="Создать ячейку"
      testId="warehouse-map-cell-dialog"
      actions={
        <ActionGroup>
          <SecondaryAction onClick={onClose} data-testid="warehouse-map-cell-cancel">
            Отмена
          </SecondaryAction>
          <PrimaryAction
            onClick={onClose}
            disabledReason={disabledReason}
            data-testid="warehouse-map-cell-submit"
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

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <PreferenceSwitch
            label="Учитывать стороны"
            checked={useSides}
            onChange={setUseSides}
            testId="wms-654-use-sides"
          />
          <PreferenceSwitch
            label="Учитывать ярусы"
            checked={useTiers}
            onChange={setUseTiers}
            testId="wms-654-use-tiers"
          />
        </Stack>

        <TextInput
          label="Стеллаж"
          value={rack}
          onChange={setRack}
          required
          helperText="Как написано на стеллаже: А, Б, В1"
          testId="warehouse-map-cell-rack"
        />

        {useSides ? (
          <SelectInput
            label="Сторона"
            value={side}
            onChange={setSide}
            options={[
              { value: '1', label: 'Сторона 1' },
              { value: '2', label: 'Сторона 2' },
            ]}
            testId="warehouse-map-cell-side"
          />
        ) : null}

        {useTiers ? (
          <NumberInput
            label="Ярус"
            value={tier}
            onChange={setTier}
            min={1}
            testId="warehouse-map-cell-tier"
          />
        ) : null}

        <Box
          sx={{
            minWidth: 0,
            '& .MuiFormHelperText-root': { overflowWrap: 'anywhere' },
          }}
        >
          <NumberInput
            label="Позиция"
            value={position}
            onChange={setManualPosition}
            min={1}
            helperText={`Следующая свободная позиция для контекста: ${context}`}
            testId="warehouse-map-cell-position"
          />
        </Box>

        <Typography
          variant="subtitle2"
          sx={{ overflowWrap: 'anywhere' }}
          data-testid="warehouse-map-cell-preview"
        >
          Код ячейки: {code || 'появится после стеллажа'}
        </Typography>
      </Stack>
    </AppDialog>
  )
}
