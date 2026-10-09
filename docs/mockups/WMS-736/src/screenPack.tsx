import React, { useState } from "react";
import { Box, Order, productById, sellerById } from "./data";
import { fmtFull, notPickedVerb, pieceWord, underpicks } from "./logic";
import { DeliveryDialog } from "./screensFbs";
import { newId, useScan, useStore } from "./store";
import { Btn, ConfirmSheet, Dialog, Field, Photo, Scaffold } from "./ui";

const isKiz = (v: string) => v.startsWith("]d2") || v.startsWith("(01)") || (/^01\d{14}21/.test(v) && v.length >= 20);

/** Упаковка FBS поставки: прежний экран + WMS-737 (недобор), WMS-738 (очистить/удалить короб), WMS-739 (передача). */
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
  const [deliver, setDeliver] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const openBox = boxes.find((b) => b.id === openBoxId) ?? null;
  const packed = orders.filter((o) => o.packed).length;
  const under = underpicks(w.orders, supplyId);
  const editable = !sup.delivered;

  const assign = (box: Box, o: Order) => {
    s.update((x) => ({ ...x, boxes: x.boxes.map((b) => b.id === box.id ? { ...b, orderIds: [...b.orderIds, o.id] } : b) }));
    s.log(`POST boxes/${box.number}/orders → WB ${o.wbId} в короб №${box.number}`);
    s.flashOk();
  };

  const onScan = (raw: string) => {
    const v = raw.trim();
    const box = boxes.find((b) => b.barcode === v);
    if (box) { setOpenBoxId(box.id); s.log(`Скан короба ${v} → короб №${box.number} открыт`); return; }
    if (isKiz(v)) {
      const o = orders.find((x) => x.id === kizOrderId);
      if (!o) { s.flashErr("Сначала отсканируйте QR заказа"); return; }
      s.update((x) => ({ ...x, orders: x.orders.map((y) => y.id === o.id ? { ...y, kizSaved: true } : y) }));
      setKizOrderId(null); setKizResult("КИЗ сохранён. WB принял код.");
      s.log(`POST kiz/commit → WB ${o.wbId}: код сохранён`); s.flashOk();
      return;
    }
    const qrOrder = orders.find((o) => String(o.wbId) === v);
    if (!openBox) {
      if (qrOrder) { setKizOrderId(qrOrder.id); setKizResult(null); s.log(`Скан QR заказа WB ${qrOrder.wbId} → ждём ЧЗ`); return; }
      s.flashErr("Заказ не найден."); return;
    }
    const inSupply = qrOrder || orders.some((o) => productById(o.productId).barcode === v);
    if (!inSupply) { s.flashErr(`Товара нет в этой поставке (ШК: ${v})`); return; }
    const assigned = new Set(boxes.flatMap((b) => b.orderIds));
    if (qrOrder) {
      setKizOrderId(qrOrder.id); setKizResult(null);
      if (openBox.orderIds.includes(qrOrder.id)) return;
      if (assigned.has(qrOrder.id)) { s.flashErr("Позиция уже в другом коробе. Проверьте распределение."); return; }
      assign(openBox, qrOrder); return;
    }
    const o = orders.filter((x) => !assigned.has(x.id) && productById(x.productId).barcode === v)[0];
    if (!o) { s.flashErr("Нет нераспределённого заказа с таким кодом"); return; }
    assign(openBox, o);
  };
  useScan(onScan, [
    ...orders.slice(0, 4).map((o) => ({ code: String(o.wbId), label: `QR заказа WB ${o.wbId}` })),
    { code: "(01)04650118240015(21)5aB7xK9", label: "Код ЧЗ (после QR)" },
    ...[...new Set(orders.map((o) => o.productId))].slice(0, 3).map((id) => ({ code: productById(id).barcode, label: `ШК ${productById(id).sku}` })),
    ...boxes.map((b) => ({ code: b.barcode, label: `Короб №${b.number}` })),
    { code: "4601234567890", label: "Чужой товар" },
  ]);

  const createBox = () => {
    const n = (boxes.reduce((m, b) => Math.max(m, b.number), 0)) + 1;
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

  const unchanged = () => s.snack("Макет: печать не выполняется");
  const shownUnder = expanded ? under : under.slice(0, 3);

  return (
    <Scaffold
      title="Упаковка FBS"
      onExit={s.back}
      primary={editable && orders.length > 0 && packed === orders.length ? { label: "Передать поставку в WB", onClick: () => setDeliver(true) } : null}
    >
      <div className="scroll" style={{ flex: 1 }}>
        {under.length ? (
          <div className="warnblock" data-testid="underpick">
            {shownUnder.map((u) => (
              <div className="ln" key={u.productId}><b>{notPickedVerb(u.count)} {u.count} {pieceWord(u.count)}:</b> {u.name}, {u.sku}</div>
            ))}
            {under.length > 3 ? (
              <button className="more" onClick={() => setExpanded(!expanded)}>{expanded ? "Свернуть" : `Ещё ${under.length - 3} ${under.length - 3 === 1 ? "товар" : under.length - 3 < 5 ? "товара" : "товаров"}`}</button>
            ) : null}
          </div>
        ) : null}
        <div style={{ padding: 10, fontWeight: 700 }}>{kizOrderId ? `WB ${orders.find((o) => o.id === kizOrderId)?.wbId}: сканируйте ЧЗ` : "QR заказа → код ЧЗ"}</div>
        {kizResult ? <div style={{ padding: "0 10px" }}>{kizResult}</div> : null}
        <div style={{ display: "flex", gap: 8, padding: 8 }}>
          <Btn onClick={unchanged}>Все QR</Btn>
          <Btn onClick={unchanged}>Печать всего</Btn>
        </div>

        {openBox ? (
          <div style={{ background: "rgba(46,125,50,.10)", padding: "6px 8px" }} data-testid="open-box">
            <div style={{ fontSize: 18, fontWeight: 700 }}>Короб №{openBox.number} открыт · {openBox.orderIds.length} шт</div>
            <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
              {editable ? (openBox.orderIds.length > 0
                ? <Btn kind="outlined" h={48} style={{ flex: 1, color: "var(--error)" }} onClick={() => setConfirm({ kind: "clear", box: openBox })} testId="box-clear">Очистить короб</Btn>
                : <Btn kind="outlined" h={48} style={{ flex: 1, color: "var(--error)" }} onClick={() => setConfirm({ kind: "delete", box: openBox })} testId="box-delete">Удалить короб</Btn>) : null}
              <Btn h={48} style={{ flex: 1 }} onClick={() => setOpenBoxId(null)}>Закрыть короб</Btn>
            </div>
            {openBox.orderIds.length === 0 ? (
              <div style={{ fontSize: 13, color: "var(--text2)", marginTop: 6 }}>Короб пуст — сканируйте товары или QR заказов</div>
            ) : (
              <>
                <div style={{ fontSize: 13, color: "var(--text2)", marginTop: 6 }}>Сканируйте товары или QR заказов</div>
                {[...new Set(openBox.orderIds.map((id) => w.orders.find((o) => o.id === id)!.productId))].map((pid) => {
                  const p = productById(pid);
                  const inBox = openBox.orderIds.filter((id) => w.orders.find((o) => o.id === id)!.productId === pid).length;
                  return (
                    <div key={pid} className="card tap" style={{ marginTop: 6, padding: 10, display: "flex" }} onClick={() => setQtyEdit({ box: openBox, productId: pid, value: String(inBox) })}>
                      <Photo p={p} w={112} h={146} />
                      <div style={{ flex: 1, paddingLeft: 12 }}>
                        <div className="clamp3" style={{ fontSize: 15 }}>{p.name}, {p.size}</div>
                        <div style={{ fontSize: 13 }}>{p.sku}</div>
                        <div style={{ fontSize: 12, color: "var(--text2)", marginTop: 4 }}>ШК: {p.barcode}</div>
                        <div style={{ fontSize: 20, fontWeight: 700, marginTop: 8 }}>В коробе: {inBox} шт.</div>
                      </div>
                    </div>
                  );
                })}
              </>
            )}
          </div>
        ) : editable ? (
          <div style={{ padding: "4px 8px" }}><Btn block h={44} onClick={createBox}>Создать короб</Btn></div>
        ) : null}

        {boxes.length ? (
          <>
            <div style={{ display: "flex", alignItems: "center", padding: "4px 8px" }}>
              <div style={{ fontWeight: 700, fontSize: 14, flex: 1 }}>Короба</div>
              <Btn kind="text" fs={13} onClick={unchanged}>Все этикетки</Btn>
            </div>
            <div style={{ padding: "0 8px" }}>
              {boxes.map((b) => {
                const open = b.id === openBoxId;
                return (
                  <div key={b.id} className="tap" style={{ display: "flex", alignItems: "center", padding: "8px 0", borderBottom: "1px solid var(--bg)" }} onClick={() => setOpenBoxId(open ? null : b.id)}>
                    <div style={{ flex: 1, fontSize: 14, fontWeight: open ? 700 : 400, color: open ? "var(--success)" : "var(--text)" }}>Короб №{b.number} · {b.orderIds.length} шт · {open ? "открыт" : "закрыт"}</div>
                    <Btn kind="text" fs={13} onClick={unchanged}>Этикетка</Btn>
                  </div>
                );
              })}
            </div>
          </>
        ) : null}

        <div style={{ padding: 8, display: "flex", flexDirection: "column", gap: 8 }}>
          {orders.map((o) => {
            const p = productById(o.productId);
            return (
              <div key={o.id} style={{ background: o.picked ? "rgba(46,125,50,.12)" : "var(--tonal1)", borderRadius: 12, padding: 12, display: "flex", flexDirection: "column", gap: 5, boxShadow: "0 1px 2px rgba(0,0,0,.12)" }}>
                <div style={{ display: "flex", alignItems: "center" }}>
                  <Photo p={p} w={66} h={66} />
                  <div style={{ flex: 1, paddingLeft: 10, minWidth: 0 }}>
                    <div style={{ fontWeight: 700, fontSize: 22 }}>WB {o.wbId}</div>
                    <div style={{ fontSize: 17 }}>{p.name}, {p.size}</div>
                    <div style={{ fontSize: 14 }}>{p.sku}</div>
                  </div>
                </div>
                <div>ШК: {p.barcode}</div>
                <div>WB · {sellerById(o.sellerId).name}</div>
                <div>Маршрут: Склад / СЦ · Статус: В сборке</div>
                <div>Поступил: {fmtFull(o.createdAt)}</div>
                <div style={{ fontWeight: 500 }}>Отгрузить до: {fmtFull(o.deadlineAt)}</div>
                {o.picked ? <div style={{ color: "var(--success)" }}>Подобран · {o.pickedFrom ? w.placements.find((q) => q.key === o.pickedFrom)?.locCode.replace("__SORTING__", "сортировка") : ""}</div> : null}
                <div style={{ fontSize: 36, fontWeight: 900 }}>{String(o.wbId).slice(-4)}</div>
                <Btn block h={56} fs={20} onClick={unchanged}>Печатать этикетки</Btn>
                <Btn kind="outlined" block disabled={o.packed || !editable} onClick={() => { s.update((x) => ({ ...x, orders: x.orders.map((y) => y.id === o.id ? { ...y, packed: true } : y) })); s.log(`POST packaging pack → WB ${o.wbId} упакован`); s.flashOk(); }}>{o.packed ? "Упакован" : "Отметить упакованным"}</Btn>
              </div>
            );
          })}
        </div>
        {sup.delivered ? <div style={{ padding: "4px 12px 16px", color: "var(--success)", fontWeight: 700, fontSize: 18 }}>Поставка передана в WB</div> : null}
      </div>

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
          <Btn kind="text" onClick={() => setQtyEdit(null)}>Отмена</Btn>
          <Btn disabled={qtyEdit.value === ""} onClick={() => {
            const want = Number(qtyEdit.value);
            const box = qtyEdit.box;
            const inBox = box.orderIds.filter((id) => w.orders.find((o) => o.id === id)!.productId === qtyEdit.productId);
            const assigned = new Set(w.boxes.flatMap((b) => b.orderIds));
            const free = orders.filter((o) => o.productId === qtyEdit.productId && !assigned.has(o.id));
            if (want > inBox.length && want - inBox.length > free.length) { s.flashErr("Не хватает свободных заказов этого товара"); return; }
            const next = want < inBox.length ? box.orderIds.filter((id) => !inBox.slice(want).includes(id)) : [...box.orderIds, ...free.slice(0, want - inBox.length).map((o) => o.id)];
            s.update((x) => ({ ...x, boxes: x.boxes.map((b) => b.id === box.id ? { ...b, orderIds: next } : b) }));
            s.log(`Количество в коробе №${box.number}: ${inBox.length} → ${want}`);
            setQtyEdit(null); s.flashOk();
          }}>Сохранить</Btn>
        </>}>
          <Field label="Штук" value={qtyEdit.value} inputMode="numeric" autoFocus onChange={(v) => setQtyEdit({ ...qtyEdit, value: v })} />
        </Dialog>
      ) : null}
      {deliver ? <DeliveryDialog supplyId={supplyId} onClose={() => setDeliver(false)} /> : null}
    </Scaffold>
  );
}
