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

  // Элемент, вылезший за пределы своей карточки.
  document.querySelectorAll('.MuiPaper-root').forEach((paper) => {
    const box = paper.getBoundingClientRect();
    paper.querySelectorAll('.MuiButton-root, .MuiChip-root').forEach((el) => {
      const inner = el.getBoundingClientRect();
      if (inner.right > box.right + 1 || inner.left < box.left - 1) {
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
