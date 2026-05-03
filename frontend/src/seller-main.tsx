import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import './index.css'
import './ui/ui.css'
import { muiTheme } from './mui/theme'
import { SellerApp } from './apps/seller/SellerApp'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={muiTheme}>
      <BrowserRouter basename="/seller">
        <SellerApp />
      </BrowserRouter>
    </ThemeProvider>
  </StrictMode>,
)

