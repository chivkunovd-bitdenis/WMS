import type { ScanContext } from './sortingScan'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'

// WMS-650 · «назад» на экране раскладки.
//
// История — только подтверждённые сервером действия (R13). Каждый шаг помнит
// operation_id действия (по нему сервер найдёт свои квитанции и отменит его,
// решение Д2), что написать оператору и куда вернуть экран: открытые ячейку и
// тару и строку, которую подсветить. История живёт в sessionStorage вкладки по
// ключу «документ + сотрудник» (Д1): переживает обновление страницы, пустая в
// другом документе, у другого сотрудника и после закрытия вкладки.

export type UndoEntry = {
  /** operation_id отменяемого действия (запроса place или scan). */
  operationId: string
  /** Что отменится: «Короб КР-000482 → ячейку А 1.1». */
  label: string
  /** Кого оно переместило — для причины отказа. */
  subject: string
  /** Что было открыто до действия. */
  before: ScanContext
  /** Строка, которую подсветить после отмены (та, что вернулась). */
  focus: string | null
  /** Идентификатор самой отмены: повтор после сбоя идёт с ним же (R13). */
  undoOperationId?: string
}

export function readUndoHistory(key: string | undefined): UndoEntry[] {
  if (!key) return []
  try {
    const raw = sessionStorage.getItem(key)
    const parsed = raw ? JSON.parse(raw) as unknown : []
    return Array.isArray(parsed) ? parsed as UndoEntry[] : []
  } catch {
    return []
  }
}

export function writeUndoHistory(key: string | undefined, entries: UndoEntry[]) {
  if (!key) return
  try {
    if (entries.length) sessionStorage.setItem(key, JSON.stringify(entries))
    else sessionStorage.removeItem(key)
  } catch { /* История — удобство вкладки; запись на сервере от неё не зависит. */ }
}

/** Сервер ответил отказом по существу: шаг снимается с вершины истории (Д4). */
export class RejectedUndo extends Error {
  detail: string | null
  constructor(detail: string | null, message: string) {
    super(message)
    this.detail = detail
  }
}

/** Почему отменить нельзя — по-русски, с названием того, что двигали. */
export function undoRefusalText(entry: UndoEntry, detail: string | null, message: string): string {
  if (detail === 'undo_document_posted') {
    return 'Приёмка уже оприходована этим действием — отменить нельзя; переставьте тару сканом в нужную ячейку'
  }
  if (detail === 'undo_target_moved') {
    return `${entry.subject} уже ${movedWord(entry.subject)} после этого действия — отменить нельзя`
  }
  if (detail === 'undo_target_not_found') {
    return `${entry.label}: сервер не нашёл это действие — отменить нельзя`
  }
  return `${entry.label}: ${message.replace(/\.$/, '')} — отменить нельзя`
}

function movedWord(subject: string): string {
  if (subject.startsWith('Палета')) return 'перемещена'
  if (subject.startsWith('Грузоместо')) return 'перемещено'
  return 'перемещён'
}

// Отказы ручек раскладки — по-русски (R16). Общий словарь приложения знает не
// все коды раскладки, а сырой код оператору ничего не говорит.
const PLACE_DETAIL_RU: Record<string, string> = {
  cell_not_found: 'Ячейка не найдена — возможно, её удалили. Обновите документ.',
  object_not_found: 'Не найдено в этом документе. Обновите документ.',
  destination_not_found: 'Место назначения не найдено в этом документе.',
  destination_conflict: 'Выберите одно место: ячейку или тару.',
  destination_required: 'Выберите место.',
  invalid_container_destination: 'Сюда эту тару поставить нельзя.',
  container_cycle: 'Нельзя положить тару внутрь самой себя.',
  nothing_to_move: 'Уже стоит в этом месте — перемещать нечего.',
  insufficient_stock: 'Столько штук здесь нет. Обновите документ.',
  operation_conflict: 'Этот запрос уже выполнен с другими данными. Обновите документ.',
  address_storage_disabled: 'Адресное хранение выключено.',
  not_distributable: 'Документ не в статусе сортировки.',
  quantity_must_be_positive: 'Укажите количество больше нуля.',
}

/** Код отказа и текст для оператора. */
export async function readSortingFailure(response: Response): Promise<{ detail: string | null; message: string }> {
  let detail: string | null = null
  try {
    const body = await response.clone().json() as { detail?: unknown }
    if (typeof body.detail === 'string') detail = body.detail
  } catch { /* Не JSON — текст разберёт общий читатель ошибок. */ }
  const message = (detail && PLACE_DETAIL_RU[detail]) ?? await readApiErrorMessage(response)
  // Сырой код вроде «cell_not_found» — не текст для склада.
  return { detail, message: /^[a-z0-9_]+$/.test(message) ? 'Сервер отказал в действии.' : message }
}
