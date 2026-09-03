package ru.wms.tsd.core.api

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import ru.wms.tsd.core.api.BaseUrlValidationException.CleartextNotAllowed
import ru.wms.tsd.core.api.BaseUrlValidationException.Empty
import ru.wms.tsd.core.api.BaseUrlValidationException.InvalidFormat
import ru.wms.tsd.core.api.BaseUrlValidationException.InvalidScheme
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.security.cert.CertificateException
import javax.net.ssl.SSLHandshakeException

class BaseUrlTest {
    @Test
    fun `normalize adds trailing slash`() {
        assertEquals("https://example.com/api/", normalizeBaseUrl("https://example.com/api"))
        assertEquals("https://example.com/api/", normalizeBaseUrl("https://example.com/api/"))
    }

    @Test
    fun `release accepts https and normalizes`() {
        val result = validateAndNormalizeBaseUrl(
            "https://web-production-9e7c1.up.railway.app/api",
            allowCleartext = false,
        )
        assertTrue(result.isSuccess)
        assertEquals("https://web-production-9e7c1.up.railway.app/api/", result.getOrNull())
    }

    @Test
    fun `release rejects http`() {
        val result = validateAndNormalizeBaseUrl("http://example.com/", allowCleartext = false)
        assertTrue(result.isFailure)
        assertEquals(CleartextNotAllowed, result.exceptionOrNull())
    }

    @Test
    fun `debug allows loopback cleartext hosts only`() {
        val allowed = listOf(
            "http://10.0.2.2:18080",
            "http://localhost:18080/",
            "http://127.0.0.1:18080/",
            "http://[::1]:18080/",
        )
        allowed.forEach { url ->
            val result = validateAndNormalizeBaseUrl(url, allowCleartext = true)
            assertTrue("Expected $url to pass", result.isSuccess)
        }
        assertEquals(
            CleartextNotAllowed,
            validateAndNormalizeBaseUrl("http://192.168.0.5/", allowCleartext = true).exceptionOrNull(),
        )
        assertEquals(
            CleartextNotAllowed,
            validateAndNormalizeBaseUrl("http://example.com/", allowCleartext = true).exceptionOrNull(),
        )
    }

    @Test
    fun `empty and invalid schemes fail`() {
        assertEquals(Empty, validateAndNormalizeBaseUrl("  ", false).exceptionOrNull())
        assertEquals(InvalidScheme, validateAndNormalizeBaseUrl("ftp://x/", false).exceptionOrNull())
        assertEquals(InvalidFormat, validateAndNormalizeBaseUrl("://missing-host", false).exceptionOrNull())
        assertEquals(InvalidScheme, validateAndNormalizeBaseUrl("not-a-url", false).exceptionOrNull())
    }

    @Test
    fun `rejects credentials query fragment and invalid port`() {
        assertEquals(
            InvalidFormat,
            validateAndNormalizeBaseUrl("https://user:pass@example.com/api", false).exceptionOrNull(),
        )
        assertEquals(
            InvalidFormat,
            validateAndNormalizeBaseUrl("https://example.com/api?x=1", false).exceptionOrNull(),
        )
        assertEquals(
            InvalidFormat,
            validateAndNormalizeBaseUrl("https://example.com/api#frag", false).exceptionOrNull(),
        )
        assertEquals(
            InvalidFormat,
            validateAndNormalizeBaseUrl("https://example.com:70000/api", false).exceptionOrNull(),
        )
    }
}

class NetworkFailureTest {
    @Test
    fun `classifies http statuses`() {
        assertEquals(NetworkFailure.InvalidCredentials, classifyHttpStatus(401, forLogin = true))
        assertEquals(NetworkFailure.AccessForbidden, classifyHttpStatus(403, forLogin = true))
        assertEquals(NetworkFailure.InvalidLoginForm, classifyHttpStatus(422, forLogin = true))
        assertEquals(NetworkFailure.Http404, classifyHttpStatus(404))
        assertEquals(NetworkFailure.Http429, classifyHttpStatus(429))
        assertEquals(NetworkFailure.Http5xx, classifyHttpStatus(503))
        assertEquals(NetworkFailure.InvalidResponse, classifyHttpStatus(400))
    }

