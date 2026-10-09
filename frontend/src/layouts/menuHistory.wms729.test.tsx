// @vitest-environment jsdom
// SSR has no viewport; render the desktop drawer so seller menu checks
// exercise the real navigation instead of an unopened mobile drawer.
vi.mock('@mui/material', async (importOriginal) => ({
  ...await importOriginal<typeof import('@mui/material')>(),
  useMediaQuery: () => true,
}))
// Decorative icon barrel exports thousands of SVGs; they are outside this contract.
vi.mock('@mui/icons-material', () => new Proxy({}, {
  has: () => true,
  get: (_target, key) => key === 'then' ? undefined : () => null,
}))
import { MemoryRouter } from 'react-router-dom'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import * as React from 'react'
import { FfReportsPage } from '../screens/ff/FfReportsPage'
import { FfSuppliesShipmentsPage } from '../screens/ff/FfSuppliesShipmentsPage'
import { canAccessFfBlock } from '../utils/ffPermissions'

import { SellerLayout } from '../apps/seller/SellerLayout'
import { AuthedAppLayout } from './AuthedAppLayout'
import { resolveFfPermissions, type FfPermissions } from '../utils/ffPermissions'
import { emptySellerPermissions } from '../utils/sellerPermissions'

const permissions = (patch: Partial<FfPermissions> = {}) => ({ ...resolveFfPermissions('fulfillment_staff', null), ...patch })
const dom = (element: React.ReactElement) => new DOMParser().parseFromString(renderToStaticMarkup(element), 'text/html')
function ffMenu(role: string, patch: Partial<FfPermissions>) {
  return dom(<MemoryRouter initialEntries={['/app/ff/reports']}><AuthedAppLayout portal="ff" meRole={role} ffPermissions={permissions(patch)} onLogout={() => {}}>child</AuthedAppLayout></MemoryRouter>)
}
function sellerMenu(products: boolean) {
  return dom(<MemoryRouter><SellerLayout permissions={{ ...emptySellerPermissions(), products, documents: true }} onLogout={() => {}} children={null} /></MemoryRouter>)
}
// Execute the production route JSX, not a copied route/guard. SSR keeps unrelated
// network effects outside this small contract and retains the actual page component.
function reportRoute(portal: 'ff' | 'seller', role: string, allowed: boolean, packaging = false) {
  const source = readFileSync(new URL(portal === 'ff' ? '../App.tsx' : '../apps/seller/SellerApp.tsx', import.meta.url), 'utf8')
  const file = ts.createSourceFile('route.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const wanted = portal === 'ff' ? 'ff/reports' : '/reports'
  let expression = ''
  let mpGuard = ''
  function visit(node: ts.Node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(file) === 'canMpShipmentOps') mpGuard = node.initializer!.getText(file)
    if (ts.isJsxSelfClosingElement(node) && node.tagName.getText(file) === 'Route') {
      const attrs = node.attributes.properties.filter(ts.isJsxAttribute)
      const path = attrs.find(attr => attr.name.getText(file) === 'path')?.initializer
      if (path && ts.isStringLiteral(path) && path.text === wanted) {
        const element = attrs.find(attr => attr.name.getText(file) === 'element')?.initializer
        if (element && ts.isJsxExpression(element)) expression = element.expression!.getText(file)
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(file)
  expect(expression, `real route ${wanted}`).not.toBe('')
  const me = { role, permissions: permissions({ inventory: allowed, packaging }), seller_permissions: { ...emptySellerPermissions(), products: allowed }, address_storage_enabled: true }
  const scope: Record<string, unknown> = {
    React, token: 'test', me, isFulfillmentAdmin: role === 'fulfillment_admin', canAccessFfBlock,
    FfReportsPage, FfSuppliesShipmentsPage, SectionErrorBoundary: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    ffAccessDenied: <div>Нет доступа</div>, accessDenied: <div>Нет доступа</div>,
    sellerPermissions: me.seller_permissions, catalogScopeKey: 'test', sellers: [{ id: 'control-seller', name: 'CONTROL-SELLER' }], warehouses: [], reportWarehouseOptions: () => [],
    products: [], inboundSummaries: [], outboundSummaries: [], marketplaceUnloadSummaries: [], discrepancyActSummaries: [],
    opsBusy: false, opsError: null, ffSuppliesNotice: null, pendingMpUnloadId: null,
    onCreateFfMpShipment: () => {}, onCreateFfDiscrepancyAct: () => {},
  }
  function execute(code: string) {
    const js = ts.transpileModule(`const result = (${code});`, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2022 } }).outputText
    return new Function(...Object.keys(scope), `${js}; return result`)(...Object.values(scope))
  }
  if (mpGuard) scope.canMpShipmentOps = execute(mpGuard)
  return dom(execute(expression) as React.ReactElement)
}

describe('WMS-729 · меню истории товаров', () => {
  it.each(['fulfillment_admin', 'fulfillment_staff'])('c1_%s_renames_reports_preserving_href_and_neighbor_order', role => {
      const doc = ffMenu(role, { inventory: true, cells: true, mp_shipments: true, packaging: true })
      const link = doc.querySelector('[data-testid="nav-ff-reports"]')!
      expect(link.textContent).toBe('История по товарам')
      expect(link.getAttribute('href')).toBe('/app/ff/reports')
      expect(doc.querySelectorAll('a[href="/app/ff/reports"]')).toHaveLength(1)
      const links = [...doc.querySelectorAll('a[data-testid]')].map(el => el.getAttribute('data-testid'))
      expect(links.indexOf('nav-ff-reports')).toBe(links.indexOf('nav-catalog') + 1)
      expect(doc.querySelector('[aria-label="Разделы ФФ"]')?.textContent).not.toContain('Отчёты')
  })
  it('c1_seller_renames_reports_preserving_href_and_neighbor_order', () => {
    const doc = sellerMenu(true)
    const link = doc.querySelector('[data-testid="nav-seller-reports"]')!
    expect(link.textContent).toBe('История по товарам'); expect(link.getAttribute('href')).toBe('/reports')
    expect(doc.querySelectorAll('a[href="/reports"]')).toHaveLength(1)
    const links = [...doc.querySelectorAll('a[data-testid]')].map(el => el.getAttribute('data-testid'))
    expect(links.indexOf('nav-seller-reports')).toBe(links.indexOf('nav-seller-products') + 1)
    expect(links.indexOf('nav-seller-billing')).toBe(links.indexOf('nav-seller-reports') + 1)
  })
  it('c2_menu_and_direct_routes_keep_inventory_products_permissions_and_admin_access', () => {
    expect(ffMenu('fulfillment_staff', {}).querySelector('[data-testid="nav-ff-reports"]')).toBeNull()
    expect(sellerMenu(false).querySelector('[data-testid="nav-seller-reports"]')).toBeNull()
    for (const portal of ['ff', 'seller'] as const) {
      const denied = reportRoute(portal, portal === 'ff' ? 'fulfillment_staff' : 'fulfillment_seller', false)
      expect(denied.body.textContent).not.toContain('Остатки и движения')
      expect(denied.body.textContent).toMatch(/Нет доступа|Доступ ограничен|нет прав/i)
    }
    expect(reportRoute('ff', 'fulfillment_admin', false).body.textContent).toContain('Остатки и движения')
  })
  it('c3_original_reports_routes_keep_real_report_heading_and_seller_export_scope', () => {
    const ff = reportRoute('ff', 'fulfillment_staff', true)
    const seller = reportRoute('seller', 'fulfillment_seller', true)
    for (const doc of [ff, seller]) {
      expect(doc.body.textContent).toContain('Остатки и движения')
      expect(doc.querySelector('[data-testid="ff-reports-next-page"]')).not.toBeNull()
    }
    expect(ff.querySelector('[data-testid="ff-reports-download-excel"]')).not.toBeNull()
    expect(ff.querySelector('[data-testid="ff-reports-seller"]')).not.toBeNull()
    expect(seller.querySelector('[data-testid="ff-reports-download-excel"]')).toBeNull()
    expect(seller.querySelector('[data-testid="ff-reports-seller"]')).toBeNull()
  })
})
