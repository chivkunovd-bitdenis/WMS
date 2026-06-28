import { Autocomplete, TextField } from '@mui/material'
import { useMemo } from 'react'

export type MarkingSellerOption = { id: string; name: string }

type Props = {
  sellers: MarkingSellerOption[]
  selectedSellerId: string | null
  onSelectedSellerIdChange: (id: string | null) => void
  testIdPrefix: string
}

export function MarkingSellerPicker({
  sellers,
  selectedSellerId,
  onSelectedSellerIdChange,
  testIdPrefix,
}: Props) {
  const selectedSeller = useMemo(
    () => sellers.find((s) => s.id === selectedSellerId) ?? null,
    [sellers, selectedSellerId],
  )

  if (sellers.length === 0) {
    return null
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
      sx={{ maxWidth: 420 }}
    />
  )
}
