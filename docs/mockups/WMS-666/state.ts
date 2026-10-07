import type { FbsWorkspace } from '../../../reference-frontend/src/screens/v2/fbsApi'
export type PackingEntry = {
  id: string; title: string; seller: string; marketplace: 'wb'|'ozon'; orders: FbsWorkspace['orders']; selected: Set<string>; printed: number; packed: number
  busy: boolean; editable: boolean; codes: number; clearable: number; honestSignSkipped: boolean; skipBusy: boolean; packAllDisabled: boolean
  select: (ids: Set<string>) => void; print: (orders: FbsWorkspace['orders']) => void
  verify: () => void; packAll: () => void; skip: () => void; transfer: () => void; clear: () => void
}
const entries = new Map<string, PackingEntry>()
const signatures = new Map<string,string>()
const listeners = new Set<() => void>()
const journalListeners = new Set<() => void>()
let journalVersion=0
let version = 0
export let proposal = true
export function setProposal(next: boolean) { proposal = next }
export const journal: Array<{ text: string; detail: unknown }> = []
export const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener) } }
export const snapshot = () => version
export const emit = () => { version++; [...listeners].forEach(listener => listener()) }
export const subscribeJournal = (listener:()=>void) => {journalListeners.add(listener);return()=>{journalListeners.delete(listener)}}
export const journalSnapshot = () => journalVersion
export function log(text: string, detail: unknown = null) { journal.unshift({text, detail}); if(journal.length>60)journal.pop(); journalVersion++; [...journalListeners].forEach(listener=>listener()) }
export function register(entry: PackingEntry) {
 const signature=JSON.stringify([entry.title,entry.marketplace,entry.orders,Array.from(entry.selected).sort(),entry.printed,entry.packed,entry.seller,entry.busy,entry.editable,entry.codes,entry.clearable,entry.honestSignSkipped,entry.skipBusy,entry.packAllDisabled])
 entries.set(entry.id,entry)
 if(signatures.get(entry.id)!==signature){signatures.set(entry.id,signature);emit()}
}
export function unregister(id: string) { entries.delete(id); signatures.delete(id); emit() }
export function entryFor(id: string) { return entries.get(id) }
let printQueue: Array<() => void> = []
export function groupedPrint(groups: Array<{ entry: PackingEntry; orders: FbsWorkspace['orders'] }>) {
  log('Ручная печать: очередь отдельных поставок', groups.map(({entry,orders}) => ({supply:entry.title, seller:entry.seller, orders: orders.map(order=>order.id), labels: entry.marketplace==='wb'?['QR заказа','ЧЗ','ШК']:['ЧЗ','ШК']})))
  printQueue = groups.map(({entry,orders}) => () => entry.print(orders))
  advancePrint()
}
export function cancelPrintQueue() { if(printQueue.length)log('Очередь ручной печати остановлена: окно отменено');printQueue=[] }
export function advancePrint() { printQueue.shift()?.() }
