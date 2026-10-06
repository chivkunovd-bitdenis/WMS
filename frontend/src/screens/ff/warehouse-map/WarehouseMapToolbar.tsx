import { Box, Stack, Typography } from '@mui/material'
import AddOutlined from '@mui/icons-material/AddOutlined'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ActionGroup,
  AppDialog,
  FilterBar,
  IconAction,
  PrimaryAction,
  ScannerField,
  SecondaryAction,
  SelectInput,
  TextInput,
  NumberInput,
  PreferenceSwitch,
} from '../../../ui-kit'
import { searchTokens, type MapFilters } from './WarehouseMapRows'
import {
  formatLocationCode,
  normalizeRackName,
  suggestNextLocationForRack,
} from '../../../utils/formatLocationCode'
import { WarehouseMapWarehouseSwitch } from './WarehouseMapWarehouseSwitch'
import type { WarehouseOption } from './WarehouseMapTypes'

export type CreateCellBody = {
  code: string
  rack_name: string
  side: 1 | 2 | null
  tier: number | null
  position: number
  use_sides: boolean
  use_tiers: boolean
}

export type CreateCellSuggestion = {
  position: number
  code: string
}

export type CreateCellSuggestionRequest = Pick<
  CreateCellBody,
  'rack_name' | 'side' | 'tier' | 'use_sides' | 'use_tiers'
>

// Склады занимали полэкрана под список, который меняется раз в квартал. Здесь они
// стали переключателем в строке фильтров: высота растёт от числа складов, а место
// на экране отдано тому, ради чего экран существует — ячейкам и их содержимому.

export function WarehouseMapToolbar({
  warehouses,
  warehouseId,
  onWarehouseChange,
  sellers,
  categories,
  filters,
  onFiltersChange,
  missing,
  scanValue,
  onScanValueChange,
  onScan,
  scanError,
  scanNotice,
  allExpanded,
  onToggleAll,
  onCreateCell,
  onCreateWarehouse,
  onPrinter,
  createCellDisabledReason,
  toggleAllDisabledReason,
}: {
  warehouses: WarehouseOption[]
  warehouseId: string | null
  onWarehouseChange: (id: string) => void
  sellers: string[]
  categories: string[]
  filters: MapFilters
  onFiltersChange: (filters: MapFilters) => void
  /** Значения из вставленной пачки, которых на складе нет. */
  missing: string[]
  scanValue: string
  onScanValueChange: (value: string) => void
  onScan: (code: string) => void
  scanError: string | null
  scanNotice: string | null
  allExpanded: boolean
  onToggleAll: () => void
  onCreateCell: () => void
  onCreateWarehouse: () => void
  onPrinter: () => void
  createCellDisabledReason?: string
  toggleAllDisabledReason?: string
}) {
  const tokens = searchTokens(filters.query)
  const searchHelperText =
    tokens.length > 1
      ? missing.length > 0
        ? `Ищем ${tokens.length} значений. Не нашлось: ${missing.join(', ')}`
        : `Ищем ${tokens.length} значений — нашлись все`
      : 'Можно вставить сразу список: штрихкоды или названия через пробел или столбцом'

  return (
    <FilterBar
      search={filters.query}
      onSearchChange={(query) => onFiltersChange({ ...filters, query })}
      searchPlaceholder="Товар, артикул, ШК, короб или ячейка"
      searchHelperText={searchHelperText}
      testId="warehouse-map-filters"
      scanner={
        <ScannerField
          value={scanValue}
          onChange={onScanValueChange}
          onScan={onScan}
          expects="ШК короба, палеты, грузоместа или ячейки"
          error={scanError}
          notice={scanNotice}
          testId="warehouse-map-scan"
        />
      }
      actions={
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
          <SecondaryAction onClick={onPrinter} data-testid="warehouse-map-printer">
            Принтер
          </SecondaryAction>
        </ActionGroup>
      }
    >
      <Box sx={{ minWidth: 210 }}>
        <SelectInput
          label="Селлер"
          value={filters.seller}
          onChange={(seller) => onFiltersChange({ ...filters, seller })}
          options={sellers.map((seller) => ({ value: seller, label: seller }))}
          emptyLabel="Все селлеры"
          testId="warehouse-map-filter-seller"
        />
      </Box>
      <Box sx={{ minWidth: 210 }}>
        <SelectInput
          label="Категория"
          value={filters.category}
          onChange={(category) => onFiltersChange({ ...filters, category })}
          options={categories.map((category) => ({ value: category, label: category }))}
          emptyLabel="Все категории"
          testId="warehouse-map-filter-category"
        />
      </Box>
      <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
        <WarehouseMapWarehouseSwitch
          warehouses={warehouses}
          warehouseId={warehouseId}
          onWarehouseChange={onWarehouseChange}
        />
        <IconAction
          title="Создать склад"
          onClick={onCreateWarehouse}
          testId="warehouse-map-create-warehouse"
        >
          <AddOutlined fontSize="small" />
        </IconAction>
      </Stack>
    </FilterBar>
  )
}

