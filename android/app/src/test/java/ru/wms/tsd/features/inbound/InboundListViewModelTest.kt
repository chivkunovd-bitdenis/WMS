package ru.wms.tsd.features.inbound

import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Response
import ru.wms.tsd.core.api.ApiProvider
import ru.wms.tsd.core.api.generated.apis.OperationsApi
import ru.wms.tsd.core.api.generated.models.InboundIntakeRequestSummaryOut

/**
 * Юнит-тесты InboundListViewModel: фильтрация очереди приёмки по submitted и receiving статусам
 */
@OptIn(ExperimentalCoroutinesApi::class)
class InboundListViewModelTest {

    private val warehouseId = "bbbbbbbb-0000-0000-0000-000000000002"

    private lateinit var ops: OperationsApi
    private lateinit var api: ApiProvider

    @Before
    fun setUp() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
        ops = mockk()
        api = mockk {
            every { operations() } returns ops
        }
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun request(status: String, id: String = UUID.randomUUID().toString()) =
        InboundIntakeRequestSummaryOut(
            id = id,
            warehouseId = warehouseId,
            status = status,
            lineCount = 5,
            createdAt = "2026-07-06T00:00:00Z",
        )

    private fun <T> err(code: Int = 500, msg: String = "Server error"): Response<T> =
        Response.error(code, msg.toResponseBody())

    @Test
    fun testFiltersOnlySubmittedAndReceiving() = runTest {
        val allRequests = listOf(
            request("submitted"),           // должен быть
            request("receiving"),           // должен быть
            request("primary_accepted"),    // должен быть (receiving-статус)
            request("verifying"),           // должен быть (receiving-статус)
            request("sorting"),             // не должен быть
            request("verified"),            // не должен быть
            request("done"),                // не должен быть
            request("draft"),               // не должен быть
        )

        coEvery { ops.listInboundRequestsOperationsInboundIntakeRequestsGet() } returns
            Response.success(allRequests)

        val vm = InboundListViewModel(api)
        advanceUntilIdle()

        val state = vm.state.value
        assertEquals("Фильтр applied, только 4 заявки в очереди", 4, state.requests.size)
        assertTrue("Первая заявка submitted", state.requests[0].status == "submitted")
        assertTrue("Все заявки имеют статус submitted или receiving-related",
            state.requests.all { it.status == "submitted" || isReceivingStatus(it.status) })
        assertNull("Ошибка отсутствует при успешном ответе", state.error)
    }

    @Test
    fun testNetworkErrorHandling() = runTest {
        coEvery { ops.listInboundRequestsOperationsInboundIntakeRequestsGet() } returns
            err(500, "Network error")

        val vm = InboundListViewModel(api)
        advanceUntilIdle()

        val state = vm.state.value
        assertNotNull("Ошибка установлена", state.error)
        assertEquals("Список заявок пуст", 0, state.requests.size)
        assertEquals("Loading завершился", false, state.loading)
    }
}
