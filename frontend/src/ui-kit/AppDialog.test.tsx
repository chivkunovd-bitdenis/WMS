import { describe, expect, it } from 'vitest'

import { __appDialogTest } from './AppDialog'

describe('AppDialog', () => {
  it('keeps MUI focus trapping, focus restoration and Escape close enabled for every consumer', () => {
    expect(__appDialogTest.accessibility).toEqual({
      disableAutoFocus: false,
      disableEnforceFocus: false,
      disableRestoreFocus: false,
      disableEscapeKeyDown: false,
    })
  })
})
