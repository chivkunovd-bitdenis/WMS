import React, { useEffect, useState } from "react";
import { InboundDoc, InboundStatus, productById, sellerById, sellers } from "./data";
import {
  InboundFilters, activeFilterCount, filterInbound, inboundOpenMode, inboundStatusColor, inboundStatusRu, noFilters,
} from "./logic";
import { useScan, useStore } from "./store";
import { Btn, Field, Icon, Photo, Scaffold, Sheet } from "./ui";

// ---------------- Главный экран (A2), без изменений ----------------
export function HomeScreen() {
  const s = useStore();
  useScan(() => {}, []);
  // WMS-736 R7: фильтры приёмки живут, пока список в стеке; выход на главный экран их сбрасывает.
  useEffect(() => { s.update((w) => (w.inboundFilters === noFilters ? w : { ...w, inboundFilters: noFilters })); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const inboundCount = s.w.inbound.filter((d) => d.status === "submitted" || d.status === "receiving").length;
  const sortingCount = s.w.inbound.filter((d) => d.status === "sorting" && d.sortingRemaining > 0).length;
  const tiles: { label: string; icon: string; count: number | null; go: () => void }[] = [
    { label: "Приёмка", icon: "input", count: inboundCount, go: () => s.push({ name: "inbound" }) },
    { label: "Сортировка", icon: "inbox", count: sortingCount, go: () => s.snack("Макет: «Сортировка» в этом пакете не меняется") },
    { label: "Отгрузка", icon: "truck", count: 2, go: () => s.snack("Макет: «Отгрузка» (FBO) в этом пакете не меняется") },
    { label: "FBS", icon: "truck", count: null, go: () => s.push({ name: "fbs" }) },
  ];
  return (
    <div className="scaffold" style={{ padding: 16 }}>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8, minHeight: 0 }}>
        {tiles.map((t) => (
          <button key={t.label} className="tile" style={{ flex: 1 }} onClick={t.go}>
            <Icon name={t.icon} size={44} color="var(--primary)" />
            <span className="lbl">{t.label}</span>
            {t.count ? <span className="cnt">{t.count}</span> : null}
          </button>
        ))}
      </div>
      <Btn kind="text" block h={48} fs={18} onClick={() => s.snack("Макет: обновление приложения не показывается")}>Обновление приложения</Btn>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", height: 56 }}>
        <div>
          <div style={{ fontSize: 16 }}>Ирина Соколова</div>
          <div style={{ fontSize: 13, color: "var(--text2)" }}>Кладовщик</div>
        </div>
        <Btn kind="text" fs={16} onClick={() => s.snack("Макет: смена сотрудника не показывается")}>Сменить</Btn>
      </div>
    </div>
  );
}

// ---------------- WMS-736: список «Приёмка» с фильтрами ----------------
function TaskCard({ d, onClick }: { d: InboundDoc; onClick: () => void }) {
  const seller = sellerById(d.sellerId).name;
  const sub = [
    d.plannedDate ? `Привоз: ${d.plannedDate}` : null,
    `${d.lines.length} позиций`,
    d.plannedBoxes != null ? `коробов: ${d.boxes} из ${d.plannedBoxes}` : null,
  ].filter(Boolean).join(" · ");
  const color = inboundStatusColor(d.status);
  return (
    <div className="card tap" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 6 }} onClick={onClick}>
      <div style={{ display: "flex", alignItems: "center" }}>
        <div className="ellipsis" style={{ fontSize: 18, fontWeight: 600, flex: 1 }}>Поставка {d.displayNumber} · {seller}</div>
        {d.discrepancy ? <span style={{ marginLeft: 8 }}><Icon name="warning" color="var(--warning)" /></span> : null}
      </div>
      <div className="ellipsis" style={{ fontSize: 14, color: "var(--text2)" }}>{sub}</div>
      <div><span style={{ fontSize: 14, fontWeight: 500, color, background: `color-mix(in srgb, ${color} 12%, transparent)`, borderRadius: 8, padding: "4px 10px" }}>{inboundStatusRu(d.status)}</span></div>
    </div>
  );
}

const STATUS_OPTIONS: (InboundStatus | "all")[] = ["all", "draft", "submitted", "receiving", "sorting", "done"];

