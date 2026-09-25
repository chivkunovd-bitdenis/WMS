import { ErrorBoundary, RootRouteError } from './components/errors/ErrorBoundary'
import { installClientErrorHandlers } from './utils/clientErrorReport'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import './index.css'
import './ui/ui.css'
import { muiTheme } from './mui/theme'
import { WmsDatePickersProvider } from './mui/WmsDatePickersProvider'
import { SellerApp } from './apps/seller/SellerApp'

const sellerRouterBasename =
  import.meta.env.VITE_SELLER_ROUTER_BASENAME?.trim() || '/seller'

installClientErrorHandlers('seller')
const router = createBrowserRouter([{
  path: '*',
  element: <ErrorBoundary component="SellerApp" root portal="seller"><SellerApp /></ErrorBoundary>,
  errorElement: <RootRouteError portal="seller" />,
}], { basename: sellerRouterBasename })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={muiTheme}>
      <ErrorBoundary component="portal" root portal="seller">
        <WmsDatePickersProvider>
          <RouterProvider router={router} />
        </WmsDatePickersProvider>
      </ErrorBoundary>
    </ThemeProvider>
  </StrictMode>,
)

