// WMS-433, R6: контекст экрана, который прикладывается к каждому сообщению
// помощнику без действий пользователя. Берётся из того, что человек реально
// видит: адрес, название экрана и весь видимый текст области содержимого.

export type AssistantScreenContext = {
  screen_path: string
  screen_title: string
  screen_text: string
}

// Пределы совпадают с серверными (backend/app/models/assistant_message.py):
// сервер и сам обрежет текст до 20 000 символов, здесь режем заранее, чтобы
// не гонять по сети лишнее. По длине отправка никогда не отклоняется.
export const ASSISTANT_SCREEN_TEXT_MAX_CHARS = 20_000
export const ASSISTANT_SCREEN_TITLE_MAX_CHARS = 256
export const ASSISTANT_SCREEN_PATH_MAX_CHARS = 512

const CONTENT_SELECTOR = '[data-testid="app-content"]'
const SIDEBAR_ACTIVE_LINK_SELECTOR = '[data-testid="app-sidebar"] a.active'
// Открытые диалоги MUI (документ приёмки открывается полноэкранным диалогом
// поверх раздела, ошибки внутри него пользователь видит именно там).
const DIALOG_PAPER_SELECTOR = '.MuiDialog-root .MuiDialog-paper'
const FULLSCREEN_DIALOG_CLASS = 'MuiDialog-paperFullScreen'
const HEADING_SELECTOR = 'h1, h2, h3, h4, h5'

function visibleText(el: Element | null | undefined): string {
  if (!(el instanceof HTMLElement)) {
    return ''
  }
  // innerText (в отличие от textContent) отдаёт только отрисованный текст:
  // скрытые вкладки и display:none не попадают.
  return el.innerText.replace(/\n{3,}/g, '\n\n').trim()
}

function firstHeading(root: Element | null | undefined): string {
  if (!root) {
    return ''
  }
  const heading = root.querySelector(HEADING_SELECTOR)
  return heading instanceof HTMLElement ? heading.innerText.replace(/\s+/g, ' ').trim() : ''
}

function collapseSpaces(value: string): string {
  return value.replace(/\s+/g, ' ').trim()
}

export function collectAssistantScreenContext(doc: Document = document): AssistantScreenContext {
  const { pathname, search } = doc.location
  const screenPath = `${pathname}${search}`.slice(0, ASSISTANT_SCREEN_PATH_MAX_CHARS)

  const content = doc.querySelector(CONTENT_SELECTOR)
  // Диалоги: верхний — последний в DOM, поэтому разворачиваем порядок, чтобы
  // самое видимое шло первым и не отрезалось при обрезке. Полноэкранный
  // документ закрывает всё под собой — и раздел, и другие документы ниже, —
  // поэтому сбор останавливается на первом полноэкранном сверху.
  const dialogs = Array.from(doc.querySelectorAll(DIALOG_PAPER_SELECTOR)).reverse()
  const regions: Array<Element | null> = []
  let topFullscreen: Element | null = null
  for (const dialog of dialogs) {
    regions.push(dialog)
    if (dialog.classList.contains(FULLSCREEN_DIALOG_CLASS)) {
      topFullscreen = dialog
      break
    }
  }
  if (!topFullscreen) {
    regions.push(content)
  }
  const screenText = regions
    .map(visibleText)
    .filter(Boolean)
    .join('\n\n')
    .slice(0, ASSISTANT_SCREEN_TEXT_MAX_CHARS)

  // Название экрана: пункт меню + заголовок экрана. «Экран» — полноэкранный
  // документ, если он открыт, иначе раздел; малые диалоги (подтверждения,
  // формы) экраном не считаются — их текст уже приложен выше. Заголовок
  // документа обычно уже содержит раздел («Инвентаризация ИНВ-000124»), тогда
  // берём его как есть; иначе «Раздел — Заголовок» («Приёмка на FF — №000001»).
  const section = collapseSpaces(doc.querySelector(SIDEBAR_ACTIVE_LINK_SELECTOR)?.textContent ?? '')
  const heading = firstHeading(topFullscreen ?? content)
  let screenTitle: string
  if (!heading) {
    screenTitle = section || pathname
  } else if (!section || heading.toLowerCase().startsWith(section.toLowerCase())) {
    screenTitle = heading
  } else {
    screenTitle = `${section} — ${heading}`
  }

  return {
    screen_path: screenPath,
    screen_title: screenTitle.slice(0, ASSISTANT_SCREEN_TITLE_MAX_CHARS),
    screen_text: screenText,
  }
}