function FilterSheet({ value, onChange, docs, onClose }: { value: InboundFilters; onChange: (f: InboundFilters) => void; docs: InboundDoc[]; onClose: () => void }) {
  const count = filterInbound(docs, value).length;
  const sellerIds = [...new Set(docs.map((d) => d.sellerId))];
  const sellerOptions = sellers.filter((x) => sellerIds.includes(x.id)).sort((a, b) => a.name.localeCompare(b.name, "ru"));
  return (
    <Sheet
      onDismiss={onClose}
      footer={<>
        <Btn kind="text" h={56} fs={16} onClick={() => onChange(noFilters)} disabled={activeFilterCount(value) === 0}>Сбросить</Btn>
        <Btn kind="filled" h={56} fs={18} style={{ flex: 1 }} onClick={onClose}>Показать ({count})</Btn>
      </>}
    >
      <div style={{ fontSize: 22, fontWeight: 600, margin: "2px 0 4px" }}>Фильтры</div>
      <Field label="Поиск: документ, селлер, товар" value={value.search} onChange={(v) => onChange({ ...value, search: v })} clearable />
      <div style={{ fontSize: 14, color: "var(--text2)", margin: "14px 0 6px" }}>Статус</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        {STATUS_OPTIONS.map((st) => {
          const sel = value.status === st;
          return (
            <button key={st} className={`chip${sel ? " sel" : ""}`} style={{ height: 48, justifyContent: "flex-start", fontSize: 15, padding: "0 10px" }} onClick={() => onChange({ ...value, status: st })}>
              {sel ? <Icon name="check" size={18} /> : null}
              <span className="ellipsis">{st === "all" ? "Все статусы" : inboundStatusRu(st)}</span>
            </button>
          );
        })}
      </div>
      <div style={{ fontSize: 14, color: "var(--text2)", margin: "14px 0 2px" }}>Селлер</div>
      {[{ id: "all", name: "Все селлеры" }, ...sellerOptions].map((x) => (
        <div key={x.id} className={`radio${value.sellerId === x.id ? " on" : ""}`} onClick={() => onChange({ ...value, sellerId: x.id })}>
          <span className="dot" /><span className="ellipsis" style={{ flex: 1 }}>{x.name}</span>
        </div>
      ))}
    </Sheet>
  );
}

