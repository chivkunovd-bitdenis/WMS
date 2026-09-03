package ru.wms.tsd.core.auth

import ru.wms.tsd.BuildConfig
import ru.wms.tsd.core.api.ConnectivityHint
import ru.wms.tsd.core.api.NetworkFailure
import ru.wms.tsd.core.api.ServerHealthCheck
import ru.wms.tsd.core.api.classifyHttpStatus
import ru.wms.tsd.core.api.classifyThrowable
import ru.wms.tsd.core.api.generated.apis.AuthApi
import ru.wms.tsd.core.api.generated.infrastructure.ApiClient
import ru.wms.tsd.core.api.generated.models.LoginBody
import ru.wms.tsd.core.api.loginApiClient
import ru.wms.tsd.core.api.refineWithConnectivityHint
import ru.wms.tsd.core.api.toNetworkFailure
import ru.wms.tsd.core.api.validateAndNormalizeBaseUrl
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.withContext

/**
 * Модель текущей сессии.
 */
data class AuthSession(
    val email: String,
    val displayName: String,
    val token: String,
)

/**
 * Управление текущей сессией авторизации.
 * Методы: loginWithPassword (проверка на сервере), loginWithPin (локально),
 * logout (очистка текущей сессии).
 */
class AuthManager(
    private val authStore: AuthStore,
    private val connectivityHint: ConnectivityHint,
    private val serverHealthCheck: ServerHealthCheck = ServerHealthCheck(),
    private val apiClientFactory: (String) -> ApiClient = ::loginApiClient,
) {
    private var currentSession: AuthSession? = null

    /** Сигнал «токен протух» (401 от API) — UI разлогинивает на экран входа. */
    private val _sessionExpired = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
    val sessionExpired: SharedFlow<Unit> = _sessionExpired

    fun getCurrentSession(): AuthSession? = currentSession

    fun isLoggedIn(): Boolean = currentSession != null

    fun getWorkingBaseUrl(): String =
        authStore.getBaseUrl() ?: BuildConfig.DEFAULT_API_BASE_URL

    /**
     * Вызывается интерсептором при 401: токен мёртв. Инвалидируем его у
     * сохранённого сотрудника (PIN-вход потребует пароль) и шлём сигнал UI.
     */
    fun notifySessionExpired() {
        val session = currentSession ?: return
        authStore.invalidateToken(session.email)
        currentSession = null
        _sessionExpired.tryEmit(Unit)
    }

    /**
     * Вход по email+пароль через API.
     * При успехе сохраняет в currentSession и только тогда — base URL.
     */
    suspend fun loginWithPassword(
        baseUrl: String,
        email: String,
        password: String,
    ): Result<AuthSession> = withContext(Dispatchers.IO) {
        val trimmedEmail = email.trim()
        val normalizedUrl = validateAndNormalizeBaseUrl(baseUrl, allowCleartext = BuildConfig.DEBUG)
            .getOrElse { throwable ->
                val failure = (throwable as? ru.wms.tsd.core.api.BaseUrlValidationException)
                    ?.toNetworkFailure()
                    ?: NetworkFailure.InvalidUrl
                return@withContext Result.failure(failure)
            }

        try {
            val apiClient = apiClientFactory(normalizedUrl)
            val authApi = apiClient.createService(AuthApi::class.java)

            val response = authApi.loginRouteAuthLoginPost(LoginBody(trimmedEmail, password))
            if (!response.isSuccessful) {
                return@withContext Result.failure(classifyHttpStatus(response.code(), forLogin = true))
            }

            val token = response.body()?.accessToken
                ?: return@withContext Result.failure(NetworkFailure.InvalidResponse)

            val session = AuthSession(
                email = trimmedEmail,
                displayName = trimmedEmail,
                token = token,
            )
            try {
                authStore.setBaseUrl(normalizedUrl)
                authStore.getSavedStaff().find { it.email == trimmedEmail }?.let {
                    authStore.saveStaff(it.copy(token = token))
                }
            } catch (_: Exception) {
                currentSession = null
                return@withContext Result.failure(NetworkFailure.StorageFailure)
            }
            currentSession = session
            Result.success(session)
        } catch (error: CancellationException) {
            throw error
        } catch (error: Exception) {
            val failure = classifyThrowable(error)
            Result.failure(
                refineWithConnectivityHint(failure, connectivityHint.hasActiveNetwork()),
            )
        }
    }

    /**
     * Проверка GET {base}/health по запросу пользователя. Кандидатный URL не сохраняется.
     */
    suspend fun checkServerConnection(baseUrl: String): Result<Unit> = withContext(Dispatchers.IO) {
        val normalizedUrl = validateAndNormalizeBaseUrl(baseUrl, allowCleartext = BuildConfig.DEBUG)
            .getOrElse { throwable ->
                val failure = (throwable as? ru.wms.tsd.core.api.BaseUrlValidationException)
                    ?.toNetworkFailure()
                    ?: NetworkFailure.InvalidUrl
                return@withContext Result.failure(failure)
            }

        serverHealthCheck.check(
            normalizedBaseUrl = normalizedUrl,
            hasActiveNetwork = connectivityHint.hasActiveNetwork(),
        )
    }

    /**
     * Вход по PIN (4 цифры) из сохранённых сотрудников.
     * Проверка локальная.
     */
    fun loginWithPin(email: String, pin: String): Result<AuthSession> {
        val staff = authStore.getSavedStaff().find { it.email == email }
            ?: return Result.failure(AuthException.StaffNotFound())

        if (staff.pin != pin) {
            return Result.failure(AuthException.InvalidPin())
        }

        if (staff.token.isEmpty()) {
            return Result.failure(AuthException.TokenExpired())
        }

        val session = AuthSession(
            email = staff.email,
            displayName = staff.displayName,
            token = staff.token,
        )
        currentSession = session
        return Result.success(session)
    }

    fun logout() {
        currentSession = null
    }
}

sealed class AuthException(message: String) : Exception(message) {
    class InvalidCredentials : AuthException("Неверный email или пароль")
    class InvalidPin : AuthException("Неверный PIN")
    class StaffNotFound : AuthException("Сотрудник не найден")
    class TokenExpired : AuthException("Сессия истекла — войдите по паролю")
}

fun Throwable.toLoginErrorMessage(): String = when (this) {
    is NetworkFailure -> toOperatorMessage()
    is AuthException -> message ?: "Ошибка авторизации"
    else -> NetworkFailure.Unknown.toOperatorMessage()
}
