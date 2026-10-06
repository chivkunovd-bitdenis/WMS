import React from '../../../frontend/node_modules/react'
import { renderToStaticMarkup } from '../../../frontend/node_modules/react-dom/server'
import { writeFileSync } from 'node:fs'
import { ProductBarcodeCell } from '../../../frontend/src/components/ProductBarcodeCell'
const markup=renderToStaticMarkup(<table><tbody><tr><td>WB · UT0123/0</td><td><ProductBarcodeCell barcode="04640556102658" barcodes={['2055629421109','4610264735875']}/></td></tr><tr><td>WB · UT0127/0</td><td><ProductBarcodeCell barcode="04640556141886" barcodes={['2055629422335','4610264735912']}/></td></tr><tr><td>Ozon · отдельная строка</td><td><ProductBarcodeCell barcode="OZN-TEST" barcodes={[]}/></td></tr></tbody></table>)
writeFileSync(new URL('component.html',import.meta.url),`<html><meta charset="utf-8"><style>body{font:18px Arial;padding:24px;background:white}td{padding:16px;border-bottom:1px solid #ddd}</style><h2>WMS-660 · изолированный компонент на тестовых данных</h2>${markup}</html>`)