    @Test
    fun `classifies throwables without leaking messages`() {
        assertEquals(NetworkFailure.DnsFailure, classifyThrowable(UnknownHostException("secret.host")))
        assertEquals(NetworkFailure.Timeout, classifyThrowable(SocketTimeoutException("slow")))
        assertEquals(NetworkFailure.ConnectionRefused, classifyThrowable(ConnectException("refused")))
        assertEquals(NetworkFailure.TlsFailure, classifyThrowable(SSLHandshakeException("bad cert")))
    }

    @Test
    fun `classifies nested tls dns timeout and connection failures from chain`() {
        val certCause = CertificateException("bad cert")
        val sslOuter = SSLHandshakeException("handshake").apply { initCause(certCause) }
        assertEquals(NetworkFailure.TlsFailure, classifyThrowable(sslOuter))

        val dnsInner = UnknownHostException("dns")
        val connOuter = ConnectException("conn").apply { initCause(dnsInner) }
        assertEquals(NetworkFailure.ConnectionRefused, classifyThrowable(connOuter))

        val timeoutInner = SocketTimeoutException("slow")
        val genericOuter = Exception("wrapper").apply { initCause(timeoutInner) }
        assertEquals(NetworkFailure.Timeout, classifyThrowable(genericOuter))
    }

    @Test
    fun `causal cycle terminates without infinite loop`() {
        val root = UnknownHostException("dns")
        val middle = ConnectException("conn").apply { initCause(root) }
        val outer = SSLHandshakeException("tls").apply { initCause(middle) }
        root.initCause(outer)

        assertEquals(NetworkFailure.TlsFailure, classifyThrowable(outer))
        assertEquals(3, throwableChainSafe(outer).size)
    }

    @Test
    fun `connectivity hint refines only connectivity class failures`() {
        assertEquals(
            NetworkFailure.NoActiveNetwork,
            refineWithConnectivityHint(NetworkFailure.DnsFailure, hasActiveNetwork = false),
        )
        assertEquals(
            NetworkFailure.DnsFailure,
            refineWithConnectivityHint(NetworkFailure.DnsFailure, hasActiveNetwork = true),
        )
        assertEquals(
            NetworkFailure.TlsFailure,
            refineWithConnectivityHint(NetworkFailure.TlsFailure, hasActiveNetwork = false),
        )
        assertEquals(
            NetworkFailure.Http5xx,
            refineWithConnectivityHint(NetworkFailure.Http5xx, hasActiveNetwork = false),
        )
        assertEquals(
            NetworkFailure.InvalidResponse,
            refineWithConnectivityHint(NetworkFailure.InvalidResponse, hasActiveNetwork = false),
        )
    }

    @Test
    fun `operator messages are concise Russian with safe codes`() {
        allNetworkFailures().forEach { failure ->
            val message = failure.toOperatorMessage()
            failure.assertSafeOperatorMessage()
            assertFalse(message.contains("http://"))
            assertFalse(message.contains("https://"))
            assertFalse(message.contains("Exception"))
            assertTrue(message.contains(failure.diagnosticCode))
        }
    }
}

class HealthBodyValidationTest {
    @Test
    fun `accepts only documented health contract`() {
        assertTrue(isValidHealthBody("""{"status":"ok"}"""))
        assertTrue(isValidHealthBody("  {\"status\":\"ok\"}  "))
        assertFalse(isValidHealthBody("""{"status":"OK"}"""))
        assertFalse(isValidHealthBody("<html>ok</html>"))
        assertFalse(isValidHealthBody(""))
        assertFalse(isValidHealthBody(null))
    }
}

private fun allNetworkFailures(): List<NetworkFailure> = listOf(
    NetworkFailure.InvalidCredentials,
    NetworkFailure.InvalidLoginForm,
    NetworkFailure.AccessForbidden,
    NetworkFailure.InvalidUrl,
    NetworkFailure.NoActiveNetwork,
    NetworkFailure.DnsFailure,
    NetworkFailure.ConnectionRefused,
    NetworkFailure.Timeout,
    NetworkFailure.TlsFailure,
    NetworkFailure.Http404,
    NetworkFailure.Http429,
    NetworkFailure.Http5xx,
    NetworkFailure.InvalidResponse,
    NetworkFailure.StorageFailure,
    NetworkFailure.Unknown,
)