export function InboundListScreen() {
  const s = useStore();
  const [sheet, setSheet] = useState(false);
  useScan((c) => s.log(`Скан «${c}» на списке приёмки не обрабатывается (как сейчас)`), []);
  const f = s.w.inboundFilters;
  const setF = (nf: InboundFilters) => s.update((w) => ({ ...w, inboundFilters: nf }));
  const list = filterInbound(s.w.inbound, f);
  const n = activeFilterCount(f);
  const open = (d: InboundDoc) => {
    const mode = inboundOpenMode(d);
    s.log(`Открыт ${d.displayNumber} (${inboundStatusRu(d.status)}) → ${mode === "view" ? "просмотр" : mode === "sorting" ? "экран сортировки" : mode === "draft" ? "черновик" : "экран приёмки"}`);
    s.push({ name: "inbound-doc", id: d.id, mode });
  };
  const chips: { label: string; clear: () => void }[] = [];
  if (f.status !== "all") chips.push({ label: inboundStatusRu(f.status), clear: () => setF({ ...f, status: "all" }) });
  if (f.sellerId !== "all") chips.push({ label: sellerById(f.sellerId).name, clear: () => setF({ ...f, sellerId: "all" }) });
  if (f.search.trim()) chips.push({ label: `«${f.search.trim()}»`, clear: () => setF({ ...f, search: "" }) });
  return (
    <Scaffold title="Приёмка" onExit={s.back} camera={false} primary={{ label: "Создать приёмку", onClick: () => s.snack("Макет: создание приёмки не меняется") }}>
      <div style={{ background: "var(--bg)", padding: "4px 4px 0 8px", flex: "none" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", minHeight: 44 }}>
          {chips.length ? <Btn kind="text" h={44} fs={15} onClick={() => setF(noFilters)} testId="inbound-reset">Сбросить</Btn> : null}
          <Btn kind="text" h={44} fs={15} onClick={() => setSheet(true)} testId="inbound-filters">
            <Icon name="filter" size={20} />{n ? `Фильтры · ${n}` : "Фильтры"}
          </Btn>
        </div>
        {chips.length ? (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, padding: "0 4px 4px 0" }}>
            {chips.map((c) => (
              <button key={c.label} className="chip sel" style={{ height: 36, maxWidth: "100%" }} onClick={c.clear} title="Снять фильтр">
                <span className="ellipsis">{c.label}</span><Icon name="close" size={16} />
              </button>
            ))}
          </div>
        ) : null}
      </div>
      {list.length === 0 ? (
        <div style={{ padding: "64px 24px", textAlign: "center" }}>
          <div style={{ fontSize: 18, color: "var(--text2)", marginBottom: 16 }}>Нет документов по выбранным фильтрам</div>
          <Btn kind="outlined" h={48} fs={16} onClick={() => setF(noFilters)}>Сбросить</Btn>
        </div>
      ) : (
        <div className="scroll" style={{ flex: 1, padding: "8px 16px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
          {list.map((d) => <TaskCard key={d.id} d={d} onClick={() => open(d)} />)}
        </div>
      )}
      {sheet ? <FilterSheet value={f} onChange={setF} docs={s.w.inbound} onClose={() => setSheet(false)} /> : null}
    </Scaffold>
  );
}

// ---------------- Документ: просмотр / рабочие экраны без изменений ----------------
export function InboundDocScreen({ id, mode }: { id: string; mode: "draft" | "receiving" | "sorting" | "view" }) {
  const s = useStore();
  const d = s.w.inbound.find((x) => x.id === id)!;
  const seller = sellerById(d.sellerId).name;
  const accepted = d.lines.reduce((a, l) => a + l.accepted, 0);
  const planned = d.lines.reduce((a, l) => a + l.planned, 0);
  useScan((c) => {
    if (mode === "view") { s.flashErr("Документ сейчас нельзя менять на ТСД"); s.log(`Скан «${c}» на просмотре не отправлен на сервер`); }
    else s.snack("Макет: рабочий экран этого статуса не меняется — сканы не моделируются");
  }, [{ code: "2047870000244", label: "Любой товар" }]);
  const unchanged = () => s.snack("Макет: этот экран остаётся как сейчас");
  const lines = (
    <div className="scroll" style={{ flex: 1, padding: "8px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
      {d.lines.map((l) => {
        const p = productById(l.productId);
        const done = l.accepted >= l.planned;
        return (
          <div key={l.productId} className="card" style={{ padding: 12, display: "flex", gap: 10, alignItems: "center", background: done ? "color-mix(in srgb, var(--success) 8%, white)" : "white" }}>
            <Photo p={p} w={44} h={52} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="ellipsis" style={{ fontSize: 18, fontWeight: 600 }}>{p.sku}</div>
              <div className="ellipsis" style={{ fontSize: 14, color: "var(--text2)" }}>{p.name}</div>
              <div style={{ height: 4, background: "#e3e3e3", borderRadius: 2, marginTop: 6 }}><div style={{ height: 4, width: `${Math.min(100, (100 * l.accepted) / l.planned)}%`, background: done ? "var(--success)" : "var(--primary)", borderRadius: 2 }} /></div>
            </div>
            <div style={{ fontSize: 18, fontWeight: 700, whiteSpace: "nowrap" }}>{l.accepted} / {l.planned}</div>
          </div>
        );
      })}
    </div>
  );
  if (mode === "view") {
    return (
      <Scaffold title={`Приёмка ${d.displayNumber}`} subtitle={seller} onExit={s.back} progress={[accepted, planned]}>
        <div style={{ padding: "10px 16px 2px", display: "flex", alignItems: "center", gap: 8, flex: "none" }}>
          <span style={{ fontSize: 14, fontWeight: 500, color: inboundStatusColor(d.status), background: `color-mix(in srgb, ${inboundStatusColor(d.status)} 12%, transparent)`, borderRadius: 8, padding: "4px 10px" }}>{inboundStatusRu(d.status)}{d.createdBySeller && d.status === "draft" ? " селлера" : ""}</span>
          <span style={{ fontSize: 14, color: "var(--text2)" }}>коробов: {d.boxes}</span>
        </div>
        {lines}
      </Scaffold>
    );
  }
  if (mode === "sorting") {
    return (
      <Scaffold title={`Сортировка ${d.displayNumber}`} subtitle={seller} onExit={s.back} progress={[planned - d.sortingRemaining, planned]}>
        <div style={{ padding: 16, flex: "none" }} className="card tap" onClick={unchanged}>
          <div style={{ fontSize: 20, fontWeight: 700 }}>Сканируйте товар</div>
          <div style={{ fontSize: 15, color: "var(--text2)" }}>Затем ячейку, куда кладёте · осталось разместить {d.sortingRemaining} шт.</div>
        </div>
        {lines}
      </Scaffold>
    );
  }
  if (mode === "draft") {
    return (
      <Scaffold title={`Черновик ${d.displayNumber}`} subtitle={seller} onExit={s.back} camera={false}>
        <div style={{ padding: "12px 16px", display: "flex", gap: 8, flex: "none" }}>
          <Btn kind="tonal" style={{ flex: 1 }} onClick={unchanged}>Добавить товар</Btn>
          <Btn kind="outlined" style={{ flex: 1 }} onClick={unchanged}>Короба и грузоместа</Btn>
        </div>
        {lines}
      </Scaffold>
    );
  }
  return (
    <Scaffold title={`Приёмка ${d.displayNumber}`} subtitle={seller} onExit={s.back} progress={[accepted, planned]} primary={accepted > 0 ? { label: "Завершить пересчёт", onClick: unchanged } : null}>
      <div style={{ display: "flex", gap: 12, padding: "12px 16px", flex: "none" }}>
        <Btn kind="filled" h={64} fs={18} style={{ flex: 1 }} onClick={unchanged}>Создать короб</Btn>
        <Btn kind="tonal" h={64} fs={18} style={{ flex: 1 }} onClick={unchanged}>Приёмка без короба</Btn>
      </div>
      {lines}
    </Scaffold>
  );
}
