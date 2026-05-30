const API_PREFIX = '/api';

export type AuthStoragePortal = 'fulfillment' | 'seller';

const TOKEN_KEYS: Record<AuthStoragePortal, string> = {
  fulfillment: 'wms_token_ff',
  seller: 'wms_token_seller',
};

const LEGACY_TOKEN_KEY = 'wms_token';

export function apiUrl(path: string): string {
  const p = path.startsWith('/') ? path : `/${path}`;
  return `${API_PREFIX}${p}`;
}

export function getStoredToken(
  portal: AuthStoragePortal = 'fulfillment',
): string | null {
  const key = TOKEN_KEYS[portal];
  const value = localStorage.getItem(key);
  if (value) {
    return value;
  }
  // Legacy single-key storage applied only to FF portal (historical default).
  if (portal === 'fulfillment') {
    const legacy = localStorage.getItem(LEGACY_TOKEN_KEY);
    if (legacy) {
      localStorage.setItem(key, legacy);
      localStorage.removeItem(LEGACY_TOKEN_KEY);
      return legacy;
    }
  }
  return null;
}

export function setStoredToken(
  token: string | null,
  portal: AuthStoragePortal = 'fulfillment',
): void {
  const key = TOKEN_KEYS[portal];
  if (token === null) {
    localStorage.removeItem(key);
    localStorage.removeItem(LEGACY_TOKEN_KEY);
    return;
  }
  localStorage.setItem(key, token);
  localStorage.removeItem(LEGACY_TOKEN_KEY);
}
