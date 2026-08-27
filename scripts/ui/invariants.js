// Инварианты исполнения WMS: то, что нельзя проверить чтением кода.
//
// Канон описывает решения, а ломается исполнение: колонки наползают, текст
// обрезается, строки красятся, шапка уезжает. Ни одно правило в файле этого
// не остановит — поэтому геометрия меряется прямо в браузере.
//
// Главное свойство: эталон не нужен. Скрипт работает на экране, которого вчера
// не существовало, — значит годится и для Ozon, который рисуется с нуля.
//
// Запуск: вставить содержимое в mcp__Claude_Browser__javascript_tool или в page.evaluate.
(() => {
  const violations = [];
  const add = (rule, what, sample) => violations.push({ rule, what, sample });
  const text = (el) => (el.innerText || '').trim().slice(0, 60);
  const hasHint = (el) =>
    Boolean(el.closest('[title]') || el.closest('[aria-label]') || el.getAttribute('aria-label'));

  // R-01: страница не ездит вбок. Переполняться имеет право только контейнер таблицы.
  if (document.documentElement.scrollWidth > window.innerWidth + 1) {
    add('R-01', 'страница переполнена по горизонтали', `${document.documentElement.scrollWidth}px > ${window.innerWidth}px`);
  }

  // Обрезанный текст без подсказки: оператор не может прочитать значение целиком.
  document.querySelectorAll('td, th, .MuiChip-label, .MuiButton-root').forEach((el) => {
    if (el.scrollWidth > el.clientWidth + 1 && !hasHint(el)) {
      add('R-02', 'текст обрезан без подсказки', text(el));
    }
  });

  // Наползание ячеек считаем внутри каждой таблицы отдельно.
  document.querySelectorAll('table').forEach((table) => {
    const row = table.querySelector('tbody tr');
    if (!row) return;
    const boxes = [...row.children].map((cell) => cell.getBoundingClientRect());
    for (let i = 1; i < boxes.length; i += 1) {
      if (boxes[i].left < boxes[i - 1].right - 1) {
        add('R-09', 'колонки наползают', `столбец ${i + 1} в таблице`);
      }
    }
  });

  // R-36: перенос в шапке рвёт связь колонки с данными, перенос в кнопке ломает ряд.
  // Считаем прямоугольники текстового узла: сравнение высоты с line-height врёт,
  // потому что в высоту входят отступы, и порог плавает от темы к теме.
  const twoLine = (el) => {
    const node = [...el.childNodes].find((n) => n.nodeType === 3 && n.textContent.trim());
    if (!node) return false;
    const range = document.createRange();
    range.selectNodeContents(node);
    return range.getClientRects().length > 1;
  };
  document.querySelectorAll('th').forEach((el) => twoLine(el) && add('R-36', 'заголовок колонки в две строки', text(el)));
  document.querySelectorAll('.MuiButton-root').forEach((el) => twoLine(el) && add('R-36', 'подпись кнопки в две строки', text(el)));

  // R-11: цвет строки означает ровно одно. Любой второй оттенок — светофор.
  const tints = new Map();
  document.querySelectorAll('tbody tr').forEach((row) => {
    const bg = getComputedStyle(row).backgroundColor;
    if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') {
      tints.set(bg, (tints.get(bg) || 0) + 1);
    }
  });
  if (tints.size > 1) {
    add('R-11', 'строки окрашены больше чем одним цветом', [...tints.keys()].join(' · '));
  }

  // R-17: иконка без подсказки — тык наугад, а часть тыков печатает или списывает.
  document.querySelectorAll('.MuiIconButton-root').forEach((el) => {
    if (!text(el) && !hasHint(el)) add('R-17', 'иконка без подсказки', el.outerHTML.slice(0, 70));
  });

  // R-32: в одном ряду кнопки одной высоты, иначе панель читается лесенкой.
  document.querySelectorAll('.MuiStack-root').forEach((stack) => {
    const heights = [...stack.querySelectorAll(':scope > .MuiButton-root')].map((el) => Math.round(el.getBoundingClientRect().height));
    if (new Set(heights).size > 1) add('R-32', 'кнопки в ряду разной высоты', heights.join('/'));
  });

  const isReachableDataTableOverflow = (el, paper) => {
    if (getComputedStyle(el).position === 'fixed') return false;
    const paperBox = paper.getBoundingClientRect();
    const clippingAncestors = [];
    let scrollport = el.parentElement;
    while (scrollport && paper.contains(scrollport)) {
      const style = getComputedStyle(scrollport);
      // An inner clip is a permanent visual boundary: an outer table scrollbar
      // can only make its descendant reachable when that descendant remains
      // visible inside every clipping box at the same scroll endpoint.
      if (style.overflowX === 'hidden' || style.overflowX === 'clip') {
        clippingAncestors.push(scrollport);
      }
      const canScrollHorizontally = style.overflowX === 'auto' || style.overflowX === 'scroll';
      if (canScrollHorizontally) {
        // Only the shared DataTable container may own this exception.  A generic
        // scrollable Paper is not a licence for a button or chip to leave its card.
        if (
          !scrollport.classList.contains('MuiTableContainer-root') ||
          getComputedStyle(scrollport).position === 'fixed' ||
          scrollport.scrollWidth <= scrollport.clientWidth + 1
        ) return false;
        const scrollportBox = scrollport.getBoundingClientRect();
        if (
          scrollportBox.left < paperBox.left - 1 ||
          scrollportBox.right > paperBox.right + 1
        ) return false;
        const visibleInScrollport = (box) =>
          box.right > scrollportBox.left + 1 && box.left < scrollportBox.right - 1;
        const visibleAtEndpoint = () => {
          const targetBox = el.getBoundingClientRect();
          return visibleInScrollport(targetBox) && clippingAncestors.every((clip) => {
            const clipBox = clip.getBoundingClientRect();
            return targetBox.right > clipBox.left + 1 && targetBox.left < clipBox.right - 1;
          });
        };
        const originalScrollLeft = scrollport.scrollLeft;
        scrollport.scrollLeft = 0;
        const visibleAtStart = visibleAtEndpoint();
        scrollport.scrollLeft = scrollport.scrollWidth - scrollport.clientWidth;
        const visibleAtEnd = visibleAtEndpoint();
        scrollport.scrollLeft = originalScrollLeft;
        return visibleAtStart || visibleAtEnd;
      }
      if (scrollport === paper) break;
      scrollport = scrollport.parentElement;
    }
    return false;
  };

  // Элемент, вылезший за пределы своей карточки.
  document.querySelectorAll('.MuiPaper-root').forEach((paper) => {
    const box = paper.getBoundingClientRect();
    paper.querySelectorAll('.MuiButton-root, .MuiChip-root').forEach((el) => {
      const inner = el.getBoundingClientRect();
      const outsidePaper = inner.right > box.right + 1 || inner.left < box.left - 1;
      if (outsidePaper && !isReachableDataTableOverflow(el, paper)) {
        add('R-08', 'элемент вылезает за карточку', text(el));
      }
    });
  });

  return JSON.stringify(
    { ok: violations.length === 0, count: violations.length, violations: violations.slice(0, 40) },
    null,
    1,
  );
})();
