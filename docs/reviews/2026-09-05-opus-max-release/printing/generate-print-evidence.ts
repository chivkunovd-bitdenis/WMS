import { writeFileSync } from 'node:fs'
import { buildProductThermalLabelDocument, buildProductLabelSectionHtml } from '../../../../frontend/src/utils/printProductThermalLabel.ts'
import { buildMarkingTapeDocument } from '../../../../frontend/src/utils/printMarkingCodeLabel.ts'
const data = { product_name: 'Тестовый товар WMS-371', sku_code: 'TEST-WMS-371', barcode: 'TEST371000001', wb_vendor_code: 'TEST-ARTICLE', seller_name: 'Тестовый селлер', wb_brand: 'TEST', wb_color: 'коричневый', wb_composition: 'пластик' }
const barcode = 'data:image/svg+xml;base64,' + Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="240" height="50"><path d="M10 0V50M20 0V50M25 0V50M35 0V50M50 0V50M55 0V50M80 0V50M100 0V50M120 0V50M125 0V50M140 0V50M150 0V50M180 0V50M200 0V50M220 0V50" stroke="black" stroke-width="4"/></svg>').toString('base64')
writeFileSync('/tmp/wms371-product.html', buildProductThermalLabelDocument(data, 3, barcode))
writeFileSync('/tmp/wms371-tape.html', buildMarkingTapeDocument(Array.from({ length: 3 }, () => buildProductLabelSectionHtml(data, barcode))))
