import { escapeLabelHtml } from '../../../utils/productLabelText'
import { humanMoment, type ApiPrintSheet } from './inventoryCountApi'

/**
 * Печатный лист инвентаризации (WMS-497) — лист А4 для ручного пересчёта.
 *
 * Владелец строго ограничил состав: только шапка документа (номер, кто создал,
 * когда, отбор) и таблица «ШК — Артикул — Название — Всего — В резерве —
 * Факт» с зеброй. Ни комментария документа, ни статуса, ни подсказок, ни
 * итогов, ни строки подписи, ни номеров страниц на листе нет — это лишнее,
 * которое владелец прямо запретил (docs/requirements/WMS-497.md, R2).
 *
 * Печатаем тем же способом, что и опись тары (`printContainerContents.ts`) и
 * лист приёмки (`utils/printInboundReceivingSheet.ts`): скрытый iframe и
 * `@page { margin: 0 }` — без полей браузеру некуда вписать свою шапку/подвал
 * (дата, адрес страницы, заголовок вкладки).
 */

/** Строки отбора документа — только для заданных при создании параметров (R4). */
function filterLines(filters: ApiPrintSheet['filters']): string[] {
  if (filters.object) return ['По объекту']
  const lines: string[] = []
  if (filters.warehouse_name) lines.push(`Склад: ${filters.warehouse_name}`)
  if (filters.seller_name) lines.push(`Селлер: ${filters.seller_name}`)
  if (filters.category) lines.push(`Категория: ${filters.category}`)
  if (filters.product_articles.length > 0) {
    lines.push(`Товары: ${filters.product_articles.join(', ')}`)
  }
  return lines
}

function rowHtml(row: ApiPrintSheet['rows'][number], index: number): string {
  return `<tr class="${index % 2 === 1 ? 'odd' : 'even'}" data-testid="inv-sheet-row">
      <td class="barcode">${escapeLabelHtml(row.barcode || '—')}</td>
      <td class="article">${escapeLabelHtml(row.article || '—')}</td>
      <td class="name">${escapeLabelHtml(row.name)}</td>
      <td class="num total">${row.total}</td>
      <td class="num reserved">${row.reserved}</td>
      <td class="num fact" data-testid="inv-sheet-fact"></td>
    </tr>`
}

/** HTML печатного листа — вынесен из printInventorySheet для тестов (vitest). */
export function buildInventorySheetHtml(sheet: ApiPrintSheet): string {
  const headLines = [
    `Инвентаризация ${sheet.number}`,
    `Создал: ${sheet.created_by}`,
    humanMoment(sheet.created_at),
    ...filterLines(sheet.filters),
  ]
  const head = headLines
    .map((line, index) => `<div class="doc-line${index === 0 ? ' doc-title' : ''}">${escapeLabelHtml(line)}</div>`)
    .join('')

  return `<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <title>Лист инвентаризации ${escapeLabelHtml(sheet.number)}</title>
    <style>
      /* Поля НУЛЕВЫЕ, отступ даёт сама страница — иначе браузер печатает в
         оставленное поле свою шапку (дату слева, заголовок вкладки справа). */
      @page { size: A4 portrait; margin: 0; }
      * { box-sizing: border-box; }
      html, body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      body {
        margin: 0;
        padding: 10mm 8mm;
        color: #14110F;
        background: #FFFFFF;
        font-family: Arial, Helvetica, system-ui, sans-serif;
        font-variant-numeric: tabular-nums;
      }
      .head { margin-bottom: 5mm; }
      .doc-line { font-size: 10pt; line-height: 1.4; }
      .doc-title { font-size: 13pt; font-weight: 700; margin-bottom: 1mm; }
      table { width: 100%; border-collapse: collapse; table-layout: fixed; }
      /* Длинный документ рвёт на страницы — шапка колонок обязана повториться,
         иначе на втором листе стоят голые цифры без заголовков (R11). Шапка
         документа (.head) выше таблицы не повторяется — она печатается один раз. */
      thead { display: table-header-group; }
      thead th {
        text-align: left;
        font-size: 9pt;
        font-weight: 700;
        padding: 2mm 2mm;
        border-bottom: 0.6mm solid #14110F;
        white-space: nowrap;
      }
      thead th.num { text-align: right; }
      tbody tr { break-inside: avoid; page-break-inside: avoid; }
      tbody tr.odd { background: #F1EEEB; }
      tbody tr.even { background: #FFFFFF; }
      tbody td {
        padding: 2.4mm 2mm;
        font-size: 9pt;
        vertical-align: top;
        word-break: break-word;
        overflow-wrap: anywhere;
      }
      td.barcode {
        font-family: "Courier New", ui-monospace, monospace;
        white-space: nowrap;
        overflow-wrap: normal;
        word-break: keep-all;
      }
      td.num { text-align: right; }
    </style>
  </head>
  <body>
    <div class="head">${head}</div>
    <table>
      <!-- table-layout: fixed берёт ширины колонок из ПЕРВОЙ строки таблицы —
           это строка thead, а не тела. Ширина на td тут не сработала бы: до
           20-значный штрихкод наезжал на «Артикул» (нашли в PDF-проверке),
           пока ширины не переехали в colgroup — он один задаёт ширину колонки
           независимо от того, что и где внутри неё написано. -->
      <colgroup>
        <col style="width: 52mm" />
        <col style="width: 26mm" />
        <col />
        <col style="width: 20mm" />
        <col style="width: 20mm" />
        <col style="width: 26mm" />
      </colgroup>
      <thead>
        <tr>
          <th>ШК</th>
          <th>Артикул</th>
          <th>Название</th>
          <th class="num">Всего</th>
          <th class="num">В резерве</th>
          <th class="num">Факт</th>
        </tr>
      </thead>
      <tbody>
        ${sheet.rows.map(rowHtml).join('\n')}
      </tbody>
    </table>
  </body>
</html>`
}

