import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Box, CssBaseline, Stack, ThemeProvider, Typography } from '@mui/material'
import { muiTheme } from '../../../mui/theme'
import { ProductsScreen } from './ProductsScreen'
import { FbsMetricScreen } from './FbsMetricScreen'
import { SellerSettingsScreen } from './SellerSettingsScreen'
import { ToggleButton, ToggleButtonGroup } from '@mui/material'
import '../../../index.css'

export function ProductsHarness() {
  const [note, setNote] = useState<string | null>(null)
  const [screen, setScreen] = useState<'products' | 'fbs' | 'seller'>('products')
  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <Box sx={{ px: 3, py: 1.5, bgcolor: 'text.primary', color: 'common.white' }}>
        <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>
            ЭТО НЕ ЭКРАН
          </Typography>
          <Typography variant="body2" sx={{ opacity: 0.75 }}>
            Товары и склады выдуманы. А цифры времени сборки на вкладке FBS —
            настоящие: сняты с боевой базы 28.08.2026, ИП Чжоу и все продавцы.
          </Typography>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={screen}
            onChange={(_event, value: 'products' | 'fbs' | 'seller' | null) => {
              if (value) setScreen(value)
            }}
            data-testid="harness-screen"
          >
            <ToggleButton
              value="products"
              sx={{ textTransform: 'none', color: 'common.white', borderColor: 'rgba(255,255,255,0.35)', '&.Mui-selected': { color: 'common.white', bgcolor: 'rgba(255,255,255,0.22)' } }}
            >
              Товары
            </ToggleButton>
            <ToggleButton
              value="seller"
              sx={{ textTransform: 'none', color: 'common.white', borderColor: 'rgba(255,255,255,0.35)', '&.Mui-selected': { color: 'common.white', bgcolor: 'rgba(255,255,255,0.22)' } }}
            >
              Настройки продавца
            </ToggleButton>
            <ToggleButton
              value="fbs"
              sx={{ textTransform: 'none', color: 'common.white', borderColor: 'rgba(255,255,255,0.35)', '&.Mui-selected': { color: 'common.white', bgcolor: 'rgba(255,255,255,0.22)' } }}
            >
              FBS · первая вкладка
            </ToggleButton>
          </ToggleButtonGroup>
          {note ? (
            <Typography variant="body2" sx={{ opacity: 0.85 }} data-testid="products-note">
              {note}
            </Typography>
          ) : null}
        </Stack>
      </Box>
      <Box sx={{ display: 'flex' }}>
        <Box sx={{ width: 260, flexShrink: 0, bgcolor: 'background.paper' }} />
        <Box sx={{ flexGrow: 1, minWidth: 0, p: 3 }}>
          {screen === 'products' ? (
            <ProductsScreen onNote={setNote} />
          ) : screen === 'seller' ? (
            <SellerSettingsScreen onNote={setNote} />
          ) : (
            <FbsMetricScreen />
          )}
        </Box>
      </Box>
    </Box>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <ProductsHarness />
    </ThemeProvider>
  </StrictMode>,
)
