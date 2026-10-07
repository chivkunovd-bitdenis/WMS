// A quick close/reopen must read after the save started by unmount cleanup.
// Only live HTTP promises are retained; no selection or credentials are stored.
const pending = new Map<string, Set<Promise<unknown>>>()
const failed = new Map<string, Error>()

export function trackPickSave(ids: string[], save: Promise<unknown>, keepFailure: () => boolean = () => true): void {
  for (const id of ids) {
    failed.delete(id)
    const saves = pending.get(id) ?? new Set<Promise<unknown>>()
    saves.add(save)
    pending.set(id, saves)
  }
  const release = () => {
    for (const id of ids) {
      const saves = pending.get(id)
      saves?.delete(save)
      if (saves?.size === 0) pending.delete(id)
    }
  }
  void save.then(release, (cause: unknown) => {
    const error = cause instanceof Error ? cause : new Error('Не удалось сохранить подбор. Проверьте количество после обновления.')
    // An open screen already shows its readback/error; a closed screen needs
    // to carry that failure to the next opening.
    if (keepFailure()) for (const id of ids) failed.set(id, error)
    release()
  })
}

export async function waitForPickSaves(ids: string[]): Promise<void> {
  const saves = ids.flatMap((id) => [...(pending.get(id) ?? [])])
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    await Promise.race([
      Promise.allSettled(saves),
      new Promise<never>((_resolve, reject) => {
        timer = setTimeout(() => reject(new Error('Сохранение подбора ещё не подтверждено. Обновите документ и проверьте количество.')), 10000)
      }),
    ])
    for (const id of ids) {
      const error = failed.get(id)
      if (error) {
        failed.delete(id)
        throw error
      }
    }
  } finally {
    if (timer) clearTimeout(timer)
  }
}
