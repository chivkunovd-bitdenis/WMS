// @vitest-environment jsdom
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
import { resolveFfPermissions, FF_PERMISSION_BLOCKS, FF_STAFF_ACCESS_BLOCKS, applyFfStaffAccessChange, ffPermissionsToStaffAccess, type FfPermissions } from '../utils/ffPermissions'
import { emptySellerPermissions } from '../utils/sellerPermissions'

const permissions = (patch: Partial<FfPermissions> = {}) => ({ ...resolveFfPermissions('fulfillment_staff', null), ...patch })
const dom = (element: React.ReactElement) => new DOMParser().parseFromString(renderToStaticMarkup(element), 'text/html')
function ffMenu(role: string, patch: Partial<FfPermissions>) {
  return dom(<MemoryRouter initialEntries={['/app/ff/mp-shipments']}><AuthedAppLayout portal="ff" meRole={role} ffPermissions={permissions(patch)} onLogout={() => {}}>child</AuthedAppLayout></MemoryRouter>)
}
function sellerMenu(products: boolean) {
  return dom(<MemoryRouter><SellerLayout permissions={{ ...emptySellerPermissions(), products, documents: true }} onLogout={() => {}} /></MemoryRouter>)
}
// Execute the production route JSX, not a copied route/guard. SSR keeps unrelated
// network effects outside this small contract and retains the actual page component.
function reportRoute(portal: 'ff' | 'seller', role: string, allowed: boolean, packaging = false) {
  const source = readFileSync(new URL(portal === 'ff' ? '../App.tsx' : '../apps/seller/SellerApp.tsx', import.meta.url), 'utf8')
  const file = ts.createSourceFile('route.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const wanted = portal === 'ff' ? 'ff/mp-shipments' : '/reports'
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
  const me = { role, permissions: permissions({ mp_shipments: allowed, packaging }), seller_permissions: { ...emptySellerPermissions(), products: allowed }, address_storage_enabled: true }
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
  return dom(<MemoryRouter>{execute(expression) as React.ReactElement}</MemoryRouter>)
}

describe('WMS-730 · меню FBO', () => {
  it.each(['fulfillment_admin', 'fulfillment_staff'])('c1_%s_renames_only_shipments_item_to_latin_fbo_next_to_unchanged_fbs', role => {
      const doc = ffMenu(role, { mp_shipments: true, packaging: true, cells: true })
      const link = doc.querySelector('[data-testid="nav-ff-mp-shipments"]')!
      expect(link.textContent).toBe('FBO'); expect(link.getAttribute('href')).toBe('/app/ff/mp-shipments')
      expect(doc.querySelectorAll('a[href="/app/ff/mp-shipments"]')).toHaveLength(1)
      expect(doc.querySelector('[aria-label="Разделы ФФ"]')?.textContent).not.toMatch(/ФБО|Отгрузки/)
      expect(doc.querySelector('[data-testid="nav-ff-fbs"]')?.textContent).toBe('FBS')
      expect(doc.querySelector('[data-testid="nav-ff-fbs"]')?.getAttribute('href')).toBe('/app/ff/fbs')
      const keys = [...doc.querySelectorAll('a[data-testid]')].map(el => el.getAttribute('data-testid'))
      expect(keys.indexOf('nav-ff-mp-shipments')).toBe(keys.indexOf('nav-ff-fbs') + 1)
      expect(keys.indexOf('nav-catalog')).toBe(keys.indexOf('nav-ff-mp-shipments') + 1)
  })
  it('c2_packaging_does_not_grant_fbo_menu_or_direct_route_but_admin_and_mp_shipments_do', () => {
    for (const patch of [{}, { packaging: true }]) {
      const doc = ffMenu('fulfillment_staff', patch)
      expect(doc.querySelector('[data-testid="nav-ff-mp-shipments"]')).toBeNull()
      expect(Boolean(doc.querySelector('[data-testid="nav-ff-fbs"]'))).toBe(Boolean('packaging' in patch))
    }
    for (const packaging of [false, true]) {
      const denied = reportRoute('ff', 'fulfillment_staff', false, packaging)
      expect(denied.body.textContent).not.toContain('Отгрузки на МП')
      expect(denied.body.textContent).toMatch(/Нет доступа|Доступ ограничен|нет прав/i)
    }
    expect(reportRoute('ff', 'fulfillment_staff', true).body.textContent).toContain('Отгрузки на МП')
    expect(reportRoute('ff', 'fulfillment_admin', false).body.textContent).toContain('Отгрузки на МП')
  })
  it('c3_preserves_shipments_screen_permission_labels_group_functions_and_seller_menu', () => {
    expect(reportRoute('ff', 'fulfillment_admin', false).body.textContent).toContain('Отгрузки на МП')
    expect(FF_PERMISSION_BLOCKS.map(({ key, label }) => ({ key, label }))).toEqual([
      { key: 'settings', label: 'Настройки' }, { key: 'mp_shipments', label: 'Отгрузки на МП' },
      { key: 'reception', label: 'Приёмка' }, { key: 'cells', label: 'Ячейки' },
      { key: 'inventory', label: 'Инвентаризация' }, { key: 'packaging', label: 'Упаковка' }, { key: 'shift_lead', label: 'Старший смены' },
    ])
    expect(FF_STAFF_ACCESS_BLOCKS).toEqual([{ key: 'reception', label: 'Приёмка' }, { key: 'shipments', label: 'Отгрузки' }, { key: 'catalog_cells', label: 'Каталог и ячейки' }, { key: 'settings_staff', label: 'Настройки и сотрудники' }])
    for (const patch of [{ mp_shipments: true }, { packaging: true }, {}]) expect(ffPermissionsToStaffAccess(permissions(patch)).shipments).toBe(Object.values(patch).some(Boolean))
    const before = permissions({ reception: true, cells: true })
    for (const checked of [true, false]) expect(applyFfStaffAccessChange(before, 'shipments', checked)).toEqual({ ...before, mp_shipments: checked, packaging: checked, shift_lead: checked })
    expect(sellerMenu(true).querySelector('a[href$="mp-shipments"]')).toBeNull()
    expect(sellerMenu(true).body.textContent).not.toMatch(/FBO|ФБО/)
  })
})
