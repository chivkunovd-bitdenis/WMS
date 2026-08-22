import { useMemo, useState } from 'react'
import { Box, MenuItem, Paper, Select, Stack, Tabs, Tab, Typography } from '@mui/material'
import { FilterBar, PeriodPicker, ScreenHeader } from '../../ui-kit'

type Seller = { id: string; name: string }

type Props = {
  sellers?: Seller[]
}

function currentMonth(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

export function FfBillingScreen({ sellers = [] }: Props) {
  const [tab, setTab] = useState(0)
  const [month, setMonth] = useState(currentMonth)
  const [sellerId, setSellerId] = useState('all')
  const selectedSeller = useMemo(() => sellers.find((seller) => seller.id === sellerId), [sellerId, sellers])

  return (
    <Box data-testid="ff-billing-screen">
      <ScreenHeader
        title="Расчёты"
        purpose="Начисления за работу склада и автоматически выставленные счета селлерам."
      />
      <Tabs value={tab} onChange={(_, value: number) => setTab(value)} aria-label="Расчёты">
        <Tab label="Начисления" data-testid="billing-tab-charges" />
        <Tab label="Счета" data-testid="billing-tab-invoices" />
      </Tabs>
      <FilterBar
        search=""
        onSearchChange={() => undefined}
        searchPlaceholder={tab === 0 ? 'Номер документа' : 'Номер счёта'}
        testId="billing-filter-bar"
      >
        <PeriodPicker value={month} onChange={setMonth} testId="billing-period" />
        <Select
          size="small"
          value={sellerId}
          onChange={(event) => setSellerId(event.target.value)}
          inputProps={{ 'data-testid': 'billing-seller' }}
          sx={{ minWidth: 190 }}
          aria-label="Селлер"
        >
          <MenuItem value="all">Все селлеры</MenuItem>
          {sellers.map((seller) => (
            <MenuItem key={seller.id} value={seller.id}>
              {seller.name}
            </MenuItem>
          ))}
        </Select>
      </FilterBar>
      <Paper variant="outlined" sx={{ p: 3 }} data-testid="billing-tab-content">
        <Stack spacing={1}>
          <Typography variant="subtitle1">{tab === 0 ? 'Начисления' : 'Счета'}</Typography>
          <Typography variant="body2" color="text.secondary">
            {tab === 0
              ? 'Начисления за выбранный месяц появятся после загрузки операций.'
              : 'Счета за выбранный месяц появятся после формирования.'}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Период: {month} · Селлер: {selectedSeller?.name ?? 'Все селлеры'}
          </Typography>
        </Stack>
      </Paper>
    </Box>
  )
}
