import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Box, CssBaseline, Stack, ThemeProvider, Typography } from '@mui/material'
import { muiTheme } from '../../../mui/theme'
import { FbsSpeedScreen } from './FbsSpeedScreen'
import '../../../index.css'

// Превью экрана без сервера. Открывается по адресу /fbs-speed.html
// при запущенном `npm run dev`.

type RootHost = HTMLElement & { __previewRoot?: ReturnType<typeof createRoot> }

export function SpeedHarness() {
  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <Box sx={{ px: 3, py: 1.5, bgcolor: 'text.primary', color: 'common.white' }}>
        <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>
            МАКЕТ, ЦИФРЫ НАСТОЯЩИЕ
          </Typography>
          <Typography variant="body2" sx={{ opacity: 0.75 }}>
            ИП Чжоу, боевая база на 28.08.2026, последние семь дней. Экран ещё не
            подключён к серверу — данные снял запросом и вписал руками.
          </Typography>
        </Stack>
      </Box>
      <Box sx={{ p: 3 }}>
        <FbsSpeedScreen />
      </Box>
    </Box>
  )
}

const container = document.getElementById('root') as RootHost | null
if (container) {
  const root = container.__previewRoot ?? createRoot(container)
  container.__previewRoot = root
  root.render(
    <StrictMode>
      <ThemeProvider theme={muiTheme}>
        <CssBaseline />
        <SpeedHarness />
      </ThemeProvider>
    </StrictMode>,
  )
}
