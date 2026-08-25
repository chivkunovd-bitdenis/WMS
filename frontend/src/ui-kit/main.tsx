import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { CssBaseline, ThemeProvider } from '@mui/material'
import { muiTheme } from '../mui/theme'
import { UiKitShowcase } from './UiKitShowcase'
import '../index.css'

// Отдельная точка входа: витрина открывается без авторизации и без бэкенда,
// чтобы её мог посмотреть и человек, и агент, не поднимая стенд.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <UiKitShowcase />
    </ThemeProvider>
  </StrictMode>,
)
