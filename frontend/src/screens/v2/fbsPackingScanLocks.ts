/** Lifetime owner locks distinguish a reopened tab from a cloned active tab.
 * Scope locks cover the whole physical scan and every read/modify/write of its
 * durable pointer. Closing a tab releases its owner lock for exact-key recovery. */
export function createPackingScanLocks(manager: LockManager, session: Storage, createId: () => string = () => crypto.randomUUID()) {
  const OWNER = 'wms:fbs:packing-owner:'
  const SESSION = 'wms:fbs:packing-owner'
  let ownerPromise: Promise<string> | undefined
  const owner = (): Promise<string> => {
    if (ownerPromise) return ownerPromise
    ownerPromise = new Promise<string>((resolve, reject) => {
      const acquire = (candidate: string) => {
        void manager.request(`${OWNER}${candidate}`, { ifAvailable: true }, async (lock) => {
          if (!lock) { acquire(createId()); return }
          session.setItem(SESSION, candidate)
          resolve(candidate)
          await new Promise<void>(() => undefined) // Released by document teardown, including reload/crash.
        }).catch(reject)
      }
      try { acquire(session.getItem(SESSION) || createId()) } catch (cause) { reject(cause) }
    }).catch(() => { throw new Error('Не удалось сохранить принадлежность скана этой вкладке. Проверьте доступ к хранилищу браузера; новый заказ не выбран.') })
    return ownerPromise
  }
  return {
    owner,
    active: async (id: string) => manager.request(`${OWNER}${id}`, { ifAvailable: true }, (lock) => lock === null),
    run: async <T>(scope: string, action: () => Promise<T>): Promise<T> => {
      await owner()
      return manager.request(`wms:fbs:packing-scope:${scope}`, action)
    },
  }
}
let current: ReturnType<typeof createPackingScanLocks> | undefined
export function packingScanLocks() {
  if (!navigator.locks) throw new Error('Браузер не поддерживает безопасное сохранение одновременных сканов. Откройте сборку в актуальном Chrome.')
  return current ??= createPackingScanLocks(navigator.locks, window.sessionStorage)
}
