"""F4-R: partial fresh STATUS cannot accept every retained displayed document.

Real services, isolated SQLite and fake Ozon responses. The optional DOM runner
uses the existing component in jsdom (Node), without launching a browser.
"""

import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest
from test_wms663_accepted_current_status import _accepted_then_current_status
from test_wms663_astra_regressions import SET, SNAPSHOT, STATUS, _exemplar, _scan
from test_wms663_customs_documents_contract import SKU_ONE, SKU_TWO

from app.services import ozon_exemplar_documents_service as documents
from app.services import ozon_fbs_process_service as process

VALUE_FIELDS = ("gtd", "rnpt", "is_gtd_absent", "is_rnpt_absent", "weight", "marks")
MISSING = {
    "a_exemplar": (SKU_ONE, 81),
    "a_product": (SKU_ONE, 81),
    "sibling_exemplar": (SKU_ONE, 82),
    "b_product": (SKU_TWO, 91),
}


async def _fresh_reply_after_rejection(session, missing=None):
    order, first, transport, rejected, before, kwargs = await _accepted_then_current_status(
        session, "rejected"
    )
    assert before["state"] == "rejected"
    assert "gtd_invalid" in before["errors"]
    assert "gtd_invalid" in _exemplar(before)["errors"]
    history = deepcopy(documents.document_data(order))
    reply = deepcopy(rejected)
    reply["status"] = "ship_available"
    _exemplar(reply)["gtd_error_codes"] = []
    if missing:
        sku, exemplar_id = MISSING[missing]
        if missing.endswith("product"):
            reply["products"] = [p for p in reply["products"] if p["product_id"] != sku]
        else:
            product = next(p for p in reply["products"] if p["product_id"] == sku)
            product["exemplars"] = [
                e for e in product["exemplars"] if e["exemplar_id"] != exemplar_id
            ]
    transport.endpoint_responses[STATUS] = reply
    calls_before = len(transport.endpoint_calls)
    view = await documents.get_exemplar_documents(session, **kwargs)
    reads = transport.endpoint_calls[calls_before:]
    assert [path for path, _ in reads] == [STATUS]
    assert view["status"] == "ship_available"
    assert view["version"] == before["version"] == history["version"]
    assert view["editable"] is True
    stored = documents.document_data(order)
    assert stored["choices"] == history["choices"]
    assert stored["choice"] == history["choice"]
    assert stored["version"] == history["version"]
    assert _exemplar(stored["snapshot"])["gtd"] == "CABINET-NEW"
    assert history["choices"][f"{SKU_ONE}:81"]["gtd"] == "001/ABC-09"
    # Compare all displayed values to the actual fresh reply, or to the last
    # observed snapshot where this reply omitted an exemplar. Retention is not
    # evidence of acceptance, nor is an old raw error a fresh rejection.
    for product in before["products"]:
        for prior in product["exemplars"]:
            sku, exemplar_id = product["product_id"], prior["exemplar_id"]
            try:
                expected = _exemplar(reply, sku, exemplar_id)
            except StopIteration:
                expected = prior
            for field in VALUE_FIELDS:
                assert _exemplar(view, sku, exemplar_id)[field] == expected[field], field
                assert _exemplar(stored["snapshot"], sku, exemplar_id)[field] == expected[field]
    assert sum(path == SET for path, _ in transport.endpoint_calls) == 1
    return order, first, transport, rejected, view, kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", MISSING)
async def test_f4r_partial_fresh_status_does_not_accept_all_displayed_documents(
    db_session, missing
):
    _, _, _, _, view, _ = await _fresh_reply_after_rejection(db_session, missing)
    sku, exemplar_id = MISSING[missing]
    absent = _exemplar(view, sku, exemplar_id)
    assert absent["state"] == "unknown"
    assert absent["errors"] == []  # No fresh rejection was returned for it.
    if missing.startswith("a_"):
        assert absent["gtd"] == "CABINET-NEW"
        assert absent["gtd_error_codes"] == ["gtd_invalid"]  # Historical snapshot retained.
    assert view["errors"] == []
    assert view["state"] == "unknown", (
        "Partial ship_available is not positive proof for every displayed document", view
    )


