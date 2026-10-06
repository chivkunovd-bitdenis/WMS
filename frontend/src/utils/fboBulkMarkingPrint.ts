import { apiUrl } from '../api'
import { readApiErrorMessage } from './readApiErrorMessage'
import type { PrintLayout } from './printTemplate'
import type { FboBulkPrintResponse } from '../components/MarkingPrintDialog'
import type { ProductThermalLabelData } from './printProductThermalLabel'

/**
 * WMS-618: one atomic bulk CZ issuance for the whole FBO shipment.
 *
 * The server response is the CURRENT snapshot of every line in the task
 * (CZ-required and not) plus the FULL set of CZ codes now bound to each line.
 * A retry after a lost response returns the SAME codes without re-issuing,
 * so double-click protection is server-side; the frontend simply replays the
 * same tape it would have built the first time.
 */
export async function postFboBulkMarkingPrint(args: {
  token: string
  taskId: string
  layout: PrintLayout
  allowPartial: boolean
  issueMarkingCodes: boolean
}): Promise<FboBulkPrintResponse> {
  const res = await fetch(
    apiUrl(`/operations/marking-codes/packaging-tasks/${args.taskId}/print-fbo-bulk`),
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${args.token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ layout_json: args.layout, allow_partial: args.allowPartial, issue_marking_codes: args.issueMarkingCodes }),
    },
  )
  if (!res.ok) {
    throw new Error(await readApiErrorMessage(res))
  }
  const data = (await res.json()) as {
    packaging_task_id: string
    layout: unknown
    shortage: number
    lines: Array<{
      packaging_task_line_id: string
      product_id: string
      sku_code: string
      product_name: string
      requires_honest_sign: boolean
      quantity: number
      shortage: number
      product_label: ProductThermalLabelData
      printed_codes: Array<{ id: string; cis_code: string; has_label_artifact: boolean }>
    }>
  }
  return {
    lines: data.lines.map((line) => ({
      lineId: line.packaging_task_line_id,
      productId: line.product_id,
      skuCode: line.sku_code,
      productName: line.product_name,
      requiresHonestSign: line.requires_honest_sign,
      quantity: line.quantity,
      shortage: line.shortage,
      productLabel: line.product_label,
      printedCodes: line.printed_codes.map((code) => ({
        id: code.id,
        cisCode: code.cis_code,
        hasLabelArtifact: code.has_label_artifact,
      })),
    })),
    shortage: data.shortage,
  }
}
