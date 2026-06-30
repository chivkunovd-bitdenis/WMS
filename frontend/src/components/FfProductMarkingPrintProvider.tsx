import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { Snackbar } from '@mui/material'
import {
  useFfProductMarkingPrint,
  type OpenFfProductPrintOpts,
} from '../utils/useFfProductMarkingPrint'

type FfProductMarkingPrintContextValue = {
  openCatalogProductPrint: (opts: OpenFfProductPrintOpts) => Promise<void>
}

const FfProductMarkingPrintContext = createContext<FfProductMarkingPrintContextValue | null>(null)

export function useFfProductMarkingPrintContext(): FfProductMarkingPrintContextValue {
  const ctx = useContext(FfProductMarkingPrintContext)
  if (!ctx) {
    throw new Error('FfProductMarkingPrintProvider is required')
  }
  return ctx
}

export function useFfProductMarkingPrintContextOptional(): FfProductMarkingPrintContextValue | null {
  return useContext(FfProductMarkingPrintContext)
}

type ProviderProps = {
  token: string
  children: ReactNode
}

/** Один MarkingPrintDialog на страницу + toast при ошибке загрузки marking-overview. */
export function FfProductMarkingPrintProvider({ token, children }: ProviderProps) {
  const { openCatalogProductPrint: openRaw, dialog } = useFfProductMarkingPrint(token)
  const [error, setError] = useState<string | null>(null)

  const openCatalogProductPrint = useCallback(
    async (opts: OpenFfProductPrintOpts) => {
      setError(null)
      try {
        await openRaw(opts)
      } catch (e) {
        const message = e instanceof Error ? e.message : 'Не удалось открыть печать.'
        setError(message)
        throw e
      }
    },
    [openRaw],
  )

  return (
    <FfProductMarkingPrintContext.Provider value={{ openCatalogProductPrint }}>
      {children}
      {dialog}
      <Snackbar
        open={error !== null}
        autoHideDuration={5000}
        onClose={() => setError(null)}
        message={error ?? ''}
        data-testid="ff-product-marking-print-error"
      />
    </FfProductMarkingPrintContext.Provider>
  )
}
