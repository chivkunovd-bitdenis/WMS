import { mkdirSync, writeFileSync } from 'node:fs'
import * as bwipjs from 'bwip-js'
import { buildMarkingTapeDocument, buildWbOrderQrLabelHtml } from '../src/utils/printMarkingCodeLabel'
import { buildProductLabelSectionHtml } from '../src/utils/printProductThermalLabel'
import { LABEL_SIZES } from '../src/utils/labelSize'
async function main() {
  const dir = process.argv[2] ?? '../docs/evidence/WMS-611'
  mkdirSync(dir, { recursive: true })
  const qr = 'data:image/png;base64,' + (await bwipjs.toBuffer({ bcid: 'qrcode', text: 'WMS-611-PRINT-PROOF', scale: 3 })).toString('base64')
  const barcode = 'data:image/png;base64,' + (await bwipjs.toBuffer({ bcid: 'code128', text: '2038400000123', scale: 3, height: 10 })).toString('base64')
  const product = { product_name: 'Куртка зимняя больших размеров с мехом и капюшоном', sku_code: 'ФА_МОД44а/202/42', barcode: '2038400000123', wb_size: '54', seller_name: 'ИП Фадин', brand: 'Fadin' }
  for (const size of LABEL_SIZES) {
    const sections = Array.from({ length: 12 }, (_, i) => [buildWbOrderQrLabelHtml(qr, i+1), buildProductLabelSectionHtml(product, barcode, undefined, size)]).flat()
    writeFileSync(`${dir}/tape-${size.id}.html`, buildMarkingTapeDocument(sections, size))
  }
}
void main()
