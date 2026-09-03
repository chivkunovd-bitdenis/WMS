package ru.wms.tsd.core.api.fbs

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface FbsApi {
    @GET("operations/fbs-supplies/worklist")
    suspend fun worklist(
        @Query("marketplace") marketplace: String = "wb",
        @Query("status_group") statusGroup: String,
        @Query("limit") limit: Int = 100,
    ): Response<FbsWorklistResponse>

    @GET("operations/fbs-supplies/{supplyId}/workspace")
    suspend fun workspace(@Path("supplyId") supplyId: String): Response<FbsWorkspace>

    @POST("operations/fbs-supplies/{supplyId}/start-work")
    suspend fun startWork(@Path("supplyId") supplyId: String): Response<FbsWorkspace>

    @POST("operations/fbs-supplies/{supplyId}/pick/scan-location")
    suspend fun scanLocation(
        @Path("supplyId") supplyId: String,
        @Body body: ScanLocationBody,
    ): Response<FbsPickLocation>

    @POST("operations/fbs-supplies/{supplyId}/pick/scan-product")
    suspend fun scanProduct(
        @Path("supplyId") supplyId: String,
        @Body body: ScanProductBody,
    ): Response<FbsWorkspace>

    @GET("operations/packaging-tasks/{taskId}")
    suspend fun packagingTask(@Path("taskId") taskId: String): Response<PackagingTask>

    @POST("operations/packaging-tasks/{taskId}/lines/{lineId}/pack")
    suspend fun pack(
        @Path("taskId") taskId: String,
        @Path("lineId") lineId: String,
        @Body body: PackProgressBody,
    ): Response<PackProgressResponse>

    @POST("operations/fbs-supplies/{supplyId}/boxes")
    suspend fun createBoxes(
        @Path("supplyId") supplyId: String,
        @Body body: CreateBoxesBody,
    ): Response<FbsWorkspace>

    @POST("operations/fbs-supplies/{supplyId}/boxes/{boxId}/orders")
    suspend fun assignOrders(
        @Path("supplyId") supplyId: String,
        @Path("boxId") boxId: String,
        @Body body: AssignOrdersBody,
    ): Response<FbsWorkspace>

    @POST("operations/fbs-supplies/{supplyId}/delivery-preflight")
    suspend fun deliveryPreflight(@Path("supplyId") supplyId: String): Response<FbsDeliveryPreflight>

    @POST("operations/fbs-supplies/{supplyId}/deliver")
    suspend fun deliver(
        @Path("supplyId") supplyId: String,
        @Body body: DeliverBody,
    ): Response<FbsWorkspace>

    @POST("operations/fbs-supplies/{supplyId}/sync-tracking")
    suspend fun syncTracking(@Path("supplyId") supplyId: String): Response<FbsWorkspace>
}
