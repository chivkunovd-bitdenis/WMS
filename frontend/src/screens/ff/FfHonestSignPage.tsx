import { useEffect, useState } from 'react'
import { HonestSignScreen } from '../shared/HonestSignScreen'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

type Props = {
  token: string
}

type SellerRow = { id: string; name: string }

export function FfHonestSignPage({ token }: Props) {
  const [sellers, setSellers] = useState<SellerRow[]>([])
  const [selectedSellerId, setSelectedSellerId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

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
      />
    </>
  )
}
