import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  IconButton,
} from "@mui/material";
import ExpandMoreOutlined from "@mui/icons-material/ExpandMoreOutlined";
import DeleteOutlined from "@mui/icons-material/DeleteOutlined";
import { dispatchDemo, getDemo, isBaseline, products } from "./mockApi";
import type { DemoAction, Unit } from "./model";
function useDemo() {
  const [, render] = useState(0);
  useEffect(() => {
    const f = () => render((v) => v + 1);
    window.addEventListener("wms686-change", f);
    return () => window.removeEventListener("wms686-change", f);
  }, []);
  return getDemo();
}
export function FboPickActions({ source }: { source: string | null }) {
  const state = useDemo();
  const [productId, setProduct] = useState("p1"),
    [qty, setQty] = useState("1"),
    [kiz, setKiz] = useState(""),
    [message, setMessage] = useState("");
  if (isBaseline() || !source) return null;
  const sourceBox = state.sourceBoxes.find((b) => "obj:" + b.id === source);
  const cell = sourceBox?.cell ?? (source === "cell:cell1" ? "А-1-1" : null);
  const apply = (a: DemoAction) => {
    const r = dispatchDemo(a);
    setMessage(r.error ?? "Подбор сохранён");
    return r;
  };
  return (
    <Stack spacing={1.25} data-testid="fbo-pick-actions">
      <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }} useFlexGap>
        {sourceBox && (
          <Button
            variant="outlined"
            size="small"
            disabled={!sourceBox.units.length}
            onClick={() => apply({ type: "pickWholeBox", boxId: sourceBox.id })}
            data-testid="fbo-whole-box"
          >
            Забрать весь короб
          </Button>
        )}
        {cell && (
          <Button
            variant="outlined"
            size="small"
            disabled={
              !state.sourceBoxes.some((b) => b.cell === cell && b.units.length)
            }
            onClick={() => apply({ type: "pickWholeCell", cell })}
            data-testid="fbo-whole-cell"
          >
            Забрать всё из ячейки
          </Button>
        )}
      </Stack>
      {sourceBox && sourceBox.units.length > 0 && (
        <Stack
          direction={{ xs: "column", md: "row" }}
          spacing={1}
          sx={{ alignItems: { md: "flex-start" } }}
        >
          <TextField
            select
            size="small"
            label="Товар из короба"
            value={productId}
            onChange={(e) => setProduct(e.target.value)}
            sx={{ minWidth: 220 }}
            data-testid="fbo-partial-product"
          >
            {products
              .filter((p) => sourceBox.units.some((u) => u.productId === p.id))
              .map((p) => (
                <MenuItem key={p.id} value={p.id}>
                  {p.sku_code}
                </MenuItem>
              ))}
          </TextField>
          <TextField
            label="Количество"
            type="number"
            size="small"
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            sx={{ width: 120 }}
            slotProps={{
              htmlInput: { min: 1, "data-testid": "fbo-partial-quantity" },
            }}
          />
          <TextField
            label="КИЗ выбранных единиц"
            size="small"
            value={kiz}
            onChange={(e) => setKiz(e.target.value)}
            placeholder="Каждый КИЗ через пробел или с новой строки"
            multiline
            sx={{ flex: 1, minWidth: 220 }}
            slotProps={{ htmlInput: { "data-testid": "fbo-partial-kiz" } }}
          />
          <Button
            variant="contained"
            onClick={() =>
              apply({
                type: "pickPartial",
                boxId: sourceBox.id,
                productId,
                quantity: Number(qty),
                kizCodes: kiz.split(/[\s,;]+/).filter(Boolean),
              })
            }
            data-testid="fbo-partial-pick"
          >
            Забрать
          </Button>
        </Stack>
      )}
      {message && (
        <Alert severity={message === "Подбор сохранён" ? "success" : "error"}>
          {message}
        </Alert>
      )}
    </Stack>
  );
}
export function FboPackingActions() {
  const state = useDemo();
  const [selected, setSelected] = useState<string | null>(null),
    [scan, setScan] = useState(""),
    [product, setProduct] = useState<string | null>(null),
    [pending, setPending] = useState<Unit | null>(null),
    [message, setMessage] = useState("");
  useEffect(() => {
    const feedback = () =>
      setMessage("Макет: на принтер ничего не отправлялось.");
    window.addEventListener("wms686-print-blocked", feedback);
    return () => window.removeEventListener("wms686-print-blocked", feedback);
  }, []);
  if (isBaseline()) return null;
  const boxId =
    selected && state.shipmentBoxes.some((b) => b.id === selected)
      ? selected
      : state.selectedBoxId;
  const box = state.shipmentBoxes.find((b) => b.id === boxId);
  const apply = (a: DemoAction) => {
    const r = dispatchDemo(a);
    setMessage(r.error ?? "Сохранено");
    return r;
  };
  const submit = () => {
    const code = scan.trim();
    setScan("");
    const scannedBox = state.shipmentBoxes.find((b) => b.code === code);
    if (scannedBox) {
      setSelected(scannedBox.id);
      if (pending) {
        const r = apply({
          type: "addUnit",
          boxId: scannedBox.id,
          unit: pending,
        });
        if (!r.error) {
          setPending(null);
          setProduct(null);
          setMessage("Единица добавлена в " + scannedBox.code);
        }
      } else setMessage("Выбран " + scannedBox.code);
      return;
    }
    const p = products.find((p) => p.wb_barcodes.includes(code));
    if (p) {
      setProduct(p.id);
      setPending(null);
      setMessage("Товар выбран. Отсканируйте КИЗ.");
      return;
    }
    const inShipment = state.shipmentBoxes
      .flatMap((b) => b.units)
      .find((u) => u.kiz === code);
    if (inShipment && box) {
      const r = apply({
        type: "verifyKiz",
        boxId: box.id,
        kiz: code,
        ...(product ? { productId: product } : {}),
      });
      if (!r.error) {
        setProduct(null);
        setMessage("КИЗ проверен. Состав короба не изменился.");
      }
      return;
    }
    const unit = state.sourceBoxes
      .flatMap((b) => b.units)
      .find((u) => u.kiz === code);
    if (unit && product === unit.productId) {
      setPending(unit);
      setMessage("КИЗ выбран. Отсканируйте короб назначения.");
      return;
    }
    if (
      product &&
      /^DEMO-(?:NEW-)?KIZ(?:-[A-Z0-9]+)*$/.test(code) &&
      !state.kizHistory[code]
    ) {
      const unmarked = [
        ...(box?.units ?? []),
        ...state.sourceBoxes.flatMap((sourceBox) => sourceBox.units),
      ].find((candidate) => candidate.productId === product && !candidate.kiz);
      if (unmarked) {
        setPending({ ...unmarked, kiz: code, intakeId: null });
        setMessage("Нанесённый КИЗ выбран. Отсканируйте короб назначения.");
        return;
      }
    }
    setMessage(
      "Код не относится к выбранному товару/коробу. Сканируйте ШК товара, затем его КИЗ и короб.",
    );
  };
  return (
    <Stack spacing={1.25} data-testid="fbo-packing-actions">
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1}
        sx={{ alignItems: { sm: "flex-start" } }}
      >
        {state.shipmentBoxes.length > 0 && (
          <FormControl size="small" sx={{ minWidth: 240 }}>
            <InputLabel id="fbo-box-label">Короб</InputLabel>
            <Select
              labelId="fbo-box-label"
              label="Короб"
              value={boxId ?? ""}
              onChange={(e) => setSelected(e.target.value)}
              data-testid="fbo-box-select"
            >
              {state.shipmentBoxes.map((b) => (
                <MenuItem key={b.id} value={b.id}>
                  {b.code}
                  {b.closed ? " · закрыт" : ""}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        )}
        <TextField
          size="small"
          label="ШК товара / КИЗ / короб"
          value={scan}
          onChange={(e) => setScan(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              submit();
            }
          }}
          fullWidth
          slotProps={{ htmlInput: { "data-testid": "fbo-pack-scan" } }}
        />
        <Button
          variant="outlined"
          onClick={submit}
          data-testid="fbo-pack-submit"
        >
          Сканировать
        </Button>
      </Stack>
      {message && (
        <Typography variant="body2" data-testid="fbo-pack-feedback">
          {message}
        </Typography>
      )}
      {box && (
        <>
          <Stack
            direction="row"
            spacing={1}
            sx={{ flexWrap: "wrap" }}
            useFlexGap
          >
            {box.closed ? (
              <Button
                variant="outlined"
                size="small"
                onClick={() => apply({ type: "openBox", boxId: box.id })}
              >
                Открыть короб
              </Button>
            ) : (
              <Button
                variant="outlined"
                size="small"
                data-testid="fbo-close-box"
                onClick={() => {
                  const r = apply({ type: "closeBox", boxId: box.id });
                  if (!r.error) {
                    setSelected(null);
                    setMessage("Короб закрыт. Выбран следующий короб.");
                  }
                }}
              >
                Закрыть короб
              </Button>
            )}
            <Button
              variant="text"
              size="small"
              onClick={() =>
                setMessage(
                  "Готовый состав сохранён. Дополнительная упаковка не требуется.",
                )
              }
              data-testid="fbo-skip-packing"
            >
              Без дополнительной упаковки
            </Button>
          </Stack>
          <Accordion variant="outlined" disableGutters>
            <AccordionSummary expandIcon={<ExpandMoreOutlined />}>
              <Typography variant="body2">КИЗ короба {box.code}</Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={0.75}>
                {box.units.map((u) => (
                  <Stack
                    key={u.id}
                    direction="row"
                    sx={{ alignItems: "center" }}
                    spacing={1}
                  >
                    <Typography
                      variant="body2"
                      sx={{ flex: 1, overflowWrap: "anywhere" }}
                    >
                      {u.kiz ?? "Без КИЗ"} ·{" "}
                      {products.find((p) => p.id === u.productId)?.sku_code} ·{" "}
                      {u.intakeId ? "Приёмка 000007" : "Приёмка не указана"} ·
                      Отгрузка 000086
                    </Typography>
                    {!box.closed && (
                      <IconButton
                        size="small"
                        title="Убрать из короба"
                        onClick={() =>
                          apply({
                            type: "removeUnit",
                            boxId: box.id,
                            unitId: u.id,
                          })
                        }
                      >
                        <DeleteOutlined fontSize="small" />
                      </IconButton>
                    )}
                  </Stack>
                ))}
              </Stack>
            </AccordionDetails>
          </Accordion>
        </>
      )}
    </Stack>
  );
}
