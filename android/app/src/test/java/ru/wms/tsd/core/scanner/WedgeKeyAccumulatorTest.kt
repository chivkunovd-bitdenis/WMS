package ru.wms.tsd.core.scanner

import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class WedgeKeyAccumulatorTest {

    private fun accumulator(manager: ScannerManager) =
        WedgeKeyAccumulator(manager, minLength = 4, maxInterKeyMs = 60)

    private fun TestScope.collectScans(manager: ScannerManager): MutableList<ScanEvent> {
        val received = mutableListOf<ScanEvent>()
        backgroundScope.launch { manager.scans.collect { received += it } }
        runCurrent() // даём коллектору подписаться до первого tryEmit
        return received
    }

    @Test
    fun `fast input ending with enter is emitted as scan`() = runTest {
        val manager = ScannerManager()
        val acc = accumulator(manager)
        val received = collectScans(manager)

        var t = 1000L
        "4600000000017".forEach { ch ->
            acc.feedChar(ch, t)
            t += 20
        }
        assertTrue(acc.feedEnter(t + 20))
        runCurrent()

        assertEquals(1, received.size)
        assertEquals("4600000000017", received[0].barcode)
        assertEquals(ScanSource.KEYBOARD_WEDGE, received[0].source)
    }

    @Test
    fun `slow human typing is not a scan`() = runTest {
        val manager = ScannerManager()
        val acc = accumulator(manager)
        val received = collectScans(manager)

        var t = 1000L
        "1234".forEach { ch ->
            acc.feedChar(ch, t)
            t += 300 // человек печатает медленно
        }
        assertFalse(acc.feedEnter(t))
        runCurrent()
        assertTrue(received.isEmpty())
    }

    @Test
    fun `short input is not a scan`() = runTest {
        val manager = ScannerManager()
        val acc = accumulator(manager)
        val received = collectScans(manager)

        var t = 1000L
        "12".forEach { ch ->
            acc.feedChar(ch, t)
            t += 10
        }
        assertFalse(acc.feedEnter(t + 10))
        runCurrent()
        assertTrue(received.isEmpty())
    }

    @Test
    fun `human pause resets buffer so only tail is considered`() = runTest {
        val manager = ScannerManager()
        val acc = accumulator(manager)
        val received = collectScans(manager)

        acc.feedChar('X', 1000L)
        // пауза 5 секунд — буфер сбрасывается, дальше быстрый скан
        var t = 6000L
        "ABCD1234".forEach { ch ->
            acc.feedChar(ch, t)
            t += 15
        }
        assertTrue(acc.feedEnter(t))
        runCurrent()

        assertEquals(1, received.size)
        assertEquals("ABCD1234", received[0].barcode)
    }
}
