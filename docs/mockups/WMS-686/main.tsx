import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider, CssBaseline } from '@mui/material'
import { muiTheme } from '../../../frontend/src/mui/theme'
import { FfSuppliesShipmentsPage } from '../../../frontend/src/screens/ff/FfSuppliesShipmentsPage'
import { detailFor, installMockApi, products, shipments } from './mockApi'
import { DemoScanCodes } from './Controls'

// WMS-686 · настоящий экран «Отгрузки на МП» с вымышленными данными и локальным API.
installMockApi()

const params = new URLSearchParams(location.search)
const opened = shipments.find((shipment) => shipment.id === params.get('open_mp'))?.id ?? shipments[0].id

createRoot(document.getElementById('root')!).render(
  <ThemeProvider theme={muiTheme}>
    <CssBaseline />
    <BrowserRouter>
      <FfSuppliesShipmentsPage
        pageVariant="mp-shipments"
        busy={false}
        error={null}
        infoNotice={null}
        onDismissInfoNotice={() => {}}
        token="fictional-demo-token"
        sellers={[{ id: 'demo-seller', name: 'Демо селлер · ИП Иванов' }]}
        productPicklist={products.map((product) => ({ id: product.id, sku_code: product.sku, name: product.name }))}
        onRefreshFfSupplyExtras={async () => {}}
        inboundSummaries={[]}
        outboundSummaries={[]}
        marketplaceUnloadSummaries={shipments.map((shipment) => {
          const detail = detailFor(shipment.id)
          return { ...detail, line_count: detail.lines.length }
        })}
        discrepancyActSummaries={[]}
        onOpenInbound={() => {}}
        onOpenOutbound={() => {}}
        onCreateMpShipment={async () => null}
        onCreateDiverge={async () => null}
        initialMarketplaceUnloadId={opened}
        addressStorageEnabled
      />
      <DemoScanCodes />
    </BrowserRouter>
  </ThemeProvider>,
)
