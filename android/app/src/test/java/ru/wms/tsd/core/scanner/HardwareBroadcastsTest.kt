package ru.wms.tsd.core.scanner

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class HardwareBroadcastsTest {

    private fun parse(
        action: String?,
        extras: Map<String, String?>,
    ): ScanEvent? = parseHardwareBroadcast(action) { key -> extras[key] }

    @Test
    fun `ATOL action with its extra returns barcode`() {
        val event = parse(
            action = "com.xcheng.scanner.action.BARCODE_DECODING_BROADCAST",
            extras = mapOf("EXTRA_BARCODE_DECODING_DATA" to "4600000000017"),
        )

        assertEquals(ScanEvent("4600000000017", ScanSource.HARDWARE_BROADCAST), event)
    }

    @Test
    fun `empty barcode is ignored`() {
        val event = parse(
            action = "com.xcheng.scanner.action.BARCODE_DECODING_BROADCAST",
            extras = mapOf("EXTRA_BARCODE_DECODING_DATA" to "   "),
        )

        assertNull(event)
    }

    @Test
    fun `unknown action is ignored`() {
        val event = parse(
            action = "com.example.UNKNOWN_SCAN",
            extras = mapOf("EXTRA_BARCODE_DECODING_DATA" to "4600000000017"),
        )

        assertNull(event)
    }

    @Test
    fun `ATOL scan source is hardware broadcast`() {
        val event = parse(
            action = "com.xcheng.scanner.action.BARCODE_DECODING_BROADCAST",
            extras = mapOf("EXTRA_BARCODE_DECODING_DATA" to "ATOL-001"),
        )

        assertEquals(ScanSource.HARDWARE_BROADCAST, event?.source)
    }
}
