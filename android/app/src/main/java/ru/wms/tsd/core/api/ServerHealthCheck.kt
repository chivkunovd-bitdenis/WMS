package ru.wms.tsd.core.api

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

internal const val HEALTH_OK_BODY = """{"status":"ok"}"""

/**
 * Пользовательская проверка GET {base}health без сохранения кандидатного URL.
 */
class ServerHealthCheck(
    private val okHttpClient: OkHttpClient = defaultClient(),
) {
    suspend fun check(
        normalizedBaseUrl: String,
        hasActiveNetwork: Boolean,
    ): Result<Unit> = withContext(Dispatchers.IO) {
        val healthUrl = "${normalizedBaseUrl}health"
        val outcome = try {
            val request = Request.Builder().url(healthUrl).get().build()
            val response = okHttpClient.newCall(request).execute()
            response.use {
                when {
                    !it.isSuccessful -> Result.failure(classifyHttpStatus(it.code))
                    isValidHealthBody(it.body?.string()) -> Result.success(Unit)
                    else -> Result.failure(NetworkFailure.InvalidResponse)
                }
            }
        } catch (error: CancellationException) {
            throw error
        } catch (error: Exception) {
            Result.failure(classifyThrowable(error))
        }

        outcome.fold(
            onSuccess = { Result.success(Unit) },
            onFailure = { error ->
                val failure = error as? NetworkFailure ?: NetworkFailure.Unknown
                Result.failure(refineWithConnectivityHint(failure, hasActiveNetwork))
            },
        )
    }

    companion object {
        private fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(15, TimeUnit.SECONDS)
            .writeTimeout(15, TimeUnit.SECONDS)
            .callTimeout(30, TimeUnit.SECONDS)
            .build()
    }
}

internal fun isValidHealthBody(body: String?): Boolean = body?.trim() == HEALTH_OK_BODY
