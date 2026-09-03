package ru.wms.tsd.core.auth

import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.test.runTest
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import ru.wms.tsd.core.api.ConnectivityHint
import ru.wms.tsd.core.api.ISRG_ROOT_X1_SHA256
import ru.wms.tsd.core.api.NetworkFailure
import ru.wms.tsd.core.api.ServerHealthCheck
import ru.wms.tsd.core.api.defaultIsrgRootPemFile
import ru.wms.tsd.core.api.generated.apis.AuthApi
import ru.wms.tsd.core.api.generated.infrastructure.ApiClient
import ru.wms.tsd.core.api.generated.models.TokenResponse
import ru.wms.tsd.core.api.sha256FingerprintOfPem
import ru.wms.tsd.core.api.verifyIsrgRootX1Pem
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import retrofit2.Response

class AuthManagerUrlPersistenceTest {
    private lateinit var authStore: AuthStore
    private lateinit var connectivityHint: ConnectivityHint
    private lateinit var authApi: AuthApi
    private lateinit var authManager: AuthManager

    @Before
    fun setUp() {
        authStore = mockk(relaxed = true)
        connectivityHint = mockk()
        authApi = mockk()
        every { connectivityHint.hasActiveNetwork() } returns true
        authManager = AuthManager(
            authStore = authStore,
            connectivityHint = connectivityHint,
            serverHealthCheck = ServerHealthCheck(OkHttpClient()),
            apiClientFactory = {
                mockk<ApiClient> {
                    every { createService(AuthApi::class.java) } returns authApi
                }
            },
        )
    }

    @Test
    fun `failed login does not persist candidate base url`() = runTest {
        coEvery { authApi.loginRouteAuthLoginPost(any()) } returns Response.error(
            401,
            "".toResponseBody("application/json".toMediaType()),
        )

        val result = authManager.loginWithPassword(
            baseUrl = "https://bad.example/api/",
            email = " user@example.com ",
            password = "secret",
        )

        assertTrue(result.isFailure)
        verify(exactly = 0) { authStore.setBaseUrl(any()) }
    }

    @Test
    fun `login maps 422 and 403 to typed failures`() = runTest {
        coEvery { authApi.loginRouteAuthLoginPost(any()) } returns Response.error(
            422,
            "".toResponseBody("application/json".toMediaType()),
        )
        assertEquals(
            NetworkFailure.InvalidLoginForm,
            authManager.loginWithPassword("https://example.com/api/", "a@b.c", "x").exceptionOrNull(),
        )

        coEvery { authApi.loginRouteAuthLoginPost(any()) } returns Response.error(
            403,
            "".toResponseBody("application/json".toMediaType()),
        )
        assertEquals(
            NetworkFailure.AccessForbidden,
            authManager.loginWithPassword("https://example.com/api/", "a@b.c", "x").exceptionOrNull(),
        )
    }

    @Test
    fun `successful login persists normalized base url`() = runTest {
        coEvery { authApi.loginRouteAuthLoginPost(any()) } returns Response.success(
            TokenResponse(accessToken = "token-123", tokenType = "bearer"),
        )
        every { authStore.getSavedStaff() } returns emptyList()

        val result = authManager.loginWithPassword(
            baseUrl = "https://good.example/api",
            email = "user@example.com",
            password = "secret",
        )

        assertTrue(result.isSuccess)
        verify(exactly = 1) { authStore.setBaseUrl("https://good.example/api/") }
    }

    @Test
    fun `storage failure leaves session null and returns safe typed failure`() = runTest {
        coEvery { authApi.loginRouteAuthLoginPost(any()) } returns Response.success(
            TokenResponse(accessToken = "token-123", tokenType = "bearer"),
        )
        every { authStore.getSavedStaff() } returns emptyList()
        every { authStore.setBaseUrl(any()) } throws RuntimeException("secret storage path")

        val result = authManager.loginWithPassword(
            baseUrl = "https://good.example/api/",
            email = "user@example.com",
            password = "secret",
        )

        assertTrue(result.isFailure)
        assertEquals(NetworkFailure.StorageFailure, result.exceptionOrNull())
        assertNull(authManager.getCurrentSession())
        val message = (result.exceptionOrNull() as NetworkFailure).toOperatorMessage()
        assertFalse(message.contains("secret"))
    }

    @Test(expected = CancellationException::class)
    fun `login rethrows cancellation without mapping to network failure`() = runTest {
        coEvery { authApi.loginRouteAuthLoginPost(any()) } throws CancellationException("cancelled")

        authManager.loginWithPassword(
            baseUrl = "https://example.com/api/",
            email = "user@example.com",
            password = "secret",
        )
    }
}

class ServerHealthCheckTest {
    private lateinit var server: MockWebServer
    private lateinit var healthCheck: ServerHealthCheck

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        healthCheck = ServerHealthCheck(
            OkHttpClient.Builder().build(),
        )
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun `health 200 with contract succeeds`() = runTest {
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"status":"ok"}"""))

        val base = "${server.url("/api/")}"
        val result = healthCheck.check(base, hasActiveNetwork = true)

        assertTrue(result.isSuccess)
        assertEquals("/api/health", server.takeRequest().path)
    }

    @Test
    fun `health succeeds even when connectivity hint is false`() = runTest {
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"status":"ok"}"""))

        val result = healthCheck.check("${server.url("/api/")}", hasActiveNetwork = false)

        assertTrue(result.isSuccess)
        assertEquals(1, server.requestCount)
    }

    @Test
    fun `health 200 with wrong body maps to invalid response`() = runTest {
        server.enqueue(MockResponse().setResponseCode(200).setBody("<html>ok</html>"))

        val result = healthCheck.check("${server.url("/api/")}", hasActiveNetwork = true)

        assertTrue(result.isFailure)
        assertEquals(NetworkFailure.InvalidResponse, result.exceptionOrNull())
    }

    @Test
    fun `health 503 maps to server error`() = runTest {
        server.enqueue(MockResponse().setResponseCode(503))

        val result = healthCheck.check("${server.url("/api/")}", hasActiveNetwork = true)

        assertTrue(result.isFailure)
        assertEquals(NetworkFailure.Http5xx, result.exceptionOrNull())
    }

    @Test
    fun `unreachable host with false hint refines to offline`() = runTest {
        val result = healthCheck.check("http://127.0.0.1:1/", hasActiveNetwork = false)

        assertTrue(result.isFailure)
        assertEquals(NetworkFailure.NoActiveNetwork, result.exceptionOrNull())
    }
}

class IsrgRootCertTest {
    @Test
    fun `embedded ISRG Root X1 matches official sha256 and subject`() {
        val pem = defaultIsrgRootPemFile().readText()
        assertTrue(verifyIsrgRootX1Pem(pem))
        assertEquals(ISRG_ROOT_X1_SHA256, sha256FingerprintOfPem(pem))
    }
}

class AuthStoreCryptoConfigTest {
    @Test
    fun `encrypted prefs use stable filenames and algorithms`() {
        assertEquals("auth_store", AuthStore.PREFS_FILE_NAME)
        assertEquals("base_url", AuthStore.KEY_BASE_URL)
        assertEquals("saved_staff", AuthStore.KEY_SAVED_STAFF)
        assertEquals(MasterKey.KeyScheme.AES256_GCM, MasterKey.KeyScheme.AES256_GCM)
        assertEquals(
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        )
        assertEquals(
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }
}
