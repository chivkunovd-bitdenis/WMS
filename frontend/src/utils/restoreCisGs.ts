/**
 * I3 (docs/BACKLOG-2026-08-19-CHAT-RU.md, раздел I3): сканер честного знака
 * отдаёт код с невидимым байтом-разделителем GS (0x1D, group separator) перед
 * блоками 91 (проверочный код) и 92 (криптоподпись). Браузерное текстовое
 * поле этот байт не пропускает вообще — не подменяет видимым символом (для
 * такого случая есть отдельная защита на сервере, восстановление по
 * подстановке), а просто вырезает его без следа. Код склеивается, и Wildberries
 * заворачивает его с ошибкой sgtinNoGS («КИЗ передан на проверку без скрытых
 * разделителей»).
 *
 * Структура полного КИЗ Честного знака одинакова что на клиенте, что на
 * сервере (см. backend/app/services/fbs_kiz_service.py,
 * _restore_missing_gs_by_structure — этот файл сознательно зеркалит тот же
 * алгоритм на клиенте, чтобы оператор видел результат сразу, до сетевого
 * запроса; сервер остаётся последним рубежом для любого другого входа —
 * мобильного терминала, curl, чего угодно):
 *
 *   01<GTIN, 14 цифр>21<серийный номер, переменная длина>
 *   91<проверочный код, ровно 4 символа>
 *   92<криптоподпись: 44 символа для одежды, 88 — для обуви>
 *
 * Искать подстроки "91"/"92" по всей строке нельзя — они регулярно попадают в
 * серийный номер (пример в тестах: серийник "A91XB92YC7z" выглядит как начало
 * блока 91, а это просто символы серии). Поэтому разбор идёт не поиском, а
 * фиксированными смещениями от конца строки: пробуем оба известных варианта
 * длины подписи (44 и 88) и засчитываем только тот, для которого на нужном
 * месте от конца буквально стоят маркеры "91" и "92". Длины 44 и 88
 * отличаются на 44 символа, а серийный номер по GS1 не длиннее 20 символов —
 * значит, оба варианта одновременно совпасть не могут (предполагаемые ими
 * серийники отличались бы на те же 44 символа и не поместились бы вместе в
 * окно длиной 20). Если совпал ровно один вариант — структура однозначна.
 */

const GS = '\x1d'
const CIS_PREFIX_LENGTH = 18 // "01" + 14-значный GTIN + "21"
const CIS_SERIAL_MAX_LENGTH = 20 // максимум для AI 21 по GS1 General Specifications
const AI91_VALUE_LENGTH = 4
const SIGNATURE_LENGTHS = [44, 88] as const // одежда, обувь

export type RestoreCisGsResult = {
  /** Значение с восстановленными разделителями (или исходное, если не требовалось). */
  value: string
  /** true — разделители физически отсутствовали и были вставлены по структуре. */
  restored: boolean
  /**
   * true — код похож на длинный КИЗ без разделителей, но ни длина одежды, ни
   * длина обуви не подошли: угадывать нельзя, отправлять такой код в WB
   * нельзя. `value` в этом случае возвращается БЕЗ ИЗМЕНЕНИЙ.
   */
  unrestorable: boolean
}

function cisPrefixOk(value: string): boolean {
  return (
    value.length >= CIS_PREFIX_LENGTH &&
    value.startsWith('01') &&
    /^\d{14}$/.test(value.slice(2, 16)) &&
    value.slice(16, 18) === '21'
  )
}

/**
 * Восстанавливает GS-разделители, вырезанные целиком, по структуре КИЗ.
 * Ничего не делает (restored=false, unrestorable=false), если:
 *  - строка вообще не похожа на КИЗ (нет префикса 01<GTIN>21) — это не наша
 *    забота, дальше отработает обычная проверка «это не похоже на Честный знак»;
 *  - разделитель уже на месте;
 *  - это короткий КИЗ без криптохвоста (валидный формат WB, см.
 *    verify-product-identifiers.md «Короткий и длинный КИЗ») — разделять
 *    нечего, разделитель перед последним полем GS1 не ставится.
 */
export function restoreCisGs(raw: string): RestoreCisGsResult {
  const value = raw
  if (!cisPrefixOk(value)) {
    return { value, restored: false, unrestorable: false }
  }

  const tail = value.slice(CIS_PREFIX_LENGTH)
  if (tail.includes(GS)) {
    return { value, restored: false, unrestorable: false }
  }
  if (tail.length <= CIS_SERIAL_MAX_LENGTH) {
    return { value, restored: false, unrestorable: false }
  }

  const candidates: Array<{ serial: string; verification: string; signature: string }> = []
  for (const signatureLength of SIGNATURE_LENGTHS) {
    const suffixLength = 2 + AI91_VALUE_LENGTH + 2 + signatureLength
    if (tail.length <= suffixLength) continue
    const serial = tail.slice(0, tail.length - suffixLength)
    const block = tail.slice(tail.length - suffixLength)
    if (serial.length < 1 || serial.length > CIS_SERIAL_MAX_LENGTH) continue
    if (block.slice(0, 2) !== '91' || block.slice(6, 8) !== '92') continue
    candidates.push({ serial, verification: block.slice(2, 6), signature: block.slice(8) })
  }

  if (candidates.length !== 1) {
    // Ноль совпадений — длина хвоста не подошла ни под один известный формат
    // подписи. Два совпадения математически не должны случиться (см. комментарий
    // в начале файла), но если всё же случились — тоже не гадаем.
    return { value, restored: false, unrestorable: true }
  }

  const { serial, verification, signature } = candidates[0]
  const restored = `${value.slice(0, CIS_PREFIX_LENGTH)}${serial}${GS}91${verification}${GS}92${signature}`
  return { value: restored, restored: true, unrestorable: false }
}
