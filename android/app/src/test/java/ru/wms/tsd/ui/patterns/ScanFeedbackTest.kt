package ru.wms.tsd.ui.patterns

import org.junit.Assert.assertEquals
import org.junit.Test

class ScanFeedbackTest {
    @Test
    fun `Android 7 uses legacy vibration API`() {
        assertEquals(VibrationMode.LEGACY, vibrationModeForSdk(24))
    }

    @Test
    fun `Android 8 uses VibrationEffect API`() {
        assertEquals(VibrationMode.EFFECT, vibrationModeForSdk(26))
    }
}
