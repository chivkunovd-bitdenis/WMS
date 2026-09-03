package ru.wms.tsd.features.outbound

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
import ru.wms.tsd.core.api.generated.models.MarketplaceUnloadRequestSummaryOut

/**
 * Юнит-тесты OutboundListViewModel: фильтрация список отгрузок по confirmed и collecting статусам
 */
@OptIn(ExperimentalCoroutinesApi::class)
class OutboundListViewModelTest {

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
        MarketplaceUnloadRequestSummaryOut(
            id = id,
            warehouseId = warehouseId,
            warehouseName = "Склад 1",
            status = status,
            createdAt = "2026-07-06T00:00:00Z",
        )

    private fun <T> err(code: Int = 500, msg: String = "Server error"): Response<T> =
        Response.error(code, msg.toResponseBody())

    @Test
    fun testFiltersOnlyConfirmedAndCollecting() = runTest {
        val allRequests = listOf(
            request("confirmed"),      // должен быть
            request("collecting"),     // должен быть
            request("shipped"),        // не должен быть
            request("draft"),          // не должен быть
            request("submitted"),      // не должен быть
            request("cancelled"),      // не должен быть
        )

        coEvery { ops.listMarketplaceUnloadsOperationsMarketplaceUnloadRequestsGet() } returns
            Response.success(allRequests)

        val vm = OutboundListViewModel(api)
        advanceUntilIdle()

        val state = vm.state.value
        assertEquals("Фильтр applied, только 2 заявки в очереди", 2, state.requests.size)
        assertTrue("Первая заявка confirmed", state.requests[0].status == "confirmed")
        assertTrue("Все заявки имеют статус confirmed или collecting",
            state.requests.all { it.status == "confirmed" || it.status == "collecting" })
        assertNull("Ошибка отсутствует при успешном ответе", state.error)
    }

    @Test
    fun testNetworkErrorHandling() = runTest {
        coEvery { ops.listMarketplaceUnloadsOperationsMarketplaceUnloadRequestsGet() } returns
            err(500, "Network error")

        val vm = OutboundListViewModel(api)
        advanceUntilIdle()

        val state = vm.state.value
        assertNotNull("Ошибка установлена", state.error)
        assertEquals("Список заявок пуст", 0, state.requests.size)
        assertEquals("Loading завершился", false, state.loading)
    }
}