type CreateCellDialogBase = {
  open: boolean
  warehouseName: string
  existingCodes: string[]
  onClose: () => void
}
type CreateCellDialogProps = CreateCellDialogBase & (
  | {
      legacyCreateCell?: false
      onCreate: (body: CreateCellBody) => Promise<boolean> | boolean
      onSuggest?: (request: CreateCellSuggestionRequest) => Promise<CreateCellSuggestion | null>
    }
  | { legacyCreateCell: true; onCreate: (code: string) => void }
)

export function CreateCellDialog(props: CreateCellDialogProps) {
  if (!props.open) {
    return null
  }
  // Черновик формы живёт ровно столько, сколько открыт диалог: закрыли — забыли.
  return <CreateCellDialogBody {...props} />
}

function CreateCellDialogBody(props: CreateCellDialogProps) {
  const { warehouseName, existingCodes, onClose } = props
  const legacyCreateCell = props.legacyCreateCell === true
  const onSuggest = 'onSuggest' in props ? props.onSuggest : undefined
  const [rack, setRack] = useState('')
  const [useSides, setUseSides] = useState(true)
  const [useTiers, setUseTiers] = useState(true)
  const [side, setSide] = useState('1')
  const [tier, setTier] = useState<number | null>(1)
  // Ручной номер относится только к его контексту: смена ряда, стороны или
  // яруса снова показывает подсказку, а не старое число.
  const [manual, setManual] = useState<{ signature: string; value: number | null } | null>(null)

  const sideNumber = side === '2' ? 2 : 1
  const effectiveSide = useSides ? sideNumber : null
  const effectiveTier = useTiers ? tier : null
  const signature = `${normalizeRackName(rack)}|${effectiveSide ?? ''}|${effectiveTier ?? ''}`
  const localSuggestion = useMemo(
    () => (rack.trim() ? suggestNextLocationForRack(rack, effectiveSide, effectiveTier, existingCodes) : null),
    [effectiveSide, effectiveTier, existingCodes, rack],
  )
  const [suggestion, setSuggestion] = useState<CreateCellSuggestion | null>(null)
  const suggestionRequestVersion = useRef(0)

  useEffect(() => {
    const requestVersion = suggestionRequestVersion.current + 1
    suggestionRequestVersion.current = requestVersion
    if (!rack.trim()) {
      setSuggestion(null)
      return
    }
    if (legacyCreateCell || !onSuggest) {
      setSuggestion(localSuggestion)
      return
    }

    setSuggestion(null)
    void onSuggest({
      rack_name: rack.trim(),
      side: effectiveSide,
      tier: effectiveTier,
      use_sides: useSides,
      use_tiers: useTiers,
    }).then((next) => {
      if (requestVersion === suggestionRequestVersion.current && next) {
        setSuggestion(next)
      }
    })
  }, [
    effectiveSide,
    effectiveTier,
    legacyCreateCell,
    localSuggestion,
    onSuggest,
    rack,
    useSides,
    useTiers,
  ])
  const position =
    manual && manual.signature === signature ? manual.value : (suggestion?.position ?? null)
  const code = rack.trim() && position !== null
    ? formatLocationCode(rack, effectiveSide, effectiveTier, position)
    : ''
  const body: CreateCellBody | null = code && position !== null
    ? {
        rack_name: rack.trim(), side: effectiveSide, tier: effectiveTier, position,
        use_sides: useSides, use_tiers: useTiers, code,
      }
    : null

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
            onClick={() => {
              if (!body) return
              if (!legacyCreateCell) void props.onCreate(body)
              else props.onCreate(body.code)
            }}
            disabledReason={body ? undefined : 'Укажите стеллаж'}
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
        {!legacyCreateCell ? <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <PreferenceSwitch label="Учитывать стороны" checked={useSides} onChange={setUseSides} testId="wms-654-use-sides" />
          <PreferenceSwitch label="Учитывать ярусы" checked={useTiers} onChange={setUseTiers} testId="wms-654-use-tiers" />
        </Stack> : null}
        <TextInput
          label="Стеллаж"
          value={rack}
          onChange={setRack}
          required
          helperText="Как написано на стеллаже: А, Б, В1"
          testId="warehouse-map-cell-rack"
        />
        {useSides ? <SelectInput
          label="Сторона"
          value={side}
          onChange={setSide}
          options={[
            { value: '1', label: 'Сторона 1' },
            { value: '2', label: 'Сторона 2' },
          ]}
          testId="warehouse-map-cell-side"
        /> : null}
        {useTiers ? <NumberInput
          label="Ярус"
          value={tier}
          onChange={setTier}
          min={1}
          testId="warehouse-map-cell-tier"
        /> : null}
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
