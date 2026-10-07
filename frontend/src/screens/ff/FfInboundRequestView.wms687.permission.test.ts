import { describe, expect, it } from 'vitest'
import appSource from '../../App.tsx?raw'

// WMS-687 R4: this wiring assertion complements the DOM permission test. The
// screen may receive a distinct catalog right, but it is App that must not
// replace it with canReceptionOps when it opens a reception document.
describe('WMS-687 catalog permission wiring', () => {
  it('passes the existing catalog-settings permission, not reception permission, to the inbound stock entry', () => {
    const inboundModal = appSource.slice(
      appSource.indexOf("ffDocModal === 'inbound'"),
      appSource.indexOf("ffDocModal === 'outbound'"),
    )
    expect(inboundModal).toContain('canManageCatalog={isFulfillmentAdmin}')
    expect(inboundModal).not.toContain('isFulfillmentAdmin={canReceptionOps}')
  })
})
