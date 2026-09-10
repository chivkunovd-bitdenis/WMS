import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import './index.css'
import './ui/ui.css'
import App from './App.tsx'
import { muiTheme } from './mui/theme'
import { WmsDatePickersProvider } from './mui/WmsDatePickersProvider'

// Keep the existing route tree and shell; data router supports unsaved-input blocking.
const router = createBrowserRouter([{ path: '*', element: <App /> }])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={muiTheme}>
      <WmsDatePickersProvider>
        <RouterProvider router={router} />
      </WmsDatePickersProvider>
    </ThemeProvider>
  </StrictMode>,
)