/**
 * Сколько ждать загрузки скрытого iframe, прежде чем считать попытку печати
 * неудавшейся. Содержимое инлайновое (srcdoc, без сетевого запроса) — в любом
 * настоящем браузере `onload` наступает почти сразу; это только защита от
 * оборванной загрузки (WMS-497, ревью Astra №2, F2), а не обычный сценарий.
 */
const LOAD_TIMEOUT_MS = 5000

/**
 * Печать листа инвентаризации (A4, браузер). На листе нет фото, поэтому
 * ничего не ждём для сборки — но саму печать (`frameWindow.print()`) браузер
 * запускает не сразу: только после загрузки iframe и ещё через 100 мс.
 *
 * Возвращаем Promise, который разрешается не раньше фактической попытки
 * печати (вызов `print()`, каким бы ни был исход) — до этого момента
 * документ ещё «готовится». Страница держит на этом промисе свой флаг
 * повторного нажатия (WMS-497, ревью Astra №1, F1): раньше флаг снимался
 * сразу после синхронного возврата этой функции, то есть до того, как
 * `print()` вообще был вызван, и второе нажатие в этом промежутке уходило
 * вторым запросом на сервер и открывало второе окно печати.
 *
 * Единственным путём до F2 был `iframe.onload`: если загрузка обрывалась
 * (или браузер по какой-то причине не отдавал это событие) раньше него,
 * Promise не завершался никогда — кнопка оставалась заблокированной до
 * перезагрузки страницы. `LOAD_TIMEOUT_MS` — ограниченное ожидание с тем же
 * исходом, что и явный отказ: обработчики снимаются, iframe убирается,
 * Promise разрешается. Обработчики снимаются именно поэтому — если загрузка
 * всё же случится позже (сама по себе или после того, как истёк наш лимит),
 * она не должна напечатать устаревший лист поверх уже новой попытки.
 */
export function printInventorySheet(sheet: ApiPrintSheet): Promise<void> {
  const html = buildInventorySheetHtml(sheet)
  if (typeof window !== 'undefined' && window.__WMS_CAPTURE_PRINT_HTML__) {
    window.__WMS_LAST_PRINT_HTML__ = html
  }

  const iframe = document.createElement('iframe')
  iframe.setAttribute('aria-hidden', 'true')
  iframe.style.position = 'fixed'
  iframe.style.right = '0'
  iframe.style.bottom = '0'
  iframe.style.width = '0'
  iframe.style.height = '0'
  iframe.style.border = '0'
  document.body.appendChild(iframe)

  const cleanup = () => {
    try {
      document.body.removeChild(iframe)
    } catch {
      // уже убран
    }
  }

  return new Promise<void>((resolve) => {
    let settled = false
    const finish = () => {
      if (settled) return
      settled = true
      resolve()
    }

    let loadTimeoutId: ReturnType<typeof setTimeout> | null = setTimeout(() => {
      loadTimeoutId = null
      // Загрузка не случилась вовремя — печатать нечего. Снимаем обработчики
      // (поздний onload/error после этого — no-op) и убираем iframe: он не
      // должен напечатать это старьё поверх следующей попытки оператора.
      iframe.onload = null
      iframe.onerror = null
      cleanup()
      finish()
    }, LOAD_TIMEOUT_MS)

    const printNow = () => {
      // Уже отказали по таймауту (или другим путём) — поздний onload игнорируем.
      if (settled) return
      if (loadTimeoutId !== null) {
        clearTimeout(loadTimeoutId)
        loadTimeoutId = null
      }
      const frameWindow = iframe.contentWindow
      if (!frameWindow) {
        cleanup()
        finish()
        return
      }
      try {
        frameWindow.focus()
      } catch {
        // фокус не обязателен
      }
      setTimeout(() => {
        frameWindow.addEventListener('afterprint', cleanup, { once: true })
        try {
          if (window.__WMS_CAPTURE_PRINT_HTML__) {
            window.__WMS_PRINT_JOB_COUNT__ = (window.__WMS_PRINT_JOB_COUNT__ ?? 0) + 1
          }
          frameWindow.print()
        } catch {
          cleanup()
        } finally {
          // Попытка печати сделана (открылось окно печати или нет — не
          // важно для гварда): страница может снова принимать нажатие —
          // намеренная повторная печать того же документа не блокируется.
          finish()
        }
      }, 100)
    }

    iframe.onload = printNow
    // Явный сигнал отказа загрузки (если браузер его пришлёт) — тот же
    // отказ, что и по таймауту, только раньше него.
    iframe.onerror = () => {
      if (loadTimeoutId !== null) {
        clearTimeout(loadTimeoutId)
        loadTimeoutId = null
      }
      iframe.onload = null
      iframe.onerror = null
      cleanup()
      finish()
    }
    iframe.srcdoc = html
  })
}
