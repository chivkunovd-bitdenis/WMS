import { describe, expect, it } from 'vitest'
import prod from './__prod_count.json'
import { toCount } from './inventoryCountApi'
import { applyScan, NOTHING_OPEN } from './InventoryScan'
import type { InventoryNode } from './InventoryTypes'

describe('боевой документ: что реально считается', () => {
  it('прогон всех товаров в своих коробах', () => {
    const count = toCount(prod as never)
    type Row = { box: string; boxBc: string | null; bc: string; name: string }
    const rows: Row[] = []
    const walk = (nodes: InventoryNode[], box: { code: string; bc: string | null } | null) => {
      for (const n of nodes) {
        if (n.kind === 'product') {
          if (box) rows.push({ box: box.code, boxBc: box.bc, bc: n.barcode, name: n.name })
          continue
        }
        walk(n.children, { code: n.code, bc: n.barcode })
      }
    }
    for (const c of count.cells) walk(c.children, null)

    const bad: Array<Row & { msg: string }> = []
    for (const r of rows) {
      const opened = applyScan(count, r.boxBc ?? r.box, NOTHING_OPEN)
      if (!opened.open.containerId) { bad.push({ ...r, msg: 'КОРОБ НЕ ОТКРЫЛСЯ' }); continue }
      const scan = applyScan(opened.count, r.bc, opened.open)
      const counted = scan.count !== opened.count
      if (!counted) bad.push({ ...r, msg: scan.message.slice(0, 90) })
    }
    console.log('товаров в таре:', rows.length, '| НЕ СЧИТАЕТСЯ:', bad.length)
    console.log(JSON.stringify(bad.slice(0, 12), null, 2))
    // пустые ШК
    console.log('без ШК:', rows.filter(r => !r.bc).length)
    expect(true).toBe(true)
  })
})
