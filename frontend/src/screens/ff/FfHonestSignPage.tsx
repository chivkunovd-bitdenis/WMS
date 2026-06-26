import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { HonestSignScreen } from '../shared/HonestSignScreen'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

type Props = {
  token: string
}

type SellerRow = { id: string; name: string }

export function FfHonestSignPage({ token }: Props) {
  const [searchParams] = useSearchParams()
  const [sellers, setSellers] = useState<SellerRow[]>([])
  const [selectedSellerId, setSelectedSellerId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [poolPreviewTitle, setPoolPreviewTitle] = useState<string | null>(null)

  const poolId = searchParams.get('pool_id')
  const poolTitleParam = searchParams.get('pool_title')

  useEffect(() => {
    void (async () => {
      const res = await fetch(apiUrl('/sellers'), {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const rows = (await res.json()) as SellerRow[]
      setSellers(rows)
      if (rows[0]) {
        setSelectedSellerId(rows[0].id)
      }
    })()
  }, [token])

  useEffect(() => {
    if (!poolId) {
      setPoolPreviewTitle(null)
      return
    }
    setPoolPreviewTitle(poolTitleParam?.trim() || 'Пул ЧЗ')
  }, [poolId, poolTitleParam])

  const poolPreview = useMemo(() => {
    if (!poolId || !selectedSellerId) {
      return null
    }
    return {
      poolId,
      poolTitle: poolPreviewTitle ?? 'Пул ЧЗ',
      sellerId: selectedSellerId,
    }
  }, [poolId, poolPreviewTitle, selectedSellerId])

  return (
    <>
      {error ? <p data-testid="ff-honest-sign-load-error">{error}</p> : null}
      <HonestSignScreen
        token={token}
        sellerIdRequiredForImport
        sellers={sellers}
        selectedSellerId={selectedSellerId}
        onSelectedSellerIdChange={setSelectedSellerId}
        testIdPrefix="ff-honest-sign"
        poolPreview={poolPreview}
      />
    </>
  )
}
