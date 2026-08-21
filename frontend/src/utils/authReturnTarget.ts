import type { AuthPortal } from '../hooks/useAuth'

export type AuthReturnTarget = {
  portal: AuthPortal
  path: string
}

const PORTAL_FALLBACKS: Record<AuthPortal, string> = {
  fulfillment: '/app/ff/dashboard',
  seller: '/documents',
}

const FF_ROUTE_PREFIXES = [
  '/app/ff/dashboard',
  '/app/ff/supplies-shipments',
  '/app/ff/mp-shipments',
  '/app/ff/reception',
  '/app/ff/sorting',
  '/app/ff/products',
  '/app/ff/fbs',
  '/app/ff/packaging',
  '/app/ff/honest-sign',
  '/app/ff/notifications',
  '/app/ff/inventory',
  '/app/ff/settings',
  '/app/ff/integrations/wb',
  '/app/catalog',
  '/app/ops',
  '/app/integrations/wb',
]

function isSafeRelativePath(pathname: string): boolean {
  return pathname.startsWith('/') && !pathname.startsWith('//') && !pathname.includes('\\')
}

export function captureAuthReturnTarget(
  portal: AuthPortal,
  pathname: string,
  search: string,
  hash: string,
): AuthReturnTarget | null {
  if (!isSafeRelativePath(pathname)) {
    return null
  }
  if (
    portal === 'fulfillment' &&
    !FF_ROUTE_PREFIXES.some(
      (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
    )
  ) {
    return null
  }
  if (
    portal === 'seller' &&
    !['/documents', '/inbound/new', '/products', '/honest-sign', '/settings', '/notifications'].some(
      (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
    )
  ) {
    return null
  }
  return { portal, path: `${pathname}${search}${hash}` }
}

export function consumeAuthReturnTarget(
  target: AuthReturnTarget | null,
  portal: AuthPortal,
): string {
  return target?.portal === portal ? target.path : PORTAL_FALLBACKS[portal]
}
