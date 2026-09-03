package ru.wms.tsd.core.api

import okhttp3.OkHttpClient
import ru.wms.tsd.core.api.generated.infrastructure.ApiClient
import java.util.concurrent.TimeUnit

private const val CONNECT_TIMEOUT_SECONDS = 15L
private const val READ_TIMEOUT_SECONDS = 15L
private const val WRITE_TIMEOUT_SECONDS = 15L
private const val CALL_TIMEOUT_SECONDS = 30L

fun loginApiClient(normalizedBaseUrl: String): ApiClient {
    val builder = OkHttpClient.Builder()
        .connectTimeout(CONNECT_TIMEOUT_SECONDS, TimeUnit.SECONDS)
        .readTimeout(READ_TIMEOUT_SECONDS, TimeUnit.SECONDS)
        .writeTimeout(WRITE_TIMEOUT_SECONDS, TimeUnit.SECONDS)
        .callTimeout(CALL_TIMEOUT_SECONDS, TimeUnit.SECONDS)
    return ApiClient(normalizedBaseUrl, builder)
}
