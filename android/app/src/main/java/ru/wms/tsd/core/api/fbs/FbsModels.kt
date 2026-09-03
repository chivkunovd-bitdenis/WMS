package ru.wms.tsd.core.api.fbs

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

@Serializable
data class FbsWorklistResponse(
    val items: List<FbsSupplySummary> = emptyList(),
    @SerialName("server_now") val serverNow: String,
)

@Serializable
data class FbsSupplySummary(
    val id: String,
    @SerialName("wb_supply_id") val wbSupplyId: String? = null,
    val name: String,
    val status: String,
    val seller: FbsNamedRef,
    @SerialName("wb_warehouse") val wbWarehouse: FbsNamedRef,
    @SerialName("wms_warehouse") val wmsWarehouse: FbsNamedRef,
    @SerialName("orders_count") val ordersCount: Int,
    @SerialName("units_count") val unitsCount: Int,
    @SerialName("boxes_count") val boxesCount: Int,
    @SerialName("planned_shipment_date") val plannedShipmentDate: String? = null,
)

@Serializable
data class FbsNamedRef(
    val name: String? = null,
)

@Serializable
data class FbsWorkspace(
    val supply: FbsWorkspaceSupply,
    val stage: String,
    val progress: FbsProgress,
    val blockers: List<FbsBlocker> = emptyList(),
    val orders: List<FbsOrder> = emptyList(),
    val boxes: List<FbsBox> = emptyList(),
    @SerialName("delivery_preflight") val deliveryPreflight: FbsDeliveryPreflight? = null,
    @SerialName("tracking_summary") val trackingSummary: JsonObject? = null,
    @SerialName("wb_sync_stale") val wbSyncStale: Boolean = false,
    @SerialName("server_now") val serverNow: String,
)

@Serializable
data class FbsWorkspaceSupply(
    val id: String,
    @SerialName("wb_supply_id") val wbSupplyId: String? = null,
    val name: String,
    val status: String,
    val seller: FbsNamedRef,
    @SerialName("wb_warehouse") val wbWarehouse: FbsNamedRef,
    @SerialName("wms_warehouse") val wmsWarehouse: FbsNamedRef,
    @SerialName("planned_shipment_date") val plannedShipmentDate: String? = null,
    @SerialName("nearest_deadline_at") val nearestDeadlineAt: String,
    @SerialName("packaging_task_id") val packagingTaskId: String? = null,
)

@Serializable
data class FbsProgress(
    val picked: Int,
    val packed: Int,
    @SerialName("metadata_ready") val metadataReady: Int,
    @SerialName("stickers_ready") val stickersReady: Int,
    val total: Int,
)

@Serializable
data class FbsBlocker(
    val stage: String,
    val code: String,
    val message: String,
    @SerialName("order_id") val orderId: String? = null,
    val retryable: Boolean = false,
)

@Serializable
data class FbsOrder(
    val id: String,
    @SerialName("external_order_id") val externalOrderId: String? = null,
    @SerialName("wb_order_id") val wbOrderId: Long,
    val status: String,
    val product: FbsProduct,
    val positions: List<FbsPosition> = emptyList(),
    val sticker: FbsSticker,
    val pick: FbsPickState,
    val pack: FbsPackState,
    @SerialName("deadline_at") val deadlineAt: String,
)

@Serializable
data class FbsProduct(
    val id: String? = null,
    val name: String,
    @SerialName("seller_article") val sellerArticle: String? = null,
    val barcode: String? = null,
    val sku: String? = null,
    @SerialName("packaging_instructions") val packagingInstructions: String? = null,
)

@Serializable
data class FbsPosition(
    @SerialName("product_id") val productId: String? = null,
    val name: String,
    @SerialName("seller_article") val sellerArticle: String? = null,
    val sku: String? = null,
    val quantity: Int,
    @SerialName("picked_quantity") val pickedQuantity: Int,
)

@Serializable data class FbsSticker(val code: String? = null, val status: String)
@Serializable data class FbsPickState(val status: String, @SerialName("location_code") val locationCode: String? = null)
@Serializable data class FbsPackState(val status: String)

@Serializable
data class FbsBox(
    val id: String,
    @SerialName("box_number") val boxNumber: Int,
    val barcode: String,
    @SerialName("assigned_order_ids") val assignedOrderIds: List<String> = emptyList(),
    @SerialName("wb_trbx_id") val wbTrbxId: String? = null,
    @SerialName("without_distribution") val withoutDistribution: Boolean = false,
)

@Serializable
data class FbsPickLocation(
    val id: String,
    val code: String,
    @SerialName("warehouse_name") val warehouseName: String,
    @SerialName("expected_products") val expectedProducts: List<FbsExpectedProduct> = emptyList(),
)

@Serializable
data class FbsExpectedProduct(
    @SerialName("product_id") val productId: String,
    val name: String,
    val barcode: String? = null,
    @SerialName("remaining_qty") val remainingQty: Int,
)

@Serializable data class ScanLocationBody(@SerialName("location_barcode") val locationBarcode: String)
@Serializable data class ScanProductBody(
    @SerialName("location_id") val locationId: String,
    @SerialName("product_barcode") val productBarcode: String,
    @SerialName("order_id") val orderId: String? = null,
    @SerialName("idempotency_key") val idempotencyKey: String,
)

@Serializable
data class PackagingTask(
    val id: String,
    val status: String,
    @SerialName("is_complete") val isComplete: Boolean,
    val lines: List<PackagingLine> = emptyList(),
)

@Serializable
data class PackagingLine(
    val id: String,
    @SerialName("product_id") val productId: String,
    @SerialName("sku_code") val skuCode: String,
    @SerialName("product_name") val productName: String,
    @SerialName("packaging_instructions") val packagingInstructions: String? = null,
    @SerialName("qty_total") val qtyTotal: Int,
    @SerialName("qty_done") val qtyDone: Int,
    @SerialName("qty_need_pack") val qtyNeedPack: Int,
    @SerialName("is_complete") val isComplete: Boolean,
)

@Serializable data class PackProgressBody(
    val quantity: Int,
    @SerialName("order_id") val orderId: String? = null,
    @SerialName("idempotency_key") val idempotencyKey: String,
)

@Serializable data class PackProgressResponse(
    @SerialName("packaging_task") val packagingTask: PackagingTask,
    @SerialName("fulfilled_order") val fulfilledOrder: FulfilledOrder? = null,
    val warnings: List<String>? = null,
)

@Serializable data class FulfilledOrder(
    val id: String,
    @SerialName("wb_order_id") val wbOrderId: Long,
)

@Serializable data class CreateBoxesBody(
    val count: Int = 1,
    @SerialName("idempotency_key") val idempotencyKey: String,
    @SerialName("without_distribution") val withoutDistribution: Boolean = false,
)

@Serializable data class AssignOrdersBody(@SerialName("order_ids") val orderIds: List<String>)

@Serializable
data class FbsDeliveryPreflight(
    @SerialName("can_deliver") val canDeliver: Boolean,
    val version: String,
    @SerialName("checked_at") val checkedAt: String,
    val checks: List<FbsDeliveryCheck> = emptyList(),
)

@Serializable
data class FbsDeliveryCheck(
    val code: String,
    val message: String,
    val ok: Boolean,
    val severity: String,
    @SerialName("order_id") val orderId: String? = null,
)

@Serializable data class DeliverBody(
    @SerialName("idempotency_key") val idempotencyKey: String,
    @SerialName("confirmed_preflight_version") val confirmedPreflightVersion: String,
)
