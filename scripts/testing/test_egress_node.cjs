'use strict';

if (process.env.WMS_TEST_EGRESS === 'deny') {
  const net = require('node:net');
  const tls = require('node:tls');
  const { isIP } = require('node:net');

  const liveSuffixes = ['wildberries.ru', 'ozon.ru'];
  const defaults = '127.0.0.1,::1,localhost,*.test,wb-emulator,db,redis';
  const patterns = (process.env.WMS_TEST_EGRESS_ALLOW_HOSTS || defaults)
    .split(',')
    .map((item) => item.trim().toLowerCase().replace(/\.$/, ''))
    .filter(Boolean);
  if (process.env.WMS_TEST_EGRESS_ALLOW_LIVE_MARKETPLACES === '1') {
    patterns.push(...liveSuffixes);
    patterns.push(...liveSuffixes.map((suffix) => `*.${suffix}`));
  }

  function allowed(host) {
    const normalized = String(host || 'localhost').toLowerCase().replace(/\.$/, '');
    if (normalized === '127.0.0.1' || normalized === '::1') return true;
    if (isIP(normalized)) return false;
    return patterns.some((pattern) =>
      pattern.startsWith('*.') ? normalized.endsWith(pattern.slice(1)) : normalized === pattern,
    );
  }

  function hostFromArgs(args) {
    const first = args[0];
    if (typeof first === 'object' && first !== null) return first.host || first.hostname;
    return args[1];
  }

  function guard(connect) {
    return function guardedConnect(...args) {
      const host = hostFromArgs(args);
      if (!allowed(host)) throw new Error(`WMS test egress denied host: ${host || 'localhost'}`);
      return connect.apply(this, args);
    };
  }

  net.connect = guard(net.connect);
  net.createConnection = net.connect;
  tls.connect = guard(tls.connect);
}
