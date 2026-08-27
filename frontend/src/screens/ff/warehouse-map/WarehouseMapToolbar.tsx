import { Box, Stack, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material'
import AddOutlined from '@mui/icons-material/AddOutlined'
import { useMemo, useState } from 'react'
import {
  ActionGroup,
  AppDialog,
  FilterBar,
  IconAction,
  PrimaryAction,
  SecondaryAction,
  SelectInput,
  TextInput,
  NumberInput,
} from '../../../ui-kit'
import {
  formatLocationCode,
  normalizeRackName,
  suggestNextLocationForRack,
} from '../../../utils/formatLocationCode'
import type { WarehouseOption } from './WarehouseMapTypes'

// Склады занимали полэкрана под список, который меняется раз в квартал. Здесь они
// стали переключателем в строке фильтров: высота растёт от числа складов, а место
// на экране отдано тому, ради чего экран существует — ячейкам и их содержимому.

export function WarehouseMapToolbar({
  warehouses,
  warehouseId,
  onWarehouseChange,
  query,
  onQueryChange,
  allExpanded,
  onToggleAll,
  onCreateCell,
  onCreateWarehouse,
  createCellDisabledReason,
  toggleAllDisabledReason,
}: {
  warehouses: WarehouseOption[]
  warehouseId: string | null
  onWarehouseChange: (id: string) => void
  query: string
  onQueryChange: (value: string) => void
  allExpanded: boolean
  onToggleAll: () => void
  onCreateCell: () => void
  onCreateWarehouse: () => void
  createCellDisabledReason?: string
  toggleAllDisabledReason?: string
}) {
  return (
    <FilterBar
      search={query}
      onSearchChange={onQueryChange}
      searchPlaceholder="Товар, ШК или ячейка"
      testId="warehouse-map-filters"
    >
      <ToggleButtonGroup
        exclusive
        size="small"
        value={warehouseId}
        onChange={(_event, value: string | null) => {
          if (value) onWarehouseChange(value)
        }}
        aria-label="Склад"
        data-testid="warehouse-map-warehouses"
        sx={{ flexWrap: 'wrap' }}
      >
        {warehouses.map((warehouse) => (
          <ToggleButton
            key={warehouse.id}
            value={warehouse.id}
            data-testid={`warehouse-map-warehouse-${warehouse.id}`}
            sx={{ textTransform: 'none', fontWeight: 600, px: 1.75 }}
          >
            {warehouse.name}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>
      <IconAction
        title="Создать склад"
        onClick={onCreateWarehouse}
        testId="warehouse-map-create-warehouse"
      >
        <AddOutlined fontSize="small" />
      </IconAction>
      <Box sx={{ flexGrow: 1 }} />
      <ActionGroup>
        <SecondaryAction
          onClick={onToggleAll}
          disabledReason={toggleAllDisabledReason}
          data-testid="warehouse-map-toggle-all"
        >
          {allExpanded ? 'Свернуть всё' : 'Развернуть всё'}
        </SecondaryAction>
        <PrimaryAction
          onClick={onCreateCell}
          disabledReason={createCellDisabledReason}
          data-testid="warehouse-map-create-cell"
        >
          Создать ячейку
        </PrimaryAction>
      </ActionGroup>
    </FilterBar>
  )
}

export function CreateCellDialog({
  open,
  warehouseName,
  existingCodes,
  onClose,
  onCreate,
}: {
  open: boolean
  warehouseName: string
  existingCodes: string[]
  onClose: () => void
  onCreate: (code: string) => void
}) {
  if (!open) {
    return null
  }
  // Черновик формы живёт ровно столько, сколько открыт диалог: закрыли — забыли.
  return (
    <CreateCellDialogBody
      warehouseName={warehouseName}
      existingCodes={existingCodes}
      onClose={onClose}
      onCreate={onCreate}
    />
  )
}

function CreateCellDialogBody({
  warehouseName,
  existingCodes,
  onClose,
  onCreate,
}: {
  warehouseName: string
  existingCodes: string[]
  onClose: () => void
  onCreate: (code: string) => void
}) {
  const [rack, setRack] = useState('')
  const [side, setSide] = useState('1')
  // Позицию подставляем сами — первую свободную. Ручной ввод помним только для
  // того стеллажа и стороны, для которых его набрали: сменил стеллаж — снова
  // подсказка, а не число от прошлого ряда.
  const [manual, setManual] = useState<{ signature: string; value: number | null } | null>(null)

  const sideNumber = side === '2' ? 2 : 1
  const signature = `${normalizeRackName(rack)}|${side}`
  const suggestion = useMemo(
    () => (rack.trim() ? suggestNextLocationForRack(rack, sideNumber, existingCodes) : null),
    [existingCodes, rack, sideNumber],
  )
  const position =
    manual && manual.signature === signature ? manual.value : (suggestion?.position ?? null)
  const code = rack.trim() && position !== null ? formatLocationCode(rack, sideNumber, position) : ''

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
            onClick={() => onCreate(code)}
            disabledReason={code ? undefined : 'Укажите стеллаж'}
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
        <TextInput
          label="Стеллаж"
          value={rack}
          onChange={setRack}
          required
          helperText="Как написано на стеллаже: А, Б, В1"
          testId="warehouse-map-cell-rack"
        />
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
        <NumberInput
          label="Позиция"
          value={position}
          onChange={(value) => setManual({ signature, value })}
          min={1}
          helperText="Свободная позиция подставлена автоматически"
          testId="warehouse-map-cell-position"
        />
        <Typography variant="subtitle2" data-testid="warehouse-map-cell-preview">
          Код ячейки: {code || 'появится после стеллажа'}
        </Typography>
      </Stack>
    </AppDialog>
  )
}

export function CreateWarehouseDialog({
  open,
  onClose,
  onCreate,
}: {
  open: boolean
  onClose: () => void
  onCreate: (name: string, code: string) => void
}) {
  if (!open) {
    return null
  }
  return <CreateWarehouseDialogBody onClose={onClose} onCreate={onCreate} />
}

function CreateWarehouseDialogBody({
  onClose,
  onCreate,
}: {
  onClose: () => void
  onCreate: (name: string, code: string) => void
}) {
  const [name, setName] = useState('')
  const [code, setCode] = useState('')

  const codeInvalid = code.trim().length > 0 && !/^[A-Za-z0-9_-]+$/.test(code.trim())

  return (
    <AppDialog
      open
      onClose={onClose}
      title="Создать склад"
      testId="warehouse-map-warehouse-dialog"
      actions={
        <ActionGroup>
          <SecondaryAction onClick={onClose} data-testid="warehouse-map-warehouse-cancel">
            Отмена
          </SecondaryAction>
          <PrimaryAction
            onClick={() => onCreate(name.trim(), code.trim())}
            disabledReason={
              !name.trim() || !code.trim()
                ? 'Заполните название и код'
                : codeInvalid
                  ? 'Код: латиница, цифры, _ и -'
                  : undefined
            }
            data-testid="warehouse-map-warehouse-submit"
          >
            Создать
          </PrimaryAction>
        </ActionGroup>
      }
    >
      <Stack spacing={2}>
        <TextInput
          label="Название"
          value={name}
          onChange={setName}
          required
          testId="warehouse-map-warehouse-name"
        />
        <TextInput
          label="Код"
          value={code}
          onChange={setCode}
          required
          error={codeInvalid ? 'Латиница, цифры, знаки _ и -' : undefined}
          helperText="Короткий код склада — он попадает в коды ячеек и на этикетки"
          testId="warehouse-map-warehouse-code"
        />
      </Stack>
    </AppDialog>
  )
}
