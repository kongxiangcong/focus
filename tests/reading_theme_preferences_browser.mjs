import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const { chromium } = createRequire(import.meta.url)(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({
  headless: true, executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});
const base = process.env.FOCUS_TEST_URL || `http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT || '8765'}`;

async function checkTheme(page, theme, accent, action) {
  await page.waitForFunction(([theme, accent, action]) => {
    const root = document.documentElement;
    return root.dataset.theme === theme && root.dataset.accent === accent &&
      getComputedStyle(root).getPropertyValue('--reader-action').trim().toLowerCase() === action;
  }, [theme, accent, action]);
}

try {
  const page = await browser.newPage({ colorScheme: 'dark' });
  page.setDefaultTimeout(6000);
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.addInitScript(() => {
    if (sessionStorage.getItem('seeded')) return;
    localStorage.setItem('focus.theme', 'system');
    localStorage.setItem('focus.accent', 'red');
    sessionStorage.setItem('seeded', 'true');
  });
  let releaseEntry;
  const entryGate = new Promise(resolve => { releaseEntry = resolve; });
  await page.route(/\/assets\/index-[^/]+\.js$/, async route => {
    await entryGate;
    await route.continue();
  });
  try {
    const response = await page.goto(`${base}/reading`, { waitUntil: 'commit' });
    assert.ok(response.ok());
    assert.match(response.headers()['content-security-policy'], /default-src 'self'/);
    await checkTheme(page, 'dark', 'red', '#e4e6eb');
    assert.equal(await page.locator('#root').innerHTML(), '', 'theme applies before the app starts');
  } finally {
    releaseEntry();
  }

  await page.getByRole('link', { name: '设置', exact: true }).click();
  await page.getByRole('radio', { name: '跟随系统', exact: true }).waitFor();
  await page.emulateMedia({ colorScheme: 'light' });
  await checkTheme(page, 'light', 'red', '#9f1239');
  for (const [name, accent, action] of [
    ['钴蓝白', 'blue', '#1d4ed8'], ['松青绿白', 'green', '#0f766e'],
    ['绯红白', 'red', '#9f1239'], ['极简黑白', 'neutral', '#18181b'],
  ]) {
    await page.getByRole('radio', { name, exact: true }).check();
    await checkTheme(page, 'light', accent, action);
  }
  await page.emulateMedia({ colorScheme: 'dark' });
  await checkTheme(page, 'dark', 'neutral', '#e4e6eb');
  await page.emulateMedia({ colorScheme: 'light' });
  await checkTheme(page, 'light', 'neutral', '#18181b');
  await page.getByRole('radio', { name: '深色', exact: true }).check();
  await checkTheme(page, 'dark', 'neutral', '#e4e6eb');
  assert.equal(await page.getByRole('group', { name: '浅色配色' }).count(), 0);
  await page.reload();
  await page.getByRole('radio', { name: '浅色', exact: true }).check();
  await checkTheme(page, 'light', 'neutral', '#18181b');
  assert.equal(await page.getByRole('radio', { name: '极简黑白', exact: true }).isChecked(), true);
  assert.deepEqual(errors.filter(message => /content security policy/i.test(message)), []);

  const privatePage = await browser.newPage({ colorScheme: 'dark' });
  await privatePage.addInitScript(() => Object.defineProperty(window, 'localStorage', {
    get() { throw new DOMException('Storage unavailable', 'SecurityError'); },
  }));
  await privatePage.goto(`${base}/reading`);
  await checkTheme(privatePage, 'light', 'blue', '#1d4ed8');
  console.log('PASS theme preferences, early Host startup, system changes, and storage fallback');
} finally {
  await browser.close();
}
