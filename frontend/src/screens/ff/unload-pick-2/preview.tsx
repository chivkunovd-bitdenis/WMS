import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Box, CssBaseline, Stack, ThemeProvider, Typography } from '@mui/material'
import { muiTheme } from '../../../mui/theme'
import { UnloadPickRouteScreen } from './UnloadPickRouteScreen'
import '../../../index.css'

// Отдельная точка входа: /unload-pick-2.html
// Вариант А живёт рядом на /unload-pick.html и не трогается — владелец
// сравнивает два устройства экрана, а не две раскраски одного.
export function UnloadPickRouteHarness() {
  const [note, setNote] = useState<string | null>(null)
  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <Box sx={{ px: 3, py: 1.5, bgcolor: 'text.primary', color: 'common.white' }}>
        <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>
            ЭТО НЕ ЭКРАН
          </Typography>
          <Typography variant="body2" sx={{ opacity: 0.75 }}>
            Вариант Б, маршрут обхода: данные выдуманные, сервера нет, ничего не списывается.
          </Typography>
          {note ? (
            <Typography variant="body2" sx={{ opacity: 0.85 }} data-testid="route-note">
              {note}
            </Typography>
          ) : null}
        </Stack>
      </Box>
      <Box sx={{ display: 'flex' }}>
        <Box sx={{ width: 260, flexShrink: 0, bgcolor: 'background.paper' }} />
        <Box sx={{ flexGrow: 1, minWidth: 0, p: 3 }}>
          <UnloadPickRouteScreen onNote={setNote} />
        </Box>
      </Box>
    </Box>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <UnloadPickRouteHarness />
    </ThemeProvider>
  </StrictMode>,
)
