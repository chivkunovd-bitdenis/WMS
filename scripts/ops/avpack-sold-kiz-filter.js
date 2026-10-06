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
  const TARGET_COUNT = 80;
  const FILTER_MARKER = Symbol.for('wms.avpackSoldKizFilter.active');

  // Production read-only snapshot, 2026-10-05: exact WMS-517 eligible rows with
  // FbsOrder.wb_status == "sold", no active withdrawal claim and valid WB price.
  // CIS values are deliberately not persisted in this operational script.
  const TARGET_ROW_IDS = Object.freeze([
    '076e540e-a663-4b4e-acac-c76f1bc32b47', '0d2b2f9f-799c-476c-b4f8-8090efff5ddb',
    '1448adff-ab8f-4b98-bb93-ff1c94884354', '16ac02f7-d28c-4ad7-a2d1-1de398b91b10',
    '194cec2f-a1fe-455f-adea-8c18c47af7c4', '1b7364c8-3cd5-4df2-8f82-6d5920686b67',
    '1d31f59a-61c1-44fe-aabf-d8fed9393f22', '20765aea-1118-41c0-83b2-539747460d80',
    '2203a0ff-70fd-4bc5-a1dd-cf2e2b99f865', '249ccc60-7b88-4c4f-9951-1645943d62d2',
    '2797064e-6eb8-4591-9f10-b8c158d78573', '2a711328-07d8-4d18-98b3-de5d5286cb8e',
    '2d7f9070-3296-4e0a-9b37-f9caa732fa64', '2dc9344b-0445-43e6-a142-703018d48631',
    '2f47bddf-0f62-453c-a90f-4b016c9ccea0', '3bb90f51-e57b-4d62-858f-f9893e4700cf',
    '3db6a144-c80d-4ffe-82ff-48fd464c9b9e', '4c2424e6-8694-4ce8-a4ae-bf8c26ff12f5',
    '4e7d9860-af10-4e94-ac80-69d477cf4732', '5358c1aa-8ec1-45b6-8575-c5929eaa1a50',
    '5ace981a-716f-4776-80cf-4e7d3a5e964a', '5f2ab33c-8977-4004-b933-cc9e659f081a',
    '61ccae09-7fba-4d12-b07a-64f77199e888', '654d84c2-2e3b-4666-81d8-1d3de30a5ddf',
    '677a666e-bc7a-454b-8854-b54db56e0773', '68b5caae-b6f4-4551-8fd4-5c582cd67861',
    '6990f114-490f-4c26-9e27-9c2a01d68535', '6c5b9ad3-d9d9-47af-a62e-5fe00cdde91a',
    '7389967b-1e87-4b66-9797-c9d641b99e9f', '76dbb4e8-a225-4b9e-ac26-3263dd4eaef3',
    '795de647-69e7-402f-aef7-d94686d21181', '79ea2e70-afc8-4ac4-a778-b6271f9f2ef8',
    '7c8880ee-fe16-43c0-9db5-47dda2c3a5e0', '81892e40-c34f-4417-bbc1-c85688454ae8',
    '81a42d48-6231-466a-98c8-480f07ca0eb8', '895b16d1-0b18-4e88-9a40-7ef5f3c2bf3c',
    '8a55696a-0cd5-4325-af2b-50500acb2cfc', '8cb4ac19-699b-4ff1-aa94-53c6e790874e',
    '8f174987-f7cf-4f23-99f3-63ef54584a97', '924d6a02-b1a9-49ce-9fe2-095d9339209f',
    '943280fe-2324-42cf-8d48-f3eeb2d472a3', '9680c1e7-45c7-4199-a31f-4166c2e8ba5c',
    '9cfeb72a-197c-41cf-9402-89792a729d8e', '9d2c7535-e3e7-4228-a155-06de1143cc3e',
    '9d8b62f7-f9ec-4858-b4a2-be425058228e', 'a61f1b1a-8c0a-4e56-b078-60fad85a5359',
    'a6d27c01-1453-4815-9c20-70e0e3077873', 'a7e9b9a5-55f9-4814-b035-2305f3fbec99',
    'a83a66e7-78bb-4ec5-9324-80ca9cf31dba', 'ab8be18b-bee1-4c36-b8a9-5391ead3ec28',
    'aee615ad-5bdd-49c3-8df4-26f3984f7d63', 'b0b78a7a-db22-4716-90ae-0a1e3c43a58d',
    'b8489102-34ac-460e-8cbf-b51a2f66f3ee', 'bfb5e4ff-dbfb-406e-b81a-0c03c6ca9a6b',
    'c03394b0-6264-491c-8b99-6ec5ca5c7174', 'c1716e47-e2e3-490f-bbf8-e1291558a824',
    'c215df68-78de-4dcf-82ab-7788d8e3b419', 'c5219133-721a-41b3-b6a4-093c575daeeb',
    'c9391ebe-21f5-4b1a-89c4-1607563e341a', 'cc5e2db9-eef5-4f0a-88e4-237c9add2b15',
    'cda5fad8-0b4b-48e1-98dd-23a46216853d', 'cecbc538-7c28-47a8-8c38-52d1dbae1b5e',
    'd4265905-b9fe-4366-b979-7071d54ded6a', 'd4b5f1a2-e4be-49db-9e3d-dff90107dbad',
    'd713c7eb-4ef7-472e-95de-794400536b0e', 'd79b900c-7bdb-4cbf-840c-3abe6efb9299',
    'd92b6072-c1e3-4fe7-9243-1d6f2d6b35ee', 'dcf8853c-c496-40f3-828c-79268e671887',
    'e03e5e9b-2e8a-49bf-9c4b-f820ee14c559', 'e324a9e0-0d68-42ba-a423-61afebe28378',
    'e3900a60-ddc1-4d65-8496-34cb9b51e186', 'e690a619-15aa-4675-8610-969751142d7a',
    'ea17ae7f-1470-46d8-85cf-ca495c5bb554', 'ee3f9ce2-515b-4141-9b8a-03220b45b317',
    'f149cee5-b6d7-4f6a-964a-dfb7f2930e04', 'f5bedf17-4c1c-4cd1-a8ef-27409af61b48',
    'f8c488e6-d6b8-464b-86c6-9d25d6b1e87b', 'fb8b5faf-cbcb-4f84-a95e-600064a938f3',
    'fca14802-f8cd-4221-9f62-e853d8bfaedf', 'fd2599f8-acd7-4207-a3f0-fdc3ede7d3dc',
  ]);

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
      const response = await callOriginalFetch(`${EXPECTED_ORIGIN}${path}`, {
        method: 'GET',
        headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
        redirect: 'error',
      });
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
    const readRegistry = async (token) => {
      const rows = [];
      let expectedTotal = null;
      for (let offset = 0; expectedTotal === null || offset < expectedTotal; offset += PAGE_SIZE) {
        const page = await requestJson(
          `${REGISTRY_PATH}?only_not_withdrawn=true&limit=${PAGE_SIZE}&offset=${offset}`,
          token,
        );
        if (!page || !Array.isArray(page.rows) || !Number.isInteger(page.total) || page.total < 0 || page.rows.length > PAGE_SIZE) {
          throw new SoldKizFilterError('Реестр вернул неожиданную структуру.');
        }
        if (expectedTotal === null) expectedTotal = page.total;
        if (page.total !== expectedTotal || (offset < expectedTotal && page.rows.length === 0)) {
          throw new SoldKizFilterError('Реестр изменился во время проверки. Перезагрузите страницу и повторите dry-run.');
        }
        rows.push(...page.rows);
      }
      return rows;
    };
    const exactTargets = (rows) => TARGET_ROW_IDS.map((rowId) => {
      const matches = rows.filter((row) => row?.row_id === rowId);
      if (matches.length !== 1) throw new SoldKizFilterError(`Строка ${rowId} отсутствует или задублирована.`);
      const row = matches[0];
      if (row.status !== 'not_withdrawn' || row.operation_id !== null) {
        throw new SoldKizFilterError(`Строка ${rowId} уже выводится, выведена или связана с операцией.`);
      }
      return Object.freeze({ ...row });
    });
    const installFilter = (token, rows) => {
      if (!root || typeof ResponseClass !== 'function' || typeof originalFetch !== 'function') {
        throw new SoldKizFilterError('Браузер не поддерживает безопасный локальный фильтр.');
      }
      const patchedFetch = async (input, init = {}) => {
        const url = new URL(typeof input === 'string' || input instanceof URL ? input : input.url, location.origin);
        const method = String(init.method ?? input?.method ?? 'GET').toUpperCase();
        if (
          method === 'POST' &&
          url.origin === EXPECTED_ORIGIN &&
          url.pathname === `${REGISTRY_PATH}/operations`
        ) {
          if (root.fetch === patchedFetch) root.fetch = originalFetch;
          return callOriginalFetch(input, init);
        }
        if (method !== 'GET' || url.origin !== EXPECTED_ORIGIN || url.pathname !== REGISTRY_PATH) {
          return callOriginalFetch(input, init);
        }
        let currentToken;
        try {
          currentToken = readToken();
        } catch (error) {
          if (root.fetch === patchedFetch) root.fetch = originalFetch;
          throw error;
        }
        if (currentToken !== token) {
          if (root.fetch === patchedFetch) root.fetch = originalFetch;
          throw new SoldKizFilterError('Seller-сессия изменилась. Перезагрузите страницу.');
        }
        const limit = Number(url.searchParams.get('limit') ?? '50');
        const offset = Number(url.searchParams.get('offset') ?? '0');
        if (![50, 100, 250].includes(limit) || !Number.isInteger(offset) || offset < 0) {
          throw new SoldKizFilterError('Штатный экран запросил неожиданную пагинацию.');
        }
        return new ResponseClass(JSON.stringify({ rows: rows.slice(offset, offset + limit), total: rows.length }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        });
      };
      Object.defineProperty(patchedFetch, FILTER_MARKER, { value: true });
      root.fetch = patchedFetch;
      return () => {
        if (root.fetch === patchedFetch) root.fetch = originalFetch;
      };
    };

    const run = async (input = {}) => {
      assertLocation();
      const mode = input?.mode ?? 'dry-run';
      if (!input || typeof input !== 'object' || Array.isArray(input) || !['dry-run', 'execute'].includes(mode)) {
        throw new SoldKizFilterError('Режим должен быть равен dry-run или execute.');
      }
      if (new Set(TARGET_ROW_IDS).size !== TARGET_COUNT) throw new SoldKizFilterError('Снимок row_id повреждён.');
      const token = readToken();
      validateIdentity(await requestJson('/api/auth/me', token));
      const targets = exactTargets(await readRegistry(token));
      const inspection = await ui.inspectSelection();
      if (!inspection || inspection.selectedCount !== 0) {
        throw new SoldKizFilterError('Перед запуском снимите все ранее выбранные КИЗ.');
      }
      if (readToken() !== token) throw new SoldKizFilterError('Seller-сессия изменилась во время проверки.');
      if (mode === 'dry-run') {
        return Object.freeze({ mode, status: 'ready', targetCount: targets.length, noSend: true, signed: false, sent: false });
      }
      const restore = installFilter(token, targets);
      const assertCurrentSession = () => {
        if (readToken() !== token) {
          throw new SoldKizFilterError('Seller-сессия изменилась во время подготовки.');
        }
      };
      try {
        const opened = await ui.refreshSelectAllAndOpen(TARGET_COUNT, assertCurrentSession);
        if (!opened || opened.selectedCount !== TARGET_COUNT || opened.dialogOpen !== true) {
          throw new SoldKizFilterError('Штатный экран не подтвердил точное выделение и диалог сертификата.');
        }
        assertCurrentSession();
        return Object.freeze({
          mode,
          status: 'certificate_dialog_open',
          targetCount: targets.length,
          noSend: true,
          signed: false,
          sent: false,
          message: 'Выбраны ровно 80 проверенных WB sold КИЗ. Сертификат и отправку подтверждает Виталий.',
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

  return Object.freeze({ TARGET_ROW_IDS, createHelper });
});
