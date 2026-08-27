import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Box, CssBaseline, Stack, ThemeProvider, Typography } from '@mui/material'
import { muiTheme } from '../../../../mui/theme'
import { MoveLab } from './MoveLab'
import '../../../../index.css'

// Отдельная точка входа: /move-lab.html при запущенном `npm run dev`.
// Это набросок «а что если», а не экран системы — лента сверху говорит об этом
// прямо, чтобы его случайно не приняли за утверждённое решение.
export function MoveLabHarness() {
  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <Box sx={{ px: 3, py: 1.5, bgcolor: 'text.primary', color: 'common.white' }}>
        <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>
            ЭТО НАБРОСОК
          </Typography>
          <Typography variant="body2" sx={{ opacity: 0.75 }}>
            Не экран системы и не согласованное решение — идея на посмотреть. Данные выдуманные,
            подсказки считаются прямо на странице.
          </Typography>
        </Stack>
      </Box>
      <Box sx={{ p: 3 }}>
        <MoveLab />
      </Box>
    </Box>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <MoveLabHarness />
    </ThemeProvider>
  </StrictMode>,
)
