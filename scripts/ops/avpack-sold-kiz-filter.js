'use strict';

(function exposeAvpackSoldKizFilter(root, factory) {
  const api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.AvpackSoldKizFilter = api;
})(typeof globalThis === 'undefined' ? this : globalThis, function buildAvpackSoldKizFilter(globalRoot) {
  const EXPECTED_ORIGIN = 'https://wms.sellerfocus.pro';
  const EXPECTED_PATH = '/seller/honest-sign/withdrawals';
  const EXPECTED_TENANT = 'd6e1ad21-8afa-4acf-8d0b-907b9f2adcfe';
  const EXPECTED_SELLER = '0b8da5d8-f43a-42f5-a2ec-43173ea844bd';
  const TOKEN_STORAGE_KEY = 'wms_token_seller';
  const REGISTRY_PATH = '/api/operations/marking-codes/self/withdrawals';
  const PAGE_SIZE = 250;
  const FILTER_MARKER = Symbol.for('wms.avpackSoldKizFilter.active');

  // Eligibility and prices come only from the current server sales-backed registry.
  // No historical row IDs or WB status predicate are maintained in the helper.
  class SoldKizFilterError extends Error {
    constructor(message) {
      super(message);
      this.name = 'SoldKizFilterError';
    }
  }

  const normalizedText = (node) => String(node?.textContent ?? '').replace(/\s+/g, ' ').trim();

  function createDomAdapter(root) {
    const document = root?.document;
    const waitFor = async (predicate, message) => {
      for (let attempt = 0; attempt < 80; attempt += 1) {
        const value = predicate();
        if (value) return value;
        await new Promise((resolve) => root.setTimeout(resolve, 100));
      }
      throw new SoldKizFilterError(message);
    };
    const page = () => {
      const pages = [...(document?.querySelectorAll?.('[data-testid="seller-kiz-withdrawal-page"]') ?? [])];
      if (pages.length !== 1) throw new SoldKizFilterError('Ожидался ровно один экран вывода КИЗ.');
      return pages[0];
    };
    const actionButton = (container, count) => [...container.querySelectorAll('button')].find(
      (button) => normalizedText(button) === `Вывести из оборота (${count})`,
    );
    return {
      async inspectSelection() {
        const container = page();
        if (document.querySelector('[role="dialog"]')) {
          throw new SoldKizFilterError('Закройте открытый диалог перед запуском.');
        }
        const selectedLabel = [...container.querySelectorAll('*')].find((node) =>
          /^Выбрано КИЗ:\s*\d+$/.test(normalizedText(node)),
        );
        const selectedCount = Number(normalizedText(selectedLabel).match(/(\d+)$/)?.[1] ?? 0);
        return { selectedCount };
      },
      async clearFilters() {
        const container = page();
        const field = (label) => {
          const labels = [...container.querySelectorAll('label')].filter(
            (node) => normalizedText(node) === label,
          );
          if (labels.length !== 1) throw new SoldKizFilterError(`Не найдено поле «${label}».`);
          const id = labels[0].getAttribute('for');
          const input = id ? document.getElementById(id) : labels[0].querySelector('input');
          if (!input) throw new SoldKizFilterError(`Не найдено поле «${label}».`);
          return input;
        };
        const setEmpty = (input) => {
          // React tracks value assignments: use the native setter and dispatch its input event.
          const setter = Object.getOwnPropertyDescriptor(root.HTMLInputElement.prototype, 'value').set;
          setter.call(input, '');
          input.dispatchEvent(new root.Event('input', { bubbles: true }));
          input.dispatchEvent(new root.Event('change', { bubbles: true }));
        };
        const product = field('Товар');
        if (product.value) {
          const clear = product.closest('.MuiAutocomplete-root')?.querySelector('button[title="Clear"], button[aria-label="Clear"]')
            ?? product.parentElement.querySelector('button[title="Clear"], button[aria-label="Clear"]');
          if (!clear || clear.disabled) throw new SoldKizFilterError('Штатная очистка товара недоступна.');
          clear.click();
        }
        for (const label of ['Передано WB с', 'по', 'Поиск']) setEmpty(field(label));
        const only = [...container.querySelectorAll('input[role="switch"]')].filter((input) =>
          /Только не\s*выведенные/.test(normalizedText(input.closest('label'))),
        );
        if (only.length !== 1 || only[0].disabled) throw new SoldKizFilterError('Фильтр невыведенных КИЗ недоступен.');
        if (!only[0].checked) only[0].click();
        // Let React commit all fields and its debounced search before the explicit refresh.
        await new Promise((resolve) => root.setTimeout(resolve, 400));
        if (['Передано WB с', 'по', 'Товар', 'Поиск'].some((label) => field(label).value !== '') || !only[0].checked) {
          throw new SoldKizFilterError('Штатный экран не подтвердил очистку фильтров.');
        }
      },
      async refreshSelectAllAndOpen(expectedCount, assertCurrentSession) {
        const container = page();
        const refresh = [...container.querySelectorAll('button')].filter(
          (button) => normalizedText(button) === 'Обновить',
        );
        if (refresh.length !== 1 || refresh[0].disabled) {
          throw new SoldKizFilterError('Штатная кнопка обновления реестра недоступна.');
        }
        refresh[0].click();
        await waitFor(
          () => [...container.querySelectorAll('*')].some(
            (node) => normalizedText(node) === `Найдено: ${expectedCount}`,
          ),
          `Штатный экран не показал ровно ${expectedCount} проверенных КИЗ.`,
        );
        assertCurrentSession();
        const selectAll = await waitFor(() => {
          const inputs = [...container.querySelectorAll('input[aria-label="Выбрать все доступные КИЗ по фильтрам"]')];
          return inputs.length === 1 && !inputs[0].disabled ? inputs[0] : null;
        }, 'Штатный выбор всех КИЗ недоступен.');
        if (selectAll.checked) throw new SoldKizFilterError('Перед запуском снимите текущее выделение КИЗ.');
        assertCurrentSession();
        selectAll.click();
        assertCurrentSession();
        const action = await waitFor(() => {
          const button = actionButton(container, expectedCount);
          return button && !button.disabled ? button : null;
        }, `Штатный экран не подтвердил выбор ровно ${expectedCount} КИЗ.`);
        assertCurrentSession();
        action.click();
        await waitFor(
          () => [...document.querySelectorAll('[role="dialog"]')].some(
            (dialog) => normalizedText(dialog).includes('Выберите сертификат'),
          ),
          'Штатный диалог выбора сертификата не открылся.',
        );
        assertCurrentSession();
        return { selectedCount: expectedCount, dialogOpen: true };
      },
      async rollbackPreparation() {
        const container = page();
        const dialogs = [...document.querySelectorAll('[role="dialog"]')];
        for (const dialog of dialogs) {
          if (!normalizedText(dialog).includes('Выберите сертификат')) continue;
          const close = [...dialog.querySelectorAll('button')].find(
            (button) => button.getAttribute?.('aria-label') === 'Закрыть' && !button.disabled,
          );
          close?.click();
        }
        const selectAll = container.querySelector(
          'input[aria-label="Выбрать все доступные КИЗ по фильтрам"]',
        );
        if (selectAll?.checked && !selectAll.disabled) selectAll.click();
      },
    };
  }

  function createHelper(dependencies = {}) {
    const root = dependencies.root ?? globalRoot;
    if (root?.fetch?.[FILTER_MARKER] === true) {
      throw new SoldKizFilterError(
        'Локальный фильтр уже установлен. Завершите текущий диалог или перезагрузите вкладку.',
      );
    }
    const location = root?.location;
    const storage = root?.localStorage;
    const originalFetch = root?.fetch;
    const callOriginalFetch = (input, init) => originalFetch.call(root, input, init);
    const ResponseClass = root?.Response;
    const ui = dependencies.ui ?? createDomAdapter(root);

    const assertLocation = () => {
      if (!location || location.origin !== EXPECTED_ORIGIN || ![EXPECTED_PATH, `${EXPECTED_PATH}/`].includes(location.pathname)) {
        throw new SoldKizFilterError(`Откройте ${EXPECTED_ORIGIN}${EXPECTED_PATH} перед запуском.`);
      }
    };
    const readToken = () => {
      const token = storage?.getItem?.(TOKEN_STORAGE_KEY);
      if (typeof token !== 'string' || token.length === 0) {
        throw new SoldKizFilterError('Войдите в seller-кабинет перед запуском.');
      }
      return token;
    };
    const requestJson = async (path, token) => {
      if (typeof originalFetch !== 'function') throw new SoldKizFilterError('Браузерный fetch недоступен.');
      let response;
      try {
        response = await callOriginalFetch(`${EXPECTED_ORIGIN}${path}`, {
          method: 'GET',
          headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
          redirect: 'error',
        });
      } catch {
        throw new SoldKizFilterError(`GET ${path.split('?')[0]} недоступен. Подготовка остановлена.`);
      }
      if (!response?.ok) throw new SoldKizFilterError(`GET ${path.split('?')[0]} вернул HTTP ${response?.status ?? 'unknown'}.`);
      try {
        return await response.json();
      } catch {
        throw new SoldKizFilterError(`GET ${path.split('?')[0]} вернул некорректный JSON.`);
      }
    };
    const validateIdentity = (identity) => {
      if (!identity || identity.tenant_id !== EXPECTED_TENANT || identity.seller_id !== EXPECTED_SELLER ||
          identity.active_seller_id !== EXPECTED_SELLER || identity.role !== 'fulfillment_seller' ||
          identity.withdrawal_enabled !== true) {
        throw new SoldKizFilterError('Текущий tenant, seller, роль или право вывода не совпадают с AVpack/ИП Горячкина.');
      }
    };
    const assertCurrentToken = (token) => {
      assertLocation();
      if (readToken() !== token) throw new SoldKizFilterError('Seller-сессия изменилась во время подготовки.');
    };
    const readRegistry = async (token) => {
      const rows = [], ids = new Set();
      let expectedTotal = null;
      for (let offset = 0; expectedTotal === null || offset < expectedTotal; offset += PAGE_SIZE) {
        assertCurrentToken(token);
        const page = await requestJson(
          `${REGISTRY_PATH}?only_not_withdrawn=true&limit=${PAGE_SIZE}&offset=${offset}`, token,
        );
        assertCurrentToken(token);
        if (!page || !Array.isArray(page.rows) || !Number.isSafeInteger(page.total) || page.total < 0) {
          throw new SoldKizFilterError('Реестр вернул неожиданную структуру.');
        }
        if (expectedTotal === null) expectedTotal = page.total;
        if (page.total !== expectedTotal || page.rows.length !== Math.min(PAGE_SIZE, expectedTotal - offset)) {
          throw new SoldKizFilterError('Реестр изменился или прочитан не полностью. Обновите страницу.');
        }
        for (const row of page.rows) {
          if (!row || typeof row.row_id !== 'string' || !row.row_id || ids.has(row.row_id) ||
              (row.tenant_id !== undefined && row.tenant_id !== EXPECTED_TENANT) ||
              (row.seller_id !== undefined && row.seller_id !== EXPECTED_SELLER)) {
            throw new SoldKizFilterError('Реестр содержит повторную строку или неожиданный состав.');
          }
          ids.add(row.row_id);
          rows.push(row);
        }
      }
      return rows.filter((row) => row.status === 'not_withdrawn' && row.operation_id === null && !row.error);
    };
    const installFreshRegistry = (token, targets) => {
      if (!root || typeof ResponseClass !== 'function' || typeof originalFetch !== 'function') {
        throw new SoldKizFilterError('Браузер не поддерживает безопасную подготовку.');
      }
      const expectedIds = new Set(targets.map((row) => row.row_id));
      const patchedFetch = async (input, init = {}) => {
        const url = new URL(typeof input === 'string' || input instanceof URL ? input : input.url, location.origin);
        const method = String(init.method ?? input?.method ?? 'GET').toUpperCase();
        if (method !== 'GET' || url.origin !== EXPECTED_ORIGIN || url.pathname !== REGISTRY_PATH) {
          return callOriginalFetch(input, init);
        }
        assertCurrentToken(token);
        const limit = Number(url.searchParams.get('limit') ?? '50');
        const offset = Number(url.searchParams.get('offset') ?? '0');
        if (![50, 100, 250].includes(limit) || !Number.isInteger(offset) || offset < 0) {
          throw new SoldKizFilterError('Штатный экран запросил неожиданную пагинацию.');
        }
        // Read every original page afresh, including during native mass selection.
        // Never answer from the initial snapshot when returns/claims changed its set.
        const fresh = await readRegistry(token);
        if (fresh.length !== expectedIds.size || fresh.some((row) => !expectedIds.has(row.row_id))) {
          throw new SoldKizFilterError('Пригодный состав КИЗ изменился. Обновите страницу перед новой подготовкой.');
        }
        return new ResponseClass(JSON.stringify({ rows: fresh.slice(offset, offset + limit), total: fresh.length }), {
          status: 200, headers: { 'content-type': 'application/json' },
        });
      };
      Object.defineProperty(patchedFetch, FILTER_MARKER, { value: true });
      root.fetch = patchedFetch;
      return () => { if (root.fetch === patchedFetch) root.fetch = originalFetch; };
    };

    const run = async (input = {}) => {
      assertLocation();
      const mode = input?.mode ?? 'dry-run';
      if (!input || typeof input !== 'object' || Array.isArray(input) || !['dry-run', 'execute'].includes(mode)) {
        throw new SoldKizFilterError('Режим должен быть равен dry-run или execute.');
      }
      const token = readToken();
      validateIdentity(await requestJson('/api/auth/me', token));
      const targets = await readRegistry(token);
      const inspection = await ui.inspectSelection();
      if (!inspection || inspection.selectedCount !== 0) {
        throw new SoldKizFilterError('Перед запуском снимите все ранее выбранные КИЗ.');
      }
      if (readToken() !== token) throw new SoldKizFilterError('Seller-сессия изменилась во время проверки.');
      if (targets.length === 0) {
        return Object.freeze({ mode, status: 'empty', targetCount: 0, noSend: true, signed: false, sent: false });
      }
      if (mode === 'dry-run') {
        return Object.freeze({ mode, status: 'ready', targetCount: targets.length, noSend: true, signed: false, sent: false });
      }
      validateIdentity(await requestJson('/api/auth/me', token));
      const restore = installFreshRegistry(token, targets);
      const assertCurrentSession = () => assertCurrentToken(token);
      try {
        assertCurrentSession();
        await ui.clearFilters();
        assertCurrentSession();
        const opened = await ui.refreshSelectAllAndOpen(targets.length, assertCurrentSession);
        if (!opened || opened.selectedCount !== targets.length || opened.dialogOpen !== true) {
          throw new SoldKizFilterError('Штатный экран не подтвердил точное выделение и диалог сертификата.');
        }
        assertCurrentSession();
        validateIdentity(await requestJson('/api/auth/me', token));
        assertCurrentSession();
        restore();
        return Object.freeze({
          mode,
          status: 'certificate_dialog_open',
          targetCount: targets.length,
          noSend: true,
          signed: false,
          sent: false,
          message: `Выбраны ${targets.length} пригодных КИЗ из свежего реестра WMS. Сертификат и отправку подтверждает Виталий.`,
        });
      } catch (error) {
        try {
          await ui.rollbackPreparation?.();
        } catch {
          // The original error is more useful. Reloading the tab is the final rollback.
        }
        restore();
        throw error;
      }
    };

    return Object.freeze({ run });
  }

  return Object.freeze({ createHelper });
});
