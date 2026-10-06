import { mergeConfig } from 'vite';
import original from './wms672-vite.config.ts';
const target = "setError(e instanceof Error ? e.message : 'Не удалось напечатать этикетки.')";
export default mergeConfig(original, {
  cacheDir: `${process.env.RUNNER_TEMP || '/tmp'}/wms672-c5-diagnostic-vite-cache`,
  plugins: [{
    name: 'c5-error-observation-only', enforce: 'pre',
    transform(source, id) {
      if (!id.split('?')[0].endsWith('/src/screens/ff/FfInboundRequestView.tsx')) return;
      if (source.split(target).length !== 2) throw new Error('Diagnostic screen catch target drift');
      return source.replace(target, `;(window as any).__wms672DiagnosticRecord?.('screen-catch', e); ${target}`);
    },
  }],
});
