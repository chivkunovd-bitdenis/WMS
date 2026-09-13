import { Stack, Typography } from '@mui/material'
import { useEffect, useRef, useState } from 'react'
import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { ActionGroup, AppDialog, ErrorNotice, PrimaryAction, SecondaryAction, TextInput } from '../../../ui-kit'

type Destination = { connection_id: string; queue_name: string; platform: string; warehouse_id: string; last_seen_at: string | null; online: boolean }
type Preview = Pick<Destination, 'connection_id' | 'queue_name' | 'platform'>
const headers = (token: string) => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' })
function message(raw: string) {
  if (raw === 'pairing_not_found_or_expired') return 'Код не найден или истёк. Получите новый код в программе на ПК.'
  if (raw === 'pairing_already_used') return 'Этот код уже использован для другого подключения.'
  if (raw === 'Forbidden' || raw === 'forbidden') return 'У вас нет права подключать принтер.'
  return raw
}
function state(destination: Destination) {
  if (destination.online) return 'Программа на связи. Это не подтверждает выход бумаги.'
  if (destination.last_seen_at) return `Программа была на связи: ${destination.last_seen_at}`
  return 'Программа ещё не выходила на связь.'
}

export function WarehousePrinterDialog({ open, warehouseId, warehouseName, token, isAdmin, onClose }: { open: boolean; warehouseId: string | null; warehouseName: string; token: string; isAdmin: boolean; onClose: () => void }) {
  const [destination, setDestination] = useState<Destination | null>(null)
  const [destinationLoaded, setDestinationLoaded] = useState(false)
  const [code, setCode] = useState('')
  const [preview, setPreview] = useState<Preview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const version = useRef(0)
  async function readDestination() {
    if (!warehouseId) return null
    const response = await fetch(apiUrl(`/operations/print/warehouses/${warehouseId}/destination`), { headers: headers(token) })
    if (!response.ok) throw new Error(message(await readApiErrorMessage(response)))
    const data = await response.json() as { destination: Destination | null }
    setDestination(data.destination)
    setDestinationLoaded(true)
    return data.destination
  }
  useEffect(() => {
    if (!open || !warehouseId) return
    const request = ++version.current
    setDestination(null); setDestinationLoaded(false); setCode(''); setPreview(null); setError(null); setNotice(null)
    void readDestination().catch((cause) => { if (request === version.current) setError(cause instanceof Error ? cause.message : 'Не удалось прочитать назначение принтера.') })
  // warehouseId resets all temporary pairing state.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, warehouseId, token])
  function changeCode(next: string) { setCode(next); setPreview(null); setError(null); setNotice(null) }
  async function inspect() {
    if (!warehouseId || !code.trim()) return
    const request = ++version.current
    setBusy(true); setPreview(null); setError(null); setNotice(null)
    try {
      const response = await fetch(apiUrl(`/operations/print/warehouses/${warehouseId}/pair/preview`), { method: 'POST', headers: headers(token), body: JSON.stringify({ pairing_code: code.trim() }) })
      if (!response.ok) throw new Error(message(await readApiErrorMessage(response)))
      const data = await response.json() as Destination
      if (request === version.current) setPreview(data)
    } catch (cause) { if (request === version.current) setError(cause instanceof Error ? cause.message : 'Не удалось проверить код.') }
    finally { if (request === version.current) setBusy(false) }
  }
  async function reconcile(checked: Preview) {
    try {
      const current = await readDestination()
      if (current?.connection_id === checked.connection_id) { setCode(''); setPreview(null); setNotice('Принтер подключён. Назначение подтверждено сервером.') }
      else if (current) { setPreview(null); setNotice(`Сейчас назначен принтер ${current.queue_name}. Предыдущее назначение не возвращали.`) }
      else setError('Не удалось подтвердить подключение. Проверьте состояние или повторите подключение тем же кодом.')
    } catch { setError('Не удалось проверить подключение. Проверьте состояние перед повтором.') }
  }
  async function connect() {
    if (!warehouseId || !preview || !code.trim()) return
    const checked = preview
    setBusy(true); setError(null)
    try {
      const response = await fetch(apiUrl(`/operations/print/warehouses/${warehouseId}/pair`), { method: 'POST', headers: headers(token), body: JSON.stringify({ pairing_code: code.trim() }) })
      if (!response.ok) { setError(message(await readApiErrorMessage(response))); return }
      await reconcile(checked)
    } catch { await reconcile(checked) }
    finally { setBusy(false) }
  }
  return (
    <AppDialog
      open={open}
      onClose={onClose}
      title="Принтер"
      testId="warehouse-printer-dialog"
      actions={(
        <ActionGroup>
          <SecondaryAction onClick={onClose}>Закрыть</SecondaryAction>
          {isAdmin ? (
            <SecondaryAction
              onClick={() => void readDestination()}
              disabledReason={busy ? 'Проверяем подключение' : undefined}
            >
              Проверить состояние
            </SecondaryAction>
          ) : null}
          {isAdmin && preview ? (
            <PrimaryAction
              onClick={() => void connect()}
              disabledReason={busy ? 'Подключаем принтер' : undefined}
              data-testid="warehouse-printer-connect"
            >
              {destination ? 'Заменить принтер' : 'Подключить'}
            </PrimaryAction>
          ) : null}
        </ActionGroup>
      )}
    >
      <Stack spacing={2}>
        <Typography variant="body2">Склад: {warehouseName || 'не выбран'}</Typography>
        {destination ? (
          <Stack spacing={0.5} data-testid="warehouse-printer-destination">
            <Typography>
              Назначен: {destination.queue_name} · {destination.platform}. {state(destination)}
            </Typography>
            <Typography variant="body2" color="text.secondary" data-testid="warehouse-printer-connection-id">
              Подключение: {destination.connection_id}
            </Typography>
          </Stack>
        ) : destinationLoaded ? (
          <Typography data-testid="warehouse-printer-empty">Принтер для этого склада не назначен.</Typography>
        ) : (
          <Typography data-testid="warehouse-printer-loading">Читаем назначение принтера…</Typography>
        )}
        {notice ? <Typography color="success.main">{notice}</Typography> : null}
        {error ? <ErrorNotice>{error}</ErrorNotice> : null}
        {isAdmin ? (
          <>
            <Typography variant="body2">Введите код из программы WMS Print на компьютере с принтером.</Typography>
            <Typography variant="body2" color="text.secondary">
              Пакет передаётся вместе с проверяемой сборкой; опубликованной ссылки на скачивание пока нет.
            </Typography>
            <TextInput label="Код подключения" value={code} onChange={changeCode} testId="warehouse-printer-code" />
            <ActionGroup>
              <SecondaryAction
                onClick={() => void inspect()}
                disabledReason={!code.trim() ? 'Введите код подключения' : busy ? 'Проверяем код' : undefined}
                data-testid="warehouse-printer-preview"
              >
                Проверить
              </SecondaryAction>
            </ActionGroup>
            {preview ? (
              <Typography data-testid="warehouse-printer-preview-result">
                Проверено: очередь {preview.queue_name} · {preview.platform}.{' '}
                {destination && destination.connection_id !== preview.connection_id
                  ? `Новые задания пойдут на ${preview.queue_name}; уже созданные сохранят прежний принтер.`
                  : ''}
              </Typography>
            ) : null}
          </>
        ) : (
          <Typography color="text.secondary">Статус доступен для просмотра. Подключить принтер может администратор.</Typography>
        )}
      </Stack>
    </AppDialog>
  )
}
