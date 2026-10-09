import React, { useState } from "react";
import { Box, Order, SORTING, productById, sellerById } from "./data";
import { fmtFull, notPickedVerb, pieceWord, underpicks } from "./logic";
import { DeliveryDialog } from "./screensFbs";
import { isLandscape, newId, useScan, useStore } from "./store";
import { Btn, ConfirmSheet, Dialog, Field, Icon, Photo, Scaffold, Sheet } from "./ui";

const isKiz = (v: string) => v.startsWith("]d2") || v.startsWith("(01)") || (/^01\d{14}21/.test(v) && v.length >= 20);

/** WMS-737: недобор по товарам; первые три строки, остальное — по нажатию. */
export function UnderpickBlock({ supplyId, compact }: { supplyId: string; compact?: boolean }) {
  const s = useStore();
  const [expanded, setExpanded] = useState(false);
  const under = underpicks(s.w.orders, supplyId);
  if (!under.length) return null;
  const shown = expanded ? under : under.slice(0, 3);
  const rest = under.length - 3;
  return (
    <div className="warnblock" data-testid="underpick" style={compact ? { margin: 0 } : undefined}>
      {shown.map((u) => (
        <div className="ln" key={u.productId}><b>{notPickedVerb(u.count)} {u.count} {pieceWord(u.count)}:</b> {u.name}, {u.sku}</div>
      ))}
      {rest > 0 ? <button className="more" onClick={() => setExpanded(!expanded)}>{expanded ? "Свернуть" : `Ещё ${rest} ${rest === 1 ? "товар" : rest < 5 ? "товара" : "товаров"}`}</button> : null}
    </div>
  );
}

