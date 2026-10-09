import React, { ReactNode } from "react";
import { createPortal } from "react-dom";

/** Окна и листы перекрывают весь экран приложения, как ModalBottomSheet/AlertDialog. */
const overlay = (node: ReactNode) => {
  const host = document.getElementById("app-overlay");
  return host ? createPortal(node, host) : node;
};
import { Product } from "./data";

// ---------- иконки Material (пути из Material Icons) ----------
const P: Record<string, string> = {
  back: "M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z",
  qr: "M9.5 6.5v3h-3v-3h3M11 5H5v6h6V5zm-1.5 9.5v3h-3v-3h3M11 13H5v6h6v-6zm6.5-6.5v3h-3v-3h3M19 5h-6v6h6V5zm-6 8h1.5v1.5H13V13zm1.5 1.5H16V16h-1.5v-1.5zM16 13h1.5v1.5H16V13zm-3 3h1.5v1.5H13V16zm1.5 1.5H16V19h-1.5v-1.5zM16 16h1.5v1.5H16V16zm1.5-1.5H19V16h-1.5v-1.5zm0 3H19V19h-1.5v-1.5zM22 7h-2V4h-3V2h5v5zm0 15v-5h-2v3h-3v2h5zM2 22h5v-2H4v-3H2v5zM2 2v5h2V4h3V2H2z",
  input: "M21 3.01H3c-1.1 0-2 .9-2 2V9h2V4.99h18v14.03H3V15H1v4.01c0 1.1.9 1.98 2 1.98h18c1.1 0 2-.88 2-1.98v-14c0-1.11-.9-2-2-2zM11 16l4-4-4-4v3H1v2h10v3z",
  inbox: "M19 3H4.99C3.88 3 3 3.9 3 5l.01 14c0 1.1.88 2 1.99 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 12h-4c0 1.66-1.35 3-3 3s-3-1.34-3-3H4.99V5H19v10zm-3-5h-2V7h-4v3H8l4 4 4-4z",
  truck: "M20 8h-3V4H3c-1.1 0-2 .9-2 2v11h2c0 1.66 1.34 3 3 3s3-1.34 3-3h6c0 1.66 1.34 3 3 3s3-1.34 3-3h2v-5l-3-4zM6 18.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm13.5-9l1.96 2.5H17V9.5h2.5zm-1.5 9c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5z",
  warning: "M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z",
  filter: "M10 18h4v-2h-4v2zM3 6v2h18V6H3zm3 7h12v-2H6v2z",
  close: "M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z",
  check: "M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z",
  box: "M20 2H4c-1 0-2 .9-2 2v3.01c0 .72.43 1.34 1 1.69V20c0 1.1 1.1 2 2 2h14c.9 0 2-.9 2-2V8.7c.57-.35 1-.97 1-1.69V4c0-1.1-1-2-2-2zm-5 12H9v-2h6v2zm5-7H4V4l16-.02V7z",
  pallet: "M2 18h20v2H2zM4 14h4v3H4zm6 0h4v3h-4zm6 0h4v3h-4zM3 4h18v9H3z",
  delete: "M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z",
  undo: "M12.5 8c-2.65 0-5.05.99-6.9 2.6L2 7v9h9l-3.62-3.62c1.39-1.16 3.16-1.88 5.12-1.88 3.54 0 6.55 2.31 7.6 5.5l2.37-.78C21.08 11.03 17.15 8 12.5 8z",
  chevron: "M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z",
  expand: "M16.59 8.59L12 13.17 7.41 8.59 6 10l6 6 6-6z",
  collapse: "M12 8l-6 6 1.41 1.41L12 10.83l4.59 4.58L18 14z",
  print: "M19 8H5c-1.66 0-3 1.34-3 3v6h4v4h12v-4h4v-6c0-1.66-1.34-3-3-3zm-3 11H8v-5h8v5zm3-7c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm-1-9H6v4h12V3z",
};
export function Icon({ name, size = 24, color = "currentColor" }: { name: keyof typeof P | string; size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden style={{ flex: "none" }}>
      <path d={P[name]} fill={color} />
    </svg>
  );
}

