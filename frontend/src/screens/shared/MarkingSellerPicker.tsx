import { Autocomplete, Skeleton, TextField } from '@mui/material'
import { useMemo } from 'react'

export type MarkingSellerOption = { id: string; name: string }

type Props = {
  sellers: MarkingSellerOption[]
  selectedSellerId: string | null
  onSelectedSellerIdChange: (id: string | null) => void
  testIdPrefix: string
  loading?: boolean
}

export function MarkingSellerPicker({
  sellers,
  selectedSellerId,
  onSelectedSellerIdChange,
  testIdPrefix,
  loading = false,
}: Props) {
  const selectedSeller = useMemo(
    () => sellers.find((s) => s.id === selectedSellerId) ?? null,
    [sellers, selectedSellerId],
  )

  if (loading) {
    return (
      <Skeleton
        variant="rounded"
        height={40}
        sx={{ minWidth: 260, maxWidth: 420, flex: { sm: '0 0 280px' } }}
        data-testid={`${testIdPrefix}-seller-picker-loading`}
      />
    )
  }

  if (sellers.length === 0) {
    return (
      <TextField
        size="small"
        label="Селлер"
        value=""
        placeholder="Нет селлеров"
        disabled
        sx={{ minWidth: 260, maxWidth: 420, flex: { sm: '0 0 280px' } }}
        data-testid={`${testIdPrefix}-seller-picker`}
      />
    )
  }

  return (
    <Autocomplete
      size="small"
      options={sellers}
      value={selectedSeller}
      onChange={(_, value) => onSelectedSellerIdChange(value?.id ?? null)}
      getOptionLabel={(option) => option.name}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      noOptionsText="Селлер не найден"
      renderOption={(props, option) => (
        <li {...props} key={option.id} data-testid={`${testIdPrefix}-seller-${option.id}`}>
          {option.name}
        </li>
      )}
      renderInput={(params) => (
        <TextField
          {...params}
          label="Селлер"
          placeholder="Поиск по названию"
          data-testid={`${testIdPrefix}-seller-picker`}
        />
      )}
      sx={{ minWidth: 260, maxWidth: 420, flex: { sm: '0 0 280px' } }}
    />
  )
}
