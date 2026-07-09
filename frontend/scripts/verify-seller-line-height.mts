#!/usr/bin/env npx tsx
/**
 * Visual proof: ИП Горячкина seller line spacing on all label sizes.
 * Run from frontend/: npx tsx scripts/verify-seller-line-height.mts
 */
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { chromium } from 'playwright'
import bwipjs from 'bwip-js'
import {
  buildProductLabelSectionHtml,
  buildProductThermalLabelCss,
} from '../src/utils/printProductThermalLabel.ts'
import { LABEL_SIZES } from '../src/utils/labelSize.ts'

const SUNGLASSES = {
  product_name: 'Очки солнцезащитные квадратные модные',
  sku_code: 'ОчкиАVКоричневыйКВ',
  wb_vendor_code: 'ОчкиАVКоричневыйКВ',
  wb_size: '0',
  wb_color: 'коричневый, шоколадный, шоколадный трюфель',
  wb_brand: 'Alte Vette',
  wb_composition: null,
  seller_name: 'ИП Горячкина Т И',
  barcode: '2052582795896',
}

async function code128(text: string): Promise<string> {
  const png = await bwipjs.toBuffer({
    bcid: 'code128',
    text,
    scale: 3,
    height: 18,
    includetext: false,
  })
  return `data:image/png;base64,${png.toString('base64')}`
}

async function main(): Promise<void> {
  const outDir = resolve(process.argv[2] ?? '../output/pdf/_verify/seller-line-fix')
  mkdirSync(outDir, { recursive: true })
  const barcode = await code128(SUNGLASSES.barcode)
  const browser = await chromium.launch()

  for (const size of LABEL_SIZES) {
    const css = buildProductThermalLabelCss(size)
    const section = buildProductLabelSectionHtml(SUNGLASSES, barcode, undefined, size)
    const html = `<!doctype html><html><head><meta charset="utf-8" /><style>${css}</style></head><body>${section}</body></html>`
    const page = await browser.newPage()
    await page.setContent(html, { waitUntil: 'networkidle' })
    await page.emulateMedia({ media: 'print' })

    const metrics = await page.evaluate(() => {
      const seller = document.querySelector('.seller') as HTMLElement | null
      const name = document.querySelector('.name') as HTMLElement | null
      const digits = document.querySelector('.digits') as HTMLElement | null
      if (!seller || !name || !digits) {
        return null
      }
      const sr = seller.getBoundingClientRect()
      const nr = name.getBoundingClientRect()
      const dr = digits.getBoundingClientRect()
      return {
        sellerHeight: Math.round(sr.height * 100) / 100,
        nameTop: Math.round(nr.top * 100) / 100,
        sellerBottom: Math.round(sr.bottom * 100) / 100,
        gapSellerName: Math.round((nr.top - sr.bottom) * 100) / 100,
        gapDigitsSeller: Math.round((sr.top - dr.bottom) * 100) / 100,
        sellerFontSize: getComputedStyle(seller).fontSize,
        sellerLineHeight: getComputedStyle(seller).lineHeight,
      }
    })

    await page.pdf({
      path: `${outDir}/goryachkina-${size.id}.pdf`,
      width: `${size.widthMm}mm`,
      height: `${size.heightMm}mm`,
      margin: { top: '0', right: '0', bottom: '0', left: '0' },
      printBackground: true,
      preferCSSPageSize: true,
    })
    await page.screenshot({
      path: `${outDir}/goryachkina-${size.id}.png`,
      clip: {
        x: 0,
        y: 0,
        width: Math.ceil(size.widthMm * 3.78),
        height: Math.ceil(size.heightMm * 3.78),
      },
    })
    await page.close()

    if (!metrics) {
      throw new Error(`metrics missing for ${size.id}`)
    }
    // Seller line must have real height; gap to name must be positive (not overlapping).
    if (metrics.sellerHeight < 8) {
      throw new Error(`${size.id}: seller height too small: ${metrics.sellerHeight}`)
    }
    if (metrics.gapSellerName < 1.5) {
      throw new Error(`${size.id}: seller/name gap too small: ${metrics.gapSellerName}`)
    }
    console.log(JSON.stringify({ size: size.id, ...metrics }))
  }

  await browser.close()
  console.log(`ok wrote ${outDir}`)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
