import { mkdir, writeFile } from 'node:fs/promises'

const backend = process.env.WMS666_BACKEND || 'http://127.0.0.1:16709'
const output = process.env.WMS666_GROUP_EVIDENCE
if (!output) throw Error('Set WMS666_GROUP_EVIDENCE to the persistent evidence directory')
const idleResponse = await fetch(`${backend}/idle`)
if (!idleResponse.ok) throw Error(`API idle check failed: ${idleResponse.status}`)
const idle = await idleResponse.json()
if (idle.active !== 0) throw Error(`Refusing isolated test DB reset while ${idle.active} API requests are active`)

const response = await fetch(`${backend}/seed`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ codes: 4, multi: true, bare: true }),
})
const seeded = await response.json()
if (!response.ok) throw Error(`Synthetic group seed failed: ${response.status}`)
const tuple = {
  supply_id: seeded.supply_id,
  supply_ids: seeded.supply_ids,
  order_ids: seeded.order_ids,
  barcode: seeded.barcode,
  task_id: seeded.task_id,
  line_id: seeded.line_id,
}
if (!tuple.supply_ids || tuple.supply_ids.length !== 2 || !tuple.order_ids || tuple.order_ids.length !== 2) {
  throw Error('Expected a two-supply/two-order group seed')
}
await mkdir(`${output}/fixtures`, { recursive: true })
await writeFile(`${output}/seed-public.json`, JSON.stringify(tuple, null, 2) + '\n')
await writeFile(`${output}/seed-run.json`, JSON.stringify({
  backend,
  isolated_test_database: 'wms_test_666_browser_proof',
  options: { codes: 4, multi: true, bare: true },
  idle_before_seed: idle,
  tuple,
  secret_header_fields_removed: true,
}, null, 2) + '\n')
process.stdout.write(JSON.stringify({ supply_ids: tuple.supply_ids, order_ids: tuple.order_ids, barcode: tuple.barcode }) + '\n')
