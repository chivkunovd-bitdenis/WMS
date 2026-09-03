/**
 * Очередь сканов-находок.
 *
 * Две беды, которые она закрывает, обе про потерянный или задвоенный товар.
 *
 * Первая: склад работает по вайфаю, который рвётся. Ответ не доехал, экран
 * показал ошибку — а запись на сервере уже прошла. Кладовщик сканирует ещё раз,
 * и это уже ДРУГОЙ скан: серверная защита от повтора его не узнаёт, на остатке
 * оказывается двойка. Поэтому повторяем мы сами и тем же идентификатором, а
 * человеку про обрыв вообще не сообщаем: его дело — сканировать.
 *
 * Вторая: два быстрых скана уходили независимо, ответы возвращались вперемешку,
 * и поздний ответ со старым состоянием документа стирал с экрана строку,
 * которую добавил ранний. Оператор видел, что находки нет, и сканировал её
 * заново — снова двойка. Поэтому очередь строго одна и строго по одному.
 */

export type FoundPlace = {
  barcodes: string[]
  cellId: string | null
  containerKind: 'pallet' | 'box' | 'cargo_place' | null
  containerId: string | null
  scanId: string
  /** Документ, в котором сделан скан. Без него недоставленная находка при
   *  повторе уходила в тот пересчёт, который открыт сейчас: оператор возвращался
   *  в список, открывал другой черновик — и чужая находка попадала туда. */
  countId: string
}

/**
 * Скан, который сейчас доставить некуда: он сделан в другом документе, а тот
 * закрыт или не открыт. Повторять бессмысленно — условие не рассосётся само,
 * и через четыре попытки очередь просто выбрасывала находку. Такой скан
 * откладывается и возвращается в очередь, когда оператор снова откроет свой
 * документ.
 */
export class FoundPlaceDeferredError extends Error {}

export type FoundQueueDeps<T> = {
  /** Отправка одного скана. Бросает при сетевом обрыве и при отказе сервера. */
  send: (place: FoundPlace) => Promise<T>
  /** Успешный ответ — применить к экрану. */
  onApplied: (result: T, place: FoundPlace) => void
  /** Отказ сервера: повторять бессмысленно, надо показать человеку. */
  onRejected: (error: unknown, place: FoundPlace) => void
  /** Сколько сканов ещё не доставлено — экран показывает это оператору. */
  onPendingChange: (pending: number) => void
  /** Сетевой обрыв (в отличие от отказа сервера) — такой скан повторяем. */
  isRetryable: (error: unknown) => boolean
  /** Отложенный скан вернулся в очередь: экран снова показывает недоставленное. */
  onDeferred?: (place: FoundPlace) => void
  /** Пауза между попытками; вынесена ради тестов. */
  delay?: (ms: number) => Promise<void>
}

const RETRY_DELAYS_MS = [400, 1200, 3000, 6000]

export function createFoundQueue<T>(deps: FoundQueueDeps<T>) {
  const wait = deps.delay ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)))
  const queue: FoundPlace[] = []
  // Сканы, сделанные в документе, который сейчас не открыт. Они не потеряны и
  // не мешают работать в другом документе — ждут возвращения в свой.
  const parked: FoundPlace[] = []
  let running = false

  function publishPending(): void {
    deps.onPendingChange(queue.length + (running ? 1 : 0))
  }

  async function drain(): Promise<void> {
    if (running) return
    running = true
    while (queue.length > 0) {
      const place = queue[0]
      publishPending()
      let attempt = 0
      for (;;) {
        try {
          const result = await deps.send(place)
          queue.shift()
          deps.onApplied(result, place)
          break
        } catch (error) {
          if (error instanceof FoundPlaceDeferredError) {
            // Не отказ и не обрыв: доставить некуда прямо сейчас. Откладываем,
            // не тратя одиннадцать секунд повторов и не выбрасывая находку.
            queue.shift()
            parked.push(place)
            deps.onDeferred?.(place)
            break
          }
          if (!deps.isRetryable(error) || attempt >= RETRY_DELAYS_MS.length) {
            queue.shift()
            deps.onRejected(error, place)
            break
          }
          await wait(RETRY_DELAYS_MS[attempt])
          attempt += 1
        }
      }
    }
    running = false
    publishPending()
  }

  return {
    /** Поставить скан в очередь. Возвращается сразу: сканер не должен ждать сеть. */
    push(place: FoundPlace): void {
      queue.push(place)
      publishPending()
      void drain()
    },
    /** Есть ли недоставленные сканы: пока есть, документ проводить нельзя. */
    pending(): number {
      return queue.length + (running ? 1 : 0)
    },
    /**
     * Оператор вернулся в документ — отложенные сканы этого документа снова в
     * работе. Пока они не доставлены, документ проводить нельзя, и находка не
     * пропадает молча, как было раньше.
     */
    resumeFor(countId: string): void {
      for (let i = parked.length - 1; i >= 0; i -= 1) {
        if (parked[i].countId === countId) {
          queue.push(parked.splice(i, 1)[0])
        }
      }
      publishPending()
      void drain()
    },
    /** Сколько сканов ждёт возвращения в свой документ — для тестов и отладки. */
    parked(): number {
      return parked.length
    },
  }
}
