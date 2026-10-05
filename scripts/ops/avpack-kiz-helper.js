'use strict';

(function exposeAvpackKizHelper(root, factory) {
  const api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.AvpackKizHelper = api;
})(typeof globalThis === 'undefined' ? this : globalThis, function buildAvpackKizHelper(root) {
  const EXPECTED_ORIGIN = 'https://sellerfocus.pro';
  const EXPECTED_PATH = '/seller/honest-sign/withdrawals';
  const EXPECTED_TENANT = 'd6e1ad21-8afa-4acf-8d0b-907b9f2adcfe';
  const EXPECTED_SELLER = '0b8da5d8-f43a-42f5-a2ec-43173ea844bd';
  const TOKEN_STORAGE_KEY = 'wms_token_seller';
  const REGISTRY_PATH = '/api/operations/marking-codes/self/withdrawals';
  const PAGE_SIZE = 250;
  const REQUEST_TIMEOUT_MS = 15_000;

  const TARGETS = Object.freeze([
    Object.freeze({
      row_id: 'c9391ebe-21f5-4b1a-89c4-1607563e341a',
      wb_order_id: '5803306927',
      cis: '0104630726321651215a0cGXmjtLjxb\u001d91EE12\u001d92lFBvJUaWv6uayEvcOEBE6q/Rlg8WDCxojleoRlHA+uE=',
    }),
    Object.freeze({
      row_id: 'd79b900c-7bdb-4cbf-840c-3abe6efb9299',
      wb_order_id: '5800165076',
      cis: '0104630726321637215G0(VhN1qGejx\u001d91EE12\u001d92zWp5IYlZWPYukhvkOJoKjtO1gO9qgBvrdHWJOoy6oF4=',
    }),
    Object.freeze({
      row_id: '9cfeb72a-197c-41cf-9402-89792a729d8e',
      wb_order_id: '5807803330',
      cis: '0104630726321620215XPXiykjErJGW\u001d91EE12\u001d92AFbVYzMNOCgHlYOPDbHU2znQYBQsUWJuQVNo4UwnyBE=',
    }),
    Object.freeze({
      row_id: 'c5219133-721a-41b3-b6a4-093c575daeeb',
      wb_order_id: '5809136493',
      cis: '0104630726321637215gtDu&gVcNBGs\u001d91EE12\u001d924lJI5/yBasFN8IZWHr6IlQomd/SogonGm8RUx1ydqO4=',
    }),
  ]);

  const PROFILE_PREFLIGHT = Object.freeze({
    observedAt: '2026-10-05',
    source: 'WB seller-info and production billing_profiles readback',
    inn: '132608771877',
  });

  class HelperError extends Error {
    constructor(message, code) {
      super(message);
      this.name = 'AvpackKizHelperError';
      if (code) this.code = code;
    }
  }

  const cloneTarget = (target) => ({
    row_id: target.row_id,
    wb_order_id: target.wb_order_id,
    cis: target.cis,
  });

  const compactKiz = (value) =>
    value.length <= 24 ? value : `${value.slice(0, 18)}…${value.slice(-4)}`;

  const normalizedText = (node) => String(node?.textContent ?? '').replace(/\s+/g, ' ').trim();

  function createDomAdapter(document) {
    const pageAndTable = () => {
      if (!document || typeof document.querySelectorAll !== 'function') {
        throw new HelperError('Не удалось проверить экран: DOM браузера недоступен.');
      }
      const pages = [...document.querySelectorAll('[data-testid="seller-kiz-withdrawal-page"]')];
      if (pages.length !== 1) {
        throw new HelperError('Ожидался ровно один экран вывода КИЗ.');
      }
      const page = pages[0];
      const tables = [...page.querySelectorAll('table[aria-label="КИЗ для вывода из оборота"]')];
      if (tables.length !== 1) {
        throw new HelperError('Таблица КИЗ не найдена или отображается неоднозначно.');
      }
      return { page, table: tables[0] };
    };

    const targetCheckbox = (table, target) => {
      const bodyRows = [...table.querySelectorAll('tbody tr')];
      const matchingRows = bodyRows.filter((row) =>
        [...row.querySelectorAll('a, button')].some(
          (link) => normalizedText(link) === target.wb_order_id,
        ),
      );
      if (matchingRows.length !== 1) return null;
      const row = matchingRows[0];
      const codes = [...row.querySelectorAll('code')].filter(
        (code) => normalizedText(code) === compactKiz(target.cis),
      );
      const checkboxes = [...row.querySelectorAll('input[type="checkbox"]')];
      const hasExpectedStatus = [...row.querySelectorAll('*')].some(
        (element) => normalizedText(element) === 'Не выведен',
      );
      if (
        codes.length !== 1 ||
        checkboxes.length !== 1 ||
        checkboxes[0].disabled ||
        !hasExpectedStatus
      ) {
        return null;
      }
      return checkboxes[0];
    };

    const actionButton = (page) => {
      const buttons = [...page.querySelectorAll('button')].filter((button) =>
        /^\u0412\u044b\u0432\u0435\u0441\u0442\u0438 \u0438\u0437 \u043e\u0431\u043e\u0440\u043e\u0442\u0430 \(\d+\)$/.test(normalizedText(button)),
      );
      return buttons.length === 1 ? buttons[0] : null;
    };

    const waitFor = async (predicate, message) => {
      for (let attempt = 0; attempt < 50; attempt += 1) {
        const value = predicate();
        if (value) return value;
        await new Promise((resolve) => root?.setTimeout(resolve, 100));
      }
      throw new HelperError(message);
    };

    return {
      async inspectSelection(targets) {
        const { page, table } = pageAndTable();

        if (document.querySelector('[role="dialog"]')) {
          throw new HelperError('Закройте открытый диалог перед проверкой.');
        }

        const dateInputs = [...page.querySelectorAll('input[type="date"]')];
        if (
          dateInputs.length !== 2 ||
          dateInputs[0].value !== '2026-09-18' ||
          dateInputs[1].value !== '2026-09-19'
        ) {
          throw new HelperError('Установите период «Передано WB» 18–19.09.2026.');
        }

        const checkedRows = table.querySelectorAll('tbody input[type="checkbox"]:checked').length;

        const action = actionButton(page);
        if (!action) {
          throw new HelperError('Кнопка вывода из оборота не найдена или имеет неожиданную подпись.');
        }
        const actionMatch = normalizedText(action).match(/\((\d+)\)$/);
        const actionCount = Number(actionMatch?.[1]);

        return {
          selectedCount: Math.max(checkedRows, Number.isFinite(actionCount) ? actionCount : 0),
          targetsReady: targets.every((target) => Boolean(targetCheckbox(table, target))),
        };
      },

      async selectAndOpen(targets, assertCurrentSession) {
        const { page, table } = pageAndTable();
        const checkboxes = targets.map((target) => targetCheckbox(table, target));
        if (checkboxes.some((checkbox) => !checkbox)) {
          throw new HelperError('Строки изменились перед выделением. Запустите dry-run заново.');
        }
        const clearSelection = () => {
          for (const checkbox of table.querySelectorAll('tbody input[type="checkbox"]:checked')) {
            if (!checkbox.disabled) checkbox.click();
          }
        };
        const assertExactSelection = () => {
          const currentTargets = targets.map((target) => targetCheckbox(table, target));
          const checked = table.querySelectorAll('tbody input[type="checkbox"]:checked');
          if (
            currentTargets.some((checkbox) => !checkbox || !checkbox.checked) ||
            checked.length !== targets.length
          ) {
            throw new HelperError('Строки изменились: точное выделение КИЗ не подтверждено.');
          }
        };
        try {
          assertCurrentSession();
          for (const checkbox of checkboxes) {
            checkbox.click();
            assertCurrentSession();
          }
          const action = await waitFor(() => {
            const button = actionButton(page);
            const count = Number(normalizedText(button).match(/\((\d+)\)$/)?.[1]);
            return button && !button.disabled && count === targets.length ? button : null;
          }, 'Не удалось подтвердить точное выделение КИЗ на экране.');
          assertCurrentSession();
          assertExactSelection();
          action.click();
          await waitFor(
            () => [...document.querySelectorAll('[role="dialog"]')].some(
              (dialog) => normalizedText(dialog).includes('Выберите сертификат'),
            ),
            'Штатный диалог выбора сертификата не открылся.',
          );
        } catch (error) {
          clearSelection();
          throw error;
        }
      },
    };
  }

  function validateRunInput(input) {
    if (input === undefined) input = {};
    if (!input || typeof input !== 'object' || Array.isArray(input)) {
      throw new HelperError('Параметры запуска должны быть объектом.');
    }

    const mode = input.mode === undefined ? 'dry-run' : input.mode;
    if (mode !== 'dry-run' && mode !== 'execute') {
      throw new HelperError('Режим должен быть равен dry-run или execute.');
    }

    const requested = input.orderIds === undefined ? [TARGETS[0].wb_order_id] : input.orderIds;
    if (!Array.isArray(requested) || requested.length < 1 || requested.length > TARGETS.length) {
      throw new HelperError('Укажите от одного до четырёх разрешённых заказов WB.');
    }
    const orderIds = requested.map((value) => String(value));
    if (new Set(orderIds).size !== orderIds.length) {
      throw new HelperError('Номера заказов WB не должны повторяться.');
    }

    const byOrderId = new Map(TARGETS.map((target) => [target.wb_order_id, target]));
    const selectedTargets = orderIds.map((orderId) => byOrderId.get(orderId));
    if (selectedTargets.some((target) => !target)) {
      throw new HelperError('Запрошен непроверенный заказ WB.');
    }
    return { mode, targets: selectedTargets };
  }

  function createHelper(dependencies = {}) {
    const location = dependencies.location ?? root?.location;
    const storage = dependencies.storage ?? root?.localStorage;
    const fetchRequest = dependencies.fetch ?? root?.fetch?.bind(root);
    const AbortControllerClass = dependencies.AbortController ?? root?.AbortController;
    const scheduleTimeout = dependencies.setTimeout ?? root?.setTimeout?.bind(root);
    const cancelTimeout = dependencies.clearTimeout ?? root?.clearTimeout?.bind(root);
    const ui = dependencies.ui ?? createDomAdapter(root?.document);

    const assertLocation = () => {
      if (
        !location ||
        location.origin !== EXPECTED_ORIGIN ||
        ![EXPECTED_PATH, `${EXPECTED_PATH}/`].includes(location.pathname)
      ) {
        throw new HelperError(
          `Откройте ${EXPECTED_ORIGIN}${EXPECTED_PATH} перед запуском помощника.`,
        );
      }
    };

    const readToken = () => {
      if (!storage || typeof storage.getItem !== 'function') {
        throw new HelperError('Сессия seller-кабинета недоступна.');
      }
      let token;
      try {
        token = storage.getItem(TOKEN_STORAGE_KEY);
      } catch {
        throw new HelperError('Не удалось прочитать seller-сессию.');
      }
      if (typeof token !== 'string' || token.length === 0) {
        throw new HelperError('Войдите в seller-кабинет перед запуском помощника.');
      }
      return token;
    };

    const requestJson = async (path, token) => {
      if (typeof fetchRequest !== 'function') {
        throw new HelperError('Браузерный fetch недоступен.');
      }
      if (
        typeof AbortControllerClass !== 'function' ||
        typeof scheduleTimeout !== 'function' ||
        typeof cancelTimeout !== 'function'
      ) {
        throw new HelperError('Браузер не поддерживает безопасный таймаут запроса.');
      }

      const controller = new AbortControllerClass();
      let timedOut = false;
      const timeout = scheduleTimeout(() => {
        timedOut = true;
        controller.abort();
      }, REQUEST_TIMEOUT_MS);
      try {
        const response = await fetchRequest(`${EXPECTED_ORIGIN}${path}`, {
          method: 'GET',
          headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
          redirect: 'error',
          signal: controller.signal,
        });

        if (!response || !response.ok) {
          const status = Number.isFinite(response?.status) ? response.status : 'неизвестен';
          throw new HelperError(`GET ${path.split('?')[0]} вернул HTTP ${status}.`);
        }
        try {
          return await response.json();
        } catch {
          if (timedOut) {
            throw new HelperError(`GET ${path.split('?')[0]} превысил таймаут 15 секунд.`);
          }
          throw new HelperError(`GET ${path.split('?')[0]} вернул некорректный JSON.`);
        }
      } catch (error) {
        if (error instanceof HelperError) throw error;
        if (timedOut) throw new HelperError(`GET ${path.split('?')[0]} превысил таймаут 15 секунд.`);
        throw new HelperError(`GET ${path.split('?')[0]} не выполнен.`);
      } finally {
        cancelTimeout(timeout);
      }
    };

    const validateIdentity = (identity) => {
      if (
        !identity ||
        identity.tenant_id !== EXPECTED_TENANT ||
        identity.seller_id !== EXPECTED_SELLER ||
        identity.active_seller_id !== EXPECTED_SELLER ||
        identity.role !== 'fulfillment_seller' ||
        identity.withdrawal_enabled !== true
      ) {
        throw new HelperError('Текущий tenant, seller, роль или право вывода не совпадают с AVpack/ИП Горячкина.');
      }
    };

    const readRegistry = async (token) => {
      const rows = [];
      let offset = 0;
      let expectedTotal = null;
      do {
        const query =
          '?date_from=2026-09-18&date_to=2026-09-19&only_not_withdrawn=true' +
          `&limit=${PAGE_SIZE}&offset=${offset}`;
        const page = await requestJson(`${REGISTRY_PATH}${query}`, token);
        if (
          !page ||
          !Array.isArray(page.rows) ||
          !Number.isInteger(page.total) ||
          page.total < 0 ||
          page.rows.length > PAGE_SIZE
        ) {
          throw new HelperError('Реестр вернул неожиданную структуру.');
        }
        if (expectedTotal === null) expectedTotal = page.total;
        if (page.total !== expectedTotal) {
          throw new HelperError('Реестр изменился во время постраничной проверки. Запустите dry-run заново.');
        }
        if (offset < expectedTotal && page.rows.length === 0) {
          throw new HelperError('Реестр не вернул ожидаемую страницу.');
        }
        rows.push(...page.rows);
        offset += PAGE_SIZE;
      } while (offset < expectedTotal);
      return rows;
    };

    const verifyTargets = (rows, targets) => {
      for (const target of targets) {
        const related = rows.filter((row) =>
          row &&
          (row.row_id === target.row_id ||
            String(row.wb_order_id) === target.wb_order_id ||
            row.cis === target.cis),
        );
        const exact = related.filter((row) =>
          row.row_id === target.row_id &&
          String(row.wb_order_id) === target.wb_order_id &&
          row.cis === target.cis,
        );
        if (related.length !== 1 || exact.length !== 1) {
          throw new HelperError(`Не найдена ровно одна точная строка заказа WB ${target.wb_order_id}.`);
        }
        const row = exact[0];
        if (row.status !== 'not_withdrawn' || row.operation_id !== null) {
          throw new HelperError(`КИЗ заказа WB ${target.wb_order_id} уже выводится, выведен или связан с операцией.`);
        }
      }
    };

    const run = async (input) => {
      assertLocation();
      const { mode, targets } = validateRunInput(input);
      const token = readToken();
      validateIdentity(await requestJson('/api/auth/me', token));
      verifyTargets(await readRegistry(token), targets);

      let inspection;
      try {
        inspection = await ui.inspectSelection(targets.map(cloneTarget));
      } catch (error) {
        if (error instanceof HelperError) throw error;
        throw new HelperError('Не удалось безопасно проверить видимый реестр КИЗ.');
      }
      if (!inspection || inspection.selectedCount !== 0) {
        throw new HelperError('Перед запуском снимите все ранее выбранные КИЗ.');
      }
      if (inspection.targetsReady !== true) {
        throw new HelperError('Не все проверенные КИЗ однозначно видны и доступны в таблице.');
      }

      const sessionTokenNow = readToken();
      if (sessionTokenNow !== token) {
        throw new HelperError('Сессия seller-кабинета изменилась во время проверки. Запустите dry-run заново.');
      }

      if (mode === 'execute') {
        const assertCurrentSession = () => {
          if (readToken() !== token) {
            throw new HelperError(
              'Сессия seller-кабинета изменилась во время проверки. Запустите dry-run заново.',
            );
          }
        };
        try {
          await ui.selectAndOpen(targets.map(cloneTarget), assertCurrentSession);
        } catch (error) {
          if (error instanceof HelperError) throw error;
          throw new HelperError('Не удалось безопасно выделить КИЗ и открыть диалог сертификата.');
        }
        return {
          mode,
          status: 'certificate_dialog_open',
          verifiedTargets: targets.map(cloneTarget),
          profilePreflight: PROFILE_PREFLIGHT,
          noSend: true,
          signed: false,
          sent: false,
          message: 'Точные КИЗ выделены. Проверьте сертификат и нажмите штатную кнопку вручную.',
        };
      }

      return {
        mode,
        status: 'ready',
        verifiedTargets: targets.map(cloneTarget),
        profilePreflight: PROFILE_PREFLIGHT,
        noSend: true,
        signed: false,
        sent: false,
        message: 'Строки и реквизиты проверены. Execute может открыть штатный диалог сертификата.',
      };
    };

    return Object.freeze({ run });
  }

  return Object.freeze({ TARGETS, createHelper });
});
