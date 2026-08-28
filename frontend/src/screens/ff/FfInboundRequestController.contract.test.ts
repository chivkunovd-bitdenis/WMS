import { beforeEach, describe, expect, it, vi } from 'vitest'

const runtime = vi.hoisted(() => ({
  callOrder: [] as string[],
  stateArgs: [] as Array<Record<string, unknown>>,
}))

vi.mock('react', () => ({
  createElement: (type: unknown, props: Record<string, unknown>) => ({ type, props }),
}))

vi.mock('./useFfInboundRequestState', () => ({
  useFfInboundRequestState: (props: Record<string, unknown>) => {
    runtime.callOrder.push('state')
    runtime.stateArgs.push(props)
    return {
      detail: null,
      sortingView: false,
      receivingActive: false,
      boxAddDialogBoxId: null,
      pickerOpen: false,
      dimensionsLine: null,
      receivingScanQueue: vi.fn(),
      receptionClosed: false,
    }
  },
}))

vi.mock('./useFfInboundRequestScanner', () => ({
  useFfInboundRequestScanner: () => {
    runtime.callOrder.push('scanner')
  },
}))

vi.mock('./useFfInboundRequestData', () => ({
  useFfInboundRequestData: () => {
    runtime.callOrder.push('data')
    return {}
  },
}))

vi.mock('./FfInboundRequestDistributionActions', () => ({
  useFfInboundDistributionActions: () => {
    runtime.callOrder.push('distribution')
    return {}
  },
}))

vi.mock('./FfInboundRequestReceivingActions', () => ({
  useFfInboundReceivingActions: () => {
    runtime.callOrder.push('receiving')
    return {}
  },
}))

vi.mock('./FfInboundRequestPackageActions', () => ({
  useFfInboundPackageActions: () => {
    runtime.callOrder.push('packages')
    return {}
  },
}))

vi.mock('./FfInboundRequestViewBody', () => ({
  FfInboundRequestViewBody: () => null,
}))

import {
  FfInboundRequestView,
  useFfInboundRequestController,
} from './FfInboundRequestViewController'

describe('TC-NEW-A3-005 controller defaults and hook-order instrumentation', () => {
  beforeEach(() => {
    runtime.callOrder.length = 0
    runtime.stateArgs.length = 0
  })

  it('registers scanner subscriptions before data effects and mounts the omitted-prop baseline defaults', () => {
    const props = {
      token: 'token',
      requestId: 'request-1',
      isFulfillmentAdmin: true,
      onClose: vi.fn(),
    }

    const controller = useFfInboundRequestController(props)
    const mounted = FfInboundRequestView(props) as unknown as {
      props: { controller: { workspace: string; addressStorageEnabled: boolean } }
    }

    expect(runtime.callOrder).toEqual([
      'state',
      'scanner',
      'data',
      'distribution',
      'receiving',
      'packages',
      'state',
      'scanner',
      'data',
      'distribution',
      'receiving',
      'packages',
    ])
    expect(runtime.stateArgs).toHaveLength(2)
    expect(runtime.stateArgs).toEqual([
      expect.objectContaining({ workspace: 'full', addressStorageEnabled: true }),
      expect.objectContaining({ workspace: 'full', addressStorageEnabled: true }),
    ])
    expect(controller.workspace).toBe('full')
    expect(controller.addressStorageEnabled).toBe(true)
    expect(mounted.props.controller.workspace).toBe('full')
    expect(mounted.props.controller.addressStorageEnabled).toBe(true)
  })
})
