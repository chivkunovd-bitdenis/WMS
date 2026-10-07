import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider, CssBaseline } from "@mui/material";
import { muiTheme } from "../../../frontend/src/mui/theme";
import { FfSuppliesShipmentsPage } from "../../../frontend/src/screens/ff/FfSuppliesShipmentsPage";
import { installMockApi, detail } from "./mockApi";
installMockApi();
createRoot(document.getElementById("root")!).render(
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
        sellers={[{ id: "demo-seller", name: "Демо селлер" }]}
        productPicklist={detail.lines.map((l) => ({
          id: l.product_id,
          sku_code: l.sku_code,
          name: l.product_name,
        }))}
        onRefreshFfSupplyExtras={async () => {}}
        inboundSummaries={[]}
        outboundSummaries={[]}
        marketplaceUnloadSummaries={[
          { ...detail, line_count: detail.lines.length },
        ]}
        discrepancyActSummaries={[]}
        onOpenInbound={() => {}}
        onOpenOutbound={() => {}}
        onCreateMpShipment={async () => null}
        onCreateDiverge={async () => null}
        initialMarketplaceUnloadId={detail.id}
        addressStorageEnabled
      />
    </BrowserRouter>
  </ThemeProvider>,
);
