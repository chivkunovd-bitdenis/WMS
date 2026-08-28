
import type { DistributionLineOut, InboundDetail } from './FfInboundRequestViewTypes'
import type { FfInboundRequestActionContext } from './FfInboundRequestContexts'

// The controller passes the same render-local closures this code used before extraction.
export function useFfInboundDistributionActions(ctx: FfInboundRequestActionContext) {
  const authHeaders = ctx.authHeaders
  const validateDistributionDraft = (): string | null => {
    if (!ctx.detail) return 'Заявка не загружена.'
    // пустые строки черновика игнорируем; завершение без полного распределения блокируется отдельно
    const acceptedByProductId = new Map(ctx.distributableProducts.map((p) => [p.product_id, p.accepted_qty]))
    const sumByProductId = new Map<string, number>()

    for (const [idx, r] of ctx.distLines.entries()) {
      const rowLabel = `Строка ${idx + 1}`
      const hasAny = Boolean(r.product_id || r.storage_location_id || r.quantity)
      if (!hasAny) continue

      if (!r.product_id) return `${rowLabel}: выбери товар.`
      const accepted = acceptedByProductId.get(r.product_id)
      if (accepted == null) return `${rowLabel}: товар не относится к заявке.`
      if (accepted <= 0) return `${rowLabel}: товар не принят (0).`

      if (!r.storage_location_id) return `${rowLabel}: выбери ячейку.`

      const q = Math.floor(Number(r.quantity))
      if (!Number.isFinite(q) || q <= 0) return `${rowLabel}: количество должно быть целым числом > 0.`

      const nextSum = (sumByProductId.get(r.product_id) ?? 0) + q
      if (nextSum > accepted) {
        return `${rowLabel}: превышение. По товару можно максимум ${accepted}, указано суммарно ${nextSum}.`
      }
      sumByProductId.set(r.product_id, nextSum)
    }
    return null
  }

  const saveDistribution = async () => {
    if (!ctx.detail) return
    ctx.setDistBusy(true)
    ctx.setDistError(null)
    try {
      const vErr = validateDistributionDraft()
      if (vErr) {
        ctx.setDistError(vErr)
        return
      }
      const payload = ctx.distLines
        .filter((r) => r.product_id && r.storage_location_id && r.quantity)
        .map((r) => {
          const boxId = r.box_id || ctx.defaultPutawayBoxId
          return {
            box_id: boxId || null,
            product_id: r.product_id,
            storage_location_id: r.storage_location_id,
            quantity: Math.floor(Number(r.quantity)),
          }
        })
        .filter((r) => Number.isFinite(r.quantity) && r.quantity > 0)
      const res = await fetch(
        ctx.apiUrl(`/operations/inbound-intake-requests/${ctx.requestId}/distribution-lines`),
        {
          method: 'PUT',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
      )
      if (!res.ok) {
        const code = await ctx.readApiErrorMessage(res)
        if (code === 'qty_exceeds_accepted') {
          ctx.setDistError('Превышено принятие: суммарно по товару нельзя распределить больше, чем принято по заявке.')
        } else if (code === 'product_not_on_request') {
          ctx.setDistError('Нельзя распределять товар, которого нет в этой заявке.')
        } else if (code === 'product_not_accepted') {
          ctx.setDistError('Нельзя распределять товар с принятым количеством 0.')
        } else {
          ctx.setDistError(code)
        }
        return
      }
      const rows = (await res.json()) as DistributionLineOut[]
      ctx.setDistLines(
        rows.map((r) => ({
          box_id: (r as { box_id?: string | null }).box_id ?? ctx.defaultPutawayBoxId,
          product_id: r.product_id,
          storage_location_id: r.storage_location_id,
          quantity: String(r.quantity),
        })),
      )
      ctx.setDistOpen(true)
    } catch (e) {
      ctx.setDistError(e instanceof Error ? e.message : 'Не удалось сохранить распределение.')
    } finally {
      ctx.setDistBusy(false)
    }
  }

  const reopenDistribution = async () => {
    if (!ctx.detail) return
    ctx.setDistBusy(true)
    ctx.setDistError(null)
    try {
      const res = await fetch(
        ctx.apiUrl(`/operations/inbound-intake-requests/${ctx.requestId}/distribution-reopen`),
        { method: 'POST', headers: ctx.authHeaders },
      )
      if (!res.ok) {
        ctx.setDistError(await ctx.readApiErrorMessage(res))
        return
      }
      await ctx.loadDetail()
      await ctx.loadDistribution()
      ctx.setDistOpen(true)
    } catch (e) {
      ctx.setDistError(e instanceof Error ? e.message : 'Не удалось открыть распределение.')
    } finally {
      ctx.setDistBusy(false)
    }
  }

  const completeDistribution = async () => {
    if (!ctx.detail) return
    if (ctx.distLines.every((r) => !r.product_id || !r.storage_location_id || !r.quantity)) {
      ctx.setDistError('Добавьте хотя бы одну строку с товаром, ячейкой и количеством.')
      ctx.setDistOpen(true)
      return
    }
    ctx.setDistBusy(true)
    ctx.setDistError(null)
    try {
      const vErr = validateDistributionDraft()
      if (vErr) {
        ctx.setDistError(vErr)
        return
      }
      // Always persist draft first; completion must lock what is actually saved.
      const payload = ctx.distLines
        .filter((r) => r.product_id && r.storage_location_id && r.quantity)
        .map((r) => {
          const boxId = r.box_id || ctx.defaultPutawayBoxId
          return {
            box_id: boxId || null,
            product_id: r.product_id,
            storage_location_id: r.storage_location_id,
            quantity: Math.floor(Number(r.quantity)),
          }
        })
        .filter((r) => Number.isFinite(r.quantity) && r.quantity > 0)
      const putRes = await fetch(
        ctx.apiUrl(`/operations/inbound-intake-requests/${ctx.requestId}/distribution-lines`),
        {
          method: 'PUT',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
      )
      if (!putRes.ok) {
        const code = await ctx.readApiErrorMessage(putRes)
        ctx.setDistError(code)
        return
      }
      const savedRows = (await putRes.json()) as DistributionLineOut[]
      ctx.setDistLines(
        savedRows.map((r) => ({
          box_id: (r as { box_id?: string | null }).box_id ?? ctx.defaultPutawayBoxId,
          product_id: r.product_id,
          storage_location_id: r.storage_location_id,
          quantity: String(r.quantity),
        })),
      )
      const res = await fetch(
        ctx.apiUrl(`/operations/inbound-intake-requests/${ctx.requestId}/distribution-complete`),
        { method: 'POST', headers: ctx.authHeaders },
      )
      if (!res.ok) {
        const code = await ctx.readApiErrorMessage(res)
        ctx.setDistError(code)
        return
      }
      ctx.setDetail((await res.json()) as InboundDetail)
      await ctx.loadDistribution()
      ctx.setDistOpen(true)
    } catch (e) {
      ctx.setDistError(e instanceof Error ? e.message : 'Не удалось завершить распределение.')
    } finally {
      ctx.setDistBusy(false)
    }
  }


  return {
    validateDistributionDraft,
    saveDistribution,
    reopenDistribution,
    completeDistribution,
  }
}

export type FfInboundDistributionActions = ReturnType<typeof useFfInboundDistributionActions>
