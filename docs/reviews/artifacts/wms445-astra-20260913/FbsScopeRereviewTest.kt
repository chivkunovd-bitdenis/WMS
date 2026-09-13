package ru.wms.tsd.features.fbs

import io.mockk.*
import java.io.IOException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.*
import org.junit.*
import org.junit.Assert.*
import retrofit2.Response
import ru.wms.tsd.core.api.ApiProvider
import ru.wms.tsd.core.api.FbsPendingScope
import ru.wms.tsd.core.api.fbs.*

@OptIn(ExperimentalCoroutinesApi::class)
class FbsScopeRereviewTest {
    private lateinit var api: FbsApi
    private lateinit var provider: ApiProvider
    private val a = FbsPendingScope("https://test.example/", "tenant-a", "a", "test-a")
    private val b = FbsPendingScope("https://test.example/", "tenant-b", "b", "test-b")
    private var currentScope = a
    private fun order(id: String) = FbsOrder(id=id, wbOrderId=id.toLong(), status="new",
        createdAt="2026-09-08T09:00:00Z", deadlineAt="2026-09-10T10:00:00Z",
        product=FbsProduct(id="product", name="Товар", barcode="4600000000001"),
        sticker=FbsSticker(status="ready"), pick=FbsPickState("pending"), pack=FbsPackState("pending"))
    @Before fun setup() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
        api = mockk()
        provider = mockk()
        every { provider.fbs() } returns api
        coEvery { provider.currentFbsPendingScope() } coAnswers { currentScope }
        coEvery { provider.pendingFbsSupplyCreate(any()) } returns null
        coEvery { provider.pendingFbsSupplyAdd(any()) } returns null
        coEvery { api.worklist(marketplace="wb", statusGroup="active") } returns Response.success(FbsWorklistResponse(serverNow="now"))
    }
    @After fun teardown() { Dispatchers.resetMain() }
    @Test fun `scope switch clears old selected order IDs`() = runTest {
        coEvery { api.orders(marketplace="wb", group="tsd_working", cursor=null) } returnsMany listOf(
            Response.success(FbsOrderPage(listOf(order("1")), "old", "now")),
            Response.success(FbsOrderPage(listOf(order("2")), null, "now")))
        val vm = FbsViewModel(provider)
        vm.loadOrders(); advanceUntilIdle(); vm.toggle(order("1"))
        assertEquals(listOf("1"), vm.state.value.orders.map { it.id })
        currentScope = b
        vm.loadOrders(append=true); advanceUntilIdle()
        assertEquals(listOf("2"), vm.state.value.orders.map { it.id })
        assertTrue("Selected A IDs remain in B scope: ${vm.state.value.selected}", vm.state.value.selected.isEmpty())
    }
    @Test fun `failed reload in new scope cannot display old tenant orders`() = runTest {
        var calls = 0
        coEvery { api.orders(marketplace="wb", group="tsd_working", cursor=null) } coAnswers {
            if (++calls == 1) Response.success(FbsOrderPage(listOf(order("1")), "old", "now"))
            else throw IOException("synthetic offline")
        }
        val vm = FbsViewModel(provider)
        vm.loadOrders(); advanceUntilIdle()
        assertEquals(listOf("1"), vm.state.value.orders.map { it.id })
        currentScope = b
        vm.loadOrders(append=true); advanceUntilIdle()
        assertNotNull(vm.state.value.error)
        assertTrue("Old tenant order IDs remain: ${vm.state.value.orders.map { it.id }}", vm.state.value.orders.isEmpty())
    }

    @Test fun `same scope refresh preserves selected work`() = runTest {
        coEvery { api.orders(marketplace="wb", group="tsd_working", cursor=null) } returns Response.success(FbsOrderPage(listOf(order("1")), null, "now"))
        val vm = FbsViewModel(provider)
        vm.loadOrders(); advanceUntilIdle(); vm.toggle(order("1"))
        vm.loadOrders(); advanceUntilIdle()
        assertEquals(setOf("1"), vm.state.value.selected)
        assertEquals(listOf("1"), vm.state.value.orders.map { it.id })
    }
    @Test fun `context changes during request discards old response`() = runTest {
        coEvery { api.orders(marketplace="wb", group="tsd_working", cursor=null) } returns Response.success(FbsOrderPage(listOf(order("1")), null, "now"))
        coEvery { api.worklist(marketplace="wb", statusGroup="active") } coAnswers {
            currentScope = b
            Response.success(FbsWorklistResponse(serverNow="now"))
        }
        val vm = FbsViewModel(provider)
        vm.loadOrders(); advanceUntilIdle()
        assertTrue(vm.state.value.orders.isEmpty())
        assertTrue(vm.state.value.supplies.isEmpty())
        assertNotNull(vm.state.value.error)
    }
}
