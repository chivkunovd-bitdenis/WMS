import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import './index.css'
import './ui/ui.css'
import App from './App.tsx'
import { muiTheme } from './mui/theme'
import { WmsDatePickersProvider } from './mui/WmsDatePickersProvider'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={muiTheme}>
      <WmsDatePickersProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </WmsDatePickersProvider>
    </ThemeProvider>
  </StrictMode>,
)
