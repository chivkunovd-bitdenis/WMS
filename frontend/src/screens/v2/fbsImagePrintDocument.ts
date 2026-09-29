import type { LabelSize } from '../../utils/labelSize'

export type FbsImagePrintItem = { objectUrl: string; label: string }

/**
 * Печатный документ окна «Проверка перед печатью» FBS для картинок: стикер
 * заказа WB, QR грузоместа, QR короба WMS, QR поставки. PDF Ozon сюда не
 * попадает — его печатает просмотрщик браузера.
 */
export function buildFbsImagePrintDocument(
  images: FbsImagePrintItem[],
  copies: number,
  labelSize: LabelSize,
): string {
  const safeCopies = Math.max(1, Math.min(99, copies))
  const pages = images
    .flatMap(({ objectUrl, label }) =>
      Array.from(
        { length: safeCopies },
        () => `<section class="label"><img src="${objectUrl}" alt="${label}"></section>`,
      ),
    )
    .join('')
  const pageWidthMm = `${labelSize.widthMm}mm`
  const pageHeightMm = `${labelSize.heightMm}mm`
  // Размер страницы объявляем, а по ширине вёрстку привязываем к реальному листу
  // принтера: рулон 60x40 при объявленных 58x40 обрезал QR по краю. Проценты плюс
  // max-* дают картинке вписаться в любую бумагу, поле в 1 мм не даёт упереться в срез.
  //
  // WMS-583: после ручной печати QR за этикеткой шла пустая. Раньше разрыв стоял
  // после каждой этикетки, а снять его с последней должен был `:last-child` — но
  // последним ребёнком body здесь стоит <script> печати, и правило не срабатывало:
  // последняя этикетка несла принудительный разрыв страницы. Теперь разрыв стоит
  // только перед следующей этикеткой, так что после последней ему взяться неоткуда.
  // Высота была только 100vh, то есть зависела от окна. Теперь, как у автопечати
  // при скане, она равна выбранной наклейке, но не больше листа: Chromium при печати
  // округляет лист вниз на доли пикселя, и 100vh держит этикетку ровно в листе.
  const printCss = [
    `@page{size:${pageWidthMm} ${pageHeightMm};margin:0}`,
    'html,body{margin:0;padding:0}',
    `.label{box-sizing:border-box;width:100%;height:${pageHeightMm};max-height:100vh;padding:1mm;display:flex;`,
    'align-items:center;justify-content:center;overflow:hidden}',
    '.label+.label{break-before:page;page-break-before:always}',
    '.label img{max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain;image-rendering:auto}',
  ].join('')
  return `<!doctype html><html><head><meta charset="utf-8"><title>Печать WB</title><style>${printCss}</style></head><body>${pages}<script>Promise.all(Array.from(document.images).map(function(img){return img.complete?Promise.resolve():new Promise(function(resolve){img.onload=resolve;img.onerror=resolve})})).then(function(){window.focus();window.print()})</script></body></html>`
}
