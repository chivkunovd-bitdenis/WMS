import type { Plugin } from "vite";
import { fileURLToPath } from "node:url";
const controls = fileURLToPath(new URL("./Controls.tsx", import.meta.url));
function replaceOnce(
  code: string,
  target: string,
  replacement: string,
  id: string,
) {
  if (code.split(target).length !== 2)
    throw new Error("WMS686: исходный фрагмент изменился: " + id);
  return code.replace(target, replacement);
}
export function demoTransform(): Plugin {
  return {
    name: "wms686-isolated-extensions",
    enforce: "pre",
    transform(code, id) {
      // Existing print controls keep their markup; only native print calls are
      // replaced in this demo bundle, including calls on iframe windows.
      if (/\/frontend\/src\/utils\/print[^/]+\.ts$/.test(id)) {
        const nativePrint = /\b[A-Za-z_$][\w$]*\.print\(\)/g;
        if (nativePrint.test(code)) {
          const guarded = code.replace(
            nativePrint,
            "window.dispatchEvent(new Event('wms686-print-blocked'))",
          );
          if (/\.\s*print\s*\(/.test(guarded))
            throw new Error(
              "WMS686: новый неперехваченный вызов печати: " + id,
            );
          return guarded;
        }
      }
      if (id.endsWith("/unload-pick/UnloadPickScreen.tsx")) {
        code =
          `import {FboPickActions} from ${JSON.stringify(controls)};\n` + code;
        code = replaceOnce(
          code,
          'testId="pick-scan"\n            listening={scannerListening}\n          />',
          'testId="pick-scan"\n            listening={scannerListening}\n          />\n          <FboPickActions source={source} />',
          id,
        );
        return code;
      }
      if (id.endsWith("/FfPackagingPage.tsx")) {
        code =
          `import {FboPackingActions} from ${JSON.stringify(controls)};\n` +
          code;
        code = replaceOnce(
          code,
          "sx={{ maxWidth: '100%', overflowX: 'hidden' }}>",
          "sx={{ maxWidth: '100%', overflowX: 'hidden' }}>\n      {isMpUnloadTask ? <FboPackingActions /> : null}",
          id,
        );
        return code;
      }
      if (id.endsWith("/FfSuppliesShipmentsPage.tsx")) {
        code = replaceOnce(
          code,
          "  useEffect(() => {\n    void loadPackagingTask()\n  }, [loadPackagingTask])",
          `  useEffect(() => {\n    void loadPackagingTask()\n  }, [loadPackagingTask])\n  useEffect(() => { const refresh = () => { void loadDocDetail(); void loadPackagingTask() }; window.addEventListener('wms686-change', refresh); return () => window.removeEventListener('wms686-change', refresh) }, [loadDocDetail, loadPackagingTask])`,
          id,
        );
        return code;
      }
      if (id.endsWith("/unload-pick/FfUnloadPickPage.tsx")) {
        code = replaceOnce(
          code,
          "  useEffect(() => {\n    void load()\n  }, [load])",
          `  useEffect(() => {\n    void load()\n  }, [load])\n  useEffect(() => {const refresh=()=>void load(); window.addEventListener('wms686-change',refresh); return ()=>window.removeEventListener('wms686-change',refresh)},[load])`,
          id,
        );
        return code;
      }
    },
  };
}
