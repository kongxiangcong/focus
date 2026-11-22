import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const moduleId = process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = await import(path.isAbsolute(moduleId) ? pathToFileURL(moduleId).href : moduleId);
const browser = await chromium.launch({ headless: true, executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE });
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
const other = await browser.newPage();
const base = process.env.FOCUS_TEST_URL;
const root = process.env.FOCUS_TEST_ROOT;
const fixtureLog = process.env.FOCUS_FIXTURE_LOG;
const errors = [];
for (const tab of [page, other]) tab.on('pageerror', error => errors.push(error.message));
const configuration = async tab => (await (await tab.request.get(base + '/reader/configuration')).json()).value;
const radio = (tab, name) => tab.getByRole('radio', { name, exact: true });

try {
  await page.goto(base);
  await page.getByRole('heading', { name: '开始使用 FOCUS' }).waitFor();
  assert.equal((await configuration(page)).effective, null);
  await page.getByLabel('新建工作区', { exact: true }).check();
  await page.getByLabel('父目录', { exact: true }).fill(root);
  await page.getByRole('button', { name: '进入工作台' }).click();
  await page.getByRole('navigation', { name: '应用导航' }).waitFor();
  assert.equal((await configuration(page)).saved, null);
  assert.equal(fs.existsSync(fixtureLog), false);

  await page.getByRole('link', { name: '设置', exact: true }).click();
  await radio(page, 'Fixture Alpha').waitFor();
  assert.equal(await page.locator('input[name="setup-backend"]:checked').count(), 0);
  const builtins = [
    ['codex', 'Codex'], ['deepseek', 'DeepSeek'], ['agy', 'Antigravity CLI'], ['cursor', 'Cursor CLI'],
  ];
  const descriptors = (await configuration(page)).backends;
  for (const [id, label] of builtins) {
    await radio(page, label).waitFor();
    assert.deepEqual(descriptors.filter(item => item.id === id).map(item => item.label), [label]);
  }
  const manifestErrors = page.getByRole('list', { name: 'Backend 配置错误' });
  await manifestErrors.getByText('invalid.json', { exact: false }).waitFor();
  await manifestErrors.getByText('duplicate.json', { exact: false }).waitFor();
  const manifests = path.join(root, 'machine', 'backends');
  const beta = JSON.parse(fs.readFileSync(path.join(manifests, 'fixture-beta.json'), 'utf8'));
  fs.writeFileSync(path.join(manifests, 'fixture-rescanned.json'), JSON.stringify({
    ...beta, id: 'fixture-rescanned', label: 'Fixture Rescanned',
  }));
  await page.getByRole('button', { name: '重新扫描 Backend', exact: true }).click();
  await radio(page, 'Fixture Rescanned').waitFor();
  assert.equal(fs.existsSync(fixtureLog), false);

  await radio(page, 'Fixture Alpha').check();
  await page.getByRole('button', { name: '加载模型清单', exact: true }).click();
  await page.getByRole('option', { name: '["fixture-provider","selected-model"]' }).waitFor({ state: 'attached' });
  await page.getByText('当前模型尚未验证。', { exact: true }).waitFor();
  await page.getByRole('button', { name: '连接检查', exact: true }).click();
  await page.getByText('连接检查通过', { exact: false }).waitFor();
  assert.equal((await configuration(page)).effective, null);

  await other.goto(base + '/settings');
  await radio(other, 'Fixture Alpha').waitFor();
  assert.equal(await radio(other, 'Fixture Alpha').isChecked(), false);
  await page.getByRole('button', { name: '保存并应用', exact: true }).click();
  await page.getByText('设置已保存并应用。', { exact: true }).waitFor();
  assert.equal((await configuration(page)).effective.backend, 'fixture-alpha');
  await other.waitForFunction(() => [...document.querySelectorAll('input[name="setup-backend"]')]
    .some(input => input.checked && input.closest('label')?.textContent.trim() === 'Fixture Alpha'));
  const events = fs.readFileSync(fixtureLog, 'utf8').trim().split('\n').map(JSON.parse);
  assert.equal(events.filter(item => item.kind === 'probe').length, 1);

  await radio(page, 'Fixture Bad').check();
  await page.getByRole('button', { name: '保存并应用', exact: true }).click();
  await page.getByText('后端配置未保存', { exact: false }).waitFor();
  assert.equal((await configuration(other)).effective.backend, 'fixture-alpha');
  await page.reload();
  await radio(page, 'Fixture Alpha').waitFor();
  assert.equal(await radio(page, 'Fixture Alpha').isChecked(), true);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  assert.deepEqual(errors, []);

  const passed = ['library entry without AI', 'four built-in IDs', 'malformed and duplicate manifests',
    'manual rescan finds new manifest', 'independent model catalog', 'source probe receipt reuse',
    'two-page apply', 'failed apply keeps configuration', 'reload', '390px viewport'];
  const output = process.env.FOCUS_BROWSER_OUTPUT;
  if (output) {
    await page.screenshot({ path: path.join(output, 'backend-setup.png') });
    fs.writeFileSync(path.join(output, 'backend-browser-results.json'), JSON.stringify({
      runtime: 'ACP protocol substitute', passed, errors,
    }, null, 2));
  }
  console.log(passed.join('\n'));
} finally {
  await browser.close();
}
