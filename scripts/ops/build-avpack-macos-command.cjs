'use strict';

const fs = require('node:fs');
const path = require('node:path');

const directory = __dirname;
const helper = fs.readFileSync(path.join(directory, 'avpack-sold-kiz-filter.js')).toString('base64');
const launcher = fs.readFileSync(path.join(directory, 'avpack-macos-launcher.js')).toString('base64');
const output = path.join(directory, 'avpack-sold-kiz.command');

const command = `#!/bin/zsh
exec /usr/bin/osascript -l JavaScript <<'WMS665_JXA'
'use strict';

ObjC.import('Foundation');

const HELPER_BASE64 = '${helper}';
const LAUNCHER_BASE64 = '${launcher}';

function decodeBase64(encoded) {
  const data = $.NSData.alloc.initWithBase64EncodedStringOptions($(encoded), 0);
  if (!data) throw new Error('Встроенный код повреждён. Запуск не выполнялся.');
  const string = $.NSString.alloc.initWithDataEncoding(data, $.NSUTF8StringEncoding);
  if (!string) throw new Error('Встроенный код повреждён. Запуск не выполнялся.');
  return ObjC.unwrap(string);
}

const helperSource = decodeBase64(HELPER_BASE64);
const launcherSource = decodeBase64(LAUNCHER_BASE64);
const module = { exports: {} };
const exports = module.exports;
(0, eval)(launcherSource);
const launcher = module.exports.launch ? module.exports : globalThis.Wms665MacLauncher;
if (!launcher || typeof launcher.launch !== 'function') {
  throw new Error('Оболочка запуска повреждена. Действия в браузере не выполнялись.');
}

const chromeApp = Application('Google Chrome');
const targetUrl = 'https://wms.sellerfocus.pro/seller/honest-sign/withdrawals';
const focusFailureMessage = 'Не удалось безопасно показать подготовленную вкладку Chrome. Подпись и отправка не выполнялись.';
let originalTargetTabId = null;

function isTargetChromeUrl(value) {
  return value === targetUrl || value === targetUrl + '/' ||
    value.indexOf(targetUrl + '?') === 0 || value.indexOf(targetUrl + '#') === 0 ||
    value.indexOf(targetUrl + '/?') === 0 || value.indexOf(targetUrl + '/#') === 0;
}

function chromeTabs() {
  const result = [];
  const windows = chromeApp.windows();
  for (let windowIndex = 0; windowIndex < windows.length; windowIndex += 1) {
    const tabs = windows[windowIndex].tabs();
    for (let tabIndex = 0; tabIndex < tabs.length; tabIndex += 1) {
      result.push({ id: String(tabs[tabIndex].id()), url: String(tabs[tabIndex].url()) });
    }
  }
  return result;
}

function findChromeTab(tabId) {
  const windows = chromeApp.windows();
  const matches = [];
  for (let windowIndex = 0; windowIndex < windows.length; windowIndex += 1) {
    const tabs = windows[windowIndex].tabs();
    for (let tabIndex = 0; tabIndex < tabs.length; tabIndex += 1) {
      if (String(tabs[tabIndex].id()) === String(tabId)) {
        matches.push({ tab: tabs[tabIndex], window: windows[windowIndex], tabIndex: tabIndex + 1 });
      }
    }
  }
  if (matches.length !== 1) throw new Error('Вкладка Chrome стала недоступна.');
  const match = matches[0];
  if (!isTargetChromeUrl(String(match.tab.url()))) throw new Error('Целевая вкладка Chrome перешла на другой адрес.');
  return match;
}

function focusChromeTab(tabId) {
  const match = findChromeTab(tabId);
  match.window.activeTabIndex = match.tabIndex;
  match.window.index = 1;
  chromeApp.activate();
}

const result = launcher.launch({
  chrome: {
    running: () => chromeApp.running(),
    tabs: chromeTabs,
    evaluate: (tabId, source) => {
      if (originalTargetTabId === null) originalTargetTabId = String(tabId);
      if (String(tabId) !== originalTargetTabId) throw new Error('Идентификатор целевой вкладки изменился.');
      return findChromeTab(tabId).tab.execute({ javascript: source });
    },
  },
  helperSource,
  maxPolls: 120,
  wait: () => $.NSThread.sleepForTimeInterval(0.25),
});

if (
  result.status !== 'certificate_dialog_open' || !Number.isSafeInteger(result.targetCount) || result.targetCount <= 0 ||
  result.signed !== false || result.sent !== false
) {
  throw new Error('Запуск не подтвердил безопасное открытие окна сертификата.');
}
try {
  const readyTabs = chromeTabs().filter((tab) => isTargetChromeUrl(tab.url));
  if (originalTargetTabId === null || readyTabs.length !== 1 || String(readyTabs[0].id) !== originalTargetTabId) {
    throw new Error('Целевая вкладка изменилась после подготовки.');
  }
  focusChromeTab(originalTargetTabId);
} catch (_) {
  throw new Error(focusFailureMessage);
}
console.log('Подготовлено: выбраны ' + result.targetCount + ' пригодных КИЗ и открыто штатное окно сертификата. Скрипт ничего не подписывал и не отправлял.');
WMS665_JXA
`;

fs.writeFileSync(output, command, { encoding: 'utf8', mode: 0o755 });
fs.chmodSync(output, 0o755);
