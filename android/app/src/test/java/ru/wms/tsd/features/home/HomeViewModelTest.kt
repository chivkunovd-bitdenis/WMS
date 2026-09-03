package ru.wms.tsd.features.home

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
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import retrofit2.Response
import ru.wms.tsd.core.api.ApiProvider
import ru.wms.tsd.core.api.fbs.FbsApi
import ru.wms.tsd.core.api.fbs.FbsWorklistResponse
import ru.wms.tsd.core.api.generated.apis.OperationsApi
import ru.wms.tsd.core.api.generated.models.InboundIntakeRequestSummaryOut
import ru.wms.tsd.core.api.generated.models.MarketplaceUnloadRequestSummaryOut

/**
 * Юнит-тесты HomeViewModel: загрузка counts из двух запросов и фильтрация заявок по статусам
 */
@OptIn(ExperimentalCoroutinesApi::class)
class HomeViewModelTest {

    private val warehouseId = "bbbbbbbb-0000-0000-0000-000000000002"

    private lateinit var ops: OperationsApi
    private lateinit var api: ApiProvider
    private lateinit var fbs: FbsApi

    @Before
    fun setUp() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
        ops = mockk()
        fbs = mockk()
        api = mockk {
            every { operations() } returns ops
            every { fbs() } returns fbs
        }
        coEvery { fbs.worklist(any(), any(), any()) } returns
            Response.success(FbsWorklistResponse(emptyList(), "2026-09-04T00:00:00Z"))
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun inboundRequest(status: String, id: String = UUID.randomUUID().toString()) =
        InboundIntakeRequestSummaryOut(
            id = id,
            warehouseId = warehouseId,
            status = status,
            lineCount = 5,
            createdAt = "2026-07-06T00:00:00Z",
            sortingRemainingQty = if (status == "sorting" || status == "verified") 10 else 0,
        )

    private fun outboundRequest(status: String, id: String = UUID.randomUUID().toString()) =
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
    fun testBothRequestsSuccess() = runTest {
        val inboundRequests = listOf(
            inboundRequest("submitted"),      // inbound: 1
            inboundRequest("receiving"),      // inbound: 1
            inboundRequest("sorting"),        // sorting: 1 (+ sortingRemainingQty > 0)
            inboundRequest("verified"),       // sorting: 1 (+ sortingRemainingQty > 0)
            inboundRequest("done"),           // не считаем
            inboundRequest("draft"),          // не считаем
        )

        val outboundRequests = listOf(
            outboundRequest("confirmed"),    // outbound: 1
            outboundRequest("collecting"),   // outbound: 1
            outboundRequest("shipped"),      // не считаем
            outboundRequest("draft"),        // не считаем
        )

        coEvery { ops.listInboundRequestsOperationsInboundIntakeRequestsGet() } returns
            Response.success(inboundRequests)
        coEvery { ops.listMarketplaceUnloadsOperationsMarketplaceUnloadRequestsGet() } returns
            Response.success(outboundRequests)

        val vm = HomeViewModel(api)
        vm.load()
        advanceUntilIdle()

        val counts = vm.counts.value
        assertEquals("Инбаунд: submitted + receiving", 2, counts.inbound)
        assertEquals("Сортировка: sorting/verified с sortingRemainingQty > 0", 2, counts.sorting)
        assertEquals("Аутбаунд: confirmed + collecting", 2, counts.outbound)
    }

    @Test
    fun testOutboundErrorInboundSuccess() = runTest {
        val inboundRequests = listOf(
            inboundRequest("submitted"),
            inboundRequest("sorting"),
        )

        coEvery { ops.listInboundRequestsOperationsInboundIntakeRequestsGet() } returns
            Response.success(inboundRequests)
        coEvery { ops.listMarketplaceUnloadsOperationsMarketplaceUnloadRequestsGet() } returns
            err(500)

        val vm = HomeViewModel(api)
        vm.load()
        advanceUntilIdle()

        val counts = vm.counts.value
        assertEquals("Инбаунд посчитан", 1, counts.inbound)
        assertEquals("Сортировка посчитана (sorting с sortingRemainingQty > 0)", 1, counts.sorting)
        assertNull("Аутбаунд остался null после ошибки", counts.outbound)
    }

    @Test
    fun testInboundErrorOutboundSuccess() = runTest {
        val outboundRequests = listOf(
            outboundRequest("confirmed"),
            outboundRequest("collecting"),
        )

        coEvery { ops.listInboundRequestsOperationsInboundIntakeRequestsGet() } returns
            err(500)
        coEvery { ops.listMarketplaceUnloadsOperationsMarketplaceUnloadRequestsGet() } returns
            Response.success(outboundRequests)

        val vm = HomeViewModel(api)
        vm.load()
        advanceUntilIdle()

        val counts = vm.counts.value
        // После ошибки inbound/sorting остаются null (начальные значения)
        assertNull("Инбаунд остался null после ошибки приёмки", counts.inbound)
        assertNull("Сортировка остались null после ошибки приёмки", counts.sorting)
        assertEquals("Аутбаунд посчитан успешно", 2, counts.outbound)
    }
}
