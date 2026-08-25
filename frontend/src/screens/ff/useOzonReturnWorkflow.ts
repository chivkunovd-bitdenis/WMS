import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from 'react'

import { apiUrl } from '../../api'
import type { OzonReturnPreviewGroup } from '../../components/OzonReturnPickerDialog'
import { ozonGiveoutStatus } from '../../components/ozonReturnPickerHelpers'
import { printOzonReturnReconciliation } from '../../utils/printOzonReturnReconciliation'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

type CatalogImageRow = { wb_primary_image_url?: string | null }

type Args = {
  requestId: string
  authHeaders: Record<string, string>
  isOzonReturn: boolean
  catalogById: ReadonlyMap<string, CatalogImageRow>
  documentNumber: string | null
  sellerName: string | null
  loadDetail: () => Promise<unknown>
  setBusy: Dispatch<SetStateAction<boolean>>
  setError: Dispatch<SetStateAction<string | null>>
  setSuccessMessage: Dispatch<SetStateAction<string | null>>
}

export function useOzonReturnWorkflow({
  requestId,
  authHeaders,
  isOzonReturn,
  catalogById,
  documentNumber,
  sellerName,
  loadDetail,
  setBusy,
  setError,
  setSuccessMessage,
}: Args) {
  const [pickerOpen, setPickerOpen] = useState(false)
  const [preview, setPreview] = useState<{
    groups: OzonReturnPreviewGroup[]
    message: string | null
  }>({ groups: [], message: null })
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [groups, setGroups] = useState<OzonReturnPreviewGroup[]>([])

  const fetchGroups = useCallback(async (): Promise<OzonReturnPreviewGroup[]> => {
    const response = await fetch(
      apiUrl(`/operations/inbound-intake-requests/${requestId}/ozon-returns/groups`),
      { headers: authHeaders },
    )
    if (!response.ok) throw new Error(await readApiErrorMessage(response))
    return (await response.json()) as OzonReturnPreviewGroup[]
  }, [authHeaders, requestId])

  const loadGroups = useCallback(async (): Promise<void> => {
    try {
      setGroups(await fetchGroups())
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Не удалось загрузить состав возврата Ozon.')
      setGroups([])
    }
  }, [fetchGroups, setError])

  useEffect(() => {
    if (!isOzonReturn) {
      setGroups([])
      return
    }
    void loadGroups()
  }, [isOzonReturn, loadGroups])

  const openPicker = async () => {
    setPickerOpen(true)
    setPreviewLoading(true)
    setPreviewError(null)
    try {
      const response = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/ozon-returns/preview`),
        { headers: authHeaders },
      )
      if (!response.ok) {
        setPreviewError(await readApiErrorMessage(response))
        return
      }
      const next = (await response.json()) as {
        groups: OzonReturnPreviewGroup[]
        message: string | null
      }
      setPreview({
        ...next,
        groups: next.groups.map((group) => ({
          ...group,
          items: group.items.map((item) => ({
            ...item,
            image_url:
              item.image_url ??
              (item.product_id ? catalogById.get(item.product_id)?.wb_primary_image_url : null) ??
              null,
          })),
        })),
      })
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : 'Не удалось получить возвраты Ozon.')
    } finally {
      setPreviewLoading(false)
    }
  }

  const importGiveouts = async (giveoutIds: number[]) => {
    setBusy(true)
    setPreviewError(null)
    try {
      const response = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/ozon-returns/import`),
        {
          method: 'POST',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({ giveout_ids: giveoutIds }),
        },
      )
      if (!response.ok) {
        setPreviewError(await readApiErrorMessage(response))
        return
      }
      const imported = (await response.json()) as { giveouts_imported: number; unmatched_items: number }
      setSuccessMessage(
        imported.unmatched_items > 0
          ? `Добавлено пунктов: ${imported.giveouts_imported}. Несопоставленные товары остались в документе.`
          : `Добавлено пунктов: ${imported.giveouts_imported}.`,
      )
      setPickerOpen(false)
      await loadDetail()
      await loadGroups()
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : 'Не удалось добавить возвраты Ozon.')
    } finally {
      setBusy(false)
    }
  }

  const downloadPass = async () => {
    setBusy(true)
    setError(null)
    try {
      const response = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/ozon-returns/pass.pdf`),
        { headers: authHeaders },
      )
      if (!response.ok) {
        setError(await readApiErrorMessage(response))
        return
      }
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = 'ozon-return-pass.pdf'
      link.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Не удалось получить пропуск Ozon.')
    } finally {
      setBusy(false)
    }
  }

  const printReconciliation = async () => {
    setBusy(true)
    setError(null)
    try {
      const nextGroups = await fetchGroups()
      setGroups(nextGroups)
      printOzonReturnReconciliation({
        documentNumber,
        sellerName,
        groups: nextGroups.map((group) => ({
          giveout_id: group.giveout_id,
          giveout_status: ozonGiveoutStatus(group.giveout_status).label,
          warehouse_name: group.warehouse_name,
          warehouse_address: group.warehouse_address,
          items: group.items,
        })),
      })
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Не удалось напечатать лист сверки Ozon.')
    } finally {
      setBusy(false)
    }
  }

  const saveDefective = async (lineId: string, raw: string, acceptedQty: number) => {
    const quantity = raw.trim() === '' ? 0 : Number(raw)
    if (!Number.isInteger(quantity) || quantity < 0 || quantity > acceptedQty) {
      setError('Брак не может быть больше принятого количества.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const response = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/lines/${lineId}/defective`),
        {
          method: 'PATCH',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({ defective_qty: quantity }),
        },
      )
      if (!response.ok) {
        setError(await readApiErrorMessage(response))
        return
      }
      await loadDetail()
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Не удалось сохранить брак.')
    } finally {
      setBusy(false)
    }
  }

  return {
    groups,
    pickerOpen,
    preview,
    previewError,
    previewLoading,
    closePicker: () => setPickerOpen(false),
    downloadPass,
    importGiveouts,
    openPicker,
    printReconciliation,
    saveDefective,
  }
}
