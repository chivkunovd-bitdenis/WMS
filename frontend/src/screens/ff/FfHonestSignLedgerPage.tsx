import { useEffect, useState } from 'react'
import { HonestSignLedgerPage } from '../shared/HonestSignLedgerPage'

type Props = {
  token: string
  sellers: { id: string; name: string }[]
}

export function FfHonestSignLedgerPage({ token, sellers }: Props) {
  const [selectedSellerId, setSelectedSellerId] = useState<string | null>(null)

  useEffect(() => {
    if (sellers.length === 0) {
      setSelectedSellerId(null)
      return
    }
    setSelectedSellerId((prev) => {
      if (prev && sellers.some((s) => s.id === prev)) {
        return prev
      }
      return sellers[0]?.id ?? null
    })
  }, [sellers])

  return (
    <HonestSignLedgerPage
      token={token}
      sellers={sellers}
      selectedSellerId={selectedSellerId}
      onSelectedSellerIdChange={setSelectedSellerId}
      testIdPrefix="ff-honest-sign-ledger"
      routeBase="/app/ff"
    />
  )
}