// ---------- фото товара: силуэт одежды в цвете товара ----------
const cache = new Map<string, string>();
export function garmentUrl(p: Product): string {
  const k = p.id;
  if (cache.has(k)) return cache.get(k)!;
  const c = p.color, a = p.accent ?? p.color;
  const shapes: Record<string, string> = {
    dress: `<path d="M38 14h24l6 10-8 6 6 52H34l6-52-8-6z" fill="${c}"/><path d="M38 14l12 14 12-14" fill="none" stroke="${a}" stroke-width="3"/><path d="M34 82h32" stroke="${a}" stroke-width="2"/>`,
    longsleeve: `<path d="M36 14h28l16 12-4 40-8-2 2-30v54H32V34l2 30-8 2-4-40z" fill="${c}"/><path d="M40 30l6 6m6-8l6 8m-14 10l6 6m6-8l6 8m-16 12l6 6m6-8l6 8" stroke="${a}" stroke-width="3"/><path d="M42 14q8 8 16 0" fill="none" stroke="${a}" stroke-width="2"/>`,
    blouse: `<path d="M38 16h24l14 10-6 14-6-4v40H36V36l-6 4-6-14z" fill="${c}"/><path d="M42 16h16v6H42z" fill="${a}"/><circle cx="50" cy="40" r="1.6" fill="${a}"/><circle cx="50" cy="50" r="1.6" fill="${a}"/><circle cx="50" cy="60" r="1.6" fill="${a}"/>`,
    skirt: `<path d="M36 22h28l12 62H24z" fill="${c}"/><path d="M36 22h28v6H36z" fill="${a}"/><path d="M42 28l-6 56m14-56v56m8-56l6 56" stroke="${a}" stroke-width="2"/>`,
    trousers: `<path d="M34 14h32l6 72H54l-4-44-4 44H28z" fill="${c}"/><path d="M34 14h32v6H34z" fill="${a}"/>`,
    turtleneck: `<path d="M42 8h16v8H42z" fill="${a}"/><path d="M38 16h24l16 12-4 38-8-2 2-26v50H32V38l2 26-8 2-4-38z" fill="${c}"/><path d="M40 44h20M40 54h20" stroke="${a}" stroke-width="3" stroke-dasharray="4 3"/>`,
  };
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="#f1f1f3"/>${shapes[p.kind]}</svg>`;
  const url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  cache.set(k, url);
  return url;
}
export function Photo({ p, w, h }: { p: Product; w: number; h: number }) {
  return <img className="photo" src={garmentUrl(p)} alt={p.name} style={{ width: w, height: h }} />;
}

// ---------- кнопки, чипы ----------
type BtnProps = { kind?: "filled" | "tonal" | "outlined" | "text" | "success" | "danger"; children: ReactNode; onClick?: () => void; disabled?: boolean; block?: boolean; style?: React.CSSProperties; h?: number; fs?: number; testId?: string };
export function Btn({ kind = "filled", children, onClick, disabled, block, style, h, fs, testId }: BtnProps) {
  return (
    <button data-testid={testId} className={`btn ${kind}${block ? " block" : ""}`} onClick={onClick} disabled={disabled} style={{ ...(h ? { height: h, minHeight: h } : {}), ...(fs ? { fontSize: fs } : {}), ...style }}>
      {children}
    </button>
  );
}
export function Chip({ sel, children, onClick, disabled, style }: { sel?: boolean; children: ReactNode; onClick?: () => void; disabled?: boolean; style?: React.CSSProperties }) {
  return (
    <button className={`chip${sel ? " sel" : ""}`} onClick={onClick} disabled={disabled} style={style}>
      {sel ? <Icon name="check" size={18} /> : null}
      {children}
    </button>
  );
}

// ---------- каркас рабочего экрана (ScanScaffold) ----------
export function Scaffold(props: {
  title: string; subtitle?: string; onExit: () => void; progress?: [number, number]; camera?: boolean; actions?: ReactNode;
  primary?: { label: string; onClick: () => void; disabled?: boolean; kind?: "filled" | "success" } | null;
  children: ReactNode;
}) {
  const { title, subtitle, onExit, progress, camera = true, primary, children, actions } = props;
  return (
    <div className="scaffold">
      <div className="topbar">
        <div className="topbar-row">
          <button className="icon-btn" onClick={onExit} aria-label="Назад"><Icon name="back" /></button>
          <div className="topbar-title">
            <div className="t clamp2">{title}</div>
            {subtitle ? <div className="s">{subtitle}</div> : null}
          </div>
          {progress ? <div className="topbar-progress">{progress[0]} из {progress[1]}</div> : null}
          {actions}
          {camera ? <button className="icon-btn" aria-label="Сканировать камерой" style={{ marginLeft: 0 }}><Icon name="qr" color="var(--primary)" /></button> : <div style={{ width: 8 }} />}
        </div>
        {progress && progress[1] > 0 ? (
          <div className="det-progress"><div style={{ width: `${(100 * progress[0]) / progress[1]}%` }} /></div>
        ) : null}
      </div>
      <div className="content">{children}</div>
      {primary ? (
        <div className="primary-action" style={{ padding: "8px 12px 10px" }}>
          <Btn kind={primary.kind ?? "filled"} block h={56} fs={19} onClick={primary.onClick} disabled={primary.disabled}>{primary.label}</Btn>
        </div>
      ) : null}
    </div>
  );
}

// ---------- диалоги и листы ----------
export function Dialog({ title, children, actions, onDismiss }: { title: ReactNode; children?: ReactNode; actions: ReactNode; onDismiss?: () => void }) {
  return overlay(
    <div className="scrim" onClick={(e) => { if (e.target === e.currentTarget) onDismiss?.(); }}>
      <div className="dialog" role="dialog">
        <div className="dh">{title}</div>
        {children ? <div className="db">{children}</div> : null}
        <div className="df">{actions}</div>
      </div>
    </div>
  );
}

export function Sheet({ children, footer, onDismiss }: { children: ReactNode; footer?: ReactNode; onDismiss: () => void }) {
  return overlay(
    <div className="scrim sheet-scrim" onClick={(e) => { if (e.target === e.currentTarget) onDismiss(); }}>
      <div className="sheet" role="dialog">
        <div className="handle" />
        <div className="sb">{children}</div>
        {footer ? <div className="sf">{footer}</div> : null}
      </div>
    </div>
  );
}

/** P6. ConfirmSheet: заголовок, 1–3 факта, разнесённые кнопки. */
export function ConfirmSheet({ title, facts, confirmLabel, danger, onConfirm, onDismiss }: { title: string; facts: string[]; confirmLabel: string; danger?: boolean; onConfirm: () => void; onDismiss: () => void }) {
  return (
    <Sheet onDismiss={onDismiss}>
      <div style={{ padding: "4px 4px 8px" }}>
        <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 10 }}>{title}</div>
        {facts.map((f) => <div key={f} style={{ fontSize: 16, color: "var(--text2)", margin: "6px 0" }}>{f}</div>)}
        <div style={{ marginTop: 18 }}>
          <Btn kind={danger ? "danger" : "filled"} block h={64} fs={20} onClick={onConfirm}>{confirmLabel}</Btn>
        </div>
        <div style={{ marginTop: 28 }}>
          <Btn kind="text" block h={56} fs={18} onClick={onDismiss}>Отмена</Btn>
        </div>
      </div>
    </Sheet>
  );
}

export function Radio({ on, label, sub, onClick }: { on: boolean; label: ReactNode; sub?: ReactNode; onClick: () => void }) {
  return (
    <div className={`radio${on ? " on" : ""}`} onClick={onClick}>
      <span className="dot" />
      <span style={{ flex: 1, minWidth: 0 }}>
        <span className="ellipsis" style={{ display: "block" }}>{label}</span>
        {sub ? <span style={{ display: "block", fontSize: 13, color: "var(--text2)" }}>{sub}</span> : null}
      </span>
    </div>
  );
}

export function Field({ label, value, onChange, inputMode, autoFocus, onEnter, error, help, clearable }: { label: string; value: string; onChange: (v: string) => void; inputMode?: "numeric" | "text"; autoFocus?: boolean; onEnter?: () => void; error?: boolean; help?: string; clearable?: boolean }) {
  return (
    <div className={`field${error ? " error" : ""}`}>
      <label>{label}</label>
      <input value={value} inputMode={inputMode} autoFocus={autoFocus} onChange={(e) => onChange(inputMode === "numeric" ? e.target.value.replace(/\D/g, "") : e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") onEnter?.(); }} />
      {clearable && value ? <button className="icon-btn clear" style={{ width: 40, height: 40, margin: 0 }} onClick={() => onChange("")} aria-label="Очистить"><Icon name="close" size={20} /></button> : null}
      {help ? <div className="help">{help}</div> : null}
    </div>
  );
}

export function ErrorPanel({ error, onRetry, onDismiss }: { error: string | null; onRetry?: () => void; onDismiss?: () => void }) {
  if (!error) return null;
  return (
    <div className="errpanel">
      <div className="m">{error}</div>
      <div className="row-gap" style={{ gap: 0 }}>
        {onRetry ? <Btn kind="text" onClick={onRetry}>Повторить</Btn> : null}
        {onDismiss ? <Btn kind="text" onClick={onDismiss}>Закрыть после проверки</Btn> : null}
      </div>
    </div>
  );
}
