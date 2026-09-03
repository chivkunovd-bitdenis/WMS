package ru.wms.tsd

import android.content.Context
import ru.wms.tsd.core.api.ApiProvider
import ru.wms.tsd.core.api.ConnectivityHint
import ru.wms.tsd.core.auth.AuthManager
import ru.wms.tsd.core.auth.AuthStore
import ru.wms.tsd.core.scanner.ScannerManager

/**
 * Ручной DI-граф приложения. Hilt намеренно не используем: приложение небольшое,
 * а простой объект проще для сопровождения и для исполнителей тикетов.
 * Новые зависимости добавляются сюда как lazy-поля.
 */
object AppGraph {
    val scannerManager: ScannerManager by lazy { ScannerManager() }

    private lateinit var authStore: AuthStore
    private lateinit var authManager: AuthManager
    private lateinit var connectivityHint: ConnectivityHint

    val apiProvider: ApiProvider by lazy {
        ApiProvider(authStore, authManager)
    }

    fun init(context: Context) {
        authStore = AuthStore(context)
        connectivityHint = ConnectivityHint(context)
        authManager = AuthManager(authStore, connectivityHint)
    }

    fun getAuthStore(): AuthStore = authStore
    fun getAuthManager(): AuthManager = authManager
}
