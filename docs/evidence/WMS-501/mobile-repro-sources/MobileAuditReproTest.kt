package ru.wms.tsd.audit

import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.async
import kotlinx.coroutines.withContext
import kotlinx.coroutines.test.*
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.Assert.*
import retrofit2.Response
import java.util.UUID
import ru.wms.tsd.core.api.ApiProvider
import ru.wms.tsd.core.api.generated.apis.OperationsApi
import ru.wms.tsd.core.api.generated.models.*
import ru.wms.tsd.core.auth.*
import ru.wms.tsd.core.scanner.*
import ru.wms.tsd.features.inbound.InboundReceivingViewModel
import ru.wms.tsd.ui.patterns.ScanFlash

/** Assertions describe reproduced current behavior, not acceptance of defects. */
@OptIn(ExperimentalCoroutinesApi::class)
class MobileAuditReproTest {
    @Before fun before() { Dispatchers.setMain(UnconfinedTestDispatcher()) }
    @After fun after() { Dispatchers.resetMain() }

    @Test fun managerDropsBurstWhenCollectorHasNotResumed() = runTest {
        val manager = ScannerManager()
        val received = mutableListOf<String>()
        backgroundScope.launch { manager.scans.collect { received += it.barcode } }
        runCurrent()
        repeat(20) { manager.submit("CODE-$it", ScanSource.DEV) }
        runCurrent()
        assertEquals(listOf("CODE-0"), received)
        println("REPRO manager: 20 synchronous submissions; 1 delivered, 19 absent")
    }

    @Test fun wedgeSingleEightyMillisecondGapEmitsTruncatedBarcode() = runTest {
        val manager = ScannerManager()
        val acc = WedgeKeyAccumulator(manager)
        val received = mutableListOf<String>()
        backgroundScope.launch { manager.scans.collect { received += it.barcode } }
        runCurrent()
        var t = 1000L
        "4630452635503".forEachIndexed { index, ch ->
            if (index == 3) t += 80
            acc.feedChar(ch, t)
            t += 10
        }
        assertTrue(acc.feedEnter(t))
        runCurrent()
        assertEquals(listOf("0452635503"), received)
        println("REPRO wedge: 4630452635503 with one 80ms gap -> 0452635503")
    }

    private val rid = UUID.fromString("aaaaaaaa-1111-2222-3333-444444444444")
    private fun line() = InboundIntakeLineOut(
        id="line-1", productId="product-1", skuCode="SKU", productName="Audit",
        expectedQty=100, actualQty=1, postedQty=0,
        storageLocationId=null, storageLocationCode=null, effectiveActualQty=null,
    )
    private fun request() = InboundIntakeRequestOut(
        id=rid.toString(), warehouseId="warehouse-1", status="receiving",
        lines=listOf(line()), boxes=emptyList(),
    )
    private fun fixture(): Pair<InboundReceivingViewModel, OperationsApi> {
        val ops = mockk<OperationsApi>()
        val api = mockk<ApiProvider> { every { operations() } returns ops }
        coEvery { ops.getInboundRequestOperationsInboundIntakeRequestsRequestIdGet(rid) } returns Response.success(request())
        return InboundReceivingViewModel(rid, api).also { it.setLooseMode(true) } to ops
    }

    @Test fun receivingQueueSilentlyDropsBeyondSixteenPending() = runTest {
        val (vm, ops) = fixture()
        val release = CompletableDeferred<Unit>()
        var calls = 0
        coEvery { ops.scanBarcodeToLooseIntakeOperationsInboundIntakeRequestsRequestIdReceivingScanPost(rid, any()) } coAnswers {
            calls++
            if (calls == 1) release.await()
            Response.success(line())
        }
        repeat(30) { vm.onScan("SKU") }
        assertEquals(1, calls)
        release.complete(Unit)
        assertEquals(17, calls)
        coVerify(exactly=18) { ops.getInboundRequestOperationsInboundIntakeRequestsRequestIdGet(rid) }
        println("REPRO receiving: 30 accepted onScan calls, first API held; 17 POSTs, 13 dropped; 18 GETs incl initial")
    }

