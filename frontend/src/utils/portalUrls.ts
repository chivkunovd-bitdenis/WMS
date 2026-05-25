/** Публичный URL портала селлера (тот же origin, путь /seller/). */
export function sellerPortalUrl(): string {
  const env = import.meta.env.VITE_SELLER_PORTAL_URL?.trim()
  if (env) {
    return env
  }
  if (typeof window !== 'undefined' && window.location?.origin) {
    return `${window.location.origin}/seller/`
  }
  return '/seller/'
}

/** Публичный URL портала фулфилмента. */
export function ffPortalUrl(): string {
  const env = import.meta.env.VITE_FF_PORTAL_URL?.trim()
  if (env) {
    return env
  }
  if (typeof window !== 'undefined' && window.location?.origin) {
    return `${window.location.origin}/`
  }
  return '/'
}
