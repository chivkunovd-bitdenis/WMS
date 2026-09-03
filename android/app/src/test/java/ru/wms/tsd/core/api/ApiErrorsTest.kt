package ru.wms.tsd.core.api

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Test
import retrofit2.Response

class ApiErrorsTest {
    @Test
    fun readsFbsErrorEnvelopeMessage() {
        val body = """{"detail":{"code":"wrong_location","message":"Ячейка не подходит","context":{},"retryable":false}}"""
            .toResponseBody("application/json".toMediaType())
        val response = Response.error<Unit>(400, body)

        assertEquals("Ячейка не подходит", response.readableError())
    }

    @Test
    fun keepsLegacyStringCodeTranslation() {
        val body = """{"detail":"barcode_unknown"}"""
            .toResponseBody("application/json".toMediaType())
        val response = Response.error<Unit>(400, body)

        assertEquals("Штрихкод не найден в этой заявке", response.readableError())
    }
}