/** Упаковка FBS поставки: WMS-737 (недобор), WMS-738 (короба), WMS-739 (компактный список и передача). */
export function PackScreen({ supplyId }: { supplyId: string }) {
  const s = useStore();
  const w = s.w;
  const sup = w.supplies.find((x) => x.id === supplyId)!;
  const orders = w.orders.filter((o) => o.supplyId === supplyId).sort((a, b) => Number(a.picked) - Number(b.picked) || a.createdAt.localeCompare(b.createdAt));
  const boxes = w.boxes.filter((b) => b.supplyId === supplyId).sort((a, b) => a.number - b.number);
  const [openBoxId, setOpenBoxId] = useState<string | null>(null);
  const [kizOrderId, setKizOrderId] = useState<string | null>(null);
  const [kizResult, setKizResult] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<null | { kind: "clear" | "delete"; box: Box }>(null);
  const [qtyEdit, setQtyEdit] = useState<null | { box: Box; productId: string; value: string }>(null);
  const [details, setDetails] = useState<Order | null>(null);
  const [printSheet, setPrintSheet] = useState(false);
  const [deliver, setDeliver] = useState(false);
  const openBox = boxes.find((b) => b.id === openBoxId) ?? null;
  const packed = orders.filter((o) => o.packed).length;
  const editable = !sup.delivered;
  const land = isLandscape(s.orientation);
  const boxOf = (o: Order) => boxes.find((b) => b.orderIds.includes(o.id)) ?? null;

  const assign = (box: Box, o: Order) => {
    s.update((x) => ({ ...x, boxes: x.boxes.map((b) => b.id === box.id ? { ...b, orderIds: [...b.orderIds, o.id] } : b) }));
    s.log(`POST boxes/${box.number}/orders → WB ${o.wbId} в короб №${box.number}`);
    s.flashOk();
  };
  const pack = (o: Order) => {
    s.update((x) => ({ ...x, orders: x.orders.map((y) => y.id === o.id ? { ...y, packed: true } : y) }));
    s.log(`POST packaging pack → WB ${o.wbId} упакован`); s.flashOk();
  };

  const onScan = (raw: string) => {
    const v = raw.trim();
    const box = boxes.find((b) => b.barcode === v);
    if (box) { setOpenBoxId(box.id); s.log(`Скан короба ${v} → короб №${box.number} открыт`); return; }
    if (isKiz(v)) {
      const o = orders.find((x) => x.id === kizOrderId);
      if (!o) { s.flashErr("Это код ЧЗ. Сначала отсканируйте QR заказа, к которому он относится"); return; }
      s.update((x) => ({ ...x, orders: x.orders.map((y) => y.id === o.id ? { ...y, kizSaved: true } : y) }));
      setKizOrderId(null); setKizResult(`КИЗ сохранён · WB ${o.wbId}`);
      s.log(`POST kiz/commit → WB ${o.wbId}: код привязан в WMS, передача в WB — в фоне (скан не ждёт WB)`); s.flashOk();
      return;
    }
    const qrOrder = orders.find((o) => String(o.wbId) === v);
    if (!openBox) {
      if (qrOrder) { setKizOrderId(qrOrder.id); setKizResult(null); s.log(`Скан QR заказа WB ${qrOrder.wbId} → ждём ЧЗ`); return; }
      const isProduct = orders.some((o) => productById(o.productId).barcode === v);
      s.flashErr(isProduct ? "Это штрихкод товара. Откройте короб, чтобы класть в него товары, или отсканируйте QR заказа" : `Штрихкод ${v} не относится к этой поставке`);
      return;
    }
    const inSupply = qrOrder || orders.some((o) => productById(o.productId).barcode === v);
    if (!inSupply) { s.flashErr(`Штрихкод ${v} не относится к этой поставке`); return; }
    const assigned = new Set(boxes.flatMap((b) => b.orderIds));
    if (qrOrder) {
      setKizOrderId(qrOrder.id); setKizResult(null);
      if (openBox.orderIds.includes(qrOrder.id)) return;
      const other = boxOf(qrOrder);
      if (other) { s.flashErr(`Заказ WB ${qrOrder.wbId} уже лежит в коробе №${other.number}`); return; }
      assign(openBox, qrOrder); return;
    }
    const o = orders.filter((x) => !assigned.has(x.id) && productById(x.productId).barcode === v)[0];
    if (!o) { s.flashErr(`Все заказы с товаром «${productById(orders.find((x) => productById(x.productId).barcode === v)!.productId).name.split(" ").slice(0, 2).join(" ")}» уже разложены по коробам`); return; }
    assign(openBox, o);
  };
  useScan(onScan, [
    ...orders.slice(0, 4).map((o) => ({ code: String(o.wbId), label: `QR заказа WB ${o.wbId}` })),
    { code: "(01)04650118240015(21)5aB7xK9", label: "Код ЧЗ (после QR)" },
    ...[...new Set(orders.map((o) => o.productId))].slice(0, 3).map((id) => ({ code: productById(id).barcode, label: `ШК ${productById(id).sku}` })),
    ...boxes.map((b) => ({ code: b.barcode, label: `Короб №${b.number}` })),
    { code: "4601234567890", label: "Чужой штрихкод" },
  ]);

  const createBox = () => {
    const n = boxes.reduce((m, b) => Math.max(m, b.number), 0) + 1;
    const b: Box = { id: newId("box"), supplyId, number: n, barcode: `FBS-7A1C2E90-${String(n).padStart(3, "0")}`, orderIds: [] };
    s.update((x) => ({ ...x, boxes: [...x.boxes, b] }));
    setOpenBoxId(b.id);
    s.log(`POST boxes → короб №${n} создан и открыт`); s.flashOk();
  };
  const doConfirm = () => {
    if (!confirm) return;
    const { kind, box } = confirm;
    setConfirm(null);
    if (kind === "clear") {
      s.update((x) => ({ ...x, boxes: x.boxes.map((b) => b.id === box.id ? { ...b, orderIds: [] } : b) }));
      s.log(`POST boxes/${box.number}/clear → короб №${box.number} пуст, ${box.orderIds.length} заказов снова не разложены`);
    } else {
      const key = w.boxDeleteKeys[box.id] ?? `del-${box.id}`;
      s.update((x) => ({ ...x, boxDeleteKeys: { ...x.boxDeleteKeys, [box.id]: key }, boxes: x.boxes.filter((b) => b.id !== box.id) }));
      s.log(`DELETE boxes/${box.number} (ключ повтора ${key}) → короб удалён`);
      setOpenBoxId(null);
    }
    s.flashOk();
  };
  const noPrint = () => s.snack("Макет: печать не выполняется");
  const kizLine = kizOrderId ? `WB ${orders.find((o) => o.id === kizOrderId)?.wbId}: сканируйте ЧЗ` : openBox ? `Сканы кладутся в короб №${openBox.number}` : "QR заказа → код ЧЗ";

  return (
    <Scaffold
      title="Упаковка FBS"
      onExit={s.back}
      actions={<button className="icon-btn" aria-label="Печать" title="Печать" style={{ margin: 0 }} onClick={() => setPrintSheet(true)}><Icon name="print" color="var(--primary)" /></button>}
      primary={editable && !land ? { label: "Передать поставку в WB", onClick: () => setDeliver(true) } : null}
    >
      {(() => {
        const scanPart = (<>
      <div className="scanline">
        {!sup.delivered ? <div style={{ fontWeight: 700 }}>{kizLine}</div> : null}
        {kizResult ? <div style={{ color: "var(--success)" }}>{kizResult}</div> : null}
        {sup.delivered ? <div style={{ color: "var(--success)", fontWeight: 700 }}>Поставка передана в WB</div> : null}
      </div>
        </>);
        const boxesPart = (<>

        <UnderpickBlock supplyId={supplyId} />

        <div className="boxes-card" data-testid="boxes">
          <div className="boxes-head">
            <span>Короба{boxes.length ? ` · ${boxes.length}` : ""}</span>
            {editable ? <Btn kind="text" h={48} fs={16} onClick={createBox}>+ Создать короб</Btn> : null}
          </div>
          {boxes.length === 0 ? <div className="boxes-empty">Коробов пока нет</div> : null}
          {boxes.map((b) => {
            const open = b.id === openBoxId;
            const productIds = [...new Set(b.orderIds.map((id) => w.orders.find((o) => o.id === id)!.productId))];
            return (
              <div key={b.id} className={`box-row-wrap${open ? " open" : ""}`}>
                <div className="box-row">
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 700 }}>Короб №{b.number}</div>
                    <div style={{ color: "var(--text2)" }}>{b.orderIds.length} шт · {open ? "открыт" : "закрыт"}</div>
                  </div>
                  <button className="icon-btn" aria-label={`Этикетка короба №${b.number}`} title="Этикетка" style={{ margin: 0 }} onClick={noPrint}><Icon name="print" color="var(--primary)" /></button>
                  <Btn kind={open ? "filled" : "outlined"} h={48} fs={16} style={{ padding: "0 14px" }} onClick={() => setOpenBoxId(open ? null : b.id)} testId={`box-toggle-${b.number}`}>
                    {open ? "Закрыть" : <>Открыть <Icon name="chevron" size={20} /></>}
                  </Btn>
                </div>
                {open ? (
                  <div className="box-body" data-testid="open-box">
                    {productIds.length === 0 ? <div style={{ color: "var(--text2)" }}>Короб пуст — сканируйте товары или QR заказов</div> : productIds.map((pid) => {
                      const p = productById(pid);
                      const inBox = b.orderIds.filter((id) => w.orders.find((o) => o.id === id)!.productId === pid).length;
                      return (
                        <div key={pid} className="box-line tap" onClick={() => editable && setQtyEdit({ box: b, productId: pid, value: String(inBox) })}>
                          <Photo p={p} w={36} h={44} />
                          <span className="ellipsis" style={{ flex: 1 }}><b>р. {p.size}</b> · {p.name}</span>
                          <b style={{ whiteSpace: "nowrap" }}>{inBox} шт.</b>
                        </div>
                      );
                    })}
                    {editable ? (b.orderIds.length > 0
                      ? <Btn kind="outlined" block h={48} fs={16} style={{ color: "var(--error)", marginTop: 6 }} onClick={() => setConfirm({ kind: "clear", box: b })} testId="box-clear">Очистить короб</Btn>
                      : <Btn kind="outlined" block h={48} fs={16} style={{ color: "var(--error)", marginTop: 6 }} onClick={() => setConfirm({ kind: "delete", box: b })} testId="box-delete">Удалить короб</Btn>) : null}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>

        </>);
        const ordersPart = (<>
        <div className="orders-head">Заказы · упаковано {packed} из {orders.length}</div>
        {orders.map((o) => {
          const p = productById(o.productId);
          const b = boxOf(o);
          const from = o.pickedFrom ? w.placements.find((q) => q.key === o.pickedFrom)?.locCode : undefined;
          return (
            <div key={o.id} className={`order-row tap${o.packed ? " packed" : ""}`} onClick={() => setDetails(o)} data-testid={`order-${o.wbId}`}>
              <Photo p={p} w={40} h={48} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700 }}>WB {o.wbId}</div>
                <div className="ellipsis"><b>р. {p.size}</b> · {p.name}</div>
                <div>
                  {!o.picked ? <b style={{ color: "#b25b00" }}>Не подобран</b> : <span style={{ color: "var(--success)" }}>Подобран · {from === SORTING ? "без ячейки" : from}</span>}
                  {b ? <span style={{ color: "var(--text2)" }}> · короб №{b.number}</span> : null}
                </div>
              </div>
              {o.packed ? <span className="packed-mark">Упакован</span> : (
                <Btn kind="outlined" h={48} fs={16} style={{ padding: "0 12px" }} disabled={!editable} onClick={() => pack(o)}>Упаковать</Btn>
              )}
            </div>
          );
        })}
        </>);
        if (!land) return (<>{scanPart}<div className="scroll" style={{ flex: 1, paddingBottom: 8 }}>{boxesPart}{ordersPart}</div></>);
        // WMS-707: в альбоме тот же столбец, но «Передать» — справа в строке скана, чтобы списку осталась высота.
        return (<>
          <div style={{ display: "flex", alignItems: "center", gap: 8, background: "var(--surface)", borderBottom: "1px solid #e6e6e6", paddingRight: 8 }}>
            <div style={{ flex: 1, minWidth: 0 }}>{scanPart}</div>
            {editable ? <Btn h={48} fs={16} onClick={() => setDeliver(true)}>Передать поставку в WB</Btn> : null}
          </div>
          <div className="scroll" style={{ flex: 1, paddingBottom: 8 }}>{boxesPart}{ordersPart}</div>
        </>);
      })()}

      {printSheet ? (
        <Sheet onDismiss={() => setPrintSheet(false)}>
          <div style={{ fontSize: 22, fontWeight: 600, margin: "4px 0 12px" }}>Печать</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, paddingBottom: 12 }}>
            <Btn block h={56} fs={18} onClick={() => { setPrintSheet(false); noPrint(); }}>Все QR заказов</Btn>
            <Btn block h={56} fs={18} kind="tonal" onClick={() => { setPrintSheet(false); noPrint(); }}>Печать всего</Btn>
            <Btn block h={56} fs={18} kind="outlined" onClick={() => { setPrintSheet(false); noPrint(); }}>Этикетки всех коробов</Btn>
          </div>
        </Sheet>
      ) : null}
      {details ? (() => {
        const o = w.orders.find((x) => x.id === details.id)!;
        const p = productById(o.productId);
        return (
          <Sheet onDismiss={() => setDetails(null)}>
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <Photo p={p} w={66} h={66} />
              <div>
                <div style={{ fontWeight: 700, fontSize: 22 }}>WB {o.wbId}</div>
                <div style={{ fontSize: 16 }}>{p.name}, {p.size}</div>
              </div>
            </div>
            <div style={{ fontSize: 16, display: "flex", flexDirection: "column", gap: 4, margin: "10px 0" }}>
              <div>{p.sku} · ШК {p.barcode}</div>
              <div>WB · {sellerById(o.sellerId).name}</div>
              <div>Склад / СЦ · отгрузить до {fmtFull(o.deadlineAt)}</div>
              <div>{o.picked ? "Подобран" : <b style={{ color: "#b25b00" }}>Не подобран</b>}{o.kizSaved ? " · КИЗ сохранён" : ""}</div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, paddingBottom: 12 }}>
              <Btn block h={56} fs={18} onClick={noPrint}>Печатать этикетки</Btn>
              <Btn block h={56} fs={18} kind="outlined" disabled={o.packed || !editable} onClick={() => { pack(o); setDetails(null); }}>{o.packed ? "Упакован" : "Отметить упакованным"}</Btn>
            </div>
          </Sheet>
        );
      })() : null}
      {confirm ? (
        <ConfirmSheet
          title={confirm.kind === "clear" ? `Очистить короб №${confirm.box.number}?` : `Удалить короб №${confirm.box.number}?`}
          facts={confirm.kind === "clear"
            ? [`В коробе ${confirm.box.orderIds.length} шт.`, "Заказы вернутся в неразложенные, этикетка короба остаётся"]
            : ["Короб пустой.", "Короб будет удалён; если у него есть грузоместо WB, оно удаляется и в WB"]}
          confirmLabel={confirm.kind === "clear" ? "Очистить" : "Удалить"}
          danger
          onConfirm={doConfirm}
          onDismiss={() => setConfirm(null)}
        />
      ) : null}
      {qtyEdit ? (
        <Dialog title="Количество товара в коробе" onDismiss={() => setQtyEdit(null)} actions={<>
          <Btn kind="text" h={48} fs={16} onClick={() => setQtyEdit(null)}>Отмена</Btn>
          <Btn h={48} fs={16} disabled={qtyEdit.value === ""} onClick={() => {
            const want = Number(qtyEdit.value);
            const box = qtyEdit.box;
            const inBox = box.orderIds.filter((id) => w.orders.find((o) => o.id === id)!.productId === qtyEdit.productId);
            const assigned = new Set(w.boxes.flatMap((b) => b.orderIds));
            const free = orders.filter((o) => o.productId === qtyEdit.productId && !assigned.has(o.id));
            if (want > inBox.length && want - inBox.length > free.length) { s.flashErr(`Свободных заказов этого товара только ${free.length}`); return; }
            const next = want < inBox.length ? box.orderIds.filter((id) => !inBox.slice(want).includes(id)) : [...box.orderIds, ...free.slice(0, want - inBox.length).map((o) => o.id)];
            s.update((x) => ({ ...x, boxes: x.boxes.map((b) => b.id === box.id ? { ...b, orderIds: next } : b) }));
            s.log(`Количество в коробе №${box.number}: ${inBox.length} → ${want}`);
            setQtyEdit(null); s.flashOk();
          }}>Сохранить</Btn>
        </>}>
          <div>{productById(qtyEdit.productId).name}</div>
          <Field label="Штук в коробе" value={qtyEdit.value} inputMode="numeric" autoFocus onChange={(v) => setQtyEdit({ ...qtyEdit, value: v })} />
        </Dialog>
      ) : null}
      {deliver ? <DeliveryDialog supplyId={supplyId} onClose={() => setDeliver(false)} /> : null}
    </Scaffold>
  );
}

