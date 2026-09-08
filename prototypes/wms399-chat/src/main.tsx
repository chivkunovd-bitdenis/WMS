import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { CssBaseline, ThemeProvider } from '@mui/material'
import { chatTheme } from './theme'
import { ChatProvider } from './state/store'
import { App } from './App'

const container = document.getElementById('root')!
createRoot(container).render(
  <StrictMode>
    <ThemeProvider theme={chatTheme}>
      <CssBaseline />
      <ChatProvider>
        <App />
      </ChatProvider>
    </ThemeProvider>
  </StrictMode>,
)
