package ru.wms.tsd.core.api

import okhttp3.OkHttpClient
import ru.wms.tsd.BuildConfig
import ru.wms.tsd.core.api.generated.apis.OperationsApi
import ru.wms.tsd.core.api.generated.apis.WarehousesApi
import ru.wms.tsd.core.api.generated.infrastructure.ApiClient
import ru.wms.tsd.core.api.fbs.FbsApi
import ru.wms.tsd.core.auth.AuthManager
import ru.wms.tsd.core.auth.AuthStore

/**
 * Точка получения API-сервисов с авторизацией (T-05b).
 * Токен активного сотрудника подставляется интерсептором на каждый запрос,
 * поэтому смена сотрудника не требует пересоздания клиента. Клиент пересоздаётся
 * только при смене base URL (редкий случай — настройка сервера на логине).
 */
class ApiProvider(
    private val authStore: AuthStore,
    private val authManager: AuthManager,
) {
    private var cachedBaseUrl: String? = null
    private var cachedClient: ApiClient? = null
    private var cachedOperations: OperationsApi? = null
    private var cachedWarehouses: WarehousesApi? = null
    private var cachedFbs: FbsApi? = null

    private fun baseUrl(): String {
        return normalizeBaseUrl(authStore.getBaseUrl() ?: BuildConfig.DEFAULT_API_BASE_URL)
    }

    private fun client(): ApiClient {
        val url = baseUrl()
        cachedClient?.let { if (url == cachedBaseUrl) return it }
        val builder = OkHttpClient.Builder().addInterceptor { chain ->
            val token = authManager.getCurrentSession()?.token
            val request = if (token != null) {
                chain.request().newBuilder().header("Authorization", "Bearer $token").build()
            } else {
                chain.request()
            }
            val response = chain.proceed(request)
            // Токен протух (T-05c): глобальный разлогин вместо тупика «Сессия истекла»
            if (response.code == 401 && token != null) {
                authManager.notifySessionExpired()
            }
            response
        }
        val client = ApiClient(baseUrl = url, okHttpClientBuilder = builder)
        cachedBaseUrl = url
        cachedClient = client
        cachedOperations = null
        cachedWarehouses = null
        cachedFbs = null
        return client
    }

    fun operations(): OperationsApi {
        val client = client()
        return cachedOperations ?: client.createService(OperationsApi::class.java).also { cachedOperations = it }
    }

    fun warehouses(): WarehousesApi {
        val client = client()
        return cachedWarehouses ?: client.createService(WarehousesApi::class.java).also { cachedWarehouses = it }
    }

    fun fbs(): FbsApi {
        val client = client()
        return cachedFbs ?: client.createService(FbsApi::class.java).also { cachedFbs = it }
    }
}
