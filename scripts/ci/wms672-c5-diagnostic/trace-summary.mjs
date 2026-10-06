// Bounded offline parsing; retain native engine events without asserting a cause.
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { gunzipSync } from 'node:zlib';
const dir = resolve(process.env.WMS672_EVIDENCE_DIR, 'engine');
const raw = await readFile(resolve(dir, 'trace.json.gz'));
if (raw.length > 67108864) throw new Error('Compressed trace exceeds bound');
const trace = JSON.parse(gunzipSync(raw, { maxOutputLength: 268435456 }));
if (!Array.isArray(trace.traceEvents)) throw new Error('Missing traceEvents');
const events = trace.traceEvents;
const names = {};
for (const event of events) names[event.name] = (names[event.name] || 0) + 1;
const cache = events.filter(event => /ImageDecode|DecodedImageTracker|BudgetForImage|UnrefImage/.test(event.name || ''));
const markers = events.filter(event => event.name === 'clock_sync' || (event.args?.sync_id || '').startsWith('C5-clock-'));
const memory = [];
for (const event of events) {
  const allocators = event.args?.dumps?.allocators;
  if (!allocators) continue;
  const imageAllocators = Object.fromEntries(Object.entries(allocators).filter(([name]) => name.startsWith('cc/image_memory/')));
  if (Object.keys(imageAllocators).length) memory.push({ ts: event.ts, pid: event.pid, tid: event.tid, name: event.name, imageAllocators });
}
await writeFile(resolve(dir, 'cache-events.json.gz'), (await import('node:zlib')).gzipSync(JSON.stringify(cache)));
await writeFile(resolve(dir, 'memory-and-markers.json'), JSON.stringify({ memory, markers }, null, 2));
const completion = JSON.parse(await readFile(resolve(dir, 'trace-completion.json'), 'utf8'));
console.log(JSON.stringify({ events: events.length, cacheEvents: cache.length, markers: markers.length, imageMemorySnapshots: memory.length, completion, relevantEventCounts: Object.fromEntries(Object.entries(names).filter(([name]) => /ImageDecode|DecodedImageTracker|BudgetForImage|UnrefImage|memory|clock_sync/.test(name))) }, null, 2));