    @Test fun completeDoesNotWaitForInflightOrQueuedScans() = runTest {
        val (vm, ops) = fixture()
        val release = CompletableDeferred<Unit>()
        var scansReturned = 0
        coEvery { ops.scanBarcodeToLooseIntakeOperationsInboundIntakeRequestsRequestIdReceivingScanPost(rid, any()) } coAnswers {
            release.await(); scansReturned++; Response.success(line())
        }
        coEvery { ops.completeInboundReceivingOperationsInboundIntakeRequestsRequestIdCompleteReceivingPost(rid) } returns Response.success(request())
        vm.onScan("SKU"); vm.onScan("SKU")
        var navigated = false
        vm.confirmComplete { navigated = true }
        assertTrue(navigated)
        assertEquals(0, scansReturned)
        release.complete(Unit)
        assertEquals(2, scansReturned)
        println("REPRO receiving: completion callback ran before either scan response returned")
    }

    @Test fun refreshFailureKeepsOldFactWithSuccessFlash() = runTest {
        val (vm, ops) = fixture()
        coEvery { ops.scanBarcodeToLooseIntakeOperationsInboundIntakeRequestsRequestIdReceivingScanPost(rid, any()) } returns Response.success(line().copy(actualQty=2))
        coEvery { ops.getInboundRequestOperationsInboundIntakeRequestsRequestIdGet(rid) } throws java.io.IOException("audit simulated readback outage")
        vm.onScan("SKU")
        assertTrue(vm.state.value.flash is ScanFlash.Success)
        assertEquals(1, vm.state.value.request!!.lines.first().actualQty)
        assertNull(vm.state.value.loadError)
        println("REPRO receiving: POST returns qty2, GET fails; UI retains qty1 and success flash without readback error")
    }

    @Test fun lateExpiryNotificationInvalidatesNewlySelectedEmployee() {
        val store = mockk<AuthStore>(relaxed=true)
        every { store.getSavedStaff() } returns listOf(
            SavedStaff("a@audit.invalid", "A", "FAKE-A", "1111"),
            SavedStaff("b@audit.invalid", "B", "FAKE-B", "2222"),
        )
        val manager = AuthManager(store, mockk())
        manager.loginWithPin("a@audit.invalid", "1111").getOrThrow()
        // ApiProvider captured A on an in-flight HTTP request. Operator now switches to B.
        manager.logout()
        manager.loginWithPin("b@audit.invalid", "2222").getOrThrow()
        // Existing interceptor passes no token/session identity with its delayed 401.
        manager.notifySessionExpired()
        assertNull(manager.getCurrentSession())
        io.mockk.verify(exactly=1) { store.invalidateToken("b@audit.invalid") }
        println("REPRO auth state: unscoped late expiry after A->B invalidates B")
    }
    @Test fun delayedHttp401FromAInvalidatesNewSessionB() = runTest {
        val started = java.util.concurrent.CountDownLatch(1)
        val release = java.util.concurrent.CountDownLatch(1)
        val server = okhttp3.mockwebserver.MockWebServer()
        server.dispatcher = object : okhttp3.mockwebserver.Dispatcher() {
            override fun dispatch(request: okhttp3.mockwebserver.RecordedRequest): okhttp3.mockwebserver.MockResponse {
                started.countDown()
                check(release.await(10, java.util.concurrent.TimeUnit.SECONDS))
                return okhttp3.mockwebserver.MockResponse().setResponseCode(401).setBody("{}")
            }
        }
        server.start()
        try {
            val store = mockk<AuthStore>(relaxed=true)
            every { store.getBaseUrl() } returns server.url("/").toString()
            every { store.getSavedStaff() } returns listOf(
                SavedStaff("a@audit.invalid", "A", "FAKE-A", "1111"),
                SavedStaff("b@audit.invalid", "B", "FAKE-B", "2222"),
            )
            val manager = AuthManager(store, mockk())
            manager.loginWithPin("a@audit.invalid", "1111").getOrThrow()
            val api = ApiProvider(store, manager)
            val request = async(Dispatchers.IO) {
                api.operations().getInboundRequestOperationsInboundIntakeRequestsRequestIdGet(rid)
            }
            withContext(Dispatchers.IO) { check(started.await(10, java.util.concurrent.TimeUnit.SECONDS)) }
            manager.logout()
            manager.loginWithPin("b@audit.invalid", "2222").getOrThrow()
            release.countDown()
            assertEquals(401, request.await().code())
            assertNull(manager.getCurrentSession())
            io.mockk.verify(exactly=1) { store.invalidateToken("b@audit.invalid") }
            println("REPRO real localhost HTTP: A request delayed401 after login B; B invalidated")
        } finally { release.countDown(); server.shutdown() }
    }

}
