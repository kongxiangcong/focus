import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
const { chromium } = await import(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({ headless: true, executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE });
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
const base = process.env.FOCUS_TEST_URL;
const root = process.env.FOCUS_TEST_ROOT;
const trace = message => fs.appendFileSync(path.join(process.env.FOCUS_BROWSER_OUTPUT || root, 'workspace-binding-trace.txt'), message + '\n');
const errors = [];
page.on('pageerror', e => errors.push(e.message));
const status = async () => (await (await page.request.get(base + '/reader/workspace')).json()).value;
try {
  await page.goto(base);
  if (process.env.FOCUS_TEST_RECOVERY) {
    await page.getByRole('heading', { name: '开始使用 FOCUS' }).waitFor();
    await page.getByLabel('重新定位原工作区', { exact: true }).check();
    await page.getByLabel('工作区目录', { exact: true }).fill(process.env.FOCUS_TEST_RECOVERY);
    await page.getByRole('button', { name: '进入工作台' }).click();
    await page.getByRole('navigation', { name: '应用导航' }).waitFor();
    assert.equal((await status()).workspace.path, process.env.FOCUS_TEST_RECOVERY);
    trace('missing path relocated through browser');
  } else {
  trace('page opened');
  await page.getByRole('heading', { name: '开始使用 FOCUS' }).waitFor();
  assert.equal((await status()).bound, false);
  assert.equal(fs.existsSync(path.join(root, 'knowledge-base')), false);
  await page.getByRole('button', { name: '选择目录', exact: true }).click();
  assert.equal((await status()).bound, false);
  await page.getByLabel('工作区目录', { exact: true }).fill(root);
  await page.getByRole('button', { name: '进入工作台' }).click();
  await page.getByRole('alert').waitFor();
  assert.equal((await status()).bound, false);
  await page.getByLabel('新建工作区', { exact: true }).check();
  await page.getByLabel('父目录', { exact: true }).fill(root);
  await page.getByLabel('名称', { exact: true }).fill('一号 workspace');
  await page.getByRole('button', { name: '进入工作台' }).click();
  await page.getByRole('navigation', { name: '应用导航' }).waitFor();
  const first = (await status()).workspace;
  trace('first created');
  const firstGeneration = (await status()).generation;
  const secondPage = await browser.newPage();
  await secondPage.goto(base + '/reading');
  await secondPage.getByRole('navigation', { name: '应用导航' }).waitFor();
  await page.getByRole('link', { name: '设置', exact: true }).click();
  trace('settings opened');
  await page.getByRole('button', { name: '更换工作区' }).click();
  await page.getByRole('button', { name: '取消', exact: true }).click();
  assert.equal((await status()).workspace.instanceId, first.instanceId);
  await page.getByRole('button', { name: '更换工作区' }).click();
  await page.getByLabel('新建工作区', { exact: true }).check();
  await page.getByLabel('父目录', { exact: true }).fill(root);
  await page.getByLabel('名称', { exact: true }).fill('二号 workspace');
  await page.getByRole('button', { name: '进入工作台' }).click();
  await secondPage.getByRole('heading', { name: '工作区已更换' }).waitFor();
  trace('second created');
  const response = await page.request.post(base + '/library/topics', {
    headers: { 'X-FOCUS-Instance': first.instanceId }, data: { title: 'stale draft' },
  });
  trace('old request status ' + response.status());
  assert.equal(response.status(), 400);
  const staleSelection = await page.request.post(base + '/reader/workspace', {
    data: { mode: 'create', path: root, name: 'stale-selection', generation: firstGeneration,
      configuration: { backend: 'deepseek' } },
  });
  assert.equal(staleSelection.status(), 400);
  assert.equal(fs.existsSync(path.join(root, 'stale-selection')), false);
  execFileSync(process.env.FOCUS_TEST_PYTHON, ['-c', 'import shutil,sys; shutil.copytree(sys.argv[1],sys.argv[2])', first.path, path.join(root, '复制 workspace')]);
  trace('copied');
  await page.getByRole('button', { name: '更换工作区' }).click();
  await page.getByLabel('导入工作区', { exact: true }).check();
  await page.getByLabel('工作区目录', { exact: true }).fill(path.join(root, '复制 workspace'));
  await page.getByRole('button', { name: '进入工作台' }).click();
  await page.waitForTimeout(250);
  const restored = (await status()).workspace;
  assert.equal(first.workspaceId, restored.workspaceId);
  assert.notEqual(first.instanceId, restored.instanceId);
  await page.reload();
  await page.getByRole('navigation', { name: '应用导航' }).waitFor();
  assert.equal(await page.getByRole('heading', { name: '开始使用 FOCUS' }).count(), 0);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  assert.deepEqual(errors, []);
  const output = process.env.FOCUS_BROWSER_OUTPUT;
  if (output) {
    await page.screenshot({ path: path.join(output, 'workspace-binding.png') });
    fs.writeFileSync(path.join(output, 'workspace-binding-results.json'), JSON.stringify({
      passed: ['unbound without data', 'picker cancel and manual fallback', 'invalid import retains draft',
        'create Chinese and spaced path', 'settings cancel', 'two-page isolation', 'old HTTP request rejected',
        'stopped copy with same identity', 'reload direct entry', 'narrow viewport'], errors,
    }, null, 2));
  }
  }
} catch (error) { trace(error.stack || String(error)); throw error; }
finally { await browser.close(); }
