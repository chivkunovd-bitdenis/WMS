package ru.wms.tsd.core.api

import java.io.IOException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.security.cert.CertPathValidatorException
import java.security.cert.CertificateException
import javax.net.ssl.SSLException
import javax.net.ssl.SSLHandshakeException
import javax.net.ssl.SSLPeerUnverifiedException

/**
 * Типизированные сетевые сбои для логина и проверки соединения.
 * Операторские сообщения безопасны: без exception.message, URL, тел и токенов.
 */
sealed class NetworkFailure(val diagnosticCode: String) : Exception() {
    data object InvalidCredentials : NetworkFailure("AUTH-401")
    data object InvalidLoginForm : NetworkFailure("AUTH-422")
    data object AccessForbidden : NetworkFailure("AUTH-403")
    data object InvalidUrl : NetworkFailure("NET-URL")
    data object NoActiveNetwork : NetworkFailure("NET-OFFLINE")
    data object DnsFailure : NetworkFailure("NET-DNS")
    data object ConnectionRefused : NetworkFailure("NET-CONN")
    data object Timeout : NetworkFailure("NET-TIMEOUT")
    data object TlsFailure : NetworkFailure("NET-TLS")
    data object Http404 : NetworkFailure("NET-404")
    data object Http429 : NetworkFailure("NET-429")
    data object Http5xx : NetworkFailure("NET-5XX")
    data object InvalidResponse : NetworkFailure("NET-RESP")
    data object StorageFailure : NetworkFailure("APP-STORAGE")
    data object Unknown : NetworkFailure("NET-UNK")

    fun toOperatorMessage(): String = when (this) {
        InvalidCredentials -> "Неверный email или пароль [$diagnosticCode]"
        InvalidLoginForm -> "Некорректные данные входа [$diagnosticCode]"
        AccessForbidden -> "Доступ запрещён [$diagnosticCode]"
        InvalidUrl -> "Неверный адрес сервера [$diagnosticCode]"
        NoActiveNetwork -> "Нет подключения к сети [$diagnosticCode]"
        DnsFailure -> "Сервер не найден [$diagnosticCode]"
        ConnectionRefused -> "Сервер недоступен [$diagnosticCode]"
        Timeout -> "Превышено время ожидания [$diagnosticCode]"
        TlsFailure -> "Ошибка защищённого соединения [$diagnosticCode]"
        Http404 -> "Сервис не найден [$diagnosticCode]"
        Http429 -> "Слишком много запросов [$diagnosticCode]"
        Http5xx -> "Ошибка сервера [$diagnosticCode]"
        InvalidResponse -> "Некорректный ответ сервера [$diagnosticCode]"
        StorageFailure -> "Ошибка сохранения настроек [$diagnosticCode]"
        Unknown -> "Ошибка соединения [$diagnosticCode]"
    }
}

fun classifyHttpStatus(code: Int, forLogin: Boolean = false): NetworkFailure = when (code) {
    401 -> if (forLogin) NetworkFailure.InvalidCredentials else NetworkFailure.InvalidResponse
    403 -> if (forLogin) NetworkFailure.AccessForbidden else NetworkFailure.InvalidResponse
    422 -> if (forLogin) NetworkFailure.InvalidLoginForm else NetworkFailure.InvalidResponse
    404 -> NetworkFailure.Http404
    429 -> NetworkFailure.Http429
    in 500..599 -> NetworkFailure.Http5xx
    in 200..299 -> NetworkFailure.Unknown
    else -> NetworkFailure.InvalidResponse
}

internal fun throwableChainSafe(root: Throwable): List<Throwable> {
    val chain = ArrayList<Throwable>()
    val seen = HashSet<Throwable>()
    var current: Throwable? = root
    while (current != null && seen.add(current)) {
        chain += current
        current = current.cause
    }
    return chain
}

fun classifyThrowable(error: Throwable): NetworkFailure {
    for (throwable in throwableChainSafe(error)) {
        when (throwable) {
            is UnknownHostException -> return NetworkFailure.DnsFailure
            is ConnectException -> return NetworkFailure.ConnectionRefused
            is SocketTimeoutException -> return NetworkFailure.Timeout
            is SSLHandshakeException,
            is SSLPeerUnverifiedException,
            is CertPathValidatorException,
            is CertificateException,
            is SSLException,
            -> return NetworkFailure.TlsFailure
        }
    }
    val last = throwableChainSafe(error).lastOrNull() ?: error
    return when (last) {
        is IOException -> NetworkFailure.ConnectionRefused
        else -> NetworkFailure.Unknown
    }
}

private val forbiddenOperatorMarkers = Regex(
    """(?i)(https?://|exception|stacktrace|authorization|bearer\s|password|token\s*[:=]|@\S+\.\S+)""",
)

fun NetworkFailure.assertSafeOperatorMessage() {
    val message = toOperatorMessage()
    require(!forbiddenOperatorMarkers.containsMatchIn(message)) {
        "Unsafe operator message for $this"
    }
}
