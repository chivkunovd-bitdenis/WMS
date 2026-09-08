import { useCallback, useEffect, useRef, useState } from 'react'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { inboundMarkingError, type InboundMarkingCode } from './inboundMarkingCodes'

type MarkingList = { items: InboundMarkingCode[]; checking: boolean }

export function useInboundMarkingCodes(requestId: string, token: string, enabled: boolean, documentStatus?: string) {
  const [data, setData] = useState<MarkingList>({ items: [], checking: false })
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [removingCodeId, setRemovingCodeId] = useState<string | null>(null)
  const generation = useRef(0)
  const readSequence = useRef(0)
  const base = `/operations/inbound-intake-requests/${requestId}/marking-codes`
  const load = useCallback(async () => {
    const seq = ++readSequence.current
    const epoch = generation.current
    const res = await fetch(apiUrl(base), { headers: { Authorization: `Bearer ${token}` } })
    if (!res.ok) throw new Error('Не удалось загрузить коды Честного знака. Обновите документ.')
    const next = await res.json() as MarkingList
    if (seq === readSequence.current && epoch === generation.current) {
      setData(next)
      setError(null)
    }
  }, [base, token])

  useEffect(() => {
    generation.current += 1
    setData({ items: [], checking: false })
    setExpanded({})
    setRemovingCodeId(null)
    setError(null)
    return () => { generation.current += 1; readSequence.current += 1 }
  }, [requestId, token])

  useEffect(() => {
    if (enabled) void load().catch((e: Error) => setError(e.message))
  }, [enabled, load, documentStatus])

  useEffect(() => {
    if (!enabled || !data.checking) return
    let loading = false
    const timer = window.setInterval(() => {
      if (loading) return
      loading = true
      void load().catch((e: Error) => setError(e.message)).finally(() => { loading = false })
    }, 2000)
    return () => window.clearInterval(timer)
  }, [data.checking, enabled, load])

  const attach = async (cisCode: string, lineId: string | null) => {
    if (!lineId) throw new Error('Сначала отсканируйте товар, затем его код Честного знака.')
    const epoch = generation.current
    ++readSequence.current
    const res = await fetch(apiUrl(`${base}/scan`), {
      method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ line_id: lineId, cis_code: cisCode }),
    })
    if (!res.ok) throw new Error(inboundMarkingError(await readApiErrorMessage(res)))
    const item = await res.json() as InboundMarkingCode
    if (epoch !== generation.current) return
    ++readSequence.current
    setData((current) => ({ ...current, items: [...current.items.filter((code) => code.id !== item.id), item] }))
    setExpanded((current) => ({ ...current, [lineId]: true }))
  }

  const remove = async (codeId: string) => {
    const epoch = generation.current
    setRemovingCodeId(codeId)
    setError(null)
    ++readSequence.current
    try {
      const res = await fetch(apiUrl(`${base}/${codeId}`), {
        method: 'DELETE', headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) throw new Error(inboundMarkingError(await readApiErrorMessage(res)))
      if (epoch !== generation.current) return
      ++readSequence.current
      setData((current) => ({ ...current, items: current.items.filter((code) => code.id !== codeId) }))
    } catch (e) {
      if (epoch === generation.current) setError(e instanceof Error ? e.message : 'Не удалось убрать код.')
    } finally {
      if (epoch === generation.current) setRemovingCodeId(null)
    }
  }

  const recheck = async () => {
    try {
      const res = await fetch(apiUrl(`${base}/check`), { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
      if (!res.ok) throw new Error('Не удалось начать проверку кодов. Повторите попытку.')
      await load()
    } catch (e) { setError(e instanceof Error ? e.message : 'Не удалось проверить коды.') }
  }

  const download = async () => {
    try {
      const res = await fetch(apiUrl(`${base}/problems.xlsx`), { headers: { Authorization: `Bearer ${token}` } })
      if (!res.ok) throw new Error('Не удалось скачать коды. Повторите попытку.')
      const url = URL.createObjectURL(await res.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = 'Проблемные коды ЧЗ.xlsx'
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) { setError(e instanceof Error ? e.message : 'Не удалось скачать коды.') }
  }
  return { ...data, error, expanded, setExpanded, attach, remove, removingCodeId, recheck, download }
}