@pytest.mark.asyncio
async def test_f4r_complete_healthy_reply_accepts_current_cabinet_values(db_session):
    _, _, _, _, view, _ = await _fresh_reply_after_rejection(db_session)
    assert view["state"] == "accepted"
    assert view["errors"] == []
    assert _exemplar(view)["gtd"] == "CABINET-NEW"
    assert _exemplar(view)["gtd_error_codes"] == []
    assert all(e["state"] == "accepted" and e["errors"] == []
               for p in view["products"] for e in p["exemplars"])


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["a_exemplar", "a_product"])
@pytest.mark.parametrize("next_write", ["documents_b", "marking"])
async def test_f4r_partial_read_keeps_next_explicit_action_allowed(
    db_session, missing, next_write
):
    order, first, transport, fresh, view, kwargs = await _fresh_reply_after_rejection(
        db_session, missing
    )
    # A second partial read must not turn historical A into a pending writer.
    calls_before = len(transport.endpoint_calls)
    again = await documents.get_exemplar_documents(db_session, **kwargs)
    assert again["version"] == view["version"]
    assert again["editable"] is True
    assert _exemplar(again)["gtd"] == "CABINET-NEW"
    assert [path for path, _ in transport.endpoint_calls[calls_before:]] == [STATUS]
    # Explicit Save/scan may obtain a full current snapshot, even though the
    # preceding read was partial. Its independent final acceptance is not claimed.
    assert transport.endpoint_responses[SNAPSHOT] == fresh
    if next_write == "documents_b":
        await documents.save_exemplar_documents(
            db_session, tenant_id=order.tenant_id, order_id=order.id,
            product_id=SKU_TWO, exemplar_id=91,
            gtd=None, is_gtd_absent=True, rnpt="NEW-B", is_rnpt_absent=False,
            expected_version=again["version"], provider=kwargs["provider"],
            client_id="fake-client", api_key="fake-key",
        )
    else:
        await _scan(db_session, order, first, transport, 82)
    writes = [payload for path, payload in transport.endpoint_calls if path == SET]
    assert len(writes) == 2
    assert documents.document_data(order)["version"] == view["version"] + 1
    for field in VALUE_FIELDS:
        assert _exemplar(writes[-1])[field] == _exemplar(fresh)[field], field
    if next_write == "documents_b":
        assert _exemplar(writes[-1], SKU_TWO, 91)["rnpt"] == "NEW-B"
    else:
        assert _exemplar(writes[-1], exemplar_id=82)["marks"][-1]["mark"].endswith("82")


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["a_exemplar", "a_product"])
@pytest.mark.parametrize("kind", ["documents", "marking"])
async def test_f4r_partial_read_preserves_stale_version_control(db_session, missing, kind):
    order, _, transport, _, view, _ = await _fresh_reply_after_rejection(db_session, missing)
    before = documents.document_data(order)
    count = len(transport.endpoint_calls)
    choice = dict(product_id=SKU_TWO, exemplar_id=91, gtd=None, rnpt="STALE",
                  is_gtd_absent=True, is_rnpt_absent=False) if kind == "documents" else {
                      "marking_id": "stale"
                  }
    with pytest.raises(process.OzonFbsProcessError) as error:
        await documents.claim_exemplar_write(
            db_session, order, view["version"] - 1, kind=kind, choice=choice
        )
    assert error.value.status_code == 409
    assert error.value.code == "ozon_exemplar_documents_conflict"
    assert documents.document_data(order) == before
    assert len(transport.endpoint_calls) == count


# Keeping the DOM source here keeps ownership confined to this new contract.
# The JSON is the actual service output above, not a hand-written mock view.
DOM_CONTRACT = r'''
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import { OzonExemplarDocuments } from __COMPONENT__
import view from './view.json'

it('fresh service result displays its honest acceptance label and cabinet value', async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => view })))
  const host = document.createElement('div')
  document.body.appendChild(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(
      <OzonExemplarDocuments orderId="f4r" token="fake" authHeaders={() => ({})} />
    ))
    await act(async () => Array.from(host.querySelectorAll('button'))
      .find(button => button.textContent === 'ГТД / РНПТ').click())
    const input = host.querySelector('input[aria-label="Номер ГТД · SKU 663001 · экземпляр 1"]')
    expect(input.value).toBe('CABINET-NEW')
    expect(input.disabled).toBe(false)
    console.log(JSON.stringify({ accepted: host.textContent.includes('Принято'),
      unknown: host.textContent.includes('Результат Ozon пока неизвестен'), value: input.value }))
    if (__HEALTHY__) {
      expect(host.textContent).toContain('Принято')
      expect(host.textContent).not.toContain('Результат Ozon пока неизвестен')
    } else {
      expect(host.textContent).not.toContain('Принято')
      expect(host.textContent).toContain('Результат Ozon пока неизвестен')
    }
  } finally {
    await act(async () => root.unmount())
    host.remove()
    vi.unstubAllGlobals()
  }
})
'''


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["a_exemplar", "a_product", None])
async def test_f4r_real_component_label_with_actual_service_reply(db_session, tmp_path, missing):
    frontend = Path(__file__).resolve().parents[2] / "frontend"
    vitest = frontend / "node_modules/.bin/vitest"
    if not vitest.is_file():
        pytest.skip("DOM contract needs the existing frontend vitest/jsdom dependencies")
    _, _, _, _, view, _ = await _fresh_reply_after_rejection(db_session, missing)
    scratch = tmp_path.resolve()
    (scratch / "node_modules").symlink_to((frontend / "node_modules").resolve())
    (scratch / "view.json").write_text(json.dumps(view), encoding="utf-8")
    source = DOM_CONTRACT.replace(
        "__COMPONENT__", json.dumps(str(frontend / "src/screens/v2/OzonExemplarDocuments.tsx"))
    ).replace("__HEALTHY__", "true" if missing is None else "false")
    (scratch / "partial.test.tsx").write_text(source, encoding="utf-8")
    config = scratch / "vite.config.mjs"
    config.write_text(
        'export default { esbuild: { jsx: "automatic" }, test: { environment: "jsdom" } }',
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(vitest), "run", "partial.test.tsx", "--root", str(scratch), "--config", str(config),
         "--maxWorkers", "1", "--minWorkers", "1"],
        cwd=frontend, capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
