package ru.wms.tsd

import android.content.Context
import android.os.Process
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

private const val CRASH_REPORT_FILE = "wms_safe_crash_report.txt"

/**
 * Локальная диагностика запуска без сети и без пользовательских данных.
 * В файл попадает только белый список полей: код, фаза, время, версия,
 * классы исключений, проверенное имя отсутствующего класса и имя метода приложения.
 * Полный message, аргументы, пути, URL и данные prefs запрещены.
 */
internal object CrashReportStore {
    @Volatile
    private var installed = false

    fun install(context: Context) {
        if (installed) return
        synchronized(this) {
            if (installed) return
            val appContext = context.applicationContext ?: context
            val previous = Thread.getDefaultUncaughtExceptionHandler()
            Thread.setDefaultUncaughtExceptionHandler { thread, failure ->
                runCatching {
                    write(
                        context = appContext,
                        phase = CrashPhase.UNCAUGHT,
                        failure = failure,
                    )
                }
                if (previous != null) {
                    previous.uncaughtException(thread, failure)
                } else {
                    Process.killProcess(Process.myPid())
                }
            }
            installed = true
        }
    }

    fun recordInitFailure(context: Context, failure: Throwable): Boolean =
        runCatching { write(context, CrashPhase.APP_INIT, failure) }.isSuccess

    fun read(context: Context): String? = runCatching {
        reportFile(context).takeIf(File::isFile)?.readText()?.takeIf(String::isNotBlank)
    }.getOrNull()

    fun clear(context: Context) {
        runCatching { reportFile(context).delete() }
    }

    private fun write(context: Context, phase: CrashPhase, failure: Throwable) {
        val timestamp = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
            timeZone = TimeZone.getTimeZone("UTC")
        }.format(Date())
        val report = buildSafeCrashReport(
            phase = phase,
            failure = failure,
            timestamp = timestamp,
            versionName = BuildConfig.VERSION_NAME,
        )
        reportFile(context).writeText(report)
    }

    private fun reportFile(context: Context): File = File(context.filesDir, CRASH_REPORT_FILE)
}

internal enum class CrashPhase(val wireName: String, val stableCode: String) {
    APP_INIT("app_init", "WMS-APP-INIT-001"),
    UNCAUGHT("uncaught", "WMS-UNCAUGHT-001"),
}

internal fun buildSafeCrashReport(
    phase: CrashPhase,
    failure: Throwable,
    timestamp: String,
    versionName: String,
): String {
    val chain = throwableChain(failure)
    val root = chain.last()
    val missingClass = chain.firstNotNullOfOrNull(::missingClassFromThrowable) ?: "unavailable"
    val appFrame = chain.firstNotNullOfOrNull(::firstSafeAppFrame) ?: "unavailable"
    return buildString {
        appendLine("code=${phase.stableCode}")
        appendLine("phase=${phase.wireName}")
        appendLine("timestamp_utc=$timestamp")
        appendLine("version=$versionName")
        appendLine("outer_exception_class=${failure.javaClass.name}")
        appendLine("root_cause_class=${root.javaClass.name}")
        appendLine("missing_class=$missingClass")
        append("app_frame=$appFrame")
    }
}

private fun throwableChain(failure: Throwable): List<Throwable> {
    val chain = ArrayList<Throwable>()
    var current = failure
    val seen = HashSet<Throwable>()
    while (seen.add(current)) {
        chain += current
        val cause = current.cause ?: break
        current = cause
    }
    return chain
}

private const val MAX_SAFE_CLASS_NAME_LENGTH = 200
private const val MAX_INSPECTED_MESSAGE_LENGTH = 4096

private val didntFindClassPattern = Regex("""Didn't find class \"([A-Za-z0-9_$/.;]+)\"""")
private val failedResolutionPattern = Regex("""Failed resolution of:\s*([A-Za-z0-9_$/.;]+)""")
private val forbiddenMessageMarker = Regex(
    """(?i)(https?://|(?:token|password|authorization|cookie|pin)\s*[:=])""",
)
private val javaIdentifierSegment = Regex("""[A-Za-z_$][A-Za-z0-9_$]*""")
private val javaMethodName = Regex("""(?:[A-Za-z_$][A-Za-z0-9_$]*|<init>|<clinit>)""")

internal fun missingClassNameOf(failure: Throwable): String? =
    throwableChain(failure).firstNotNullOfOrNull(::missingClassFromThrowable)

private fun missingClassFromThrowable(failure: Throwable): String? {
    if (failure !is ClassNotFoundException && failure !is NoClassDefFoundError) return null
    val message = failure.message ?: return null
    if (message.length > MAX_INSPECTED_MESSAGE_LENGTH || forbiddenMessageMarker.containsMatchIn(message)) {
        return null
    }
    val candidate = didntFindClassPattern.find(message)?.groupValues?.get(1)
        ?: failedResolutionPattern.find(message)?.groupValues?.get(1)
        ?: return null
    return normalizeSafeClassIdentifier(candidate)
}

private fun normalizeSafeClassIdentifier(candidate: String): String? {
    if (candidate.isEmpty() || candidate.length > MAX_SAFE_CLASS_NAME_LENGTH) return null
    val unwrapped = if (candidate.startsWith('L') && candidate.endsWith(';')) {
        candidate.substring(1, candidate.length - 1)
    } else {
        if (candidate.contains(';')) return null
        candidate
    }
    if (unwrapped.isEmpty()) return null
    val segments = unwrapped.split('.', '/')
    if (segments.any { !javaIdentifierSegment.matches(it) }) return null
    return segments.joinToString(".")
}

private fun firstSafeAppFrame(failure: Throwable): String? = failure.stackTrace.firstNotNullOfOrNull { frame ->
    val className = frame.className
    val methodName = frame.methodName
    if (
        className.startsWith("ru.wms.tsd.") &&
        normalizeSafeClassIdentifier(className) == className &&
        methodName.length <= MAX_SAFE_CLASS_NAME_LENGTH &&
        javaMethodName.matches(methodName)
    ) {
        "$className#$methodName"
    } else {
        null
    }
}
