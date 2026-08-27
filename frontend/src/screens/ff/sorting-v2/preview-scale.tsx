import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Box, CssBaseline, Stack, ThemeProvider, Typography } from '@mui/material'
import { muiTheme } from '../../../mui/theme'
import { SortingScaleScreen } from './SortingScaleScreen'
import '../../../index.css'

// Отдельная точка входа: /sorting-scale.html — тот же экран на настоящем объёме.
export function SortingScaleHarness() {
  const [note, setNote] = useState<string | null>(null)
  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <Box sx={{ px: 3, py: 1.5, bgcolor: 'text.primary', color: 'common.white' }}>
        <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>
            ЭТО НЕ ЭКРАН
          </Typography>
          <Typography variant="body2" sx={{ opacity: 0.75 }}>
            Тот же макет, но на объёме: три склада, сотни ячеек, 214 строк товара.
          </Typography>
          {note ? (
            <Typography variant="body2" sx={{ opacity: 0.85 }} data-testid="sorting-note">
              {note}
            </Typography>
          ) : null}
        </Stack>
      </Box>
      <Box sx={{ display: 'flex' }}>
        <Box sx={{ width: 260, flexShrink: 0, bgcolor: 'background.paper' }} />
        <Box sx={{ flexGrow: 1, minWidth: 0, p: 3 }}>
          <SortingScaleScreen onNote={setNote} />
        </Box>
      </Box>
    </Box>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <SortingScaleHarness />
    </ThemeProvider>
  </StrictMode>,
)
