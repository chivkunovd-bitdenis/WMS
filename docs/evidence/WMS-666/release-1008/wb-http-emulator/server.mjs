import { createServer } from 'node:http';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';

const require = createRequire(new URL('../../../../../frontend/package.json', import.meta.url));
const bwip = require('bwip-js');
const port = Number(process.env.WMS666_WB_EMULATOR_PORT || 16710);
const requests = [];
const sgtinByOrder = new Map();
const rejectedValuesByOrder = new Map();

async function readJson(req) {
  let raw = '';
  for await (const chunk of req) raw += chunk;
  return JSON.parse(raw || '{}');
}

function sendJson(res, status, payload) {
  res.writeHead(status, { 'content-type': 'application/json' });
  res.end(JSON.stringify(payload));
}

const server = createServer(async (req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ ok: true, provider: 'synthetic-loopback-wb' }));
    return;
  }
  if (req.method === 'GET' && req.url === '/requests') {
    sendJson(res, 200, requests);
    return;
  }
  if (req.method === 'GET' && req.url === '/state') {
    sendJson(res, 200, { requests, sgtinByOrder: Object.fromEntries(sgtinByOrder) });
    return;
  }
  if (req.method === 'POST' && req.url === '/configure-rejection') {
    const body = await readJson(req);
    if (!Number.isInteger(body.orderId) || typeof body.rejectedValue !== 'string') {
      sendJson(res, 400, { detail: 'orderId and rejectedValue are required' });
      return;
    }
    rejectedValuesByOrder.set(body.orderId, body.rejectedValue);
    sendJson(res, 200, { configured: true, orderId: body.orderId });
    return;
  }
  const requestUrl = new URL(req.url || '/', 'http://127.0.0.1');
  if (req.method === 'DELETE' && /^\/api\/v3\/orders\/\d+\/meta$/.test(requestUrl.pathname)
      && requestUrl.searchParams.get('key') === 'sgtin') {
    const orderId = Number(requestUrl.pathname.match(/^\/api\/v3\/orders\/(\d+)\/meta$/)?.[1]);
    sgtinByOrder.delete(orderId);
    requests.push({ method: 'DELETE', path: req.url, orderId, authorizationPresent: Boolean(req.headers.authorization), status: 204 });
    res.writeHead(204); res.end();
    return;
  }
  if (req.method === 'POST' && req.url === '/reset-state') {
    requests.length = 0;
    sgtinByOrder.clear();
    rejectedValuesByOrder.clear();
    sendJson(res, 200, { reset: true });
    return;
  }
  if (req.method === 'PUT' && /^\/api\/v3\/orders\/\d+\/meta\/sgtin$/.test(req.url || '')) {
    const body = await readJson(req);
    const orderId = Number((req.url || '').match(/^\/api\/v3\/orders\/(\d+)\/meta\/sgtin$/)?.[1]);
    const value = Array.isArray(body.sgtins) && body.sgtins.length === 1 ? body.sgtins[0] : null;
    if (!Number.isInteger(orderId) || typeof value !== 'string') {
      sendJson(res, 400, { detail: 'sgtins must contain exactly one string' });
      return;
    }
    const rejected = rejectedValuesByOrder.get(orderId) === value;
    requests.push({ method: 'PUT', path: req.url, orderId, authorizationPresent: Boolean(req.headers.authorization), body, status: rejected ? 409 : 204 });
    if (rejected) {
      sendJson(res, 409, {
        code: 'MetaValidationFail', message: 'Synthetic local WB rejected this exact SGTIN',
        data: { orders: [{ id: orderId, metaDetails: [{ key: 'sgtin', value, decision: 'invalid', reason: 'synthetic local WB rejection' }] }] },
      });
      return;
    }
    sgtinByOrder.set(orderId, value);
    res.writeHead(204); res.end();
    return;
  }
  if (req.method === 'POST' && req.url === '/api/marketplace/v3/orders/meta') {
    const body = await readJson(req);
    if (!Array.isArray(body.orders) || body.orders.some(id => !Number.isInteger(id))) {
      sendJson(res, 400, { detail: 'orders must be integer IDs' });
      return;
    }
    const orders = body.orders.map(orderId => {
      const value = sgtinByOrder.get(orderId);
      const rejected = rejectedValuesByOrder.get(orderId) === value;
      const detail = value ? [{ key: 'sgtin', value, decision: rejected ? 'invalid' : 'accepted', ...(rejected ? { reason: 'synthetic local WB rejection' } : {}) }] : [];
      return { id: orderId, metaDetails: detail, meta: { sgtin: value ? [{ value, checkStatus: rejected ? 'fail' : 'ok' }] : [] } };
    });
    requests.push({ method: 'POST', path: req.url, orderIds: [...body.orders], authorizationPresent: Boolean(req.headers.authorization), body, status: 200 });
    sendJson(res, 200, { orders });
    return;
  }
  if (req.method !== 'POST' || !req.url?.startsWith('/api/v3/orders/stickers')) {
    res.writeHead(404); res.end(); return;
  }
  const body = await readJson(req);
  if (!Array.isArray(body.orders) || body.orders.some(id => !Number.isInteger(id))) {
    res.writeHead(400, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ detail: 'orders must be integer IDs' })); return;
  }
  const stickers = [];
  for (const orderId of body.orders) {
    const barcode = `*WMS666-${orderId}`;
    const png = await bwip.toBuffer({ bcid: 'qrcode', text: barcode, scale: 4, padding: 4, backgroundcolor: 'FFFFFF' });
    stickers.push({ orderId, partA: `AUDIT-${orderId}`, partB: '01', barcode, file: png.toString('base64') });
  }
  requests.push({
    path: req.url.split('?')[0],
    orderIds: body.orders,
    count: body.orders.length,
    stickers: stickers.map(row => ({ orderId: row.orderId, barcode: row.barcode,
      sha256: createHash('sha256').update(Buffer.from(row.file, 'base64')).digest('hex'),
      pngBytes: Buffer.from(row.file, 'base64').length })),
    status: 200,
  });
  res.writeHead(200, { 'content-type': 'application/json' });
  res.end(JSON.stringify({ stickers }));
});

server.listen(port, '127.0.0.1', () => {
  process.stdout.write(JSON.stringify({ ready: true, host: '127.0.0.1', port }) + '\n');
});
process.on('SIGTERM', () => server.close(() => process.exit(0)));
