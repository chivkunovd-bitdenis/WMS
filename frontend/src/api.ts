const API_PREFIX = '/api';

export function apiUrl(path: string): string {
  const p = path.startsWith('/') ? path : `/${path}`;
  return `${API_PREFIX}${p}`;
}

export function getStoredToken(): string | null {
  return localStorage.getItem('wms_token');
}

export function setStoredToken(token: string | null): void {
  if (token === null) {
    localStorage.removeItem('wms_token');
    return;
  }
  localStorage.setItem('wms_token', token);
}
