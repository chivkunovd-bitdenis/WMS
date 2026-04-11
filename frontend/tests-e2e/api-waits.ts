import type { Page, Response } from '@playwright/test';

/** Browser hits Vite proxy: paths include `/api/...`. */
function isPostOk(r: Response, pathIncludes: string, urlFilter?: (url: string) => boolean): boolean {
  if (r.request().method() !== 'POST') {
    return false;
  }
  const url = r.url();
  if (!url.includes(pathIncludes)) {
    return false;
  }
  if (urlFilter && !urlFilter(url)) {
    return false;
  }
  const s = r.status();
  return s >= 200 && s < 300;
}

export function waitForPostOk(
  page: Page,
  pathIncludes: string,
  urlFilter?: (url: string) => boolean,
): Promise<Response> {
  return page.waitForResponse((r) => isPostOk(r, pathIncludes, urlFilter));
}

export function waitForGetOk(page: Page, pathIncludes: string): Promise<Response> {
  return page.waitForResponse(
    (r) =>
      r.request().method() === 'GET' &&
      r.url().includes(pathIncludes) &&
      r.status() === 200,
  );
}

/** After creating a cell, the client reloads GET /warehouses/{id}/locations. */
export function waitForLocationsListGet(page: Page): Promise<Response> {
  return page.waitForResponse(
    (r) =>
      r.request().method() === 'GET' &&
      r.url().includes('/api/warehouses/') &&
      r.url().includes('/locations') &&
      r.status() === 200,
  );
}

function isMethodOk(
  method: string,
  r: Response,
  pathIncludes: string,
  urlFilter?: (url: string) => boolean,
): boolean {
  if (r.request().method() !== method) {
    return false;
  }
  const url = r.url();
  if (!url.includes(pathIncludes)) {
    return false;
  }
  if (urlFilter && !urlFilter(url)) {
    return false;
  }
  const s = r.status();
  return s >= 200 && s < 300;
}

export function waitForPatchOk(
  page: Page,
  pathIncludes: string,
  urlFilter?: (url: string) => boolean,
): Promise<Response> {
  return page.waitForResponse((r) => isMethodOk('PATCH', r, pathIncludes, urlFilter));
}

/** Inbound line partial receive: POST .../lines/{id}/receive */
export function waitForInboundReceiveOk(page: Page): Promise<Response> {
  return page.waitForResponse((r) =>
    isMethodOk('POST', r, '/api/operations/inbound-intake-requests', (u) =>
      u.includes('/lines/') && u.includes('/receive'),
    ),
  );
}

/** Outbound line partial ship: POST .../lines/{id}/ship */
export function waitForOutboundShipOk(page: Page): Promise<Response> {
  return page.waitForResponse((r) =>
    isMethodOk('POST', r, '/api/operations/outbound-shipment-requests', (u) =>
      u.includes('/lines/') && u.includes('/ship'),
    ),
  );
}
