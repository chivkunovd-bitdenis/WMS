const WB_BARCODE='4606660000001',OZON_POSITION_BARCODE='OZON-POS-666-A';
"use strict";
function order(supplyId, marketplace) {
    const ozon = marketplace === 'ozon';
    return {
        id: `${supplyId}-order`,
        marketplace,
        external_order_id: ozon ? 'OZON-POSTING-666' : null,
        wb_order_id: ozon ? -666 : 666001,
        status: 'assembling', wb_status: 'confirm', supplier_status: 'confirm',
        seller: { id: `${supplyId}-seller`, name: `Селлер ${supplyId}` },
        wb_warehouse: { id: 507, name: 'Коледино' },
        wms_warehouse: { id: 'warehouse-666', name: 'Основной склад' },
        product: {
            id: `${supplyId}-product-a`, name: ozon ? 'Футболка Ozon, позиция A' : 'Футболка WB',
            image_url: null, seller_article: ozon ? 'OZ-A' : 'WB-A', wb_article: ozon ? null : 666001,
            barcode: ozon ? OZON_POSITION_BARCODE : WB_BARCODE, sku: ozon ? 'OZ-SKU-A' : 'WB-SKU-A',
            chrt_id: ozon ? null : 666001, category: 'Одежда', color: 'синий', size: 'M',
            marketplace_bindings: [{ marketplace, external_barcodes: [ozon ? OZON_POSITION_BARCODE : WB_BARCODE] }],
        },
        positions: ozon ? [
            {
                id: `${supplyId}-position-a`, product_id: `${supplyId}-product-a`, name: 'Футболка Ozon, позиция A',
                image_url: null, seller_article: 'OZ-A', sku: 'OZ-SKU-A', size: 'M', color: 'синий',
                barcode: OZON_POSITION_BARCODE,
                marketplace_bindings: [{ marketplace: 'ozon', external_barcodes: [OZON_POSITION_BARCODE] }],
                quantity: 1, reserved_quantity: 1, picked_quantity: 1,
            },
            {
                id: `${supplyId}-position-b`, product_id: `${supplyId}-product-b`, name: 'Брюки Ozon, позиция B',
                image_url: null, seller_article: 'OZ-B', sku: 'OZ-SKU-B', size: 'L', color: 'чёрный',
                barcode: 'OZON-POS-666-B',
                marketplace_bindings: [{ marketplace: 'ozon', external_barcodes: ['OZON-POS-666-B'] }],
                quantity: 1, reserved_quantity: 1, picked_quantity: 1,
            },
        ] : [],
        inventory: { available_unpacked: 2, locations: [] },
        buyer_type: 'individual', cargo_type: 'mgt', can_pvz: false,
        delivery_route: ozon ? 'Ozon Логистика' : null,
        metadata: {
            required: [], optional: [], states: [], delivery_allowed: true, last_checked_at: null,
        },
        sticker: { code: ozon ? 'OZON-POSTING-666' : '666001 0001', status: 'ready', asset_url: null, applied_at: null },
        pick: { status: 'picked', location_code: 'A-01-01', picked_at: null },
        pack: { status: 'pending', packed_at: null },
        created_at_wb: '2026-10-05T08:00:00Z', deadline_at: '2026-10-06T08:00:00Z',
        supply_id: supplyId, selection_blockers: [], tape_order_index: 0,
    };
}
function workspace(id, marketplace, task = `task-${id}`) {
    return {
        supply: {
            id, marketplace, wb_supply_id: marketplace === 'wb' ? `WB-GI-${id}` : null,
            source: 'wms', name: `${marketplace.toUpperCase()} ${id}`, status: 'assembling',
            delivery_type: 'warehouse_sc', seller: { id: `${id}-seller`, name: `Селлер ${id}` },
            wb_warehouse: { id: 507, name: 'Коледино' },
            wms_warehouse: { id: 'warehouse-666', name: 'Основной склад' },
            planned_destination: null, planned_shipment_date: null, nearest_deadline_at: '2026-10-06T08:00:00Z',
            packaging_task_id: task, barcode_asset: null,
        },
        stage: 'packing',
        progress: { picked: 1, packed: 0, metadata_ready: 0, stickers_ready: 1, total: 1 },
        blockers: [], orders: [order(id, marketplace)], cargo_places: [],
        boxes: [{
                id: `${id}-box`, box_number: 1, barcode: `${id}-BOX-1`, assigned_order_ids: [],
                assigned_order_product_ids: [], trbx_id: null, wb_trbx_id: null, qr_asset: null,
                without_distribution: false,
            }],
        delivery_preflight: null, last_wb_sync_at: null, server_now: '2026-10-05T08:00:00Z',
    };
}

export { workspace };
export function selectionFixtures() {
  const make=(id,seller,warehouse)=>{
    const one=workspace(id,'wb').orders[0];
    one.id=id;one.status='new';one.supply_id=null;one.wb_status='new';one.supplier_status='new';
    one.seller={id:seller,name:seller==='seller-a'?'Альфа':'Бета'};
    one.wb_warehouse={id:warehouse,name:warehouse===507?'Коледино':'Электросталь'};
    one.metadata.required=[];one.product.name=`Товар ${id}`;one.product.id=`product-${id}`;
    return one;
  };
  const orders=[make('order-a','seller-a',507),make('order-a2','seller-a',507),make('order-b','seller-b',507),make('order-c','seller-a',508),make('unselected','seller-b',509)];
  const supply=(id,seller,wh,marketplace='wb',can_add_orders=true)=>({id,marketplace,wb_supply_id:`WB-${id}`,name:id,
    status:'draft',seller:{id:seller,name:seller},wb_warehouse:{id:wh,name:String(wh)},
    wms_warehouse:{id:'warehouse-666',name:'Основной склад'},orders_count:0,units_count:0,picked_units_count:0,
    boxes_count:0,planned_shipment_date:null,can_add_orders});
  return {orders,supplies:[supply('compatible','seller-a',507),supply('foreign-seller','seller-b',507),
    supply('foreign-warehouse','seller-a',508),supply('foreign-marketplace','seller-a',507,'ozon'),
    supply('closed','seller-a',507,'wb',false)]};
}
