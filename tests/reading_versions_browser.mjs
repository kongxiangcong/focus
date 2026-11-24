import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const { chromium } = createRequire(import.meta.url)(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({ headless: true, executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE,
  args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const base = `http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT}`;
const page = await browser.newPage({ viewport: { width: 1440, height: 844 }, reducedMotion: 'reduce' });
page.setDefaultTimeout(12000);
const modes = page.getByRole('group', { name: '阅读方式' });
const body = page.getByLabel('文章原文', { exact: true });
const manage = page.getByRole('button', { name: '管理来源', exact: true });
const dialog = page.getByRole('dialog').filter({ has: page.getByRole('heading', { name: '管理来源', exact: true }) });
const notes = page.getByRole('button', { name: '笔记', exact: true });

async function snapshot() {
  const binding = await (await page.request.get(`${base}/reader/workspace`)).json();
  const headers = { 'X-FOCUS-Instance': binding.value.workspace.instanceId };
  const result = await (await page.request.get(`${base}/reader/window`, { headers })).json();
  assert.ok(result.ok, JSON.stringify(result));
  return result.value;
}

async function chat() {
  const tab = modes.getByRole('button', { name: '对话', exact: true });
  await tab.waitFor();
  if (await tab.getAttribute('aria-pressed') !== 'true') await tab.click();
}

async function switchRound(to) {
  await manage.click();
  const rounds = dialog.getByRole('list', { name: '阅读版本' });
  await rounds.getByText('第 1 轮', { exact: true }).waitFor();
  await rounds.getByText('第 2 轮', { exact: true }).waitFor();
  const rows = rounds.getByRole('listitem');
  assert.match(await rows.nth(0).innerText(), /第 1 轮.*最近备份/s);
  assert.equal(await rows.nth(2 - to).getAttribute('aria-current'), 'true');
  await rounds.getByRole('button', { name: `切换到第 ${to} 轮` }).click();
  await dialog.waitFor({ state: 'hidden' });
  await chat();
}

try {
  await page.goto(`${base}/reading`);
  await chat();
  await body.getByText('阅读段落 17 用来核对阅读位置。', { exact: true }).waitFor();
  const first = await snapshot();
  await page.getByRole('button', { name: '重新阅读', exact: true }).click();
  await page.getByRole('button', { name: '确认重新阅读', exact: true }).click();
  await page.getByRole('main', { name: '阅读与对话', exact: true })
    .getByText('重读段落 1 用来核对阅读位置。', { exact: true }).waitFor();
  await chat();
  await body.getByText('重读段落 17 用来核对阅读位置。', { exact: true }).waitFor();
  const second = await snapshot();
  assert.equal(second.readingVersion, 2);
  assert.equal(second.navigationCurrent.chunkId, 'chunk-001');
  assert.notEqual(first.discussionId, second.discussionId);

  await notes.click();
  const copied = page.locator('article').filter({ hasText: '待复现' });
  await copied.getByRole('button', { name: '编辑', exact: true }).click();
  await page.getByRole('textbox', { name: '笔记内容' }).fill('已复现');
  await page.getByRole('button', { name: '保存笔记', exact: true }).click();
  await page.getByText('已复现', { exact: true }).waitFor();

  await switchRound(1);
  await body.getByText('阅读段落 17 用来核对阅读位置。', { exact: true }).waitFor();
  let view = await snapshot();
  assert.equal(view.discussionId, first.discussionId);
  assert.equal(view.navigationCurrent.chunkId, first.navigationCurrent.chunkId);
  assert.deepEqual(view.sourceNotes.map(note => note.content), ['待复现']);

  await switchRound(2);
  await page.reload();
  await chat();
  await body.getByText('重读段落 17 用来核对阅读位置。', { exact: true }).waitFor();
  view = await snapshot();
  assert.equal(view.discussionId, second.discussionId);
  assert.deepEqual(view.sourceNotes.map(note => note.content), ['已复现']);
  console.log('PASS Workbench reading versions list, backup time, editable notes, live cursor and reload');
} catch (error) {
  console.error((await page.locator('body').innerText()).slice(0, 1800));
  throw error;
} finally {
  await browser.close();
}
