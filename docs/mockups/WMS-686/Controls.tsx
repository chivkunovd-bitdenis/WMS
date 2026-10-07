import { useRef, useState } from 'react';
import { TextField } from '@mui/material';
import { dispatchDemo, getDemo, products, queuePickKiz } from './mockApi';
import { isBaseline } from './mockApi';

type Mode = 'quantity' | 'kiz' | 'box';
type Step = { handled: boolean; notice?: string; error?: string; productCode?: string };

// The existing picker remains responsible for the source, table, quantities,
// undo and scanner intake. This hook only adds the product/KIZ pair.
export function useKizPicking() {
  const [mode, setMode] = useState<Mode>('quantity');
  const pending = useRef<{ productId: string; barcode: string; source: string | null } | null>(null);
  function changeMode(value: Mode) { pending.current = null; queuePickKiz(null); setMode(value); }
  function receive(code: string, source: string | null): Step {
    if (isBaseline()) return { handled: false };
    const state = getDemo();
    const box = state.sourceBoxes.find(b => b.code === code);
    if (code === 'А-1-1' || box) {
      pending.current = null;
      queuePickKiz(null);
      if (box && mode === 'box') {
        const result = dispatchDemo({ type: 'pickWholeBox', boxId: box.id });
        return result.error ? { handled: true, error: result.error } : { handled: true, notice: `${box.code}: подобран целиком, ${box.units.length} шт.` };
      }
      return { handled: false };
    }
    if (mode === 'box') return { handled: true, error: 'Пикните ячейку и штрихкод целого короба' };
    if (mode === 'quantity') return { handled: false };
    const product = products.find(p => p.wb_barcodes.includes(code) || p.sku_code === code);
    if (product) {
      pending.current = { productId: product.id, barcode: product.wb_barcodes[0], source };
      return { handled: true, notice: `${product.sku_code} — пикните КИЗ этой единицы` };
    }
    const one = pending.current;
    if (!one || one.source !== source) return { handled: true, error: 'Сначала пикните товар, затем его КИЗ' };
    if (!/^DEMO-(?:NEW-)?KIZ(?:-[A-Z0-9]+)*$/.test(code)) return { handled: true, error: 'Ожидается КИЗ выбранного товара' };
    queuePickKiz(code);
    pending.current = null;
    return { handled: true, productCode: one.barcode, notice: `${products.find(p => p.id === one.productId)?.sku_code} · ${code}` };
  }
  return { mode, changeMode, receive };
}
export function PickScanMode({ picking }: { picking: ReturnType<typeof useKizPicking> }) {
  if (isBaseline()) return null;
  return <TextField select size="small" label="Подбор" value={picking.mode}
    onChange={e => picking.changeMode(e.target.value as Mode)}
    slotProps={{ select: { native: true } }} sx={{ width: 220, maxWidth: '100%' }}>
    <option value="quantity">По товарам</option>
    <option value="kiz">Товар + КИЗ</option>
    <option value="box">Целый короб</option>
  </TextField>;
}
