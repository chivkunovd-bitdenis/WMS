import { ErrorBoundary, RootRouteError } from './components/errors/ErrorBoundary'
import { installClientErrorHandlers } from './utils/clientErrorReport'
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
installClientErrorHandlers('fulfillment')
const router = createBrowserRouter([{
  path: '*',
  element: <ErrorBoundary component="App" root><App /></ErrorBoundary>,
  errorElement: <RootRouteError portal="fulfillment" />,
}])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={muiTheme}>
      <ErrorBoundary component="portal" root portal="fulfillment">
        <WmsDatePickersProvider>
          <RouterProvider router={router} />
        </WmsDatePickersProvider>
      </ErrorBoundary>
    </ThemeProvider>
  </StrictMode>,
)
