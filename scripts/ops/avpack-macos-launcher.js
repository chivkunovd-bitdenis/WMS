'use strict';

(function exposeMacLauncher(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.Wms665MacLauncher = api;
})(typeof globalThis === 'undefined' ? this : globalThis, function buildMacLauncher() {
  const TARGET_URL = 'https://wms.sellerfocus.pro/seller/honest-sign/withdrawals';
  const RUN_MARKER = '__WMS665_MAC_RUN__';
  const DEFAULT_MAX_POLLS = 2400;

  class MacLauncherError extends Error {
    constructor(message) {
      super(message);
      this.name = 'MacLauncherError';
    }
  }

  const fail = (message) => new MacLauncherError(message);

  function isTargetUrl(value) {
    if (typeof value !== 'string') return false;
    return /^https:\/\/wms\.sellerfocus\.pro\/seller\/honest-sign\/withdrawals\/?(?:[?#].*)?$/.test(value);
  }

  function sanitizedState(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
    if (
      value.status === 'certificate_dialog_open' &&
      Number.isSafeInteger(value.targetCount) && value.targetCount > 0 &&
      value.noSend === true &&
      value.signed === false &&
      value.sent === false
    ) {
      return Object.freeze({
        status: 'certificate_dialog_open',
        targetCount: value.targetCount,
        noSend: true,
        signed: false,
        sent: false,
      });
    }
    if (value.status === 'running' && value.signed === false && value.sent === false) {
      return Object.freeze({ status: 'running', signed: false, sent: false });
    }
    if (value.status === 'error' && value.signed === false && value.sent === false) {
      return Object.freeze({ status: 'error', signed: false, sent: false });
    }
    return Object.freeze({ status: 'error', signed: false, sent: false });
  }

  function parseBrowserState(raw) {
    if (typeof raw !== 'string') throw fail('Chrome вернул некорректный статус запуска. Повтор автоматически не выполнялся.');
    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch {
      throw fail('Chrome вернул некорректный статус запуска. Повтор автоматически не выполнялся.');
    }
    if (parsed === null) return null;
    return sanitizedState(parsed);
  }

  const statusSource = (probe) => `(() => {
    /* ${probe ? 'WMS665_PROBE' : 'WMS665_STATUS'} */
    const state = globalThis.${RUN_MARKER};
    if (!state || typeof state !== 'object' || Array.isArray(state)) return JSON.stringify(state == null ? null : { status: 'error', signed: false, sent: false });
    if (state.status === 'certificate_dialog_open' && Number.isSafeInteger(state.targetCount) && state.targetCount > 0 && state.noSend === true && state.signed === false && state.sent === false) {
      return JSON.stringify({ status: 'certificate_dialog_open', targetCount: state.targetCount, noSend: true, signed: false, sent: false });
    }
    if (state.status === 'running' && state.signed === false && state.sent === false) return JSON.stringify({ status: 'running', signed: false, sent: false });
    return JSON.stringify({ status: 'error', signed: false, sent: false });
  })()`;

  function injectionSource(helperSource) {
    return `(() => {
      const marker = '${RUN_MARKER}';
      const current = globalThis[marker];
      if (current && typeof current === 'object') {
        if (current.status === 'certificate_dialog_open' && Number.isSafeInteger(current.targetCount) && current.targetCount > 0 && current.noSend === true && current.signed === false && current.sent === false) {
          return JSON.stringify({ status: 'certificate_dialog_open', targetCount: current.targetCount, noSend: true, signed: false, sent: false });
        }
        if (current.status === 'running' && current.signed === false && current.sent === false) return JSON.stringify({ status: 'running', signed: false, sent: false });
        return JSON.stringify({ status: 'error', signed: false, sent: false });
      }
      const page = globalThis.location;
      if (!page || page.origin !== 'https://wms.sellerfocus.pro' ||
          (page.pathname !== '/seller/honest-sign/withdrawals' && page.pathname !== '/seller/honest-sign/withdrawals/')) {
        globalThis[marker] = { status: 'error', signed: false, sent: false };
        return JSON.stringify({ status: 'error', signed: false, sent: false });
      }
      globalThis[marker] = { status: 'running', signed: false, sent: false };
      try {
${helperSource}
        const helperApi = globalThis.AvpackSoldKizFilter;
        if (!helperApi || typeof helperApi.createHelper !== 'function') throw new Error('helper unavailable');
        const browserHelper = helperApi.createHelper({ assertActive: () => {
          if (globalThis[marker]?.status !== 'running') throw new Error('run cancelled');
        } });
        if (!browserHelper || typeof browserHelper.run !== 'function') throw new Error('runner unavailable');
        Promise.resolve(browserHelper.run({ mode: 'execute' })).then((result) => {
          if (globalThis[marker]?.status !== 'running') return;
          if (result && result.status === 'certificate_dialog_open' && Number.isSafeInteger(result.targetCount) && result.targetCount > 0 && result.noSend === true && result.signed === false && result.sent === false) {
            globalThis[marker] = { status: 'certificate_dialog_open', targetCount: result.targetCount, noSend: true, signed: false, sent: false };
          } else {
            globalThis[marker] = { status: 'error', signed: false, sent: false };
          }
        }, () => {
          globalThis[marker] = { status: 'error', signed: false, sent: false };
        });
      } catch (_) {
        globalThis[marker] = { status: 'error', signed: false, sent: false };
      }
      return JSON.stringify({ status: 'running', signed: false, sent: false });
    })()`;
  }

  function evaluateSafely(chrome, tabId, source) {
    try {
      return chrome.evaluate(tabId, source);
    } catch {
      throw fail(
        'Chrome запретил управление вкладкой. Включите View → Developer → Allow JavaScript from Apple Events и разрешите Terminal управлять Chrome в настройках macOS Automation.',
      );
    }
  }

  function launch(input = {}) {
    const chrome = input.chrome;
    const helperSource = input.helperSource;
    const wait = input.wait;
    const maxPolls = input.maxPolls ?? DEFAULT_MAX_POLLS;
    if (!chrome || typeof chrome.running !== 'function' || typeof chrome.tabs !== 'function' || typeof chrome.evaluate !== 'function') {
      throw fail('Внутренняя ошибка оболочки Chrome. Запуск не выполнялся.');
    }
    if (typeof helperSource !== 'string' || helperSource.length === 0 || typeof wait !== 'function') {
      throw fail('Встроенный помощник повреждён. Запуск не выполнялся.');
    }
    if (!Number.isInteger(maxPolls) || maxPolls < 1 || maxPolls > 2400) {
      throw fail('Некорректный предел ожидания. Запуск не выполнялся.');
    }

    let running;
    try {
      running = chrome.running();
    } catch {
      throw fail('Нет доступа к Chrome через macOS Automation. Разрешите Terminal управлять Chrome и повторите запуск.');
    }
    if (running !== true) throw fail('Сначала откройте Google Chrome и авторизованную страницу вывода КИЗ.');

    let tabs;
    try {
      tabs = chrome.tabs();
    } catch {
      throw fail('Нет доступа к вкладкам Chrome через macOS Automation. Разрешите Terminal управлять Chrome и повторите запуск.');
    }
    if (!Array.isArray(tabs)) throw fail('Chrome вернул некорректный список вкладок. Запуск не выполнялся.');
    const matches = tabs.filter((tab) => tab && isTargetUrl(tab.url));
    if (matches.length !== 1) {
      throw fail(`Откройте ровно одну вкладку ${TARGET_URL} и закройте её дубликаты.`);
    }
    const tabId = matches[0].id;

    let state = parseBrowserState(evaluateSafely(chrome, tabId, statusSource(true)));
    if (state?.status === 'certificate_dialog_open') return state;
    if (state?.status === 'error') throw fail('Предыдущий запуск завершился ошибкой. Автоматический повтор отключён; перезагрузите вкладку перед новой попыткой.');

    if (state === null) {
      state = parseBrowserState(evaluateSafely(chrome, tabId, injectionSource(helperSource)));
      if (state?.status === 'certificate_dialog_open') return state;
      if (state?.status === 'error') throw fail('Помощник безопасно остановился. Подпись и отправка не выполнялись.');
    }

    for (let attempt = 0; attempt < maxPolls; attempt += 1) {
      wait();
      state = parseBrowserState(evaluateSafely(chrome, tabId, statusSource(false)));
      if (state?.status === 'certificate_dialog_open') return state;
      if (state?.status === 'error') throw fail('Помощник безопасно остановился. Подпись и отправка не выполнялись.');
    }
    evaluateSafely(chrome, tabId, `(() => {
      /* WMS517_CANCEL */
      const state = globalThis.${RUN_MARKER};
      if (state?.status === 'running') globalThis.${RUN_MARKER} = { status: 'error', signed: false, sent: false };
      return JSON.stringify({ status: 'error', signed: false, sent: false });
    })()`);
    throw fail('Время ожидания истекло. Подготовка отменена, подпись и отправка не выполнялись. Автоматический повтор отключён; перезагрузите вкладку перед новой попыткой.');
  }

  return Object.freeze({ launch });
});
