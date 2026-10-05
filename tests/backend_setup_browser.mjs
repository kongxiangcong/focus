import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
const { chromium } = await import(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({ headless: true, executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE });
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
const base = process.env.FOCUS_TEST_URL;
const root = process.env.FOCUS_TEST_ROOT;
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const configuration = async () => (await (await page.request.get(base + '/reader/configuration')).json()).value;
try {
  await page.goto(base);
  await page.getByRole('heading', { name: '开始使用 FOCUS' }).waitFor();
  await page.getByRole('radio', { name: 'Codex', exact: true }).waitFor();
  assert.equal(await page.getByRole('combobox', { name: '模型' }).inputValue(), '');
  assert.equal(await page.getByRole('option').count(), 1);
  await page.getByRole('button', { name: '登录 Codex', exact: true }).click();
  await page.getByRole('link', { name: '打开浏览器授权' }).waitFor();
  await page.getByRole('button', { name: '取消登录', exact: true }).click();
  await page.getByRole('link', { name: '打开浏览器授权' }).waitFor({ state: 'hidden' });
  await page.getByRole('button', { name: '登录 Codex', exact: true }).click();
  await page.getByText('Codex 登录成功。可继续进行连接检查。', { exact: true }).waitFor();
  await page.getByRole('button', { name: '连接检查' }).click();
  await page.getByRole('button', { name: '重试模型清单' }).click();
  await page.getByRole('option', { name: 'real-codex' }).waitFor({ state: 'attached' });
  await page.getByRole('combobox', { name: '模型' }).selectOption('real-codex');
  await page.getByText('当前模型尚未验证。').waitFor();
  await page.getByRole('radio', { name: 'DeepSeek', exact: true }).check();
  assert.equal(await page.getByRole('option', { name: 'real-codex' }).count(), 0);
  await page.getByRole('button', { name: '连接检查' }).click();
  await page.getByRole('alert').waitFor();
  await page.getByLabel('新建工作区', { exact: true }).check();
  await page.getByLabel('父目录', { exact: true }).fill(root);
  await page.getByRole('button', { name: '进入工作台' }).click();
  await page.getByRole('navigation', { name: '应用导航' }).waitFor();
  assert.equal((await configuration()).effective.backend, 'deepseek');
  assert.equal((await configuration()).preferences.codex.model, 'real-codex');
  const other = await browser.newPage();
  await other.goto(base + '/settings');
  await other.getByRole('combobox', { name: '模型' }).waitFor();
  await page.getByRole('link', { name: '设置', exact: true }).click();
  await page.getByRole('radio', { name: 'Codex', exact: true }).check();
  assert.equal(await page.getByRole('combobox', { name: '模型' }).inputValue(), 'real-codex');
  await page.getByRole('combobox', { name: '模型' }).selectOption('');
  await page.getByRole('button', { name: '保存并应用', exact: true }).click();
  await page.getByText('设置已保存并应用。', { exact: true }).waitFor();
  assert.equal((await configuration()).preferences.codex.model, null);
  await other.getByRole('radio', { name: 'Codex', exact: true }).waitFor();
  await other.waitForFunction(() => document.querySelector('input[name="setup-backend"]')?.checked);
  await page.reload();
  await page.getByRole('combobox', { name: '模型' }).waitFor();
  assert.equal(await page.getByRole('combobox', { name: '模型' }).inputValue(), '');
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  assert.deepEqual(errors, []);
  await page.screenshot({ path: path.join(process.env.FOCUS_BROWSER_OUTPUT, 'backend-setup.png') });
  fs.writeFileSync(path.join(process.env.FOCUS_BROWSER_OUTPUT, 'backend-browser-results.json'), JSON.stringify({
    passed: ['zero-action default', 'explicit login cancel and confirmed authorization protocol', 'connection then catalog failure', 'independent catalog retry', 'selection unverified',
      'no cross-backend cache', 'failed check permits default entry', 'both preferences saved with binding',
      'one save applies', 'default clears override', 'two-page configuration sync', 'reload and narrow viewport'], errors,
  }, null, 2));
} finally { await browser.close(); }
