package ru.wms.tsd

import android.content.Context
import io.mockk.every
import io.mockk.mockk
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CrashReportStoreTest {
    @Test
    fun `safe report never persists exception message or argument values`() {
        val secretUrl = "https://private.example/api?token=secret"
        val failure = IllegalStateException("password=1234 url=$secretUrl")

        val report = buildSafeCrashReport(
            phase = CrashPhase.APP_INIT,
            failure = failure,
            timestamp = "2026-08-05T10:00:00Z",
            versionName = "0.1.3-atol7",
        )

        assertTrue(report.contains("code=WMS-APP-INIT-001"))
        assertTrue(report.contains("outer_exception_class=java.lang.IllegalStateException"))
        assertTrue(report.contains("root_cause_class=java.lang.IllegalStateException"))
        assertTrue(report.contains("missing_class=unavailable"))
        assertFalse(report.contains("password"))
        assertFalse(report.contains("1234"))
        assertFalse(report.contains(secretUrl))
    }

    @Test
    fun `init fallback survives an unavailable internal report file`() {
        val context = mockk<Context>()
        every { context.filesDir } throws IllegalStateException("storage unavailable")

        val stored = CrashReportStore.recordInitFailure(
            context,
            IllegalStateException("application init failed"),
        )

        assertFalse(stored)
    }

    @Test
    fun `extracts Android didnt find class diagnostic`() {
        val failure = ClassNotFoundException(
            "Didn't find class \"android.os.VibrationEffect\" on path: DexPathList[[zip file]]",
        )

        assertEquals("android.os.VibrationEffect", missingClassNameOf(failure))
    }

    @Test
    fun `extracts Dalvik failed resolution descriptor`() {
        val failure = NoClassDefFoundError("Failed resolution of: Landroid/os/VibrationEffect;")

        assertEquals("android.os.VibrationEffect", missingClassNameOf(failure))
    }

    @Test
    fun `rejects unlabelled dotted text even when it looks like a class name`() {
        val failure = ClassNotFoundException("secret.token.value")

        assertEquals(null, missingClassNameOf(failure))
        val report = buildSafeCrashReport(
            phase = CrashPhase.UNCAUGHT,
            failure = failure,
            timestamp = "2026-08-05T10:00:00Z",
            versionName = "0.1.3-atol7",
        )
        assertTrue(report.contains("missing_class=unavailable"))
        assertFalse(report.contains("secret.token.value"))
    }

    @Test
    fun `malicious missing class message is unavailable and cannot leak`() {
        val secretUrl = "https://private.example/api"
        val failure = ClassNotFoundException(
            "Didn't find class \"ru.wms.tsd.Missing\" at $secretUrl token=secret-value",
        )

        assertEquals(null, missingClassNameOf(failure))
        val report = buildSafeCrashReport(
            phase = CrashPhase.UNCAUGHT,
            failure = failure,
            timestamp = "2026-08-05T10:00:00Z",
            versionName = "0.1.3-atol7",
        )
        assertTrue(report.contains("missing_class=unavailable"))
        assertFalse(report.contains(secretUrl))
        assertFalse(report.contains("secret-value"))
    }

    @Test
    fun `app frame is selected outer first without arguments`() {
        val root = ClassNotFoundException(
            "Didn't find class \"android.os.VibrationEffect\" on path: DexPathList[]",
        ).apply {
            stackTrace = arrayOf(
                StackTraceElement("ru.wms.tsd.Root", "rootCall", "Root.kt", 10),
            )
        }
        val outer = IllegalStateException("wrapper", root).apply {
            stackTrace = arrayOf(
                StackTraceElement("android.app.ActivityThread", "main", "ActivityThread.java", 1),
                StackTraceElement("ru.wms.tsd.WmsApp", "onCreate", "WmsApp.kt", 15),
            )
        }

        val report = buildSafeCrashReport(
            phase = CrashPhase.UNCAUGHT,
            failure = outer,
            timestamp = "2026-08-05T10:00:00Z",
            versionName = "0.1.3-atol7",
        )

        assertTrue(report.contains("outer_exception_class=java.lang.IllegalStateException"))
        assertTrue(report.contains("root_cause_class=java.lang.ClassNotFoundException"))
        assertTrue(report.contains("missing_class=android.os.VibrationEffect"))
        assertTrue(report.contains("app_frame=ru.wms.tsd.WmsApp#onCreate"))
        assertFalse(report.contains("Root.kt"))
        assertFalse(report.contains("ActivityThread.java"))
    }
}
