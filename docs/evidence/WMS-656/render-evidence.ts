// Synthetic saved-label fixture: no production data, no printer/network API.
import { writeFileSync, readFileSync } from 'node:fs'
import * as bwipjs from '../../../frontend/node_modules/bwip-js'
import { buildCzArtifactLabelHtml, buildMarkingTapeDocument, buildWbOrderQrLabelHtml } from '../../../frontend/src/utils/printMarkingCodeLabel'
import { LABEL_SIZES } from '../../../frontend/src/utils/labelSize'
const dir = new URL('.', import.meta.url).pathname
const cis = '010460055555555521WMS656TEST'
const matrix = (await bwipjs.toBuffer({ bcid: 'datamatrix', text: cis, scale: 5, padding: 6 })).toString('base64')
if (process.argv.includes('--fixture')) {
 writeFileSync(dir+'fixture.html', `<html><meta charset="utf-8"><style>html,body{margin:0;background:white}body{width:580px;height:400px;font:20px Arial;text-align:center}img{height:230px}p{margin:8px}</style><body><p>1/100 · Тестовый полный КИЗ</p><p>Товар: Куртка · Цвет: синий · Размер: 54</p><img src="data:image/png;base64,${matrix}"><p style="font-size:16px">${cis}</p></body></html>`)
} else {
 const img='data:image/png;base64,'+readFileSync(dir+'fixture.png').toString('base64')
 const qr='data:image/png;base64,'+(await bwipjs.toBuffer({bcid:'qrcode',text:'WMS656-ORDER',scale:3})).toString('base64')
 for (const size of LABEL_SIZES) writeFileSync(dir+size.id+'.html', buildMarkingTapeDocument([buildCzArtifactLabelHtml(img),buildWbOrderQrLabelHtml(qr,1),buildCzArtifactLabelHtml(img)],size))
 writeFileSync(dir+'58x39-driver.html',readFileSync(dir+'58x40.html','utf8').replace('@page { size: 58mm 40mm;','@page { size: 58mm 39mm;'))
}
