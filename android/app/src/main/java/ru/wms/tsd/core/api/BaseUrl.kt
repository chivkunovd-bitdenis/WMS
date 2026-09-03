package ru.wms.tsd.core.api

import java.net.URI

internal val DEBUG_CLEARTEXT_HOSTS = setOf(
    "10.0.2.2",
    "localhost",
    "127.0.0.1",
    "::1",
)

/**
 * Retrofit требует, чтобы base URL заканчивался слэшем: пути в сгенерированном
 * клиенте относительные («auth/login»), и без слэша Retrofit падает с
 * IllegalArgumentException ещё до сети. На адресе без пути
 * («http://host:18080») слэш подставляет сам парсер, а вот на адресе с путём
 * («https://host/api») — нет. Поэтому нормализуем в одном месте и используем
 * везде, где создаётся ApiClient.
 */
fun normalizeBaseUrl(url: String): String {
    val trimmed = url.trim()
    return if (trimmed.endsWith("/")) trimmed else "$trimmed/"
}

internal fun hostFromUri(uri: URI): String? {
    val directHost = uri.host
    if (!directHost.isNullOrBlank()) {
        return normalizeHostToken(directHost)
    }
    val authority = uri.authority ?: return null
    val bracketed = Regex("""^\[([^\]]+)\]""").find(authority)
    if (bracketed != null) {
        return normalizeHostToken(bracketed.groupValues[1])
    }
    return normalizeHostToken(authority.substringBefore(':'))
}

internal fun normalizeHostToken(host: String): String {
    val trimmed = host.trim()
    if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
        return trimmed.substring(1, trimmed.length - 1).lowercase()
    }
    return trimmed.lowercase()
}

internal fun isAllowedCleartextHost(host: String): Boolean =
    host.lowercase() in DEBUG_CLEARTEXT_HOSTS

/**
 * Проверяет и нормализует адрес API.
 * Release допускает только HTTPS; debug — HTTP только для loopback/emulator hosts.
 */
fun validateAndNormalizeBaseUrl(raw: String, allowCleartext: Boolean): Result<String> {
    val trimmed = raw.trim()
    if (trimmed.isEmpty()) {
        return Result.failure(BaseUrlValidationException.Empty)
    }

    val uri = try {
        URI(trimmed)
    } catch (_: Exception) {
        return Result.failure(BaseUrlValidationException.InvalidFormat)
    }

    if (uri.isOpaque) {
        return Result.failure(BaseUrlValidationException.InvalidFormat)
    }

    val scheme = uri.scheme?.lowercase()
    if (scheme != "https" && scheme != "http") {
        return Result.failure(BaseUrlValidationException.InvalidScheme)
    }

    if (!uri.userInfo.isNullOrEmpty()) {
        return Result.failure(BaseUrlValidationException.InvalidFormat)
    }

    if (uri.query != null || uri.fragment != null) {
        return Result.failure(BaseUrlValidationException.InvalidFormat)
    }

    val host = hostFromUri(uri)
    if (host.isNullOrBlank()) {
        return Result.failure(BaseUrlValidationException.InvalidFormat)
    }

    val port = uri.port
    if (port != -1 && (port < 1 || port > 65535)) {
        return Result.failure(BaseUrlValidationException.InvalidFormat)
    }

    if (scheme == "http") {
        if (!allowCleartext) {
            return Result.failure(BaseUrlValidationException.CleartextNotAllowed)
        }
        if (!isAllowedCleartextHost(host)) {
            return Result.failure(BaseUrlValidationException.CleartextNotAllowed)
        }
    }

    return Result.success(normalizeBaseUrl(trimmed))
}

sealed class BaseUrlValidationException : Exception() {
    object Empty : BaseUrlValidationException()
    object InvalidScheme : BaseUrlValidationException()
    object InvalidFormat : BaseUrlValidationException()
    object CleartextNotAllowed : BaseUrlValidationException()
}

fun BaseUrlValidationException.toNetworkFailure(): NetworkFailure = NetworkFailure.InvalidUrl
