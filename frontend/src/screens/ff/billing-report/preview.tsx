import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Box, Container, CssBaseline, Stack, ThemeProvider, Typography } from '@mui/material'
import { muiTheme } from '../../../mui/theme'
import { ScreenHeader } from '../../../ui-kit'
import { BillingReportScreen } from './BillingReportScreen'
import { STUB_REPORT } from './stub'
import '../../../index.css'

// Отдельная точка входа: /raschety.html
function Harness() {
  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <Box sx={{ px: 3, py: 1.5, bgcolor: 'text.primary', color: 'common.white' }}>
        <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>
            ЭТО НЕ ЭКРАН
          </Typography>
          <Typography variant="body2" sx={{ opacity: 0.75 }}>
            Макет отчёта по начислениям: данные выдуманные, сервера нет.
          </Typography>
        </Stack>
      </Box>
      <Container maxWidth="lg" sx={{ py: 3 }}>
        <Stack spacing={2}>
          <ScreenHeader
            title="Расчёты"
            purpose="Начисления за период: селлер → услуга → документ."
          />
          <BillingReportScreen data={STUB_REPORT} />
        </Stack>
      </Container>
    </Box>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <Harness />
    </ThemeProvider>
  </StrictMode>,
)
