type DocumentDisplaySource = {
  display_number?: string | null
  public_number?: string | null
  human_number?: string | null
  document_number?: string | null
}

export function formatHumanDocumentNumber(source: DocumentDisplaySource | null | undefined): string | null {
  if (!source) {
    return null
  }
  const preferred = source.display_number ?? source.public_number ?? source.human_number
  if (preferred && preferred.trim()) {
    return preferred.trim()
  }
  const documentNumber = source.document_number?.trim()
  if (!documentNumber) {
    return null
  }
  const counter = documentNumber.match(/(\d+)\s*$/)?.[1]
  if (!counter) {
    return null
  }
  return `№${counter.padStart(6, '0')}`
}
