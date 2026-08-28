import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Box, CssBaseline, Stack, ThemeProvider, Typography } from '@mui/material'
import { muiTheme } from '../../../mui/theme'
import { UnloadPickScreen } from './UnloadPickScreen'
import '../../../index.css'

// Отдельная точка входа: /unload-pick.html
export function UnloadPickHarness() {
  const [note, setNote] = useState<string | null>(null)
  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <Box sx={{ px: 3, py: 1.5, bgcolor: 'text.primary', color: 'common.white' }}>
        <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>
            ЭТО НЕ ЭКРАН
          </Typography>
          <Typography variant="body2" sx={{ opacity: 0.75 }}>
            Лента макета: данные выдуманные, сервера нет, ничего не списывается.
          </Typography>
          {note ? (
            <Typography variant="body2" sx={{ opacity: 0.85 }} data-testid="pick-note">
              {note}
            </Typography>
          ) : null}
        </Stack>
      </Box>
      <Box sx={{ display: 'flex' }}>
        <Box sx={{ width: 260, flexShrink: 0, bgcolor: 'background.paper' }} />
        <Box sx={{ flexGrow: 1, minWidth: 0, p: 3 }}>
          <UnloadPickScreen onNote={setNote} />
        </Box>
      </Box>
    </Box>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <UnloadPickHarness />
    </ThemeProvider>
  </StrictMode>,
)
