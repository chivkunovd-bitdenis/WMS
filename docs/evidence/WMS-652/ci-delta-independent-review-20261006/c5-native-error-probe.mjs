import { writeFile } from 'node:fs/promises';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ executablePath: process.env.WMS672_CHROMIUM,
  headless: true, args: ['--mute-audio'] });
try {
  const context = await browser.newContext();
  await context.route('**/*', route => new URL(route.request().url()).origin === process.env.WMS672_TEST_URL
    ? route.continue() : route.abort());
  const page = await context.newPage();
  await page.goto(`${process.env.WMS672_TEST_URL}/tests-e2e/wms672-harness.html`);
  const result = await page.evaluate(async () => {
    const { printBarcodeLabels } = await import('/src/utils/printBarcodeLabel.ts');
    let transfers = 0;
    const append = document.body.appendChild.bind(document.body);
    document.body.appendChild = function (node) {
      const result = append(node);
      if (node.tagName === 'IFRAME') node.addEventListener('load', () => {
        node.contentWindow.print = () => { throw new Error('diagnostic printer transfer prohibited'); };
      });
      return result;
    };
    try {
      await printBarcodeLabels([{ title: 'Diagnostic known bad PNG', barcode: 'DIAGNOSTIC',
        barcodeDataUrl: 'data:image/png;base64,AAAA' }], { beforeTransfer() { transfers++; } });
      return { unexpectedSuccess: true, transfers };
    } catch (error) {
      return { unexpectedSuccess: false, name: error?.name, message: error?.message,
        parentInstanceofError: error instanceof Error,
        exactScreenCatchResult: error instanceof Error ? error.message : 'Не удалось напечатать этикетки.',
        transfers, remainingFrames: document.querySelectorAll('iframe').length };
    }
  });
  await writeFile(process.env.C5_NATIVE_OUTPUT, JSON.stringify({ browser: browser.version(),
    platform: process.platform, result }, null, 2));
  console.log(result);
  await context.close();
} finally { await browser.close(); }
